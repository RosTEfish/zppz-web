import { createContext, type ReactNode, useCallback, useContext, useMemo } from "react";
import { api, EventPhasesRead, EventRead, type BackgroundAssetRead } from "../api/v1";
import { useBootstrap } from "./BootstrapContext";

interface ConfigContextType {
  event: EventRead | null;
  phases: EventPhasesRead | null;
  guessGameAvailable: boolean;
  backgrounds: BackgroundAssetRead[];
  refreshConfig: () => Promise<void>;
  refreshGuessAvailability: () => Promise<void>;
  loading: boolean;
}

const ConfigContext = createContext<ConfigContextType | null>(null);

export function ConfigProvider({ children }: { children: ReactNode }) {
  const { data: bootstrap, isLoading: bootstrapLoading, mutate: mutateBootstrap } = useBootstrap();
  const event = bootstrap?.event ?? null;
  const phases = bootstrap?.phases ?? null;
  const guessGameAvailable = bootstrap?.guess_availability?.available ?? false;
  const backgrounds = bootstrap?.backgrounds ?? [];
  const loading = bootstrapLoading;

  const refreshGuessAvailability = useCallback(async () => {
    const next = await api.guessAvailability({ cache: "no-store" });
    await mutateBootstrap((current) => (current ? { ...current, guess_availability: next } : current), { revalidate: false });
  }, [mutateBootstrap]);

  const refreshConfig = useCallback(async () => {
    const next = await api.bootstrap({ cache: "no-store" });
    await mutateBootstrap(next, { revalidate: false });
  }, [mutateBootstrap]);

  const value = useMemo(
    () => ({ event, phases, guessGameAvailable, backgrounds, refreshConfig, refreshGuessAvailability, loading }),
    [backgrounds, event, phases, guessGameAvailable, loading, refreshConfig, refreshGuessAvailability],
  );
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error("useConfig must be used within ConfigProvider");
  return ctx;
}
