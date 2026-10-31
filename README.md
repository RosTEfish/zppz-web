# ZPPZ Web

这谱谱这赛事平台 V2，使用 React + Vite 前端和 FastAPI 后端。

## 目录

- `backend/`：FastAPI、SQLAlchemy、Alembic、业务模块和后端测试。
- `frontend/`：React + TypeScript + Vite 前端。
- `infra/`：Nginx 配置。
- `scripts/deploy_remote.sh`：GitHub Actions 远程部署脚本。
- `bg/`、`ruleDetail/`、`banlist/`：赛事静态资源，会在部署流水线的自动准备阶段同步到数据目录（`bg/` 栅格图会转成 WebP 再提供给前端）。

## 本地前端

```powershell
cd frontend
npm install
npm run dev
```

前端 UI 改动遵循 `frontend/DESIGN.md` 设计契约（配色、字体、组件与构建约定）；字体声明表 `frontend/src/fonts.css` 由入口异步加载，勿在别处直接 import @fontsource 样式。

## 本地后端

后端会在启动时自动加载当前目录下的 `.env` 文件（python-dotenv）。先复制示例并填写本机所需的值：

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env        # 修改其中的 SECRET_KEY、ADMIN_SEED_PASSWORD 等
python -m app.prepare          # 仅当设置了 ADMIN_SEED_PASSWORD 时才会创建默认管理员
uvicorn app.main:app --reload --port 8000
```

> `python -m app.prepare` 用于建库/迁移并导入初始数据。默认管理员（`ADMIN_SEED_CODE`，默认 `admin`）只在设置 `ADMIN_SEED_PASSWORD` 后才会被创建；本地开发没有管理员账号时，设置该变量后重新执行一次即可。

## 测试

```bash
# 后端
cd backend && pip install -r requirements-dev.txt && python -m pytest

# 前端（单测 + 预览播放器桥接测试）
cd frontend && npm install && npm test

# 前端静态检查与构建
cd frontend && npm run lint && npm run build
```

## Docker Compose

```bash
docker compose up --build
```

默认前端入口：`http://localhost:8080`

API 与 worker 镜像以用户 `app`（uid/gid `1000`）运行。新建的 `zppz-data` 卷会继承镜像内 `/data` 的属主，四个后端服务共用该卷，因此都可以写入。若这个卷是以前以 root 运行的容器创建的，需要在更新镜像后一次性修正权限：

```bash
docker compose run --rm --no-deps --user root --entrypoint chown api -R 1000:1000 /data
```

生产环境的 systemd 部署（`scripts/deploy_remote.sh`）不运行该镜像。数据目录仍是部署用户拥有的 `$DEPLOY_PATH/data`（默认 `/opt/zppz/data`），不需要执行上面的 `chown`。

## 部署

外部 Bot 的谱面发布/更新推送采用多接收方 Webhook；接入流程、签名和事件格式见 [Webhook 接入手册](docs/webhook-integration.md)。

推送到 `main` 后，`.github/workflows/deploy.yml` 会自动完成前后端验证、构建发布包并通过 SSH 部署到服务器。Pull request 会跑同一套验证（后端 ruff 与 pytest、Rust 测试、前端类型检查、测试、构建和包体预算），但不会部署；部署任务直接使用这次验证产出的前端 `dist` 和谱面校验器，不再第二次编译。`DEPLOY_PORT` 读取 Actions Variable，未配置时使用 22。部署过程中会自动安装后端依赖、执行数据库迁移和默认数据初始化、导入当前 Ban 曲数据、同步谱面元数据与捆绑资源、检查 R2 读写权限，然后重启 systemd 服务并执行健康检查。R2 检查或健康检查失败时，流水线会尝试恢复上一版应用文件并让部署任务失败；不需要人工执行上线命令。

生产部署要求在 GitHub 仓库的 `Settings → Secrets and variables → Actions` 中配置：

