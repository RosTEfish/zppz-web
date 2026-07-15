from contextlib import asynccontextmanager
import logging
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.db.bootstrap import check_schema_current
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
from app.modules.swap.router import admin_router as admin_swap_router
from app.modules.swap.router import router as swap_router
from app.modules.users.router import router as users_router


settings = get_settings()
logger = logging.getLogger("app.requests")
FRONTEND_HTML_CACHE_CONTROL = "public, max-age=0, s-maxage=60, stale-while-revalidate=300"
TEXT_RESOURCE_CACHE_CONTROL = "public, max-age=300"
ROBOTS_TXT_FALLBACK = "User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin/\n"
LLMS_TXT_FALLBACK = "# przppz.club\n\nZPPZ Arena is an event platform for music chart submissions, draws, and interaction.\n"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    check_schema_current()
    yield


app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

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


@app.middleware("http")
async def log_slow_requests(request: Request, call_next):
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed_ms = (perf_counter() - started) * 1000
        if elapsed_ms >= settings.slow_request_ms:
            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)
            logger.warning(
                "slow_request method=%s route=%s status=%s duration_ms=%.1f",
                request.method,
                route_path,
                status_code,
                elapsed_ms,
            )


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
    swap_router,
    guess_game_router,
    admin_router,
    admin_events_router,
    users_router,
    admin_song_pool_router,
    admin_draw_router,
    admin_submissions_router,
    admin_swap_router,
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
        return FileResponse(index_file, headers={"Cache-Control": FRONTEND_HTML_CACHE_CONTROL})
    return {"message": "Frontend build not found. Run `cd frontend && npm run build`."}


def _frontend_text_file(filename: str, fallback: str):
    text_file = frontend_dist / filename
    headers = {"Cache-Control": TEXT_RESOURCE_CACHE_CONTROL}
    if text_file.exists():
        return FileResponse(text_file, media_type="text/plain", headers=headers)
    return PlainTextResponse(fallback, headers=headers)


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return _frontend_text_file("robots.txt", ROBOTS_TXT_FALLBACK)


@app.get("/llms.txt", include_in_schema=False)
def llms_txt():
    return _frontend_text_file("llms.txt", LLMS_TXT_FALLBACK)


@app.get("/{path:path}")
def frontend_fallback(path: str):
    if path.startswith("api/"):
        return {"detail": "Not found"}
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file, headers={"Cache-Control": FRONTEND_HTML_CACHE_CONTROL})
    return {"message": "Frontend build not found. Run `cd frontend && npm run build`."}
