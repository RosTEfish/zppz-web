import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { CssBaseline, ThemeProvider } from "@mui/material";
import App from "./App.tsx";
import "./index.css";
import fontsHref from "./fonts.css?url";
import { theme } from "./theme";

// 字体声明表非阻塞加载（性能优化）：media=print 不匹配屏幕故不阻塞渲染，就绪后切回 all 生效
const fontLink = document.createElement("link");
fontLink.rel = "stylesheet";
fontLink.href = fontsHref;
fontLink.media = "print";
fontLink.addEventListener("load", () => {
  fontLink.media = "all";
});
document.head.appendChild(fontLink);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </StrictMode>,
);
