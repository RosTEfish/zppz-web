# ZPPZ Arena — Design System Summary

Product: **ZPPZ Arena**（这谱谱这）— event platform for song pool, draw, submissions, guess/vote.  
Stack: **React 19 + Vite + MUI 9**, fonts **Outfit / Noto Sans SC / Noto Serif SC**.  
Canonical visual contract: `frontend/DESIGN.md`. Runtime theme: `frontend/src/theme.ts` + `frontend/src/index.css`.

---

## Direction

**浅色「水墨数字节」(Ink-Wash Digital Festival)** — airy canvas, jade interactive accent, serif display titles. Dynamic brand from event art. Gold/accent decorative only.

Hard constraint: visual changes only — do not change routes, data flow, form behavior, copy semantics, or a11y test hooks.

---

## Brand & atmosphere

- Canvas: `#FAFBFA` with jade/ink radial washes + light noise
- Ink: charcoal `#1C2321`
- Default brand: `#1F5A47` → dark `#154233` → darker `#0F2F25`
- Shell: glass top bar + horizontal nav (md+); mobile hamburger + temporary drawer
- Logo: 1:1 `square` via `BrandLogo` / `backgrounds.brand`
- Home: full-bleed hero, brand-first (ZPPZ Arena → 这谱谱这 → event name → CTA)
- Auth: split stage (`post→brand→hero`) + solid paper form

---

## Dynamic palette

`GET /api/v1/assets/backgrounds` → roles `banner` / `post` / `square` → `EventThemeProvider` samples hero/brand → accessible `brand.*` + decorative `accent` + CSS vars `--zppz-*`.

---

## Typography

```
UI: "Outfit", "Noto Sans SC", ...
Display: "Noto Serif SC", "Noto Sans SC", ...
```

---

## File map

| Concern | Path |
|---|---|
| Visual contract | `frontend/DESIGN.md` |
| MUI theme | `frontend/src/theme.ts` |
| CSS vars + canvas | `frontend/src/index.css` |
| Logo | `frontend/src/components/BrandLogo.tsx` |
| App shell | `frontend/src/App.tsx` |
| Home | `frontend/src/pages/HomePage.tsx` |
| Auth | `frontend/src/pages/AuthPage.tsx` |
