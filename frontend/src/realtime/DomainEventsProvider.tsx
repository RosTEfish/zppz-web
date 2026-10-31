import { type ReactNode, useEffect } from "react";
import { useSWRConfig } from "swr";
import {
  DOMAIN_TOPICS,
  isWatchedKey,
  parseDomainEvent,
  shouldRevalidateKey,
  streamUrl,
} from "./domainEvents";

const SAFETY_TICK_MS = 15_000;
const HEALTHY_BOOTSTRAP_TICKS = 4;
const DEDUPE_FOLLOW_UP_MS = 2_100;

export function DomainEventsProvider({ children }: { children: ReactNode }) {
  const { mutate } = useSWRConfig();

  useEffect(() => {
    if (typeof EventSource === "undefined") return undefined;
    let stopped = false;
    let source: EventSource | null = null;
    let reconnectTimer = 0;
    let attempt = 0;
    let lastId = 0;
    let healthy = false;
    let ticks = 0;
    const followUps = new Set<number>();

    const revalidate = (filter: (key: unknown) => boolean) => {
      void mutate(filter, undefined, { revalidate: true });
      const followUp = window.setTimeout(() => {
        followUps.delete(followUp);
        if (!stopped) void mutate(filter, undefined, { revalidate: true });
      }, DEDUPE_FOLLOW_UP_MS);
      followUps.add(followUp);
    };

    const connect = () => {
      if (stopped || document.visibilityState === "hidden") return;
      window.clearTimeout(reconnectTimer);
      const next = new EventSource(streamUrl(lastId));
      source = next;
      let handledError = false;
      next.onopen = () => {
        attempt = 0;
        healthy = true;
      };
      const onEvent = (message: Event) => {
        const data = "data" in message ? String(message.data ?? "") : "";
        const event = parseDomainEvent(data);
        if (!event) return;
        lastId = Math.max(lastId, event.id);
        revalidate((key) => shouldRevalidateKey(key, event));
      };
      for (const topic of DOMAIN_TOPICS) next.addEventListener(topic, onEvent);
      next.onerror = () => {
        if (handledError) return;
        handledError = true;
        healthy = false;
        next.close();
        if (source === next) source = null;
        if (stopped || document.visibilityState === "hidden") return;
        const delay = Math.min(15_000, 1000 * 2 ** attempt);
        attempt += 1;
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        window.clearTimeout(reconnectTimer);
        source?.close();
        source = null;
        healthy = false;
        return;
      }
      connect();
    };

    connect();
    document.addEventListener("visibilitychange", onVisibility);
    const safetyTimer = window.setInterval(() => {
      if (stopped || document.visibilityState !== "visible") return;
      ticks += 1;
      if (!healthy) {
        revalidate(isWatchedKey);
        return;
      }
      if (ticks % HEALTHY_BOOTSTRAP_TICKS === 0) {
        revalidate((key) => Array.isArray(key) && key[0] === "bootstrap");
      }
    }, SAFETY_TICK_MS);

    return () => {
      stopped = true;
      window.clearTimeout(reconnectTimer);
      window.clearInterval(safetyTimer);
      for (const followUp of followUps) window.clearTimeout(followUp);
      document.removeEventListener("visibilitychange", onVisibility);
      source?.close();
    };
  }, [mutate]);

  return children;
}
