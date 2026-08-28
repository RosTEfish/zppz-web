# ZPPZ Arena — Neon Arena Design System (v2 draft)

> **Scope:** Visual redesign for Superdesign generation. Preserves all routes, features, copy semantics, and accessibility structure from the existing app. Does **not** replace `frontend/DESIGN.md` until user approves.

## Atmosphere

- **Concept:** Midnight esports arena × chart editor workstation — rhythm-game energy without generic purple AI gradients.
- **Mood:** Dark, luminous, precise. Depth from layered glass panels and neon edge glows, not heavy borders.
- **Signature:** Diagonal scan-grid background + magenta spotlight on hero + cyan accent rails on active nav.

## Color Palette

| Token | Value | Usage |
|---|---|---|
| `bg.canvas` | `#0A0E14` | Page background |
| `bg.elevated` | `#111822` | Sidebar, app bar |
| `bg.glass` | `rgba(17,24,34,0.72)` | Glass panels |
| `bg.card` | `#151D2B` | Cards |
| `bg.cardHover` | `#1A2436` | Card hover |
| `ink.primary` | `#E8EDF5` | Headings, body |
| `ink.secondary` | `#8B9BB5` | Meta text |
| `ink.muted` | `#5C6B82` | Placeholders |
| `brand.magenta` | `#FF2D7A` | Primary CTA, active phase, key accents |
| `brand.magentaDark` | `#D91A63` | Hover |
| `brand.cyan` | `#00E5FF` | Secondary accent, links, J-lane chips |
| `brand.cyanDark` | `#00B8CC` | Hover |
| `state.success` | `#2EE59D` | Open chips |
| `state.warning` | `#FFB020` | Warnings |
| `state.error` | `#FF5C5C` | Errors |
| `border.subtle` | `rgba(255,255,255,0.08)` | Default borders |
| `border.glow` | `rgba(255,45,122,0.35)` | Active card outline |
| `glow.magenta` | `0 0 24px rgba(255,45,122,0.25)` | Hero / active node |
| `glow.cyan` | `0 0 20px rgba(0,229,255,0.18)` | Secondary highlights |

## Typography

- **Stack:** `"Outfit", "Noto Sans SC", system-ui, sans-serif`
- **h1:** clamp(2rem, 4vw, 2.75rem) / 800 / -0.02em
- **h2:** 1.625rem / 700
- **h3:** 1.125rem / 650
- **body:** 0.9375rem / 400 / 1.65 / tabular-nums
- **overline:** 0.6875rem / 700 / 0.14em uppercase (Latin only)
- **button:** 0.9375rem / 600, no uppercase

## Layout

- **Shell:** Top app bar (64px) + left rail (72px icon-only desktop, expandable 240px) + main content max-width 1280px
- **Mobile:** Bottom tab bar (5 items) + hamburger for account
- **Radius:** cards 14px, buttons 10px, chips pill
- **Spacing:** 8px grid; section gaps 24–32px

## Components

### AppBar
- Glass `bg.glass`, bottom border `border.subtle`
- Event name left; status chip right (success = 投稿开放)

### Nav rail
- Icon buttons with cyan dot indicator when active
- Magenta wash background on active item

### Hero (Home)
- Large event title, overline "CURRENT EVENT"
- Phase chip + live countdown
- Magenta gradient border-left accent (4px)
- Watermark: large music note at 6% opacity

### Phase timeline
- Horizontal nodes on dark track
- Active node: magenta core + glow ring
- Completed: cyan fill

### Stage cards
- 4-column grid; icon top-left, chevron top-right
- Hover: translateY(-4px) + magenta border glow

### Guess cards
- Cover 164px, level-tinted body (keep existing level color mapping, slightly desaturated for dark mode)
- J-lane: 2px cyan border
- Hover: scale 1.02 + glow

### Auth form
- Centered glass card max 430px
- Tabs: underline indicator magenta
- Primary button: magenta gradient

## Motion

- Standard: `cubic-bezier(0.32, 0.72, 0, 1) 220ms`
- Hero entrance: fade-up 400ms
- Card hover: transform 200ms
- Respect `prefers-reduced-motion`

## Hard constraints (unchanged from product)

- All nav labels: 首页 · 曲池 · 曲目分配 · 投稿 · 猜谱 · 账号
- Footer: 京ICP备2026012070号-1 · 京公网安备11010802047846号
- Brand: ZPPZ Arena / 这谱谱这
- No feature removal; visual-only redesign
