import { describe, expect, it } from "vitest";
import { queryKeys } from "../api/queryKeys";
import { isWatchedKey, parseDomainEvent, shouldRevalidateKey, streamUrl, type DomainEvent } from "./domainEvents";

function event(partial: Partial<DomainEvent> & Pick<DomainEvent, "topic" | "resources">): DomainEvent {
  return {
    id: 1,
    scope: "public",
    subject_user_id: null,
    payload: {},
    ...partial,
  };
}

describe("parseDomainEvent", () => {
  it("accepts a domain envelope and rejects malformed frames", () => {
    const parsed = parseDomainEvent(JSON.stringify({
      id: 7,
      topic: "guess.state",
      scope: "public",
      subject_user_id: null,
      resources: ["guess", "contest"],
      payload: { sources: ["GuessChart"] },
      created_at: "2026-10-31T00:00:00Z",
    }));
    expect(parsed?.id).toBe(7);
    expect(parsed?.resources).toEqual(["guess", "contest"]);
    expect(parseDomainEvent("not-json")).toBeNull();
    expect(parseDomainEvent(JSON.stringify({ id: "x" }))).toBeNull();
  });
});

describe("shouldRevalidateKey", () => {
  it("refreshes job lists for in-flight submission jobs and dependent keys only when a job finishes", () => {
    const processing = event({
      topic: "submission.job",
      scope: "user",
      resources: ["submissions"],
      payload: { jobs: [{ id: "job-1", status: "processing", stage: "validating" }] },
    });
    expect(shouldRevalidateKey(queryKeys.submissions.jobs, processing)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.submissions.adminJobs, processing)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.submissions.mine, processing)).toBe(false);
    expect(shouldRevalidateKey(queryKeys.bootstrap, processing)).toBe(false);

    const finished = event({
      topic: "submission.job",
      scope: "user",
      resources: ["submissions"],
      payload: { jobs: [{ id: "job-1", status: "completed", stage: "complete" }] },
    });
    expect(shouldRevalidateKey(queryKeys.submissions.mine, finished)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.submissions.targets, finished)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.submissions.admin("normal", 50, 0), finished)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.bootstrap, finished)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.guessAvailability, finished)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.songs.mine, finished)).toBe(false);
  });

  it("maps contest, draw, guess, and swap events onto the cached SWR keys", () => {
    const contest = event({ topic: "contest.updated", resources: ["contest", "guess", "draws", "swap", "submissions", "admin"] });
    expect(shouldRevalidateKey(queryKeys.bootstrap, contest)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.phases, contest)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.guess.charts, contest)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.draws.mine, contest)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.swap, contest)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.admin.overview, contest)).toBe(true);

    const draw = event({ topic: "draw.reveal", resources: ["draws", "swap", "admin"] });
    expect(shouldRevalidateKey(queryKeys.draws.admin, draw)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.submissions.jobs, draw)).toBe(false);

    const guess = event({ topic: "guess.state", resources: ["guess", "contest", "admin"] });
    expect(shouldRevalidateKey(queryKeys.guess.adminCharts, guess)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.guessAvailability, guess)).toBe(true);

    const swap = event({ topic: "swap.updated", resources: ["swap", "draws"] });
    expect(shouldRevalidateKey(queryKeys.swap, swap)).toBe(true);
    expect(shouldRevalidateKey(queryKeys.draws.stats, swap)).toBe(true);
    expect(isWatchedKey(queryKeys.archive.charts)).toBe(false);
    expect(streamUrl(0)).toBe("/api/v1/events");
    expect(streamUrl(12)).toBe("/api/v1/events?after=12");
  });
});
