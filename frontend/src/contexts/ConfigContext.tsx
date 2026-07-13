import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, EventPhasesRead, EventRead } from "../api/v1";

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
  const [event, setEvent] = useState<EventRead | null>(null);
  const [phases, setPhases] = useState<EventPhasesRead | null>(null);
  const [guessGameAvailable, setGuessGameAvailable] = useState(false);
  const [loading, setLoading] = useState(false);
  const inFlightRef = useRef<Promise<void> | null>(null);

  const refreshGuessAvailability = useCallback(async () => {
    const availability = await api.guessAvailability().catch(() => ({ available: false }));
    setGuessGameAvailable(availability.available);
  }, []);

  const refreshConfig = useCallback(async () => {
    if (inFlightRef.current) return inFlightRef.current;
    const task = (async () => {
      setLoading(true);
      try {
        const [nextEvent, nextPhases, availability] = await Promise.all([
          api.currentEvent(),
          api.eventPhases().catch(() => null),
          api.guessAvailability().catch(() => ({ available: false })),
        ]);
        setEvent(nextEvent);
        setPhases(nextPhases);
        setGuessGameAvailable(availability.available);
      } finally {
        setLoading(false);
        inFlightRef.current = null;
      }
    })();
    inFlightRef.current = task;
    return task;
  }, []);

  useEffect(() => {
    setLoading(true);
    void Promise.all([
      api.bootstrap(),
      api.eventPhases().catch(() => null),
      api.guessAvailability().catch(() => ({ available: false })),
    ])
      .then(([data, nextPhases, availability]) => {
        setEvent(data.event);
        setPhases(nextPhases);
        setGuessGameAvailable(availability.available);
      })
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo(() => ({ event, phases, guessGameAvailable, refreshConfig, refreshGuessAvailability, loading }), [event, phases, guessGameAvailable, loading, refreshConfig, refreshGuessAvailability]);
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error("useConfig must be used within ConfigProvider");
  return ctx;
}
