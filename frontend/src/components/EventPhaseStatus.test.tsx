import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { EventPhasesRead } from "../api/v1";
import { formatCountdown, PHASE_LABELS, PhaseHeadline } from "./EventPhaseStatus";

const capabilities = {
  song_pool_edit: false,
  submission: false,
  swap: false,
  normal_submission_public: true,
  author_guess: true,
  quality_vote: true,
};

describe("event phase status", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("formats a stable day and time countdown", () => {
    expect(formatCountdown("2026-01-02T02:03:04Z", Date.parse("2026-01-01T00:00:00Z"))).toBe("1 天 02:03:04");
  });

  it("uses API server time to correct the client clock", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    const phases: EventPhasesRead = {
      phase_mode: "auto",
      active_phase: "guess",
      server_time: "2026-01-01T01:00:00Z",
      next_transition_at: "2026-01-01T02:00:00Z",
      phases: [],
      capabilities,
    };

    render(<PhaseHeadline phases={phases} />);

    expect(screen.getByText("01:00:00")).toBeInTheDocument();
    expect(screen.getByText("01:00:00").closest("[aria-live='polite']")).toBeInTheDocument();
  });

  it("shows a non-phase read-only status after the guess deadline", () => {
    const phases: EventPhasesRead = {
      phase_mode: "auto",
      active_phase: null,
      server_time: "2026-01-02T03:00:00Z",
      next_transition_at: null,
      phases: [
        {
          phase: "guess",
          starts_at: "2026-01-02T01:00:00Z",
          ends_at: "2026-01-02T02:00:00Z",
        },
      ],
      capabilities: {
        ...capabilities,
        author_guess: false,
        quality_vote: false,
      },
    };

    render(<PhaseHeadline phases={phases} />);

    expect(screen.getByText("猜谱已截止")).toBeInTheDocument();
    expect(Object.keys(PHASE_LABELS)).toEqual([
      "registration",
      "submission_1",
      "submission_2",
      "guess",
    ]);
  });
});
