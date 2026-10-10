# Extractable DraftComponents

Menu of reusable Superdesign components. Full source lives in `components.md` / `layouts.md` — this file is the extraction catalog only.

---

## Layout Components

### AppShell
- Source: `frontend/src/App.tsx` (`AppShell`)
- Category: layout
- Description: Fixed glass AppBar + 248px Drawer + main column; switches to authLayout on `/login`
- Extractable props: `activePath` (string), `eventName` (string), `submissionOpen` (boolean), `isLoggedIn` (boolean), `isMobile` (boolean), `showGuessEntry` (boolean), `showAdmin` (boolean), `authLayout` (boolean)
- Hardcoded: DRAWER_WIDTH 248, brand "Z" mark, "ZPPZ Arena" label, Chinese nav labels, AppBar glass rgba/blur, drawer `#FBFBF9`

### SideNav (Drawer)
- Source: `frontend/src/App.tsx` (drawer JSX inside `AppShell`)
- Category: layout
- Description: Brand header, Lucide nav list with selected wash + left border, optional admin entry, bottom account/login
- Extractable props: `activeItem` (string, default `"home"`), `eventSubtitle` (string), `showGuess` (boolean), `showAdmin` (boolean), `isLoggedIn` (boolean), `userDisplayName` (string), `userIdentityLabel` (string), `managerHref` (string)
- Hardcoded: link labels (首页/曲池/曲目分配/投稿/猜谱/往届乐曲), Lucide icon names, "Z" gradient mark, "管理工作台", "退出登录"/"登录"

### TopAppBar
- Source: `frontend/src/App.tsx` (`AppBar` in `AppShell`)
- Category: layout
- Description: Glass top bar with menu button (mobile), event title, submission status Chip
- Extractable props: `title` (string), `submissionOpen` (boolean), `showMenuButton` (boolean)
- Hardcoded: Chip labels "投稿开放"/"投稿未开放", blur/glass styles, height via Toolbar 64

### SiteFooter
- Source: `frontend/src/App.tsx` (`SiteFooter`)
- Category: layout
- Description: ICP + public security beian footer links centered under main
- Extractable props: none required for design (static legal links)
- Hardcoded: ICP text/URLs, beian icon asset, caption typography

---

## Basic Components

### AuthGlassForm
- Source: `frontend/src/pages/AuthPage.tsx` (Paper form)
- Category: basic
- Description: Centered glass login/register card — Tabs, TextFields, identity Select, submit Button
- Extractable props: `mode` (`"login"` | `"register"`), `eventName` (string | null), `registrationClosed` (boolean), `errorMessage` (string), `isSubmitting` (boolean)
- Hardcoded: title "赛事账号", tab labels 登录/注册, field labels 账号/QQ/密码/身份, MenuItem copy, KeyRound icon, accent eyebrow bar, glass blur/rgba styles, maxWidth 430

### AuthStageBackground
- Source: `frontend/src/pages/AuthPage.tsx` (absolute stage layers)
- Category: basic
- Description: Full-bleed event art or palette wash fallback behind auth form
- Extractable props: `imageUrl` (string | null), `paletteWashA` / `paletteAccentSoft` / `paletteWashC` (strings)
- Hardcoded: cover objectFit, warm white diagonal veil stops, authStageIn 480ms animation

### PageHeader
- Source: `frontend/src/components/PagePrimitives.tsx`
- Category: basic
- Description: Page title row with tint icon tile + optional actions
- Extractable props: `title` (string), `meta` (string | undefined), `icon` (icon name), `showActions` (boolean)
- Hardcoded: 42px icon tile, primary.light/dark colors, h2 typography, mb 3

### LoadingBlock / ResourceState / Skeletons
- Source: `frontend/src/components/PagePrimitives.tsx`, `frontend/src/components/HomePageSkeleton.tsx`
- Category: basic
- Description: Loading spinner, empty/error states, table/card/home skeletons
- Extractable props: `loadingVariant` (`block` | `table` | `cards`), `empty` (string), `error` (string)
- Hardcoded: skeleton structure, aria labels in Chinese, CircularProgress size 30

### EventHeroArt
- Source: `frontend/src/components/EventHeroArt.tsx`
- Category: basic
- Description: Absolute cover image + readable warm-paper / palette washes for home hero
- Extractable props: `imageUrl` (string), accent/wash colors from palette
- Hardcoded: heroArtIn 420ms, objectPosition breakpoints, gradient stop values

### BrandMarkZ
- Source: drawer brand box in `frontend/src/App.tsx`
- Category: basic
- Description: 36px rounded square "Z" with brand gradient + inset highlight
- Extractable props: `main` / `dark` (colors)
- Hardcoded: letter "Z", sizes 36/19, borderRadius 2, inset highlight shadow

---

## Auth form pattern notes (for draft extraction)

Prefer extracting **AuthGlassForm** + **AuthStageBackground** as a pair when redesigning `/login`. Keep MUI primitives (TextField, Tabs, Button, Select) as the implementation language — no custom input kit. Product direction: current glass-on-bleed feels weak; explore stronger compositions in Superdesign before coding.
