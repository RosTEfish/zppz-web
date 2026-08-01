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
  const { data: phases = null, isLoading: phasesLoading, mutate: mutatePhases } = useSWR(queryKeys.phases, () => api.eventPhases().catch(() => null));
  const { data: availability, isLoading: availabilityLoading, mutate: mutateAvailability } = useSWR(queryKeys.guessAvailability, () => api.guessAvailability().catch(() => ({ available: false })));
  const event = bootstrap?.event ?? null;
  const guessGameAvailable = availability?.available ?? false;
  const loading = bootstrapLoading || phasesLoading || availabilityLoading;

  const refreshGuessAvailability = useCallback(async () => {
    await mutateAvailability();
  }, [mutateAvailability]);

  const refreshConfig = useCallback(async () => {
    const freshRequest: RequestInit = { cache: "no-store" };
    const [nextEvent, nextPhases, nextAvailability] = await Promise.all([
      api.currentEvent(freshRequest),
      api.eventPhases(freshRequest).catch(() => null),
      api.guessAvailability(freshRequest).catch(() => ({ available: false })),
    ]);
    await Promise.all([
      mutateBootstrap((current) => current ? { ...current, event: nextEvent } : current, { revalidate: !bootstrap }),
      mutatePhases(nextPhases, { revalidate: false }),
      mutateAvailability(nextAvailability, { revalidate: false }),
    ]);
  }, [bootstrap, mutateAvailability, mutateBootstrap, mutatePhases]);

  const value = useMemo(() => ({ event, phases, guessGameAvailable, refreshConfig, refreshGuessAvailability, loading }), [event, phases, guessGameAvailable, loading, refreshConfig, refreshGuessAvailability]);
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error("useConfig must be used within ConfigProvider");
  return ctx;
}
