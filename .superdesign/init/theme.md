# Theme — ZPPZ Arena

## Part 1 — Compact token summary (current production)

| Token | Value |
|-------|-------|
| canvas | `#F7F7F4` |
| paper | `#FFFFFF` |
| subtle | `#F1F3EF` |
| ink.primary | `#17211C` |
| ink.secondary | `#57645D` |
| brand.main | `#176B52` |
| brand.dark | `#0E523E` |
| gold.decorative | `#C9973B` (decorative only) |
| border | `rgba(23,33,28,0.10)` |
| font | Outfit + Noto Sans SC |
| radius | 8px (buttons), 12px (cards) |
| drawer width | 248px |
| app bar height | 64px |

## Part 2 — Redesign direction (Neon Arena)

| Token | Value |
|-------|-------|
| canvas | `#0A0E14` |
| elevated | `#111822` |
| card | `#151D2B` |
| ink.primary | `#E8EDF5` |
| ink.secondary | `#8B9BB5` |
| accent.magenta | `#FF2D7A` |
| accent.cyan | `#00E5FF` |
| glass | `rgba(17,24,34,0.72)` |
| nav rail | 72px icon / 240px expanded |

See `.superdesign/design-system.md` for full v2 tokens.

## Raw source — `frontend/src/theme.ts`

```ts
export const brand = { main: "#176B52", dark: "#0E523E", darker: "#0A3B2D", tint: "#DCEEE5", wash: "rgba(23, 107, 82, 0.06)" };
export const ink = { primary: "#17211C", secondary: "#57645D", disabled: "#93A09A" };
export const surface = { canvas: "#F7F7F4", paper: "#FFFFFF", subtle: "#F1F3EF" };
```

## Raw source — `frontend/src/index.css` (canvas)

```css
body {
  background-color: #f7f7f4;
  background-image:
    radial-gradient(1100px 480px at 88% -8%, rgba(23, 107, 82, 0.07), transparent 60%),
    radial-gradient(900px 420px at -6% 30%, rgba(31, 110, 128, 0.05), transparent 55%),
    radial-gradient(700px 380px at 70% 110%, rgba(201, 151, 59, 0.04), transparent 60%);
}
```
