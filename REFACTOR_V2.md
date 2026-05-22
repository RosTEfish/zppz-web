# ZPPZ V2 重构说明

新版实现放在 `backend/`、`frontend/` 和 `infra/` 中，后端入口为 FastAPI。

## 本地 Docker 启动

```bash
docker compose up --build
```

启动后访问：

- 前端：`http://localhost:8080`
- API 健康检查：`http://localhost:8080/health`
- OpenAPI：`http://localhost:8080/api/v1/openapi.json`

默认管理员：

- ID：`admin`
- 密码：`change-me-please`

上线前必须修改 `SECRET_KEY` 和 `ADMIN_SEED_PASSWORD`。

## 架构

- `backend/app/main.py`：FastAPI 入口，统一挂载 `/api/v1/*`。
- `backend/app/models.py`：SQLAlchemy 2 数据模型。
- `backend/app/modules/*`：按业务域拆分路由和服务。
- `frontend/src/App.tsx`：新版 React 工作台入口。
- `frontend/src/api/v1.ts`：前端 typed API client。
- `infra/nginx/default.conf`：前端静态文件和 API 反向代理。

## 文件存储

Docker volume `zppz-data` 挂载到 `/data`，包含：

- `/data/uploads`
- `/data/assets/rules`
- `/data/assets/banlists`
- `/data/assets/backgrounds`

启动时会把仓库内现有 `ruleDetail/`、`banlist/`、`bg/` 的文件复制进 assets 目录。

## 权限管理

后台「用户」页可以直接勾选角色。拥有 `admin` 角色的账号可以管理其他账号权限。

服务器也会在启动时读取 `/data/permissions.json`，用于兜底指定管理员。例如：

```json
{
  "users": [
    {
      "user_code": "RosTEfish",
      "roles": ["admin", "pool_editor", "participant"],
      "identity": "participant",
      "display_name": "赛事管理员",
      "is_active": true
    }
  ]
}
```

在当前 systemd 部署中，实际路径通常是：

```text
/opt/zppz/data/permissions.json
```

修改后重启服务即可同步：

```bash
sudo systemctl restart zppz-web
```

## 验证命令

```bash
cd frontend
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

后端在有 Python 的环境中执行：

```bash
cd backend
pip install -r requirements.txt
pytest
alembic check
```
