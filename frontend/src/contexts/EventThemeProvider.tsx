import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { ThemeProvider } from "@mui/material";
import { useEventBackgrounds } from "../hooks/useEventBackgrounds";
import { createAppTheme } from "../theme";
import {
  applyPaletteCssVars,
  clearPaletteCssVars,
  defaultEventPalette,
  extractImagePalette,
  type EventPalette,
} from "../utils/extractImagePalette";

interface EventThemeContextValue {
  palette: EventPalette;
  sourceUrl: string | null;
  extracting: boolean;
}

const EventThemeContext = createContext<EventThemeContextValue>({
  palette: defaultEventPalette,
  sourceUrl: null,
  extracting: false,
});

export function useEventTheme() {
  return useContext(EventThemeContext);
}

function preloadImage(url: string, priority: "high" | "low" = "high") {
  const existing = Array.from(document.head.querySelectorAll<HTMLLinkElement>('link[rel="preload"][as="image"]'))
    .find((link) => link.href === new URL(url, window.location.href).href);
  if (existing) return () => {};
  const link = document.createElement("link");
  link.rel = "preload";
  link.as = "image";
  link.href = url;
  if (priority === "high") {
    link.setAttribute("fetchpriority", "high");
  }
  document.head.appendChild(link);
  return () => {
    link.remove();
  };
}

export function EventThemeProvider({ children }: { children: ReactNode }) {
  const backgrounds = useEventBackgrounds();
  const sourceUrl = backgrounds.hero?.url ?? backgrounds.brand?.url ?? null;
  const heroUrl = backgrounds.hero?.url ?? null;
  const heroLargeUrl = backgrounds.heroLarge?.url ?? null;
  const [palette, setPalette] = useState<EventPalette>(defaultEventPalette);
  const [extracting, setExtracting] = useState(false);

  useEffect(() => {
    if (!heroUrl) return;
    const stopHero = preloadImage(heroUrl, "high");
    const stopLarge = heroLargeUrl && heroLargeUrl !== heroUrl ? preloadImage(heroLargeUrl, "high") : () => {};
    return () => {
      stopHero();
      stopLarge();
    };
  }, [heroLargeUrl, heroUrl]);

  useEffect(() => {
    if (!sourceUrl) {
      setPalette(defaultEventPalette);
      setExtracting(false);
      return;
    }
    let cancelled = false;
    setExtracting(true);
    const run = () => {
      void extractImagePalette(sourceUrl)
        .then((next) => {
          if (!cancelled) setPalette(next);
        })
        .catch(() => {
          if (!cancelled) setPalette(defaultEventPalette);
        })
        .finally(() => {
          if (!cancelled) setExtracting(false);
        });
    };
    const idleWindow = window as Window & {
      requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
      cancelIdleCallback?: (handle: number) => void;
    };
    const idleId = idleWindow.requestIdleCallback?.(run, { timeout: 1200 });
    const timeoutId = idleId === undefined ? window.setTimeout(run, 200) : undefined;
    return () => {
      cancelled = true;
      if (idleId !== undefined) idleWindow.cancelIdleCallback?.(idleId);
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [sourceUrl]);

  useEffect(() => {
    applyPaletteCssVars(palette);
    return () => clearPaletteCssVars();
  }, [palette]);

  const theme = useMemo(() => createAppTheme(palette), [palette]);
  const value = useMemo(
    () => ({ palette, sourceUrl, extracting }),
    [palette, sourceUrl, extracting],
  );

  return (
    <EventThemeContext.Provider value={value}>
      <ThemeProvider theme={theme}>{children}</ThemeProvider>
    </EventThemeContext.Provider>
  );
}
