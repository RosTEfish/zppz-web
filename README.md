# ZPPZ Web

这谱谱这赛事平台 V2，使用 React + Vite 前端和 FastAPI 后端。

## 目录

- `backend/`：FastAPI、SQLAlchemy、Alembic、业务模块和后端测试。
- `frontend/`：React + TypeScript + Vite 前端。
- `infra/`：Nginx 配置。
- `scripts/deploy_remote.sh`：GitHub Actions 远程部署脚本。
- `bg/`、`ruleDetail/`、`banlist/`：赛事静态资源，会在后端启动时复制到数据目录。

## 本地前端

```powershell
cd frontend
npm install
npm run dev
```

## 本地后端

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Docker Compose

```bash
docker compose up --build
```

默认前端入口：`http://localhost:8080`

## 部署

推送到 `main` 后，`.github/workflows/deploy.yml` 会构建前端并通过 SSH 部署到服务器。服务器上的 systemd 服务会运行：

```text
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

更多说明见 `REFACTOR_V2.md`。
