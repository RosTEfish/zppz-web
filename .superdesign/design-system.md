# ZPPZ Arena — Design System Summary

Product: **ZPPZ Arena**（这谱谱这）— event platform for song pool, draw, submissions, guess/vote.  
Stack: **React 19 + Vite + MUI 9**, fonts **Outfit / Noto Sans SC**.  
Canonical visual contract: `frontend/DESIGN.md`. Runtime theme: `frontend/src/theme.ts` + `frontend/src/index.css`.

---

## Direction

**高级感浅色「精密舞台」** — Stripe-inspired light surfaces + evergreen brand DNA. Depth from tinted shadows and surface brightness layers, not heavy borders. Single interactive accent family: `brand.*`. Gold/accent is decorative only (eyebrows, timeline glow, gradients) — never buttons/links.

Hard constraint from DESIGN.md: visual changes only — do not change routes, data flow, form behavior, copy semantics, or a11y test hooks (`aria-*` / `data-testid`).

---

## Brand & atmosphere

- Canvas: warm paper `#F7F7F4` with brand/teal/accent radial washes + subtle noise
- Ink: pine green `#17211C` (not pure black)
- Default brand: `#176B52` → dark `#0E523E` → darker `#0A3B2D`
- Signature: home Hero event plane + login immersive stage; fallback spotlight gradients + oversized thin Music2 watermark
- Memory: "Z" gradient mark in drawer; overline + short accent underline eyebrows

---

## Dynamic palette (EventThemeProvider)

Event art ships from repo `bg/` and is served at **`GET /api/v1/assets/backgrounds`**. Roles by filename: **`banner` / `post` / `square`** (optional event prefix e.g. `zppz4_post.png`).

Pipeline (`frontend/src/contexts/EventThemeProvider.tsx` + `frontend/src/utils/extractImagePalette.ts`):

1. `useEventBackgrounds()` resolves hero/brand/post assets for current event
2. Sample `hero?.url ?? brand?.url` in a 48px canvas bucket (skip near-white/black/gray)
3. `paletteFromSample` → accessible `main/dark/darker/tint/wash` + decorative `accent` + wash/selection CSS colors + `shadowInk`
4. `createAppTheme(palette)` rebuilds MUI theme (nested ThemeProvider; avoid MUI cssVariables so primary updates apply)
5. `applyPaletteCssVars` writes `--zppz-*` on `:root` for body washes and selection

Defaults when no art / extract fails: evergreen palette in `defaultEventPalette`.

**Usage by surface:**
- Home hero order: `banner` → `post` → `square` (`EventHeroArt` cover + washes)
- Auth stage order: `post` → `brand` → `hero` (full-bleed; glass form centered — current, disliked; redesign drafts first)
- Forbidden: side-by-side “art card + form card” on login

---

## Typography

```
"Outfit", "Noto Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif
```

Weight philosophy: 400 read / 600 UI emphasis / 800 declare. Tabular nums on body/button. Chinese: no negative tracking. Latin display may use -0.01~-0.02em.

---

## Components (token rules)

| Control | Spec |
|---|---|
| Button primary | `brand.main` solid, r8, minH 40, hover dark+sh2, active scale 0.98 — **no gradient** |
| Soft button | tint bg + dark text |
| Card | white, border.default, r12; raised gets sh1, hover sh2 + translateY(-2px) |
| Chip | pill 999; status dots per DESIGN |
| AppBar | glass canvas 0.82 + blur 12 |
| Drawer | `#FBFBF9`, selected = wash + 3px brand left bar |
| Tabs | 2px brand indicator; selected text brand.dark |
| TextField | r8; focus brand border + wash ring |
| Dialog | r16 + sh4; backdrop dark green blur |

---

## Motion

200 / 320 / 360ms with `cubic-bezier(0.32, 0.72, 0, 1)`. Animate only transform/opacity/filter. Respect `prefers-reduced-motion`. Hero art ~420ms; Auth stage ~480ms + form ~360ms fade-up.

---

## Auth redesign stance

Current `/login` is **immersive full-bleed + glass form**. Product owner finds it ugly. For Superdesign work: generate **design drafts first**; keep MUI TextField/Button/Tabs patterns and auth schema behavior, but visual composition is open.

---

## File map

| Concern | Path |
|---|---|
| Visual contract | `frontend/DESIGN.md` |
| MUI theme factory | `frontend/src/theme.ts` |
| CSS vars + canvas | `frontend/src/index.css` |
| Dynamic theme | `frontend/src/contexts/EventThemeProvider.tsx` |
| Palette extract | `frontend/src/utils/extractImagePalette.ts` |
| Background resolve | `frontend/src/utils/backgroundAssets.ts`, `frontend/src/hooks/useEventBackgrounds.ts` |
| App shell | `frontend/src/App.tsx` |
| Auth page | `frontend/src/pages/AuthPage.tsx` |
| Home page | `frontend/src/pages/HomePage.tsx` |