- **必填 Variables**：`R2_ACCOUNT_ID`、`R2_BUCKET_NAME`、`SERVER_PIP_INDEX_URL`。
- **必填 Secrets**：`DEPLOY_HOST`（服务器地址或 IP，不带协议和 `user@`）、`DEPLOY_USER`（SSH 登录用户名）、`DEPLOY_SSH_KEY`（SSH 私钥）、`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`、`WEBHOOK_SIGNING_MASTER_KEY`（独立生成的高强度随机值）。
- **可选**：Variables `OWNER_USER_CODE`、`PUBLIC_BASE_URL`、`PREVIEW_ENABLED`、`PREVIEW_PUBLIC_BUCKET_NAME`、`PREVIEW_PLAYER_ORIGIN`、`DEPLOY_PATH`、`DEPLOY_PORT`、`KEEP_RELEASES`；Secrets `PREVIEW_PUBLIC_ACCESS_KEY_ID`、`PREVIEW_PUBLIC_SECRET_ACCESS_KEY`（`PREVIEW_ENABLED=true` 时必填）、`SECRET_KEY`、`ADMIN_SEED_PASSWORD`。

说明：

- `SECRET_KEY`、`ADMIN_SEED_PASSWORD` 为可选项。首次部署时服务器会为 `SECRET_KEY` 自动生成随机值；设置了 `ADMIN_SEED_PASSWORD` 时，`python -m app.prepare` 会创建默认管理员账号。**强烈建议**配置 `SECRET_KEY` 为固定随机值，避免每次重建服务器时密钥漂移。
- `PREVIEW_ENABLED=true` 时，流水线会要求 `PREVIEW_PUBLIC_BUCKET_NAME`、`PREVIEW_PLAYER_ORIGIN`、`PREVIEW_PUBLIC_ACCESS_KEY_ID`、`PREVIEW_PUBLIC_SECRET_ACCESS_KEY`，并把公开预览播放器发布到 R2。

`SERVER_PIP_INDEX_URL` 建议设为 `https://pypi.tuna.tsinghua.edu.cn/simple`。远程服务器升级 pip 和安装依赖时会先使用该镜像；失败后自动完整重试官方 `https://pypi.org/simple`。GitHub Actions 自身的验证仍使用官方 PyPI 和 npm 源。

`OWNER_USER_CODE` 填写网站登录使用的账号 ID（`user_code`），而不是昵称、QQ 号或 GitHub 用户名。目标账号必须已经注册并处于启用状态；配置后，每次部署都会把该账号同步为唯一 Owner，并把原 Owner 保留为管理员。变量为空或未配置时，部署不会修改现有 Owner；变量非空但账号无效时，部署会失败并保留原 Owner。

部署流水线会通过单独的权限文件把 R2 配置合并进服务器持久 `.env`，配置文件不会进入发布包。生产环境固定使用 `OBJECT_STORAGE_BACKEND=r2`，不会在配置缺失或权限检查失败时回退到本地存储。

### 可观测性

生产进程由 systemd 以用户 `deploy` 运行，环境文件是 `$DEPLOY_PATH/.env`（默认 `/opt/zppz/.env`），API 监听 `127.0.0.1`。不需要 Grafana。Sentry 和指标 token 都是可选的：不填写时行为与现在一样，本地和 CI 也不会对外发送错误。

下次部署会在这个文件里补上 `SENTRY_ENVIRONMENT=production`，以及空的 `SENTRY_DSN=` 和 `METRICS_TOKEN=`（已有值不会被覆盖）。在服务器上编辑后重启服务。worker 单独安装时是 `zppz-web-worker`，否则它和 API 在同一个 `zppz-web` 里：

```bash
sudo systemctl restart zppz-web
sudo systemctl restart zppz-web-worker
```

第二条只在该单元存在时需要。不要把 DSN 或 token 放进 Git 或 GitHub Actions。

