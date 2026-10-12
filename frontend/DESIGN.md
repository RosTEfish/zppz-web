# ZPPZ Arena Design System（这谱谱这 · 视觉契约）

> 方向：**浅色「水墨数字节」(Ink-Wash Digital Festival)**——空气感画布 + 玉绿交互 + 衬线标题，
> 保留赛事动态取色基因。所有 UI 改动必须回溯到本文件的 token，禁止游离的裸 hex / 魔法 px。
> 硬约束：**只改视觉，不改任何功能逻辑、路由、数据流、表单行为、文案语义、可访问性结构（aria/testid 全部保留）。**

---

## 1. Atmosphere & Identity

- **氛围**：明亮、编辑感、"水墨洗过的数字节"。深度感来自 **柔和墨色阴影 + 表面亮度分层**，首屏以全幅赛事视觉为主。
- **签名材质**：玉绿 CTA、轻描边编辑卡、Hero 左侧/底部水墨可读性蒙版（非沉重不透明板）。
- **色彩故事**：墨炭 ink 做标题 → **赛事动态 primary**（从 `bg/` 取色；无素材时回退玉绿 `#1F5A47`）→ 冷纸白画布 `#FAFBFA` → accent 仅装饰性点缀，不参与交互色。
- **记忆点**：顶栏水平导航 + 1:1 `square` logo；首页全幅 Hero（`banner→post→square`）品牌先行（ZPPZ Arena / 这谱谱这 → 赛事名 → CTA）；登录页分栏海报 + 实体纸卡表单；时间轴活动节点用 primary 辉光。

## 2. Color

### Palette

| Token | 值 | 用途 |
|---|---|---|
| `bg.canvas` | `#FAFBFA` | 页面画布（冷纸白） |
| `bg.paper` | `#FFFFFF` | 卡片/面板表面 |
| `bg.subtle` | `#F4F6F5` | 次级填充、表头、hover 底 |
| `ink.primary` | `#1C2321` | 标题/正文主色（墨炭，非纯黑） |
| `ink.secondary` | `#5A6561` | 次级文字 |
| `ink.disabled` | `#93A09A` | 占位符、禁用文字 |
| `brand.main` | 默认 `#1F5A47`；运行时可被素材取色覆盖 | primary 主色（对白字对比 ≥ 4.5） |
| `brand.dark` | 默认 `#154233` | primary hover / 强调深色 |
| `brand.darker` | 默认 `#0F2F25` | 渐变端点、Hero 深色 |
| `brand.tint` | 默认 `#D8E5DF` | primary.light：图标底、选中底、soft 按钮 |
| `brand.wash` | 默认 `rgba(31,90,71,0.06)` | 极浅色洗（背景光晕、选中导航底） |
| `accent` / `gold.decorative` | 默认 `#C9973B`；随素材 accent 变化 | 装饰性点缀（渐变、辉光、eyebrow 下划线）。**禁止用作按钮/链接色** |
| `gold.tint` | `#F5EBD7` | 金色浅底（装饰容器；无动态覆盖时保留） |
| `state.warning` | `main #B4740A / light #FBF0DA` | 警告（唯一允许的暖色语义色） |
| `state.info` | `main #1F6E80 / light #DDF0F3` | 提示信息（teal，与绿系同族） |
| `state.success` | `main #218650 / light #DEF2E4` | 成功 |
| `state.error` | `main #BC4038 / light #FADEDC` | 错误 |
| `border.default` | `rgba(28,35,33,0.10)` | 卡片/输入默认描边（半透明墨灰） |
| `border.strong` | `rgba(28,35,33,0.16)` | hover 描边、分隔强调 |

### Rules

