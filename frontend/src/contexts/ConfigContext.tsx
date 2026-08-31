import { createContext, type ReactNode, useCallback, useContext, useMemo } from "react";
import useSWR from "swr";
import { api, EventPhasesRead, EventRead } from "../api/v1";
import { queryKeys } from "../api/queryKeys";

interface ConfigContextType {
  event: EventRead | null;
  phases: EventPhasesRead | null;
  guessGameAvailable: boolean;
  refreshConfig: () => Promise<void>;
  refreshGuessAvailability: () => Promise<void>;
  loading: boolean;
}

const ConfigContext = createContext<ConfigContextType | null>(null);

export function ConfigProvider({ children }: { children: ReactNode }) {
  const { data: bootstrap, isLoading: bootstrapLoading, mutate: mutateBootstrap } = useSWR(queryKeys.bootstrap, api.bootstrap);
  const event = bootstrap?.event ?? null;
  const phases = bootstrap?.phases ?? null;
  const guessGameAvailable = bootstrap?.guess_availability?.available ?? false;
  const loading = bootstrapLoading;

  const refreshGuessAvailability = useCallback(async () => {
    const next = await api.guessAvailability({ cache: "no-store" });
    await mutateBootstrap((current) => (current ? { ...current, guess_availability: next } : current), { revalidate: false });
  }, [mutateBootstrap]);

  const refreshConfig = useCallback(async () => {
    const next = await api.bootstrap({ cache: "no-store" });
    await mutateBootstrap(next, { revalidate: false });
  }, [mutateBootstrap]);

  const value = useMemo(() => ({ event, phases, guessGameAvailable, refreshConfig, refreshGuessAvailability, loading }), [event, phases, guessGameAvailable, loading, refreshConfig, refreshGuessAvailability]);
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error("useConfig must be used within ConfigProvider");
  return ctx;
}
