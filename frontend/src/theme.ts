import { createTheme } from "@mui/material/styles";

const shadow1 = "0 1px 2px rgba(23,107,82,0.05), 0 1px 3px rgba(23,107,82,0.08)";
const shadow2 = "0 1px 2px rgba(23,107,82,0.06), 0 2px 4px rgba(23,107,82,0.10)";
const shadow3 = "0 1px 3px rgba(23,107,82,0.07), 0 3px 6px rgba(23,107,82,0.12)";
const shadow4 = "0 2px 4px rgba(23,107,82,0.08), 0 4px 8px rgba(23,107,82,0.14)";
const shadow8 = "0 4px 8px rgba(23,107,82,0.10), 0 8px 16px rgba(23,107,82,0.16)";

const base = createTheme();
const greenShadows = base.shadows.map((s, i) => {
  if (i === 1) return shadow1;
  if (i === 2) return shadow2;
  if (i === 3) return shadow3;
  if (i === 4) return shadow4;
  if (i === 8) return shadow8;
  return s;
});

export const theme = createTheme({
  cssVariables: true,
  palette: {
    mode: "light",
    primary: { main: "#176B52", dark: "#0C4A39", light: "#D5F2E5", contrastText: "#FFFFFF" },
    secondary: { main: "#315DA8", dark: "#1E3F78", light: "#D8E6FF" },
    warning: { main: "#B76B00", light: "#FFE2AE" },
    error: { main: "#B3261E", light: "#FFDAD6" },
    success: { main: "#287A4B", light: "#C7F1D8" },
    background: { default: "#F7F9F7", paper: "#FFFFFF" },
    text: { primary: "#18201D", secondary: "#56605B" },
    divider: "#DCE3DF",
  },
  shape: { borderRadius: 8 },
  shadows: greenShadows as typeof base.shadows,
  typography: {
    fontFamily: '"Outfit", "Noto Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif',
    h1: { fontSize: "2rem", fontWeight: 900, lineHeight: 1.2 },
    h2: { fontSize: "1.5rem", fontWeight: 800, lineHeight: 1.3 },
    h3: { fontSize: "1.125rem", fontWeight: 700, lineHeight: 1.35 },
    button: { fontWeight: 650, textTransform: "none", letterSpacing: 0, fontVariantNumeric: "tabular-nums" },
    body1: { letterSpacing: 0, fontVariantNumeric: "tabular-nums" },
    body2: { letterSpacing: 0, fontVariantNumeric: "tabular-nums" },
    caption: { fontVariantNumeric: "tabular-nums" },
    overline: { fontVariantNumeric: "tabular-nums" },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          minHeight: 40,
          borderRadius: 8,
          transition: "transform 120ms ease, background-color 160ms ease, box-shadow 160ms ease",
          "&:active": { transform: "scale(0.98)" },
          "@media (prefers-reduced-motion: reduce)": {
            transition: "none",
            "&:active": { transform: "none" },
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          boxShadow: shadow1,
          transition: "transform 160ms ease, box-shadow 160ms ease",
          "&:hover": {
            transform: "translateY(-2px)",
            boxShadow: shadow4,
          },
          "@media (prefers-reduced-motion: reduce)": {
            transition: "none",
            "&:hover": { transform: "none" },
          },
        },
      },
    },
    MuiDialog: { styleOverrides: { paper: { borderRadius: 8 } } },
    MuiChip: { styleOverrides: { root: { borderRadius: 6, fontWeight: 600 } } },
    MuiTableCell: { styleOverrides: { head: { fontWeight: 700, color: "#39423E", background: "#F1F5F2" } } },
    MuiIconButton: {
      styleOverrides: {
        root: {
          transition: "transform 120ms ease, background-color 160ms ease, box-shadow 160ms ease",
          "&:active": { transform: "scale(0.98)" },
          "@media (prefers-reduced-motion: reduce)": {
            transition: "none",
            "&:active": { transform: "none" },
          },
        },
      },
    },
  },
});
