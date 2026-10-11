# Theme — ZPPZ Arena

Sources: `frontend/DESIGN.md`, `frontend/src/theme.ts`, `frontend/src/index.css`, dynamic palette via `EventThemeProvider` + `extractImagePalette`.

---

## Part 1 — Compact token summary

### Framework
- MUI 9 `createTheme` (no Tailwind). Light mode only.
- Fonts: `"Outfit", "Noto Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif`
- Base shape radius: **8**; cards 12; panels/hero/dialog 16; chips 999.
- Drawer width: **248px**. Spacing base 8px.

### Color palette (defaults; brand.* overridable from event art)

| Token | Value | Use |
|---|---|---|
| `bg.canvas` | `#F7F7F4` | Page canvas |
| `bg.paper` | `#FFFFFF` | Cards/panels |
| `bg.subtle` | `#F1F3EF` | Secondary fill, table head |
| `ink.primary` | `#17211C` | Titles/body |
| `ink.secondary` | `#57645D` | Secondary text |
| `ink.disabled` | `#93A09A` | Placeholder/disabled |
| `brand.main` | `#176B52` | Primary (dynamic) |
| `brand.dark` | `#0E523E` | Hover/emphasis |
| `brand.darker` | `#0A3B2D` | Gradient end |
| `brand.tint` | `#DCEEE5` | Soft button / icon bg |
| `brand.wash` | `rgba(23,107,82,0.06)` | Nav selected, washes |
| `accent` | `#C9973B` | Decorative only (not interactive) |
| `gold.tint` | `#F5EBD7` | Decorative container |
| `border.default` | `rgba(23,33,28,0.10)` | Default stroke |
| `border.strong` | `rgba(23,33,28,0.16)` | Hover stroke |
| `state.success` | `#218650` / `#DEF2E4` | Success |
| `state.warning` | `#B4740A` / `#FBF0DA` | Warning |
| `state.error` | `#BC4038` / `#FADEDC` | Error |
| `state.info` | `#1F6E80` / `#DDF0F3` | Info (teal) |

### CSS variables (`:root` / runtime `--zppz-*`)

```
--zppz-brand, --zppz-brand-dark, --zppz-brand-darker, --zppz-brand-tint, --zppz-brand-wash
--zppz-accent, --zppz-accent-soft
--zppz-wash-a, --zppz-wash-b, --zppz-wash-c
--zppz-selection
```

Written by `applyPaletteCssVars` when event art loads; drive body radial washes + `::selection`.

### Typography scale (MUI variants)

| Variant | Size | Weight | LH |
|---|---|---|---|
| h1 | clamp(2rem→2.75rem) | 800 | 1.15 |
| h2 | 1.625rem | 700 | 1.25 |
| h3 | 1.1875rem | 650 | 1.35 |
| subtitle1 | 1rem | 550 | 1.5 |
| body1 | 0.9375rem | 400 | 1.65 |
| body2 | 0.875rem | 400 | 1.6 |
| button | 0.9375rem | 600 | 1 (no uppercase) |
| caption | 0.8125rem | 500–600 | 1.45 |
| overline | 0.6875rem | 700 | 1.4 |

### Shadows (green-ink tinted; rebuilt from palette.shadowInk)

```
sh1 = 0 1px 2px rgba(ink,0.05), 0 1px 3px rgba(ink,0.06)
sh2 = 0 2px 4px rgba(ink,0.06), 0 12px 32px -12px rgba(ink,0.16)
sh3 = 0 4px 12px -2px rgba(ink,0.08), 0 20px 44px -16px rgba(ink,0.22)
sh4 = 0 8px 20px -8px rgba(23,23,23,0.10), 0 28px 56px -20px rgba(ink,0.26)
```

### Motion
- Standard 200ms / enter 320ms / large 360ms
- Easing: `cubic-bezier(0.32, 0.72, 0, 1)`
- `prefers-reduced-motion: reduce` → no transform/transition