1. 全站只有一个交互强调色系：`brand.*`（默认 evergreen，可按当前 `bg/` 素材动态取色）。info 用 teal 同族化，不再出现突兀的默认蓝。
2. `accent` / `gold.*` 只出现在：装饰渐变、时间轴活动节点辉光、Hero/Auth eyebrow 装饰。任何可点击元素不得使用 accent。
3. 动态取色实现：`extractImagePalette` 采样 hero/brand 图 → 派生 accessible `brand.*` + 装饰 `accent` → `EventThemeProvider` 重建 MUI theme，并写入 CSS 变量 `--zppz-*`（画布光晕、selection）。
4. 描边一律半透明墨绿灰 `border.default`，不再用不透明灰蓝 `#DCE3DF`。
5. 阴影颜色必须是染色阴影（见 §7，随 brand 墨色染色），禁止中性纯黑阴影。
6. 文字对比度：正文对画布 ≥ 4.5:1；`ink.secondary` 只用于 ≥14px 文字；动态 `brand.main` 对白字 ≥ 4.5:1。

## 3. Typography

### Font Stack

```
UI / body: "Outfit", "Noto Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif
Display (h1–h3 / 品牌字): "Noto Serif SC", "Noto Sans SC", "Songti SC", serif
```

依赖：`@fontsource/outfit`、`@fontsource/noto-sans-sc`、`@fontsource/noto-serif-sc`。字重经 `fonts.css` 异步加载。

加载字重（控制中文体积）：Outfit 400/600/700；Noto Sans SC 400/600/700；Noto Serif SC **仅 700**。勿再引入 Serif 900 / Outfit 800。

### Scale（MUI variant 映射）

| Variant | Size | Weight | LineHeight | Tracking | 备注 |
|---|---|---|---|---|---|
| h1 | clamp(2rem→3.5rem) | 700 | 1.12 | normal | Hero 赛事名（衬线） |
| h2 | 1.625rem | 700 | 1.25 | -0.01em | 区块标题（衬线） |
| h3 | 1.25rem | 700 | 1.35 | normal | 卡片标题（衬线） |
| subtitle1 | 1rem | 550 | 1.5 | normal | 强调正文 |
| body1/body2 | 0.9375rem | 400 | 1.65 | normal | 正文（保持 tabular-nums） |
| button | 0.9375rem | 600 | 1 | normal | textTransform: none |
| caption | 0.8125rem | 600 | 1.45 | normal | 辅助说明 |
| overline | 0.6875rem | 700 | 1.4 | 0.14em | eyebrow 小标签 |

### Rules

1. 三档字重：400 读 / 600 UI / 700 宣告（衬线标题共用 700，避免再拉 Serif 900）。
2. 数字一律 tabular-nums。
3. 品牌 eyebrow：玉绿短下划线（宽 ~32px 高 2px）。
4. 中文文本不加负 letter-spacing。

## 4. Spacing & Layout

- **Base unit**: 8px；常用档位 4/8/12/16/20/24/32/40/56。
- **Shell**: 固定玻璃顶栏（水平导航，md+）；移动端汉堡 + temporary Drawer。首页 `/` 全宽无内容 padding（自管 maxWidth 1280）；其余路由保持 xl 内容区 padding。
- **Rules**:
  1. 卡片内 padding：桌面 24–28px / 移动 16–20px。
  2. 相关控件组 gap 8~12px；区块之间 24~40px。
  3. 断点沿用 MUI 默认；移动端多列网格塌缩为单列/列表。

## 5. Components

### Button
- Primary：`brand.main` 实底白字，radius 8，minHeight 40，hover `brand.dark` + shadow sh2，active scale(0.98)。**不加渐变**。
- Soft（次级首选）：`brand.tint` 底 + `brand.dark` 字，hover 加深为 `brand.wash`+描边 `border.default`。
- Outlined/ghost：透明底 + `border.default` 描边 + `ink.primary` 字，hover `bg.subtle`。
- Text：同 MUI，hover `brand.wash`。
- Focus：2px `brand.main` 外环 offset 2px（键盘可见）。

