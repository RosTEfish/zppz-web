# ZPPZ Arena Design System（这谱谱这 · 视觉契约）

> 方向：**高级感浅色「精密舞台」**——以 Stripe 浅色体系为 token 源（Layer B: `stripe.md`；Layer A: `soft-skill.md` 执行纪律），
> 保留赛事既有的常青绿品牌基因。所有 UI 改动必须回溯到本文件的 token，禁止游离的裸 hex / 魔法 px。
> 硬约束：**只改视觉，不改任何功能逻辑、路由、数据流、表单行为、文案语义、可访问性结构（aria/testid 全部保留）。**

---

## 1. Atmosphere & Identity

- **氛围**：明亮、精密、"舞台灯光下的仪器"。深度感来自 **多层染色阴影 + 表面亮度分层**，而不是边框。
- **签名材质**：绿墨染色阴影（远层大模糊染色 + 近层小模糊中性，Stripe 公式）；关键卡片用「双壳嵌套」(outer shell + inner core)。
- **色彩故事**：松墨绿 ink 做标题（不是纯黑）→ 常青绿 primary 唯一强调色 → 暖纸白画布 → 琥珀金仅做装饰性点缀（时间轴辉光、渐变高光），不参与交互色。
- **记忆点**：首页 Hero 的「聚光灯」渐变 + 超大号细描边音符水印；阶段时间轴的琥珀辉光活动节点。

## 2. Color

### Palette

| Token | 值 | 用途 |
|---|---|---|
| `bg.canvas` | `#F7F7F4` | 页面画布（暖纸白，替代 #F7F9F7） |
| `bg.paper` | `#FFFFFF` | 卡片/面板表面 |
| `bg.subtle` | `#F1F3EF` | 次级填充、表头、hover 底 |
| `ink.primary` | `#17211C` | 标题/正文主色（深松墨绿，非纯黑） |
| `ink.secondary` | `#57645D` | 次级文字 |
| `ink.disabled` | `#93A09A` | 占位符、禁用文字 |
| `brand.main` | `#176B52` | primary 主色（保留品牌锚点） |
| `brand.dark` | `#0E523E` | primary hover / 强调深色 |
| `brand.darker` | `#0A3B2D` | 渐变端点、Hero 深色 |
| `brand.tint` | `#DCEEE5` | primary.light：图标底、选中底、soft 按钮 |
| `brand.wash` | `rgba(23,107,82,0.06)` | 极浅绿洗（背景光晕、选中导航底） |
| `gold.decorative` | `#C9973B` | 装饰性点缀（渐变、辉光、eyebrow 下划线）。**禁止用作按钮/链接色** |
| `gold.tint` | `#F5EBD7` | 金色浅底（装饰容器） |
| `state.warning` | `main #B4740A / light #FBF0DA` | 警告（唯一允许的暖色语义色） |
| `state.info` | `main #1F6E80 / light #DDF0F3` | 提示信息（teal，与绿系同族） |
| `state.success` | `main #218650 / light #DEF2E4` | 成功 |
| `state.error` | `main #BC4038 / light #FADEDC` | 错误 |
| `border.default` | `rgba(23,33,28,0.10)` | 卡片/输入默认描边（半透明墨绿灰） |
| `border.strong` | `rgba(23,33,28,0.16)` | hover 描边、分隔强调 |

### Rules

1. 全站只有一个交互强调色系：evergreen。info 用 teal 同族化，不再出现突兀的默认蓝。
2. 金色 `gold.*` 只出现在：装饰渐变、时间轴活动节点辉光、Hero eyebrow 装饰。任何可点击元素不得使用金色。
3. 描边一律半透明墨绿灰 `border.default`，不再用不透明灰蓝 `#DCE3DF`。
4. 阴影颜色必须是染色阴影（见 §7），禁止中性纯黑阴影。
5. 文字对比度：正文对画布 ≥ 4.5:1；`ink.secondary` 只用于 ≥14px 文字。

## 3. Typography

### Font Stack

```
"Outfit", "Noto Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif
```

依赖已存在：`@fontsource/outfit`、`@fontsource/noto-sans-sc`。按需补 import 字重（300/400/500/600/700/800），不新增字体包。

### Scale（MUI variant 映射）

