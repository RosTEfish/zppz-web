import React, { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, EventRead } from "../api/v1";

interface AppConfig {
  current_event: string;
  event_switched_at?: string | null;
  role_song_limits: { participant: number; audience: number };
  allow_duplicate_registration?: boolean;
  allow_redraw?: boolean;
  draw_songs_per_participant: number;
  true_love_vote_limit?: number;
  funny_vote_limit?: number;
  guess_game_open_at?: string | null;
  announcement_text: string;
  max_upload_mb?: number;
  allowed_extensions?: string[];
  registration_deadline?: string | null;
  submission_deadline?: string | null;
  submissions_open: boolean;
  guess_game_visible: boolean;
}

interface ConfigContextType {
  event: EventRead | null;
  config: AppConfig | null;
  refreshConfig: () => Promise<void>;
  loading: boolean;
}

const ConfigContext = createContext<ConfigContextType | null>(null);

function toConfig(event: EventRead | null): AppConfig | null {
  if (!event) return null;
  return {
    current_event: event.name,
    role_song_limits: {
      participant: event.settings.participant_song_limit,
      audience: event.settings.audience_song_limit,
    },
    draw_songs_per_participant: event.settings.draw_songs_per_participant,
    true_love_vote_limit: event.settings.true_love_vote_limit,
    funny_vote_limit: event.settings.funny_vote_limit,
    guess_game_open_at: event.settings.guess_game_open_at,
    announcement_text: event.settings.announcement_text,
    registration_deadline: event.settings.registration_deadline,
    submission_deadline: event.settings.submission_deadline,
    submissions_open: event.settings.submissions_open,
    guess_game_visible: event.settings.guess_game_visible,
  };
}

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [event, setEvent] = useState<EventRead | null>(null);
  const [loading, setLoading] = useState(false);
  const inFlightRef = useRef<Promise<void> | null>(null);

  const refreshConfig = useCallback(async () => {
    if (inFlightRef.current) return inFlightRef.current;
    const task = (async () => {
      setLoading(true);
      try {
        setEvent(await api.currentEvent());
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
    void api.bootstrap()
      .then((data) => setEvent(data.event))
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo(() => ({ event, config: toConfig(event), refreshConfig, loading }), [event, loading, refreshConfig]);
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error("useConfig must be used within ConfigProvider");
  return ctx;
}
