# Agent Notes

## Project Snapshot

- Stack: React 19 + Vite + TypeScript frontend, FastAPI + SQLAlchemy + Alembic backend.
- Frontend lives in `frontend/`; backend lives in `backend/`.
- Static event assets live in `bg/`, `ruleDetail/`, and `banlist/`; backend startup copies them into the configured data directory.
- Production deploy is driven by `.github/workflows/deploy.yml` and `scripts/deploy_remote.sh`.

## Frontend

- Main app file: `frontend/src/App.tsx`.
- Main stylesheet: `frontend/src/index.css`.
- API client: `frontend/src/api/v1.ts`.
- Local commands:
  - `cd frontend && npm run lint`
  - `cd frontend && npm test`
  - `cd frontend && npm run build`
  - `cd frontend && npm run dev`

## Backend

- FastAPI entrypoint: `backend/app/main.py`.
- Requirements: `backend/requirements.txt`.
- Local run command from `backend/`:
  - `uvicorn app.main:app --reload --port 8000`
- Permission bootstrap/sync logic is in `backend/app/db/bootstrap.py`.

## Deployment Notes

- Production deployment is fully automated through GitHub Actions. A push to `main` runs `.github/workflows/deploy.yml`, which verifies the project and invokes `scripts/deploy_remote.sh`; do not design required release steps that depend on the user manually logging in over SSH.
- Any change involving Alembic migrations, database preparation, dependencies, bundled assets, environment variables, systemd, Nginx, or startup order must also be checked against the CI/CD workflow and remote deployment script. Update those files when the new release cannot deploy safely with the existing automation.
- Database migrations and other one-time preparation must run through `python -m app.prepare` before the new service is restarted. Application startup only checks that the schema is current; it must not be relied on to perform migrations in each worker.
- Keep deployment preparation non-interactive and idempotent. GitHub Actions should validate the full Alembic chain on a fresh temporary database and execute `python -m app.prepare` twice so repeated automatic deployments remain safe.
- A successful local implementation is not complete if CI/CD cannot carry it to production automatically. Final verification for deployment-affecting work must include the relevant GitHub Actions commands and the ordering `verify -> upload -> prepare/migrate -> restart -> health check`.
- Manual server commands may be documented only as recovery procedures, not as the normal deployment path.
- The server systemd service is `zppz-web.service`.
- Service command:
  - `uvicorn app.main:app --host 127.0.0.1 --port 8000`
- If deploy reports port `8000` already in use, inspect stale `uvicorn app.main:app` processes on the server before restarting.
- Keep `bcrypt==4.0.1` pinned with `passlib==1.7.4`; newer bcrypt versions can break passlib startup.

## UI Notes

- `DESIGN.md` is the current visual direction.
- Use one interaction accent: Action Blue `#0066cc`.
- Keep admin pages dense and operational; keep participant pages clearer and more event-facing.
- Avoid bringing back long homepage marketing copy the user previously asked to remove.

## Performance Notes

- Guess chart list serialization should stay bulk-based: aggregate vote counts once per list in `backend/app/modules/common.py` instead of counting per chart.
- User role-heavy admin pages should eager-load roles with `selectinload(User.roles)` to avoid N+1 queries.
- Frontend hashed build assets under `/assets` should be served with long immutable cache headers; `index.html` stays no-cache.
- Frontend comment creation can prepend the returned comment locally instead of refetching the whole comment list.

## Git Notes

- Current cleaned baseline before the latest UI push: `7921563 Initial ZPPZ V2 release`.
- Latest pushed UI commit observed locally: `3dd8e51 更新样式和组件，优化导航链接，调整响应式设计`.
- Prefer `git revert` for public rollback unless the user explicitly wants remote history rewritten with `--force-with-lease`.