### Atmosphere
- Canvas: warm paper `#F7F7F4` + three radial washes (brand / teal / accent) + SVG noise 0.035
- AppBar glass: `rgba(247,247,244,0.82)` + blur(12px) saturate(1.4)
- Auth form glass: `rgba(255,255,255,0.72)` + blur(18px) (current; redesign drafts welcome)

### Dynamic palette pipeline
1. `GET /api/v1/assets/backgrounds` → resolve `banner` / `post` / `square` (event slug / `zppzN` prefix)
2. `EventThemeProvider` samples `hero` then `brand` URL via `extractImagePalette`
3. Derives accessible `brand.*` + decorative `accent` → `createAppTheme(palette)` + CSS vars

---

## Part 2 — Raw source dumps

### `frontend/src/theme.ts`

```ts
import { createTheme } from "@mui/material/styles";
import { defaultEventPalette, type EventPalette } from "./utils/extractImagePalette";
import { rgbaString } from "./utils/colorMath";

// ---------------------------------------------------------------------------
// ZPPZ Arena Design System tokens —— 唯一来源见 frontend/DESIGN.md
// brand.* 可由赛事素材动态取色覆盖；ink / surface 保持稳定可读性。
// ---------------------------------------------------------------------------

export const brand = {
  main: defaultEventPalette.main,
  dark: defaultEventPalette.dark,
  darker: defaultEventPalette.darker,
  tint: defaultEventPalette.tint,
  wash: defaultEventPalette.wash,
} as const;

export const ink = {
  primary: "#17211C",
  secondary: "#57645D",
  disabled: "#93A09A",
} as const;

export const surface = {
  canvas: "#F7F7F4",
  paper: "#FFFFFF",
  subtle: "#F1F3EF",
} as const;

export const borderColor = {
  default: "rgba(23, 33, 28, 0.10)",
  strong: "rgba(23, 33, 28, 0.16)",
} as const;

function buildShadows(palette: EventPalette) {
  const inkRgb = palette.shadowInk;
  const far = rgbaString(inkRgb, 0.16);
  const farStrong = rgbaString(inkRgb, 0.22);
  const farHeavy = rgbaString(inkRgb, 0.26);
  const near = rgbaString(inkRgb, 0.06);
  const nearSoft = rgbaString(inkRgb, 0.05);
  const nearMid = rgbaString(inkRgb, 0.08);
  const shadow1 = `0 1px 2px ${nearSoft}, 0 1px 3px ${near}`;
  const shadow2 = `0 2px 4px ${near}, 0 12px 32px -12px ${far}`;
  const shadow3 = `0 4px 12px -2px ${nearMid}, 0 20px 44px -16px ${farStrong}`;
  const shadow4 = `0 8px 20px -8px rgba(23,23,23,0.10), 0 28px 56px -20px ${farHeavy}`;
  return { shadow1, shadow2, shadow3, shadow4 };
}

const motion = {
  standard: "cubic-bezier(0.32, 0.72, 0, 1) 200ms",
  enter: "cubic-bezier(0.32, 0.72, 0, 1) 320ms",
};
const reducedMotion = {
  transition: "none",
  transform: "none",
};

export function createAppTheme(palette: EventPalette = defaultEventPalette) {
  const { shadow1, shadow2, shadow3, shadow4 } = buildShadows(palette);
  const base = createTheme();
  const tintedShadows = base.shadows.map((s, i) => {
    if (i === 1) return shadow1;
    if (i === 2) return shadow2;
    if (i === 3) return shadow3;
    if (i === 4) return shadow4;
    if (i === 8) return shadow3;
    return s;
  });

  return createTheme({
    // Avoid cssVariables: nested ThemeProviders would otherwise keep the
    // outer --mui-palette-* values and ignore event-art primary updates.
    palette: {
      mode: "light",
      primary: { main: palette.main, dark: palette.dark, light: palette.tint, contrastText: "#FFFFFF" },
      secondary: { main: "#1F6E80", dark: "#16505D", light: "#DDF0F3", contrastText: "#FFFFFF" },
      info: { main: "#1F6E80", dark: "#16505D", light: "#DDF0F3", contrastText: "#FFFFFF" },
      warning: { main: "#B4740A", dark: "#8A5908", light: "#FBF0DA", contrastText: "#FFFFFF" },
      error: { main: "#BC4038", dark: "#96332C", light: "#FADEDC", contrastText: "#FFFFFF" },
      success: { main: "#218650", dark: "#19683D", light: "#DEF2E4", contrastText: "#FFFFFF" },
      background: { default: surface.canvas, paper: surface.paper },
      text: { primary: ink.primary, secondary: ink.secondary, disabled: ink.disabled },
      divider: borderColor.default,
    },
    shape: { borderRadius: 8 },
    shadows: tintedShadows as typeof base.shadows,
    typography: {
      fontFamily: '"Outfit", "Noto Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif',
      h1: { fontSize: "clamp(2rem, 4vw, 2.75rem)", fontWeight: 800, lineHeight: 1.15 },
      h2: { fontSize: "1.625rem", fontWeight: 700, lineHeight: 1.25, letterSpacing: "-0.01em" },
      h3: { fontSize: "1.1875rem", fontWeight: 650, lineHeight: 1.35 },
      subtitle1: { fontSize: "1rem", fontWeight: 550, lineHeight: 1.5 },
      body1: { fontSize: "0.9375rem", lineHeight: 1.65, letterSpacing: 0, fontVariantNumeric: "tabular-nums" },
      body2: { fontSize: "0.875rem", lineHeight: 1.6, letterSpacing: 0, fontVariantNumeric: "tabular-nums" },
      button: { fontWeight: 600, textTransform: "none", letterSpacing: 0, fontVariantNumeric: "tabular-nums" },
      caption: { fontSize: "0.8125rem", fontWeight: 600, lineHeight: 1.45, fontVariantNumeric: "tabular-nums" },
      overline: { fontSize: "0.6875rem", fontWeight: 700, lineHeight: 1.4, fontVariantNumeric: "tabular-nums" },
    },
    components: {
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: {
            minHeight: 40,
            borderRadius: 8,
            transition: `transform ${motion.standard}, background-color 160ms ease, box-shadow ${motion.standard}`,
            "&:active": { transform: "scale(0.98)" },
            "&.Mui-focusVisible": { outline: `2px solid ${palette.main}`, outlineOffset: 2 },
            "&.MuiButton-containedPrimary:hover": { backgroundColor: palette.dark, boxShadow: shadow2 },
            "@media (prefers-reduced-motion: reduce)": reducedMotion,
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: 12,
            border: `1px solid ${borderColor.default}`,
            backgroundImage: "none",
            boxShadow: shadow1,
            transition: `transform ${motion.standard}, box-shadow ${motion.standard}`,
            "&:hover": {
              transform: "translateY(-2px)",
              boxShadow: shadow2,
            },
            "@media (prefers-reduced-motion: reduce)": reducedMotion,
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          outlined: { borderColor: borderColor.default },
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: {
            borderRadius: 16,
            boxShadow: shadow4,
            backgroundImage: "linear-gradient(180deg, rgba(255,255,255,0.9), rgba(255,255,255,0))",
          },
        },
      },
      MuiBackdrop: {
        styleOverrides: {
          root: {
            backgroundColor: "rgba(15,22,18,0.45)",
            backdropFilter: "blur(4px)",
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { borderRadius: 999, fontWeight: 600 },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          head: { fontWeight: 700, color: ink.secondary, background: surface.subtle },
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            transition: `box-shadow ${motion.standard}, border-color 160ms ease`,
            "& .MuiOutlinedInput-notchedOutline": { borderColor: borderColor.default },
            "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: borderColor.strong },
            "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderWidth: 1.5, borderColor: palette.main },
            "&.Mui-focused": { boxShadow: `0 0 0 3px ${palette.wash.replace("0.06", "0.12")}` },
          },
        },
      },
      MuiAlert: {
        styleOverrides: {
          root: ({ ownerState }) => ({
            borderRadius: 10,
            borderWidth: 1,
            borderStyle: "solid",
            ...(ownerState.severity === "info" && { backgroundColor: "#DDF0F3", color: "#155562", borderColor: "rgba(31, 110, 128, 0.25)" }),
            ...(ownerState.severity === "success" && { backgroundColor: "#DEF2E4", color: "#19683D", borderColor: "rgba(33, 134, 80, 0.25)" }),
            ...(ownerState.severity === "warning" && { backgroundColor: "#FBF0DA", color: "#8A5908", borderColor: "rgba(180, 116, 10, 0.28)" }),
            ...(ownerState.severity === "error" && { backgroundColor: "#FADEDC", color: "#96332C", borderColor: "rgba(188, 64, 56, 0.25)" }),
          }),
        },
      },
      MuiTabs: {
        styleOverrides: {
          indicator: { height: 2, borderRadius: 2, backgroundColor: palette.main },
        },
      },
      MuiTab: {
        styleOverrides: {
          root: {
            fontWeight: 600,
            "&.Mui-selected": { color: palette.dark },
          },
        },
      },
      MuiTooltip: {
        styleOverrides: {
          tooltip: { backgroundColor: ink.primary, fontSize: "0.75rem", borderRadius: 6, padding: "6px 10px" },
        },
      },
      MuiSkeleton: {
        styleOverrides: {
          root: { backgroundColor: palette.wash.replace("0.06", "0.08") },
        },
      },
      MuiIconButton: {
        styleOverrides: {
          root: {
            transition: `transform ${motion.standard}, background-color 160ms ease`,
            "&:active": { transform: "scale(0.98)" },
            "&.Mui-focusVisible": { outline: `2px solid ${palette.main}`, outlineOffset: 2 },
            "@media (prefers-reduced-motion: reduce)": reducedMotion,
          },
        },
      },
      MuiListItemButton: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            transition: "background-color 160ms ease",
            "&.Mui-focusVisible": { outline: `2px solid ${palette.main}`, outlineOffset: -2 },
          },
        },
      },
    },
  });
}

export const theme = createAppTheme();
```

