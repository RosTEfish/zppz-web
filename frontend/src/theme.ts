import { createTheme } from "@mui/material/styles";

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
  typography: {
    fontFamily: '"Noto Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif',
    h1: { fontSize: "2rem", fontWeight: 700, lineHeight: 1.2 },
    h2: { fontSize: "1.5rem", fontWeight: 700, lineHeight: 1.3 },
    h3: { fontSize: "1.125rem", fontWeight: 700, lineHeight: 1.35 },
    button: { fontWeight: 650, textTransform: "none", letterSpacing: 0 },
    body1: { letterSpacing: 0 },
    body2: { letterSpacing: 0 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { minHeight: 40, borderRadius: 8 } },
    },
    MuiCard: {
      styleOverrides: { root: { borderRadius: 8, boxShadow: "0 1px 2px rgba(18, 42, 33, 0.08)" } },
    },
    MuiDialog: { styleOverrides: { paper: { borderRadius: 8 } } },
    MuiChip: { styleOverrides: { root: { borderRadius: 6, fontWeight: 600 } } },
    MuiTableCell: { styleOverrides: { head: { fontWeight: 700, color: "#39423E", background: "#F1F5F2" } } },
  },
});