| Variant | Size | Weight | LineHeight | Tracking | 备注 |
|---|---|---|---|---|---|
| h1 | clamp(2rem→2.75rem) | 800 | 1.15 | -0.02em | Hero 大标题（中文为主时 tracking 归零，拉丁可用负值） |
| h2 | 1.625rem | 700 | 1.25 | -0.01em | 页面标题 |
| h3 | 1.1875rem | 650 | 1.35 | normal | 卡片标题 |
| subtitle1 | 1rem | 550 | 1.5 | normal | 强调正文 |
| body1/body2 | 0.9375rem | 400 | 1.65 | normal | 正文（保持 tabular-nums） |
| button | 0.9375rem | 600 | 1 | normal | textTransform: none |
| caption | 0.8125rem | 500 | 1.45 | normal | 辅助说明 |
| overline | 0.6875rem | 700 | 1.4 | 0.14em | eyebrow 小标签（全大写拉丁） |

### Rules

1. 三档字重哲学（Stripe 原则改造）：400 读 / 600 强调 UI / 800 宣告。标题层级靠 size+weight 对比，不靠颜色。
2. 数字一律 tabular-nums（现状保留）。
3. eyebrow 模式：overline 小标签 + 可选金色短下划线（宽 24px 高 2px 圆角）。
4. 中文文本不加负 letter-spacing；仅拉丁展示字（Outfit）允许 -0.01~-0.02em。

## 4. Spacing & Layout

- **Base unit**: 8px；常用档位 4/8/12/16/20/24/32/40/56。
- **Grid**: 保持现有 `Container maxWidth="xl"` + 左侧固定 Drawer 248px 的壳层骨架（功能不动）。页面内容纵向节奏：PageHeader → 内容块 gap 24px。
- **Rules**:
  1. 卡片内 padding：桌面 24px / 移动 16px。
  2. 相关控件组 gap 8~12px；区块之间 24~32px；页面级留白宁可多不少。
  3. 断点沿用 MUI 默认 xs/sm/md/lg/xl；移动端所有多列网格塌缩为单列。

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
- 玻璃拟态：`rgba(247,247,244,0.82)` + `backdrop-filter: blur(12px)` saturate(1.4)，底部 1px `border.default`，无阴影。
- 高度 64px；右侧状态 Chip 用 §Chip 规范。

### Drawer（侧栏导航）
- 背景 `#FBFBF9`（比画布亮半档），右缘 1px border。
- 品牌区：36px 圆角方块 "Z"（`brand.main`→`brand.dark` 渐变 + 微内高光），下方两行品牌字。
- 导航项：radius 8，selected = `brand.wash` 底 + 3px 左侧 `brand.main` 指示条 + `brand.dark` 文字 + 图标同色；hover = `bg.subtle`。过渡 160ms。
- 底部用户卡：独立 `bg.subtle` 圆角容器包住账号信息 + 退出按钮。

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
- 真实时间轴形态：横向轨道线（2px `border.default`）+ 各阶段节点圆点；已完成=`brand.main` 实心，进行中=金色点 + `rgba(201,151,59,0.25)` 8px 辉光环，未开始=`bg.subtle` 描边空心；节点下 label + 时间 caption。移动端塌缩为紧凑列表。

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
| L0 canvas | `#F7F7F4` + 顶部绿色 radial wash(0.05) + 右上 teal 光晕 + 噪点纹理(0.035) | 页面背景 |
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

**画布配方（index.css body）**：
```css
background-color: #F7F7F4;
background-image:
  radial-gradient(1100px 480px at 88% -8%, rgba(23,107,82,0.07), transparent 60%),
  radial-gradient(900px 420px at -6% 30%, rgba(31,110,128,0.05), transparent 55%),
  radial-gradient(700px 380px at 70% 110%, rgba(201,151,59,0.04), transparent 60%),
  url("noise-svg opacity 0.035");
```

**Hero 聚光灯配方（首页 Hero 内部叠加层，absolute inset-0 pointer-events-none）**：
```
radial-gradient(520px 260px at 78% 0%, rgba(201,151,59,0.14), transparent 62%),
radial-gradient(680px 320px at 96% 100%, rgba(23,107,82,0.12), transparent 58%)
```
水印音符：`color: transparent; -webkit-text-stroke` 不适用 SVG——用 lucide Music2 `strokeWidth={1}` + `opacity 0.10` + 渐变 mask 或直接 `color rgba(10,59,45,0.08)`，尺寸 200px+。

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
4. 不新增运行时依赖；字体仅扩 @fontsource 字重 import。
5. React dev 工具（react-grab/react-scan/react-doctor）本期不安装：项目有严格 bundle-size 门禁与 CI，用户约束为最小侵入；如需后续单独接入。
