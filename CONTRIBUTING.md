# 贡献指南 / Contributing

感谢你对 ZPPZ Arena（这谱谱这赛事平台）的关注！以下是参与开发时需要了解的内容。

## 项目结构

- `backend/`：FastAPI + SQLAlchemy + Alembic 后端，入口为 `app/main.py`。
- `frontend/`：React 19 + Vite + TypeScript 前端，入口为 `src/App.tsx`。
- `preview-player/`：谱面预览播放器的桥接代码与 MajdataView WebGL 构建声明（GPL-3.0）。
- `infra/`：Nginx 配置。
- `scripts/`：部署与工具脚本。

## 环境准备

1. Fork 仓库并克隆到本地。
2. 后端：见 [README 本地后端](README.md)（复制 `.env.example` 为 `.env`，安装依赖）。
3. 前端：`cd frontend && npm install`。

## 开发与验证

提交前请确保以下检查通过：

```bash
# 后端
cd backend
python -m ruff check app tests alembic
python -m pytest

# 前端
cd frontend
npm run lint        # tsc --noEmit
npm test
npm run build
```

若改动涉及 API 契约，前端有 `npm run check:api` 校验生成客户端与后端 OpenAPI 一致。

## 提交约定

- 提交信息简洁描述改动，可用中文或英文。
- 请勿在提交中混入 `.env`、本地密钥、日志或构建产物。
- 涉及数据库变更时，必须新增 Alembic 迁移，并确保 `python -m app.prepare` 可重复执行（CI 会在全新数据库上连续执行两次）。

## 部署相关

改动若涉及迁移、依赖、环境变量、systemd、Nginx 或启动顺序，必须同时检查并更新 `.github/workflows/deploy.yml` 与 `scripts/deploy_remote.sh`，保证流水线仍能自动部署。具体约束见 [agent.md](agent.md) 的「Deployment Notes」。
