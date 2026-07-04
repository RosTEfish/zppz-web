from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.db.bootstrap import backfill_guess_chart_metadata, create_schema, seed_defaults, upgrade_schema
from app.db.session import SessionLocal
from app.modules.admin.router import router as admin_router
from app.modules.assets.router import router as assets_router
from app.modules.auth.router import router as auth_router
from app.modules.bootstrap_api.router import router as bootstrap_router
from app.modules.draw.router import admin_router as admin_draw_router
from app.modules.draw.router import router as draw_router
from app.modules.events.router import admin_router as admin_events_router
from app.modules.events.router import router as events_router
from app.modules.guess_game.router import admin_router as admin_guess_game_router
from app.modules.guess_game.router import router as guess_game_router
from app.modules.song_pool.router import admin_router as admin_song_pool_router
from app.modules.song_pool.router import router as song_pool_router
from app.modules.submissions.router import admin_router as admin_submissions_router
from app.modules.submissions.router import router as submissions_router
from app.modules.submissions.service import copy_asset_from_repo
from app.modules.users.router import router as users_router


settings = get_settings()
app = FastAPI(title=settings.app_name, version="2.0.0", openapi_url=f"{settings.api_prefix}/openapi.json")

app.add_middleware(GZipMiddleware, minimum_size=512, compresslevel=5)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code < 400:
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
            if Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".pdf", ".zip", ".7z", ".rar"}:
                response.headers.setdefault("Content-Encoding", "identity")
        return response


@app.on_event("startup")
def startup() -> None:
    upgrade_schema()
    create_schema()
    with SessionLocal() as db:
        seed_defaults(db)
        backfill_guess_chart_metadata(db)
    repo_root = Path(__file__).resolve().parents[2]
    for file in (repo_root / "ruleDetail").glob("*.pdf"):
        copy_asset_from_repo(file, "rules")
    for file in (repo_root / "banlist").glob("*.*"):
        copy_asset_from_repo(file, "banlists")
    for file in (repo_root / "bg").glob("*.*"):
        copy_asset_from_repo(file, "backgrounds")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


for router in (
    auth_router,
    bootstrap_router,
    events_router,
    assets_router,
    song_pool_router,
    draw_router,
    submissions_router,
    guess_game_router,
    admin_router,
    admin_events_router,
    users_router,
    admin_song_pool_router,
    admin_draw_router,
    admin_submissions_router,
    admin_guess_game_router,
):
    app.include_router(router, prefix=settings.api_prefix)


repo_root = Path(__file__).resolve().parents[2]
frontend_dist = repo_root / "frontend" / "dist"
frontend_assets = frontend_dist / "assets"

if frontend_assets.exists():
    app.mount("/assets", CachedStaticFiles(directory=frontend_assets), name="frontend-assets")


@app.get("/")
def frontend_index():
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"message": "Frontend build not found. Run `cd frontend && npm run build`."}


@app.get("/{path:path}")
def frontend_fallback(path: str):
    if path.startswith("api/"):
        return {"detail": "Not found"}
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"message": "Frontend build not found. Run `cd frontend && npm run build`."}
