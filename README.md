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

## 部署

外部 Bot 的谱面发布/更新推送采用多接收方 Webhook；接入流程、签名和事件格式见 [Webhook 接入手册](docs/webhook-integration.md)。

推送到 `main` 后，`.github/workflows/deploy.yml` 会自动完成前后端验证、构建发布包并通过 SSH 部署到服务器。部署过程中会自动安装后端依赖、执行数据库迁移和默认数据初始化、导入当前 Ban 曲数据、同步谱面元数据与捆绑资源、检查 R2 读写权限，然后重启 systemd 服务并执行健康检查。R2 检查或健康检查失败时，流水线会尝试恢复上一版应用文件并让部署任务失败；不需要人工执行上线命令。

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

`preview-player/` 目录捆绑了 [MajdataView](https://github.com/TeamMajdata/MajdataView) / [MajdataNet](https://github.com/TeamMajdata/MajdataNet) 的 **GPL-3.0** WebGL 构建（见 [THIRD_PARTY_NOTICES.txt](preview-player/THIRD_PARTY_NOTICES.txt)）。该预览播放器分发物须保持 GPL-3.0 兼容；其余代码仍适用 MIT 许可证。主要依赖均为 MIT/BSD/Apache 等宽松许可证。

## 社区与安全

- [CONTRIBUTING.md](CONTRIBUTING.md)：贡献指南。
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)：社区行为准则。
- [SECURITY.md](SECURITY.md)：安全漏洞上报方式。
