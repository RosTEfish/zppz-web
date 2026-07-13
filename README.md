# ZPPZ Web

这谱谱这赛事平台 V2，使用 React + Vite 前端和 FastAPI 后端。

## 目录

- `backend/`：FastAPI、SQLAlchemy、Alembic、业务模块和后端测试。
- `frontend/`：React + TypeScript + Vite 前端。
- `infra/`：Nginx 配置。
- `scripts/deploy_remote.sh`：GitHub Actions 远程部署脚本。
- `bg/`、`ruleDetail/`、`banlist/`：赛事静态资源，会在部署准备命令 `python -m app.prepare` 中同步到数据目录。

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
python -m app.prepare
uvicorn app.main:app --reload --port 8000
```

## Docker Compose

```bash
docker compose up --build
```

默认前端入口：`http://localhost:8080`

## 部署

推送到 `main` 后，`.github/workflows/deploy.yml` 会先完成前后端验证，再通过 SSH 部署到服务器。部署脚本会在重启服务前执行一次 `python -m app.prepare`，负责数据库迁移、默认数据初始化、谱面元数据回填和捆绑资源同步。服务器上的 systemd 服务会按 `WEB_CONCURRENCY` 运行：

```text
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers $WEB_CONCURRENCY
```

更多说明见 `REFACTOR_V2.md`。

### 反向代理下载配置

批量投稿下载使用流式 ZIP，并通过 `X-Accel-Buffering: no` 禁止 Nginx 等待完整响应。生产环境的外部反向代理需要保留该响应头，且不能为下载接口强制开启响应缓冲。仓库内的 Docker Nginx 仅对下载路径关闭代理缓冲；普通 JSON API 保持缓冲，带哈希的前端资源使用长期缓存。
