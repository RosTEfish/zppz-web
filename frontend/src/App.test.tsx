import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const eventPayload = {
  id: 1,
  name: "测试赛事",
  slug: "test",
  is_current: true,
  settings: {
    participant_song_limit: 5,
    audience_song_limit: 3,
    draw_songs_per_participant: 1,
    true_love_vote_limit: 3,
    funny_vote_limit: 3,
    announcement_text: "公告内容",
    registration_deadline: null,
    submission_deadline: null,
    guess_game_open_at: null,
    submissions_open: false,
  },
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("Material application shell", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/");
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/auth/me")) return json({ detail: "未登录" }, 401);
      if (path.endsWith("/events/current")) return json(eventPayload);
      if (path.endsWith("/guess-game/charts")) return json([
        {
          id: 7,
          title: "测试谱面",
          author: "曲师",
          level: "13+",
          lane: "normal",
          guess_group_key: "test",
          source_submission_type: "normal",
          source_submission_id: 1,
          source_level_slot: "4",
          cover_path: "",
          storage_path: "",
          is_self_selected: true,
          plays: 7,
          created_at: "2026-07-03T00:00:00",
          love_votes: 2,
          funny_votes: 1,
          my_votes: [],
        },
      ]);
      return json({ detail: "not found" }, 404);
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the current event and workflow", async () => {
    render(<App />);
    expect(await screen.findAllByText("测试赛事")).not.toHaveLength(0);
    expect(screen.getByText("公告内容")).toBeInTheDocument();
    expect(screen.getByText("等待开放")).toBeInTheDocument();
  });

  it("labels chart activity as views instead of plays", async () => {
    window.history.pushState({}, "", "/guess");
    render(<App />);
    expect(await screen.findByText("测试谱面")).toBeInTheDocument();
    expect(screen.getByText("查看 7")).toBeInTheDocument();
    expect(screen.queryByText(/播放/)).not.toBeInTheDocument();
  });
});