**错误跟踪。** 设置 `SENTRY_DSN` 后，Web 进程上报未处理异常和直接返回的 HTTP 5xx；投稿 worker 与 webhook worker 上报它们记下来的错误。事件里带规范化路由、当前赛事阶段（`stage`）和数字用户 id（有登录态时）。查询字符串、Cookie、Authorization 以及 password/token/dsn 一类字段会在发送前去掉。`SENTRY_ENVIRONMENT` 默认 `production`。`SENTRY_RELEASE` 可选；留空时使用发布包根目录的 `REVISION`（git sha）。DSN 为空或初始化失败时，站点继续运行且不会发事件。

**指标。** `GET /api/v1/admin/metrics` 返回 Prometheus 文本。管理员登录态可以访问；若设置了 `METRICS_TOKEN`，也可以用 `Authorization: Bearer <token>`。token 只放在请求头里，不要放在 URL 上。建议在服务器本机抓取，而不是把 token 暴露到公网：

```bash
curl -fsS -H "Authorization: Bearer $METRICS_TOKEN" http://127.0.0.1:8000/api/v1/admin/metrics
```

建议关注：

- `zppz_submission_jobs`：`queued` 是等待中的投稿处理，`processing` 是已被 worker 认领的，`failed` 是终态失败（已被新任务取代的不计入）。
- `zppz_webhook_deliveries`：`pending` 与 `retrying` 是积压，`delivering` 是正在投递，`failed` 是超过重试窗口的失败。
- `zppz_webhook_endpoints{status="failing"}`：连续失败后被标成 failing 的接收方。
- `zppz_contest_stage`：当前阶段，便于把告警和赛程对上。
- `zppz_http_responses_total`：投稿（含管理端投稿）和 `POST/DELETE /guess-game/vote` 的 `5xx` 与 `other`。计数在 Web 进程重启后归零；SQLite 生产配置是 `WEB_CONCURRENCY=1`，多个 worker 时每个进程各有一份。

**日志告警。** 负责清理的投稿 worker 每分钟打一行 `contest_signals` JSON，字段与上面的队列、webhook 积压一致。出现失败任务、失败投递或 failing 接收方时级别是 `WARNING`，否则是 `INFO`。

```bash
journalctl -u zppz-web-worker -u zppz-web -g contest_signals
```

运维可以先接这两处，而不必上监控栈：Sentry 里对新 issue 告警；对 `contest_signals` 的 `WARNING`，或对 `zppz_submission_jobs{status="failed"}`、`zppz_webhook_deliveries{status="failed"}`、`zppz_webhook_endpoints{status="failing"}` 大于 0 告警。投稿高峰时 `queued` 短时间大于 0 是正常的，适合看它是否持续升高，而不是一出现就 paging。

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

## 开源许可证与赛事资源

本项目代码以 **MIT 许可证** 开源，详见 [LICENSE](LICENSE)。

**例外**：`bg/`（背景图）、`ruleDetail/`（规则 PDF）、`banlist/`（Ban 曲列表）以及 `frontend/src/assets/beian.png`（备案图标）为赛事运营资源，**不在 MIT 许可范围内**，版权归各自权利人所有，仅用于本项目运行与赛事运营，请勿另行复制、再分发或商用。这些资源属于「这谱谱这」赛事运营素材，随仓库发布以便部署时同步到站点数据目录。

在线预览播放器使用 [MiaView_Web](https://github.com/Team-MiaCode/MiaView_Web)（基于 [MiaCode](https://github.com/Team-MiaCode/MiaCode) WASM）。仓库内 [`preview-player/miaview-build.json`](preview-player/miaview-build.json) 只固定上游提交与 CI 产物名；实际 `sdk/` / `renderer/` 由部署流水线发布到公共预览域名。上游许可与第三方声明随构建产物发布，使用或再分发时请核对其中条款。其余本仓库代码仍适用 MIT 许可证。主要依赖均为 MIT/BSD/Apache 等宽松许可证。
