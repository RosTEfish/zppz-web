export const DOMAIN_TOPICS = [
  "submission.job",
  "contest.updated",
  "draw.reveal",
  "guess.state",
  "swap.updated",
] as const;

export type DomainTopic = (typeof DOMAIN_TOPICS)[number];

export type DomainJobPayload = {
  id: string;
  status: string;
  stage: string;
};

export type DomainEvent = {
  id: number;
  topic: string;
  scope: string;
  subject_user_id: number | null;
  resources: string[];
  payload: {
    jobs?: DomainJobPayload[];
    sources?: string[];
  };
  created_at?: string;
};

const RESOURCE_HEADS: Record<string, readonly string[]> = {
  submissions: ["submissions"],
  contest: ["bootstrap", "event", "event-phases", "guess-availability"],
  guess: ["guess", "guess-availability"],
  draws: ["draws"],
  swap: ["swap"],
  admin: ["admin"],
};

const TERMINAL_JOB_STATUSES = new Set(["completed", "failed", "cancelled"]);

export const WATCHED_HEADS = [
  "submissions",
  "draws",
  "guess",
  "swap",
  "bootstrap",
  "event",
  "event-phases",
  "guess-availability",
  "admin",
] as const;

export function parseDomainEvent(raw: string): DomainEvent | null {
  try {
    const value = JSON.parse(raw) as Partial<DomainEvent>;
    if (!value || typeof value.id !== "number" || typeof value.topic !== "string" || !Array.isArray(value.resources)) {
      return null;
    }
    const payload = value.payload && typeof value.payload === "object" ? value.payload : {};
    return {
      id: value.id,
      topic: value.topic,
      scope: typeof value.scope === "string" ? value.scope : "",
      subject_user_id: typeof value.subject_user_id === "number" ? value.subject_user_id : null,
      resources: value.resources.filter((item): item is string => typeof item === "string"),
      payload,
      created_at: typeof value.created_at === "string" ? value.created_at : undefined,
    };
  } catch {
    return null;
  }
}

export function isWatchedKey(key: unknown): boolean {
  return Array.isArray(key) && WATCHED_HEADS.some((head) => head === key[0]);
}

function headOf(key: unknown): string | null {
  if (!Array.isArray(key) || key.length === 0) return null;
  return String(key[0]);
}

function jobIsTerminal(event: DomainEvent): boolean {
  return (event.payload.jobs ?? []).some((job) => TERMINAL_JOB_STATUSES.has(job.status));
}

export function shouldRevalidateKey(key: unknown, event: DomainEvent): boolean {
  const head = headOf(key);
  if (head === null || !Array.isArray(key)) return false;
  if (event.topic === "submission.job") {
    if (head === "submissions") {
      const kind = String(key[1] ?? "");
      if (kind === "jobs" || kind === "admin-jobs") return true;
      return jobIsTerminal(event);
    }
    return jobIsTerminal(event) && (head === "bootstrap" || head === "guess-availability" || head === "admin");
  }
  return event.resources.some((resource) => (RESOURCE_HEADS[resource] ?? []).includes(head));
}

export function streamUrl(lastId: number): string {
  return lastId > 0 ? `/api/v1/events?after=${lastId}` : "/api/v1/events";
}