### Card / Paper
- `variant="outlined"`：白底 + `border.default` + radius 12 + 无阴影（平面层）。
- `elevation` 卡片（内容主卡）：白底 + border + radius 12 + shadow sh1，hover sh2 + translateY(-2px)。
- 双壳嵌套（仅用于首页 Hero 与关键展示卡）：outer = `bg.subtle`/wash 底 + radius 16 + p 6px + hairline 边；inner = 白底 radius 12 + inner highlight `inset 0 1px 0 rgba(255,255,255,0.8)`。
- radius 层级规则：按钮/输入 8 < 卡片 12 < 面板/Hero 16。

### Chip（状态胶囊）
- 统一 pill（radius 999），带 8px 状态圆点（开放=success 绿点、未开放=ink.disabled 灰点、进行中=gold 点+微光）。
- 开放态：`success.light` 底 + success 字；未开放：透明底 + `border.default` + secondary 字。

### AppBar（顶栏）
- 玻璃拟态：`rgba(250,251,250,0.85)` + `backdrop-filter: blur(16px)`，底部 1px `border.default`，无阴影。
- 高度 64px；左侧 1:1 `square` logo（`BrandLogo` / `backgrounds.brand`）+「ZPPZ Arena」；md+ 水平导航（选中底边 2px primary）；右侧投稿 Chip + 登录/账号。

### Drawer（仅移动端）
- temporary Drawer，宽 280；品牌区用 `BrandLogo` + 赛事名；导航项 selected = wash + 左侧 3px primary；底部账号/登录。

### Table / DataGrid
- 表头：`bg.subtle` 底、`ink.secondary` 700 字重、无竖线、行 hover `brand.wash`。
- 行分割线 `border.default`；表格容器外层卡片 radius 12 overflow hidden。

### Dialog
- Paper：radius 16 + shadow sh4 + 顶部 1px 内高光；backdrop `rgba(15,22,18,0.45)` + blur(4px)。

### Alert
- info → teal 化（`state.info`）；左侧 4px 主题色条 + tint 底 + 无默认图标时保留布局。warning/success/error 同理套用 state tokens。

### Tabs
- 指示条 2px `brand.main`；选中文字 `brand.dark` 650；未选中 `ink.secondary`；轨道线 `border.default`。

### TextField / Select
- radius 8；默认描边 `border.default`；hover `border.strong`；focus = 1.5px `brand.main` 边 + `rgba(23,107,82,0.12)` 3px 外环；label 色 `ink.secondary`。

### EmptyState（空状态 primitive，ResourceState.empty 使用）
- 居中构图：48px 圆角方块图标（tint 底 brand.dark 图标）+ 标题（h3 650 ink.primary）+ 说明（body2 secondary）+ 可选引导 Button（soft）。垂直 padding 56px。

### PageHeader（页头 primitive）
- 42px 圆角(12) 图标方块改：`linear-gradient(135deg, brand.tint, #EFF7F2)` 底 + `brand.dark` 图标 + 1px border.default；标题 h2；meta caption。右侧 actions 不变。

### PhaseTimeline（阶段时间轴）
- 横向轨道线 + 节点圆点；已完成=ink 实心，进行中=`brand.main` + tint 辉光环，未开始=描边空心；节点下 label + 时间 caption。

### Skeletons（HomePageSkeleton/TableSkeleton/CardGridSkeleton）
- 保持结构，Skeleton 波纹色改为 `rgba(23,107,82,0.08)`↔`rgba(23,107,82,0.03)`，容器卡片同步 §Card 规范。

## 6. Motion & Interaction

### Timing

- 标准：200ms；强调/入场：320ms；大型浮层：360ms。
- 曲线统一 `cubic-bezier(0.32, 0.72, 0, 1)`；退场可用 160ms ease-out。

### Rules

