# Majdata 在线预览部署

在线预览由用户浏览器运行 MajdataView WebGL。主服务器只鉴权并返回私有
R2 的短期签名 URL，不渲染、不编码，也不转发音频、图片或视频。

## 一次性 Cloudflare 配置

1. 创建公共 Bucket `zppz-preview-static`，只用于播放器、许可证和对应源码。
2. 给它绑定 `preview.przppz.club`，等待 HTTPS 证书签发。
3. 创建仅限该 Bucket 的 Object Read & Write R2 Token。
4. 私有投稿 Bucket 的 CORS 允许：
   - `https://przppz.club`
   - `https://preview.przppz.club`
   - 开发环境所需的 `http://localhost:3000`
   - 方法 `GET`、`HEAD`、`PUT`
   - 请求头 `Content-Type`、`Range`
   - 暴露 `ETag`、`Accept-Ranges`、`Content-Length`、`Content-Range`
5. 在 Cloudflare 响应头规则中，为
   `preview.przppz.club/majdata/*` 添加：
   `Content-Security-Policy: frame-ancestors https://przppz.club`

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

## 发布和回滚

`main` 分支部署会先验证后端、迁移和前端，再下载固定 Majdata 构建并校验
SHA-256。播放器被 gzip 压缩后上传到不可变版本目录；相同哈希会跳过，不同
哈希会中止部署。播放器 HEAD 检查通过后，工作流才会把生成的
`PREVIEW_PLAYER_URL` 写入服务器环境并激活网站版本。

部署脚本执行 `python -m app.prepare`、重启服务并检查 API 与播放器。失败时
代码和旧预览环境变量一起恢复。公共 R2 历史版本不会由部署流程删除，因此
至少保留最近五个版本的要求由“不自动删除”满足。

## GPL-3.0

播放器页面公开标注 MajdataView，版本目录同时发布 GPL 文本、第三方声明和
对应源码归档。升级或修改 MajdataView 源码时，必须更新固定 commit、哈希和
对应源码归档；不得删除原作者版权或许可证信息。

录制模式预览基于上游 `ad734f1272` 的修改版 WebGL（开场 SongDetail、延迟开谱、
AP、`&clock_count`）。改动源码见 `preview-player/majdata-view-record/`。出包步骤：

1. 用 Unity（实测 **6000.6.0f1**）打开打过 patch 的 MajdataView 工程并导出 WebGL。
2. 将四个产物重命名为 `Build.*` 放到 `preview-player/Build/`。
3. 运行 `python scripts/package_majdata_record_source.py` 生成对应源码 zip。
4. 运行 `python scripts/update_majdata_build_manifest.py --version <新版本名> ...`
   （`build_base_url` / `source_archive_url` 使用 `local://preview-player/...`）。
5. 提交 Build、corresponding-source.zip 与 manifest；部署时
   `publish_preview_player.py` 从 `local://` 读取并上传 R2。

独立 fork 仓库建议命名为 `MajdataView-zppz-preview`，不要把完整 Unity 工程合进
本网站仓的 `main` 历史。

## 上线验收

使用包含 `maidata.txt`、`track.mp3`、`bg.jpg` 或 `bg.png` 的真实投稿验证：

- 未打开预览时 Network 中没有 Unity 请求。
- Unity 文件来自 `preview.przppz.club`。
- 谱面、音频和背景来自私有 R2 签名地址。
- 手机端确认后才创建 iframe。
- 关闭弹窗后 iframe 消失。
- OGG/WEBP 只提示不支持，不影响投稿和下载。
- MP4 解码失败时仍能使用静态背景。
- 点击播放器内播放键后先出现 SongDetail 开场，约数秒后再出 note。
- 曲末出现 All Perfect。
- 带 `&clock_count=N` 的谱面在开头有 N 次拍子音；无该字段的谱面仍正常开场。
- 切换难度或重新加载后再次点播放仍走开场。