### `frontend/src/index.css`

```css
:root {
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  --zppz-brand: #176b52;
  --zppz-brand-dark: #0e523e;
  --zppz-brand-darker: #0a3b2d;
  --zppz-brand-tint: #dceee5;
  --zppz-brand-wash: rgba(23, 107, 82, 0.06);
  --zppz-accent: #c9973b;
  --zppz-accent-soft: rgba(201, 151, 59, 0.14);
  --zppz-wash-a: rgba(23, 107, 82, 0.07);
  --zppz-wash-b: rgba(31, 110, 128, 0.05);
  --zppz-wash-c: rgba(201, 151, 59, 0.04);
  --zppz-selection: rgba(23, 107, 82, 0.18);
}

html {
  min-width: 320px;
  background: #f7f7f4;
  scrollbar-gutter: stable;
}

body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  overflow-x: hidden;
  background-color: #f7f7f4;
  background-image:
    radial-gradient(1100px 480px at 88% -8%, var(--zppz-wash-a), transparent 60%),
    radial-gradient(900px 420px at -6% 30%, var(--zppz-wash-b), transparent 55%),
    radial-gradient(700px 380px at 70% 110%, var(--zppz-wash-c), transparent 60%),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='1' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
  background-attachment: scroll;
  transition: background-image 320ms cubic-bezier(0.32, 0.72, 0, 1);
}

* {
  box-sizing: border-box;
}

button,
input,
textarea,
select {
  font: inherit;
  letter-spacing: 0;
}

a {
  color: inherit;
  text-decoration: none;
}

svg {
  flex-shrink: 0;
  vertical-align: middle;
}

::selection {
  background: var(--zppz-selection);
}

@media (max-width: 599px) {
  .MuiDialog-paper:not(.MuiDialog-paperFullScreen) {
    margin: 12px;
    width: calc(100% - 24px);
    max-height: calc(100% - 24px);
  }

  .MuiTableCell-root {
    white-space: nowrap;
  }
}
```
