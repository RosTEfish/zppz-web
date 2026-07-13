import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    announcement_text: "",
    registration_deadline: null,
    submission_deadline: null,
    guess_game_open_at: null,
    submissions_open: false,
    guess_game_visible: true,
  },
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("Material application shell", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/");
    window.localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/bootstrap")) return json({ event: eventPayload, user: null });
      if (path.endsWith("/auth/me")) return json({ detail: "未登录" }, 401);
      if (path.endsWith("/events/current")) return json(eventPayload);
      if (path.endsWith("/guess-game/designer-guesses")) return json({ can_guess: false, candidates: [], states: [{ chart_id: 7, guessed_user_id: null }, { chart_id: 8, guessed_user_id: null }] });
      if (path.endsWith("/guess-game/charts")) return json([
        {
          id: 7,
          title: "测试谱面",
          author: "曲师",
          designer: "测试谱师",
          level: "13+",
          lane: "normal",
          guess_group_key: "test",
          source_submission_type: "normal",
          track_duration_seconds: 240,
          is_long_track: false,
          cover_path: "",
          is_self_selected: true,
          plays: 7,
          created_at: "2026-07-03T00:00:00",
          love_votes: 2,
          funny_votes: 1,
          my_votes: [],
        },
        {
          id: 8,
          title: "J谱面",
          author: "另一曲师",
          designer: "J谱师",
          level: "14",
          lane: "j",
          guess_group_key: "j-test",
          source_submission_type: "j",
          track_duration_seconds: 240.001,
          is_long_track: true,
          cover_path: "",
          is_self_selected: false,
          plays: 3,
          created_at: "2026-07-03T00:00:00",
          love_votes: 1,
          funny_votes: 0,
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
    expect(await screen.findByText("当前未开放")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看规则" })).toHaveAttribute("href", "/api/v1/assets/rule/view");
    expect(screen.getByRole("link", { name: "往期 Ban 曲列表" })).toHaveAttribute("href", "/api/v1/assets/banlist/download");
    expect(screen.getByRole("link", { name: "京ICP备2026012070号-1" })).toHaveAttribute("href", "https://beian.miit.gov.cn/");
    expect(screen.getByRole("link", { name: /京公网安备11010802047846号/ })).toHaveAttribute("href", "https://beian.mps.gov.cn/#/query/webSearch?code=11010802047846");
    expect(screen.getByAltText("公安备案图标").getAttribute("src")).toContain("beian");
  });

  it("hides the guess entry from regular users when disabled", async () => {
    const hiddenEvent = { ...eventPayload, settings: { ...eventPayload.settings, guess_game_visible: false } };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/bootstrap")) return json({ event: hiddenEvent, user: null });
      return json({ detail: "not found" }, 404);
    }));

    render(<App />);
    expect(await screen.findAllByText("测试赛事")).not.toHaveLength(0);
    expect(screen.queryByRole("link", { name: "猜谱" })).not.toBeInTheDocument();
  });

  it("renders markdown announcements and reopens after content changes", async () => {
    let currentEvent = {
      ...eventPayload,
      settings: {
        ...eventPayload.settings,
        announcement_text: "## 重要公告\n\n- 第一项\n- 第二项\n\n[查看规则](https://example.com/rules)",
      },
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/bootstrap")) return json({ event: currentEvent, user: null });
      return json({ detail: "not found" }, 404);
    }));

    render(<App />);
    const firstDialog = await screen.findByRole("dialog", { name: "赛事公告" });
    expect(within(firstDialog).getByRole("heading", { name: "重要公告" })).toBeInTheDocument();
    expect(within(firstDialog).getAllByRole("listitem")).toHaveLength(2);
    expect(within(firstDialog).getByRole("link", { name: "查看规则" })).toHaveAttribute("target", "_blank");
    fireEvent.click(within(firstDialog).getByRole("button", { name: "我知道了" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "赛事公告" })).not.toBeInTheDocument());

    cleanup();
    render(<App />);
    expect(await screen.findByRole("heading", { name: "重要公告" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "赛事公告" })).not.toBeInTheDocument();

    cleanup();
    currentEvent = {
      ...currentEvent,
      settings: { ...currentEvent.settings, announcement_text: "## 重要公告\n\n公告已更新。" },
    };
    render(<App />);
    const updatedDialog = await screen.findByRole("dialog", { name: "赛事公告" });
    expect(within(updatedDialog).getByText("公告已更新。")).toBeInTheDocument();
  });

  it("labels chart activity as views instead of plays", async () => {
    window.history.pushState({}, "", "/guess");
    render(<App />);
    expect(await screen.findByText("测试谱面")).toBeInTheDocument();
    expect(screen.getByText("查看 7")).toBeInTheDocument();
    expect(screen.queryByText(/播放/)).not.toBeInTheDocument();
  });

  it("filters guess charts and safely renders public chart metadata", async () => {
    window.history.pushState({}, "", "/guess");
    render(<App />);

    expect(await screen.findByText("测试谱面")).toBeInTheDocument();
    expect(screen.getByText("J谱面")).toBeInTheDocument();
    expect(screen.getByText(/测试谱师/)).toBeInTheDocument();
    expect(screen.getByText(/J谱师/)).toBeInTheDocument();
    expect(screen.getAllByText("自选").length).toBeGreaterThan(0);
    expect(screen.getAllByText("非自选").length).toBeGreaterThan(0);
    expect(screen.getAllByText("普通谱").length).toBeGreaterThan(0);
    expect(screen.getByText("J谱面").closest("[data-lane='j']")).toBeInTheDocument();
    expect(screen.getByText("测试谱面").closest("[data-level-slot]")).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("音频时长 4:00")).toHaveLength(2);
    expect(screen.getByLabelText("Long Track，音频超过 4 分钟")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "J" }));
    expect(screen.queryByText("测试谱面")).not.toBeInTheDocument();
    expect(screen.getByText("J谱面")).toBeInTheDocument();
    expect(screen.getByText("显示 1 / 共 2 张谱面")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "自选" }));
    expect(screen.getByText("没有符合当前筛选条件的谱面")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "清除筛选" })[0]);

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "难度" }));
    const options = await screen.findAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["全部难度", "13+", "14"]);
    fireEvent.click(screen.getByRole("option", { name: "13+" }));
    expect(screen.getByText("测试谱面")).toBeInTheDocument();
    expect(screen.queryByText("J谱面")).not.toBeInTheDocument();
  });

  it("clears batch selection when filters change", async () => {
    window.history.pushState({}, "", "/guess");
    render(<App />);

    expect(await screen.findByText("测试谱面")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "批量选择" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 测试谱面" }));
    expect(screen.getByRole("button", { name: "下载 1 项" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "J" }));
    expect(screen.getByRole("button", { name: "下载 0 项" })).toBeDisabled();
  });

  it("warns when the current user has not filled their song pool", async () => {
    window.history.pushState({}, "", "/songs");
    const participant = {
      id: 9,
      user_code: "player",
      qq_id: "9",
      identity: "participant",
      display_name: "参赛者",
      roles: ["participant"],
      is_admin: false,
      is_pool_editor: false,
      is_active: true,
    };
    const songs = [1, 2].map((id) => ({ id, song_name: `曲目 ${id}`, artist: "曲师", song_type: "A", remark: "", submitter: participant, created_at: "2026-07-04T00:00:00" }));
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/bootstrap")) return json({ event: eventPayload, user: participant });
      if (path.endsWith("/song-pool/me")) return json(songs);
      return json({ detail: "not found" }, 404);
    }));

    render(<App />);
    expect(await screen.findByRole("dialog", { name: "曲池尚未投递完成" })).toBeInTheDocument();
    expect(screen.getAllByText(/还需提交 3 首/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "继续投曲" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "曲池尚未投递完成" })).not.toBeInTheDocument());
    expect(screen.getByText(/曲池尚未投满/)).toBeInTheDocument();
  });

  it("saves a designer guess from a chart card and syncs its difficulty group", async () => {
    window.history.pushState({}, "", "/guess");
    const participant = {
      id: 9,
      user_code: "player",
      qq_id: "9",
      identity: "participant",
      display_name: "参赛者",
      roles: ["participant"],
      is_admin: false,
      is_pool_editor: false,
      is_active: true,
    };
    const chart = (id: number, level: string, slot: string) => ({ id, title: "同曲", author: "曲师", designer: "", level, lane: "normal", guess_group_key: "same-song", source_submission_type: "normal", source_submission_id: 1, source_level_slot: slot, cover_path: "", storage_path: "", is_self_selected: true, plays: 0, created_at: "2026-07-04T00:00:00", love_votes: 0, funny_votes: 0, my_votes: [] });
    const savedBodies: Array<{ guessed_user_id: number }> = [];
    let overviewCalls = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/bootstrap")) return json({ event: eventPayload, user: participant });
      if (path.endsWith("/guess-game/charts")) return json([chart(21, "13", "4"), chart(22, "14", "5")]);
      if (path.endsWith("/guess-game/designer-guesses")) {
        overviewCalls += 1;
        return json({ can_guess: true, candidates: [{ user_id: 5, display_id: "P01" }], states: [{ chart_id: 21, guessed_user_id: null }, { chart_id: 22, guessed_user_id: null }] });
      }
      if (path.endsWith("/guess-game/charts/21/designer-guess") && init?.method === "PUT") {
        savedBodies.push(JSON.parse(String(init.body)) as { guessed_user_id: number });
        return json({ message: "已保存谱师猜测" });
      }
      return json({ detail: "not found" }, 404);
    }));

    render(<App />);
    const controls = await screen.findAllByRole("combobox", { name: "谱师猜测 同曲" });
    expect(controls).toHaveLength(2);
    fireEvent.mouseDown(controls[0]);
    fireEvent.click(await screen.findByRole("option", { name: "P01" }));
    await waitFor(() => expect(savedBodies).toEqual([{ guessed_user_id: 5 }]));
    await waitFor(() => expect(screen.getAllByRole("combobox", { name: "谱师猜测 同曲" }).every((control) => control.textContent?.includes("P01"))).toBe(true));
    expect(overviewCalls).toBe(1);
  });

  it("allows only one staged J track submission", async () => {
    window.history.pushState({}, "", "/submissions");
    const participant = {
      id: 9,
      user_code: "player",
      qq_id: "9",
      identity: "participant",
      display_name: "参赛者",
      roles: ["participant"],
      is_admin: false,
      is_pool_editor: false,
      is_active: true,
    };
    const song = (id: number, name: string) => ({
      id,
      song_name: name,
      artist: "曲师",
      song_type: "A",
      remark: "",
      submitter: participant,
      created_at: "2026-07-04T00:00:00",
    });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/bootstrap")) return json({ event: eventPayload, user: participant });
      if (path.endsWith("/submissions/targets")) return json({
        is_open: true,
        targets: [
          {
            song: song(1, "第一首"),
            source_kind: "self",
            submission: {
              id: 11,
              file_name: "first.zip",
              file_size: 100,
              review_status: "approved",
              review_note: "",
              source_kind: "self",
              track: "j",
              source_song: song(1, "第一首"),
              user: participant,
              created_at: "2026-07-04T00:00:00",
            },
          },
          { song: song(2, "第二首"), source_kind: "assigned", submission: null },
        ],
      });
      return json({ detail: "not found" }, 404);
    }));

    render(<App />);
    expect(await screen.findByText("第一首")).toBeInTheDocument();
    const jButtons = await screen.findAllByRole("button", { name: "J赛道" });
    expect(jButtons[0]).toHaveAttribute("aria-pressed", "true");
    expect(jButtons[1]).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(jButtons[1]);
    expect(jButtons[0]).toHaveAttribute("aria-pressed", "false");
    expect(jButtons[1]).toHaveAttribute("aria-pressed", "true");
  });

  it("persists a submitted J track switch without replacing the file", async () => {
    window.history.pushState({}, "", "/submissions");
    const participant = {
      id: 9,
      user_code: "player",
      qq_id: "9",
      identity: "participant",
      display_name: "参赛者",
      roles: ["participant"],
      is_admin: false,
      is_pool_editor: false,
      is_active: true,
    };
    const song = (id: number, name: string) => ({
      id,
      song_name: name,
      artist: "曲师",
      song_type: "A",
      remark: "",
      submitter: participant,
      created_at: "2026-07-04T00:00:00",
    });
    let tracks: Array<"normal" | "j"> = ["j", "normal"];
    const patchBodies: Array<{ track: string }> = [];
    const submission = (id: number, songId: number, track: "normal" | "j") => ({
      id,
      file_name: `${songId}.zip`,
      file_size: 100,
      review_status: "approved",
      review_note: "",
      source_kind: songId === 1 ? "self" : "assigned",
      track,
      source_song: song(songId, `第${songId}首`),
      user: participant,
      created_at: "2026-07-04T00:00:00",
    });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/bootstrap")) return json({ event: { ...eventPayload, settings: { ...eventPayload.settings, submissions_open: true } }, user: participant });
      if (path.endsWith("/submissions/targets")) return json({
        is_open: true,
        targets: [
          { song: song(1, "第一首"), source_kind: "self", submission: submission(11, 1, tracks[0]) },
          { song: song(2, "第二首"), source_kind: "assigned", submission: submission(12, 2, tracks[1]) },
        ],
      });
      if (path.endsWith("/submissions/12/track") && init?.method === "PATCH") {
        const body = JSON.parse(String(init.body)) as { track: "normal" | "j" };
        patchBodies.push(body);
        tracks = ["normal", body.track];
        return json(submission(12, 2, body.track));
      }
      return json({ detail: "not found" }, 404);
    }));

    render(<App />);
    const jButtons = await screen.findAllByRole("button", { name: "J赛道" });
    fireEvent.click(jButtons[1]);
    expect(jButtons[0]).toHaveAttribute("aria-pressed", "false");
    expect(jButtons[1]).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(patchBodies).toEqual([{ track: "j" }]));
    await waitFor(() => expect(screen.getAllByRole("button", { name: "J赛道" })[1]).toHaveAttribute("aria-pressed", "true"));
  });

  it("lets administrators control guess entry visibility", async () => {
    window.history.pushState({}, "", "/admin/settings");
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
    let currentEvent = { ...eventPayload, settings: { ...eventPayload.settings, guess_game_visible: false } };
    const updates: Array<{ guess_game_visible: boolean }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/bootstrap")) return json({ event: currentEvent, user: admin });
      if (path.endsWith("/admin/events/current") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as typeof eventPayload.settings & { name: string };
        updates.push({ guess_game_visible: body.guess_game_visible });
        currentEvent = { ...currentEvent, name: body.name, settings: { ...currentEvent.settings, ...body } };
        return json(currentEvent);
      }
      if (path.endsWith("/events/current")) return json(currentEvent);
      return json({ detail: "not found" }, 404);
    }));

    render(<App />);
    expect(await screen.findByRole("link", { name: "猜谱" })).toBeInTheDocument();
    const visibility = await screen.findByRole("switch", { name: "向用户显示猜谱入口" });
    expect(visibility).not.toBeChecked();
    fireEvent.click(visibility);
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
    await waitFor(() => expect(updates).toEqual([{ guess_game_visible: true }]));
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
      if (path.endsWith("/bootstrap")) return json({ event: eventPayload, user: admin });
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
