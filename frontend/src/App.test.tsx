import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    expect(screen.getByRole("link", { name: "查看规则" })).toHaveAttribute("href", "/api/v1/assets/rule/view");
    expect(screen.getByRole("link", { name: "往期 Ban 曲列表" })).toHaveAttribute("href", "/api/v1/assets/banlist/download");
    expect(screen.getByRole("link", { name: "京ICP备2026012070号-1" })).toHaveAttribute("href", "https://beian.miit.gov.cn/");
    expect(screen.getByRole("link", { name: /京公网安备11010802047846号/ })).toHaveAttribute("href", "https://beian.mps.gov.cn/#/query/webSearch?code=11010802047846");
    expect(screen.getByAltText("公安备案图标")).toHaveAttribute("src", "/beian.png");
  });

  it("labels chart activity as views instead of plays", async () => {
    window.history.pushState({}, "", "/guess");
    render(<App />);
    expect(await screen.findByText("测试谱面")).toBeInTheDocument();
    expect(screen.getByText("查看 7")).toBeInTheDocument();
    expect(screen.queryByText(/播放/)).not.toBeInTheDocument();
  });

  it("submits the administrator role from user management", async () => {
    window.history.pushState({}, "", "/admin/users");
    const admin = {
      id: 1,
      user_code: "admin",
      qq_id: "1",
      identity: "participant",
      display_name: "赛事管理员",
      roles: ["admin", "pool_editor", "participant"],
      is_admin: true,
      is_pool_editor: true,
      is_active: true,
    };
    const member = {
      id: 2,
      user_code: "member",
      qq_id: "2",
      identity: "participant",
      display_name: "参赛者",
      roles: ["participant"],
      is_admin: false,
      is_pool_editor: false,
      is_active: true,
    };
    const updateBodies: Array<{ roles: string[] }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/auth/me")) return json({ user: admin });
      if (path.endsWith("/events/current")) return json(eventPayload);
      if (path.endsWith("/admin/users") && (init?.method || "GET") === "GET") return json([member]);
      if (path.endsWith("/admin/users/2") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as { roles: string[] };
        updateBodies.push(body);
        return json({ ...member, roles: body.roles, is_admin: body.roles.includes("admin") });
      }
      return json({ detail: "not found" }, 404);
    }));

    render(<App />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "管理员" }));

    await waitFor(() => expect(updateBodies).toHaveLength(1));
    expect(updateBodies[0].roles).toContain("admin");
  });
});
