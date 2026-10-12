# MiaView 在线预览部署

在线预览由用户浏览器运行 [MiaView_Web](https://github.com/Team-MiaCode/MiaView_Web)
（MiaCode WASM + WebGL 2）。主服务器只鉴权并返回私有 R2 的短期签名 URL，
不渲染、不编码，也不转发音频、图片或视频。

## 一次性 Cloudflare 配置

1. 创建公共 Bucket `zppz-preview-static`，只用于播放器静态资源（`sdk/`、`renderer/`）和对应许可声明。
2. 给它绑定 `preview.przppz.club`，等待 HTTPS 证书签发。
3. 创建仅限该 Bucket 的 Object Read & Write R2 Token。
4. 公共预览 Bucket 的 CORS 允许主站跨域 `import()` SDK：
   - `https://www.przppz.club`
   - `https://przppz.club`（根域名跳转过渡期可保留）
   - 开发环境所需的 `http://localhost:3000`
   - 方法 `GET`、`HEAD`
   - 请求头 `Content-Type`、`Range`
   - 暴露 `ETag`、`Accept-Ranges`、`Content-Length`、`Content-Range`
5. 私有投稿 Bucket 的 CORS 允许：
   - `https://www.przppz.club`
   - `https://przppz.club`
   - `https://preview.przppz.club`（renderer iframe 拉取签名素材）
   - 开发环境所需的 `http://localhost:3000`
   - 方法 `GET`、`HEAD`、`PUT`
   - 请求头 `Content-Type`、`Range`
   - 暴露 `ETag`、`Accept-Ranges`、`Content-Length`、`Content-Range`
6. 在 Cloudflare 响应头规则中，为
   `preview.przppz.club/miaview/*` 添加：
   `Content-Security-Policy: frame-ancestors https://www.przppz.club https://przppz.club`

不要公开现有投稿 Bucket，也不要将任何投稿对象复制到公共 Bucket。

## GitHub Actions 配置

Variables：

```text
PREVIEW_ENABLED=true
PREVIEW_PUBLIC_BUCKET_NAME=zppz-preview-static
PREVIEW_PLAYER_ORIGIN=https://preview.przppz.club
```

Secrets：

```text
PREVIEW_PUBLIC_ACCESS_KEY_ID
PREVIEW_PUBLIC_SECRET_ACCESS_KEY
```

现有 `R2_ACCOUNT_ID` 会复用。公共 Bucket 凭据不会上传服务器。
发布脚本用工作流自带的 `GITHUB_TOKEN` 下载 MiaView CI 产物
`miaview-preview`；目标仓库为公开仓库即可。

## 发布和回滚

`main` 分支部署会先验证后端、迁移和前端，再发布固定 MiaView 构建。若该
版本目录下 `object-inventory.json` 列出的全部对象已在公共 R2 中存在，部署会
直接跳过 GitHub Actions 产物下载（避免大体积 WASM 拖垮发布）；缺失对象才会
下载 artifact、校验并上传。相同哈希会跳过，不同哈希会中止部署。播放器 HEAD
检查通过后，工作流才会把生成的 `PREVIEW_PLAYER_URL`（指向
`…/miaview/<version>/sdk/index.mjs`）写入服务器环境并激活网站版本。后端会从该
URL 推导 `renderer_url`（`…/renderer/index.html`）；也可选设置
`PREVIEW_RENDERER_URL` 覆盖。

**升级 MiaView 时必须 bump**
`preview-player/miaview-build.json` 的 `version`，并同步更新 `commit` 到目标
提交。版本前缀是 immutable 的：同版本已发布时不会覆盖旧对象；若 pin 文件与
R2 哈希不一致，发布脚本会报错提醒 bump，避免线上继续用旧构建。

部署脚本执行 `python -m app.prepare`、重启服务并检查 API 与播放器。失败时
代码和旧预览环境变量一起恢复。公共 R2 历史版本不会由部署流程删除，因此
至少保留最近五个版本的要求由“不自动删除”满足。

## 许可说明

播放器版本目录发布 MiaView / MiaCode 上游自带的 `LICENSE`、
`LICENSE_SCOPE.md` 与 `THIRD_PARTY_NOTICES.md`。升级 pin 时请核对上游许可与
第三方资源范围；仓库内 `preview-player/` 只保留版本 pin，不提交 WASM 构建产物。

## 上线验收

使用包含 `maidata.txt`、`track.mp3`、`bg.jpg` 或 `bg.png` 的真实投稿验证：

- 未打开预览时 Network 中没有 MiaView / WASM 请求。
- SDK 与 renderer 来自 `preview.przppz.club/miaview/…`。
- 谱面、音频和背景来自私有 R2 签名地址。
- 手机端确认后才创建播放器实例。
- 关闭弹窗后播放器实例被 `destroy()`，相关请求停止。
- OGG/WEBP 只提示不支持，不影响投稿和下载。
- MP4 解码失败时仍能使用静态背景。
