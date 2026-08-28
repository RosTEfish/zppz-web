# ZPPZ Arena UI Redesign — Preview

本地 HTML 示例稿，对应计划中的 Superdesign 视觉方向（Neon Arena）。

## 查看方式

```bash
cd .superdesign/tmp/preview
python3 -m http.server 8765
```

浏览器打开：http://127.0.0.1:8765/index.html

## 页面

| 文件 | 对应路由 | 内容 |
|------|----------|------|
| `home.html` | `/` | Hero、阶段时间轴、阶段入口卡片 |
| `guess.html` | `/guess` | 筛选面板、谱面卡片网格 |
| `login.html` | `/login` | 登录/注册表单 |

## Superdesign Canvas

CLI 需先登录：`npx --yes @superdesign/cli@latest login`

登录后可 `import-design-draft` 将本目录 HTML 导入 Superdesign 项目。

## 设计系统

见 `.superdesign/design-system.md`
