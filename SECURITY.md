# 安全策略 / Security Policy

## 受支持版本 / Supported Versions

本项目为单仓库、单主线（`main`）持续交付模式，只维护最新版本。所有安全修复都会随下一次部署进入生产环境。

## 上报漏洞 / Reporting a Vulnerability

请**不要**通过公开 Issue 提交安全漏洞，以免在修复前被滥用。

请将漏洞详情通过私有渠道发送给维护者：

- GitHub 仓库：联系仓库所有者（Repository owner）
- 邮件：通过 GitHub 个人主页公开的联系方式

报告中请尽量包含：

- 受影响接口/文件与复现步骤
- 影响评估（是否能导致数据泄露、未授权访问、签名伪造等）
- 建议的修复方向（可选）

维护者会在收到后尽快确认并安排修复；修复发布前请勿公开漏洞细节。

## 安全要点 / Security Notes

- 生产环境必须为 `SECRET_KEY`、`WEBHOOK_SIGNING_MASTER_KEY` 设置独立的高强度随机值；后端启动时会对其使用默认值发出告警。
- 默认管理员账号仅在你显式设置 `ADMIN_SEED_PASSWORD` 后才会被创建，请勿在生产使用弱口令。
- R2 存储桶应为私有，并使用最小权限 Token；不要开启 `r2.dev` 公共访问。
