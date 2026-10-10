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

export function EventThemeProvider({ children }: { children: ReactNode }) {
  const backgrounds = useEventBackgrounds();
  const sourceUrl = backgrounds.hero?.url ?? backgrounds.brand?.url ?? null;
  const [palette, setPalette] = useState<EventPalette>(defaultEventPalette);
  const [extracting, setExtracting] = useState(false);

  useEffect(() => {
    if (!sourceUrl) {
      setPalette(defaultEventPalette);
      setExtracting(false);
      return;
    }
    let cancelled = false;
    setExtracting(true);
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
    return () => {
      cancelled = true;
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
