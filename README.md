# ZPPZ Web

这谱谱这赛事平台 V2，使用 React + Vite 前端和 FastAPI 后端。

## 目录

- `backend/`：FastAPI、SQLAlchemy、Alembic、业务模块和后端测试。
- `frontend/`：React + TypeScript + Vite 前端。
- `infra/`：Nginx 配置。
- `scripts/deploy_remote.sh`：GitHub Actions 远程部署脚本。
- `bg/`、`ruleDetail/`、`banlist/`：赛事静态资源，会在部署流水线的自动准备阶段同步到数据目录。

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

推送到 `main` 后，`.github/workflows/deploy.yml` 会自动完成前后端验证、构建发布包并通过 SSH 部署到服务器。部署过程中会自动安装后端依赖、执行数据库迁移和默认数据初始化、导入当前 Ban 曲数据、同步谱面元数据与捆绑资源、检查 R2 读写权限，然后重启 systemd 服务并执行健康检查。R2 检查或健康检查失败时，流水线会尝试恢复上一版应用文件并让部署任务失败；不需要人工执行上线命令。

生产部署要求在 GitHub 仓库的 `Settings → Secrets and variables → Actions` 中配置：

- Variables：`R2_ACCOUNT_ID`、`R2_BUCKET_NAME`、`SERVER_PIP_INDEX_URL`，以及可选的 `OWNER_USER_CODE`。
- Secrets：`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`。

`SERVER_PIP_INDEX_URL` 建议设为 `https://pypi.tuna.tsinghua.edu.cn/simple`。远程服务器升级 pip 和安装依赖时会先使用该镜像；失败后自动完整重试官方 `https://pypi.org/simple`。GitHub Actions 自身的验证仍使用官方 PyPI 和 npm 源。

`OWNER_USER_CODE` 填写网站登录使用的账号 ID（`user_code`），而不是昵称、QQ 号或 GitHub 用户名。目标账号必须已经注册并处于启用状态；配置后，每次部署都会把该账号同步为唯一 Owner，并把原 Owner 保留为管理员。变量为空或未配置时，部署不会修改现有 Owner；变量非空但账号无效时，部署会失败并保留原 Owner。

部署流水线会通过单独的权限文件把 R2 配置合并进服务器持久 `.env`，配置文件不会进入发布包。生产环境固定使用 `OBJECT_STORAGE_BACKEND=r2`，不会在配置缺失或权限检查失败时回退到本地存储。

### R2 存储桶要求

- 使用私有 Standard 存储桶，不开启 `r2.dev` 公共访问。
- API Token 仅授予该存储桶 `Object Read & Write` 权限。
- CORS 至少允许正式站点 Origin 使用 `PUT`、`GET`、`HEAD`，允许请求头 `Content-Type`，并暴露 `ETag`。本地开发需要时可额外允许 `http://localhost:3000`。
- 为 `pending/` 前缀设置上传 1 天后删除的生命周期规则。

浏览器先获取短期预签名 URL，再把 ZIP、7z 或 RAR 投稿直接 `PUT` 到 R2。后端完成接口会依据 R2 `HEAD` 结果核对大小和 MIME，下载到临时目录执行原有压缩包安全校验，并生成随机 Key 的原包与公开包。单文件下载使用短期预签名 `GET`；批量下载仍由后端流式组合 ZIP。

可在服务器应用目录手工验证当前配置：

```bash
set -a
. ./.env
set +a
./.venv/bin/python -m app.manage storage-check
```

更多说明见 `REFACTOR_V2.md`。

### 反向代理下载配置

批量投稿下载使用流式 ZIP，并通过 `X-Accel-Buffering: no` 禁止 Nginx 等待完整响应。生产环境的外部反向代理需要保留该响应头，且不能为下载接口强制开启响应缓冲。仓库内的 Docker Nginx 仅对下载路径关闭代理缓冲；普通 JSON API 保持缓冲，带哈希的前端资源使用长期缓存。