1. 仅动画 `transform` / `opacity` / `filter`；禁止 top/left/width/height 动画。
2. 所有可交互元素必须有 hover + active(scale .98) + focus-visible 反馈；非交互元素不得有动效（slop 禁令）。
3. `prefers-reduced-motion: reduce` 时全部动效归零（保留现有模式）。
4. backdrop-filter 只用于固定元素（AppBar、Dialog backdrop、移动 Drawer 遮罩）。
5. 入场动画克制：仅首页 Hero 允许一次 320ms fade-up（translateY(12px)→0）；其余页面不做入场动画。

## 7. Depth & Surface

### Strategy（表面亮度分层 + 染色阴影）

| 层级 | 配方 | 用途 |
|---|---|---|
| L0 canvas | `#FAFBFA` + 右上 jade tint wash + 左下 ink-wash + 轻噪点 | 页面背景 |
| L1 flat card | 白底 + `border.default` + r12，无阴影 | 列表项、次要容器 |
| L2 raised | L1 + shadow sh1 | 内容主卡 |
| L3 floating | L2 + shadow sh2；hover 升 sh3 + translateY(-2px) | 可点卡片 |
| L4 overlay | r16 + shadow sh4 | Dialog / Popover / 移动 Drawer |

**Shadow tokens（绿墨染色的 Stripe 公式：远层染色大模糊 + 近层中性小模糊）**

```ts
sh1 = "0 1px 2px rgba(18,42,33,0.05), 0 1px 3px rgba(18,42,33,0.06)"
sh2 = "0 2px 4px rgba(18,42,33,0.06), 0 12px 32px -12px rgba(13,53,41,0.16)"
sh3 = "0 4px 12px -2px rgba(18,42,33,0.08), 0 20px 44px -16px rgba(13,53,41,0.22)"
sh4 = "0 8px 20px -8px rgba(23,23,23,0.10), 0 28px 56px -20px rgba(13,53,41,0.26)"
```

**画布配方（index.css body）**：见 `frontend/src/index.css`（`#FAFBFA` + jade/ink radial washes + 轻噪点）。

**Hero / Logo / Auth**：
1. `GET /api/v1/assets/backgrounds` 解析 `banner` / `post` / `square`（届次前缀优先）。
2. Hero：`banner → post → square`，全幅 cover + 水墨可读性蒙版；首屏品牌层级：ZPPZ Arena → 这谱谱这 → 赛事名 → CTA。
3. Logo：`BrandLogo` 使用 `backgrounds.brand`（`square → post → banner`），无素材回退字母 Z。
4. 登录：独立全屏壳；`md+` 左栏 `post→brand→hero`，右栏实体纸卡表单。
5. 动效与 View Transitions 规则不变。

## 8. Accessibility Constraints & Accepted Debt

### Constraints

1. 对比度：正文/标题 ≥ 4.5:1；大字号(≥18.66px bold) ≥ 3:1；`gold.decorative` 禁止承载文字。
2. 键盘焦点环必须可见（Button/TextField/Tabs/导航项全覆盖）；`:focus-visible` 实现。
3. 触控目标 ≥ 40px（现有 minHeight 40 保留）。
4. `prefers-reduced-motion` 全局尊重。
5. aria-label / role / data-testid / 文案节点一律原样保留——测试依赖它们。
6. 移动端 Dialog 边距规则（index.css 现有 @media 块）保留。

### Accepted Debt

1. 本期不做暗色模式（palette 单 light）。
2. Admin DataGrid 密度保持紧凑，仅吃 theme 级样式，不逐列重排。
3. 存量散落的硬编码 `rgba(23,107,82,…)` / `#176B52` sx 值：**被触碰到的文件顺手迁移到 token**，不做全局扫荡替换。
4. 不新增运行时依赖；字体仅在确有必要时扩 @fontsource 字重，并评估中文 woff2 体积（每档约 1MB+）。
5. React dev 工具（react-grab/react-scan/react-doctor）本期不安装：项目有严格 bundle-size 门禁与 CI，用户约束为最小侵入；如需后续单独接入。
