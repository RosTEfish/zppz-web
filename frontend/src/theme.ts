import { createTheme } from "@mui/material/styles";

// ---------------------------------------------------------------------------
// ZPPZ Arena Design System tokens —— 唯一来源见 frontend/DESIGN.md
// ---------------------------------------------------------------------------

export const brand = {
  main: "#176B52",
  dark: "#0E523E",
  darker: "#0A3B2D",
  tint: "#DCEEE5",
  wash: "rgba(23, 107, 82, 0.06)",
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

// 绿墨染色阴影（DESIGN.md §7：远层染色大模糊 + 近层中性小模糊）
const shadow1 = "0 1px 2px rgba(18,42,33,0.05), 0 1px 3px rgba(18,42,33,0.06)";
const shadow2 = "0 2px 4px rgba(18,42,33,0.06), 0 12px 32px -12px rgba(13,53,41,0.16)";
const shadow3 = "0 4px 12px -2px rgba(18,42,33,0.08), 0 20px 44px -16px rgba(13,53,41,0.22)";
const shadow4 = "0 8px 20px -8px rgba(23,23,23,0.10), 0 28px 56px -20px rgba(13,53,41,0.26)";

const base = createTheme();
const greenShadows = base.shadows.map((s, i) => {
  if (i === 1) return shadow1;
  if (i === 2) return shadow2;
  if (i === 3) return shadow3;
  if (i === 4) return shadow4;
  if (i === 8) return shadow3;
  return s;
});

const motion = {
  standard: "cubic-bezier(0.32, 0.72, 0, 1) 200ms",
  enter: "cubic-bezier(0.32, 0.72, 0, 1) 320ms",
};
const reducedMotion = {
  transition: "none",
  transform: "none",
};

export const theme = createTheme({
  cssVariables: true,
  palette: {
    mode: "light",
    primary: { main: brand.main, dark: brand.dark, light: brand.tint, contrastText: "#FFFFFF" },
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
  shadows: greenShadows as typeof base.shadows,
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
          "&.Mui-focusVisible": { outline: `2px solid ${brand.main}`, outlineOffset: 2 },
          "&.MuiButton-containedPrimary:hover": { backgroundColor: brand.dark, boxShadow: shadow2 },
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
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderWidth: 1.5, borderColor: brand.main },
          "&.Mui-focused": { boxShadow: "0 0 0 3px rgba(23, 107, 82, 0.12)" },
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
        indicator: { height: 2, borderRadius: 2, backgroundColor: brand.main },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          fontWeight: 600,
          "&.Mui-selected": { color: brand.dark },
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
        root: { backgroundColor: "rgba(23, 107, 82, 0.08)" },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          transition: `transform ${motion.standard}, background-color 160ms ease`,
          "&:active": { transform: "scale(0.98)" },
          "&.Mui-focusVisible": { outline: `2px solid ${brand.main}`, outlineOffset: 2 },
          "@media (prefers-reduced-motion: reduce)": reducedMotion,
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          transition: `background-color 160ms ease`,
          "&.Mui-focusVisible": { outline: `2px solid ${brand.main}`, outlineOffset: -2 },
        },
      },
    },
  },
});
