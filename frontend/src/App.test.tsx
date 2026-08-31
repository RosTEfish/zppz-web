import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { mockApi } from "./testServer";

const eventPayload = {
  id: 1,
  name: "测试赛事",
  slug: "test",
  is_current: true,
  settings: {
    participant_song_limit: 5,
    audience_song_limit: 3,
    draw_songs_per_participant: 1,
    true_love_vote_limit_below_14: 3,
    true_love_vote_limit_at_least_14: 2,
    funny_vote_limit: 3,
    announcement_text: "",
  },
};

const phasesPayload = {
  event_id: 1,
  phase_mode: "auto",
  manual_phase: null,
  active_phase: "registration",
  timezone: "Asia/Shanghai",
  server_time: "2026-07-03T00:00:00",
  next_transition_at: null,
  phases: [],
  phase_snapshots: [],
  capabilities: { song_pool_edit: true, submission: false, swap: false, normal_submission_public: false, author_guess: false, quality_vote: false },
};

function bootstrapPayload(event = eventPayload, user: unknown = null, options: { available?: boolean; phases?: typeof phasesPayload } = {}) {
  return {
    event,
    user,
    phases: options.phases ?? phasesPayload,
    guess_availability: { available: options.available ?? true },
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("Material application shell", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/");
    window.localStorage.clear();
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload());
      if (path.endsWith("/auth/me")) return json({ detail: "未登录" }, 401);
      if (path.endsWith("/events/current")) return json(eventPayload);
      if (path.endsWith("/guess-game/availability")) return json({ available: true });
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
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the current event and workflow", async () => {
    render(<App />);
    expect(await screen.findAllByText("测试赛事", {}, { timeout: 3000 })).not.toHaveLength(0);
    expect(await screen.findByText("当前未开放")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看规则" })).toHaveAttribute("href", "/api/v1/assets/rule/view");
    expect(screen.queryByRole("link", { name: "往期 Ban 曲列表" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "京ICP备2026012070号-1" })).toHaveAttribute("href", "https://beian.miit.gov.cn/");
    expect(screen.getByRole("link", { name: /京公网安备11010802047846号/ })).toHaveAttribute("href", "https://beian.mps.gov.cn/#/query/webSearch?code=11010802047846");
    expect(screen.getByAltText("公安备案图标").getAttribute("src")).toContain("beian");
  });

  it("uses phase capabilities for submission status and keeps allocation read-only", async () => {
    window.history.pushState({}, "", "/draw");
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
    const phases = {
      ...phasesPayload,
      phase_mode: "manual",
      manual_phase: "submission_1",
      active_phase: "submission_1",
      capabilities: { song_pool_edit: false, submission: true, swap: false, normal_submission_public: false, author_guess: false, quality_vote: false },
    };
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, participant, { phases }));
      if (path.endsWith("/draw/results")) return json([]);
      if (path.endsWith("/swap/me")) return json({ is_open: false, active_phase: "submission_1", round: null, assignments: [], last_roll: null });
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect((await screen.findAllByText("投稿开放")).length).toBeGreaterThan(0);
    expect(await screen.findByRole("heading", { name: "我的曲目" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始抽签" })).not.toBeInTheDocument();
  });

  it("hides the guess entry from regular users when no public charts exist", async () => {
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, null, { available: false }));
      return json({ detail: "not found" }, 404);
    });

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
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(currentEvent));
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "查看公告" }));
    const firstDialog = await screen.findByRole("dialog", { name: "赛事公告" });
    expect(within(firstDialog).getByRole("heading", { name: "重要公告" })).toBeInTheDocument();
    expect(within(firstDialog).getAllByRole("listitem")).toHaveLength(2);
    expect(within(firstDialog).getByRole("link", { name: "查看规则" })).toHaveAttribute("target", "_blank");
    fireEvent.click(within(firstDialog).getByRole("button", { name: "我知道了" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "赛事公告" })).not.toBeInTheDocument());

    cleanup();
    render(<App />);
    const readSummary = await screen.findByRole("button", { name: "查看公告" });
    expect(readSummary).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "赛事公告" })).not.toBeInTheDocument();
    fireEvent.click(readSummary);
    const reopenedDialog = await screen.findByRole("dialog", { name: "赛事公告" });
    fireEvent.click(within(reopenedDialog).getByRole("button", { name: "我知道了" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "赛事公告" })).not.toBeInTheDocument());

    cleanup();
    currentEvent = {
      ...currentEvent,
      settings: { ...currentEvent.settings, announcement_text: "## 重要公告\n\n公告已更新。" },
    };
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "查看公告" }));
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

  it("allows comments on a public chart outside the voting phase", async () => {
    window.history.pushState({}, "", "/guess");
    const participant = { id: 9, user_code: "commenter", qq_id: "9", identity: "participant", display_name: "评论用户", roles: ["participant"], is_admin: false, is_pool_editor: false, is_active: true };
    const publicChart = { id: 41, title: "已公开 J 谱", author: "曲师", designer: "谱师", level: "14", lane: "j", guess_group_key: "public-j", source_submission_type: "j", source_submission_id: 41, source_level_slot: "5", cover_path: "", is_self_selected: false, plays: 0, created_at: "2026-07-04T00:00:00", love_votes: 0, funny_votes: 0, my_votes: [], can_vote: false, can_comment: true, can_author_guess: false };
    const submittedComments: string[] = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, participant));
      if (path.endsWith("/event/phases")) return json({ phase_mode: "manual", manual_phase: "registration", active_phase: "registration", phases: [], capabilities: { song_pool_edit: true, submission: false, swap: false, normal_submission_public: false, author_guess: false, quality_vote: false } });
      if (path.endsWith("/guess-game/availability")) return json({ available: true });
      if (path.endsWith("/guess-game/designer-guesses")) return json({ can_guess: false, candidates: [], states: [] });
      if (path.endsWith("/guess-game/vote-quota")) return json({ below_14: { used: 0, limit: 3, remaining: 3 }, at_least_14: { used: 0, limit: 2, remaining: 2 } });
      if (path.endsWith("/guess-game/charts/41/comments")) {
        if (init?.method === "POST") {
          const content = (JSON.parse(String(init.body)) as { content: string }).content;
          submittedComments.push(content);
          return json({ id: 2, content, user: participant, created_at: "2026-07-04T01:00:00" });
        }
        return json([{ id: 1, content: "已有评论", user: participant, created_at: "2026-07-04T00:30:00" }]);
      }
      if (path.endsWith("/guess-game/charts/41")) return json(publicChart);
      if (path.endsWith("/guess-game/charts")) return json([publicChart]);
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    fireEvent.click(await screen.findByText("已公开 J 谱"));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("已有评论")).toBeInTheDocument();
    fireEvent.change(within(dialog).getByRole("textbox", { name: "评论内容" }), { target: { value: "现在就能评论" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));

    await waitFor(() => expect(submittedComments).toEqual(["现在就能评论"]));
    expect(within(dialog).getByText("现在就能评论")).toBeInTheDocument();
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

  it("selects and clears only the charts in the current filtered result", async () => {
    window.history.pushState({}, "", "/guess");
    render(<App />);

    expect(await screen.findByText("测试谱面")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "J" }));
    fireEvent.click(screen.getByRole("button", { name: "批量选择" }));
    fireEvent.click(screen.getByRole("button", { name: "全选当前结果" }));

    expect(screen.getByRole("checkbox", { name: "选择 J谱面" })).toBeChecked();
    expect(screen.getByRole("button", { name: "下载 1 项" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "取消全选" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "取消全选" }));
    expect(screen.getByRole("checkbox", { name: "选择 J谱面" })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "下载 0 项" })).toBeDisabled();
  });

  it("shows feedback while a chart batch download is being prepared", async () => {
    window.history.pushState({}, "", "/guess");
    let resolveMetadata: ((response: Response) => void) | undefined;
    const metadata = new Promise<Response>((resolve) => { resolveMetadata = resolve; });
    mockApi((path) => path.includes("/guess-game/charts/download-metadata") ? metadata : undefined);
    let clickedHref = "";
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      clickedHref = this.getAttribute("href") || "";
    });

    render(<App />);
    expect(await screen.findByText("测试谱面")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "批量选择" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 测试谱面" }));
    fireEvent.click(screen.getByRole("button", { name: "下载 1 项" }));

    expect(screen.getByRole("dialog", { name: "正在准备批量下载" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "正在准备下载文件" })).toBeInTheDocument();
    expect(screen.getByText("正在准备…").closest("button")).toBeDisabled();

    resolveMetadata?.(json({
      download_url: "/api/v1/guess-game/charts/download.zip?ids=7",
      file_name: "guess-charts.zip",
      file_size: 1024,
    }));
    await waitFor(() => expect(clickedHref).toContain("download_token="));
    expect(screen.getByRole("dialog", { name: "正在准备批量下载" })).toBeInTheDocument();
    expect(screen.getByLabelText("选择 测试谱面")).toBeDisabled();
    expect(screen.getByText("全选当前结果").closest("button")).toBeDisabled();

    const token = new URL(clickedHref, window.location.origin).searchParams.get("download_token");
    document.cookie = `zppz_download_${token}=1; Path=/; SameSite=Lax`;
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "正在准备批量下载" })).not.toBeInTheDocument());
    expect(await screen.findByText("下载请求已开始，请查看浏览器下载列表")).toBeInTheDocument();
    expect(clickedHref).toContain("/api/v1/guess-game/charts/download.zip?ids=7&download_token=");
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
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, participant));
      if (path.endsWith("/song-pool/me")) return json(songs);
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByRole("dialog", { name: "曲池尚未投递完成" }, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getAllByText(/还需提交 3 首/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "继续投曲" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "曲池尚未投递完成" })).not.toBeInTheDocument());
    expect(screen.getByText(/曲池尚未投满/)).toBeInTheDocument();
  });

  it("shows guests a non-participating song-pool view", async () => {
    window.history.pushState({}, "", "/songs");
    const guest = {
      id: 10,
      user_code: "guest",
      qq_id: "10",
      identity: "guest",
      display_name: "访客用户",
      roles: ["guest"],
      is_admin: false,
      is_pool_editor: false,
      is_active: true,
    };
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, guest));
      if (path.endsWith("/song-pool/me")) return json([]);
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByText("访客身份不参与投曲", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText(/不需要向曲池投曲/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "添加" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "曲池尚未投递完成" })).not.toBeInTheDocument();
  });

  it("lets users submit a song without choosing a category", async () => {
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
    const songs = Array.from({ length: 5 }, (_, index) => ({
      id: index + 1,
      song_name: `已有曲目 ${index + 1}`,
      artist: "曲师",
      song_type: "A",
      remark: "",
      submitter: participant,
      created_at: "2026-07-04T00:00:00",
    }));
    const savedBodies: Array<Record<string, unknown>> = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, participant));
      if (path.endsWith("/banlist/check")) return json({ status: "clear", matches: [] });
      if (path.endsWith("/song-pool/me")) {
        if (init?.method === "POST") {
          savedBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
          return json({ ...songs[0], id: 6, song_name: "新曲目" });
        }
        return json(songs);
      }
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    const addButton = await screen.findByRole("button", { name: "添加" }, { timeout: 3000 });
    expect(screen.queryByRole("combobox", { name: "分类" })).not.toBeInTheDocument();
    const addForm = addButton.closest("form");
    expect(addForm).not.toBeNull();
    const form = within(addForm as HTMLFormElement);
    fireEvent.change(form.getByRole("textbox", { name: "曲名" }), { target: { value: "新曲目" } });
    fireEvent.change(form.getByRole("textbox", { name: "曲师" }), { target: { value: "新曲师" } });
    await screen.findByText("未发现往届 Ban 记录");
    fireEvent.click(addButton);

    await waitFor(() => expect(savedBodies).toHaveLength(1));
    expect(savedBodies[0]).toEqual({ song_name: "新曲目", artist: "新曲师", remark: "", acknowledge_ban_warning: false });
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
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, participant));
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
    });

    render(<App />);
    const controls = await screen.findAllByRole("combobox", { name: "谱师猜测 同曲" });
    expect(controls).toHaveLength(2);
    expect(screen.getAllByText(/请填写做谱人/)).toHaveLength(2);
    fireEvent.mouseDown(controls[0]);
    fireEvent.click(await screen.findByRole("option", { name: "P01" }));
    await waitFor(() => expect(savedBodies).toEqual([{ guessed_user_id: 5 }]));
    await waitFor(() => expect(screen.getAllByRole("combobox", { name: "谱师猜测 同曲" }).every((control) => control.textContent?.includes("P01"))).toBe(true));
    expect(overviewCalls).toBe(1);
  });

  it("does not request love vote quota for anonymous guess viewers", async () => {
    window.history.pushState({}, "", "/guess");
    let quotaCalls = 0;
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload());
      if (path.endsWith("/guess-game/charts")) return json([]);
      if (path.endsWith("/guess-game/designer-guesses")) return json({ can_guess: false, candidates: [], states: [] });
      if (path.endsWith("/guess-game/vote-quota")) { quotaCalls += 1; return json({ below_14: { used: 0, limit: 3, remaining: 3 }, at_least_14: { used: 0, limit: 2, remaining: 2 } }); }
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByText("暂无谱面")).toBeInTheDocument();
    expect(quotaCalls).toBe(0);
  });

  it("shows split love vote quotas and keeps exhausted selected votes removable", async () => {
    window.history.pushState({}, "", "/guess");
    const participant = { id: 9, user_code: "player", qq_id: "9", identity: "participant", display_name: "参赛者", roles: ["participant"], is_admin: false, is_pool_editor: false, is_active: true };
    const chart = (id: number, title: string, level: string, bucket: "below_14" | "at_least_14", selected: boolean) => ({ id, title, author: "曲师", designer: "谱师", level, lane: "normal", guess_group_key: `group-${id}`, source_submission_type: "normal", source_submission_id: id, source_level_slot: "4", cover_path: "", is_self_selected: false, plays: 0, created_at: "2026-07-04T00:00:00", love_votes: selected ? 1 : 0, funny_votes: 0, my_votes: selected ? ["love"] : [], love_vote_bucket: bucket, can_vote: true, can_comment: false });
    const low = chart(31, "低难度谱面", "13+", "below_14", false);
    const high = chart(32, "高难度谱面", "14", "at_least_14", true);
    let quotaCalls = 0;
    let voteCalls = 0;
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) {
        return json(bootstrapPayload(eventPayload, participant, {
          phases: {
            ...phasesPayload,
            phase_mode: "manual",
            manual_phase: "guess",
            active_phase: "guess",
            capabilities: { song_pool_edit: false, submission: false, swap: false, normal_submission_public: true, author_guess: true, quality_vote: true },
          },
        }));
      }
      if (path.endsWith("/guess-game/charts")) return json([low, high]);
      if (path.endsWith("/guess-game/designer-guesses")) return json({ can_guess: false, candidates: [], states: [] });
      if (path.endsWith("/guess-game/vote-quota")) { quotaCalls += 1; return json({ below_14: { used: 3, limit: 3, remaining: 0 }, at_least_14: { used: 1, limit: 1, remaining: 0 } }); }
      if (path.endsWith("/guess-game/charts/31")) return json({ ...low, plays: 1 });
      if (path.endsWith("/guess-game/charts/32")) return json({ ...high, plays: 1 });
      if (path.endsWith("/guess-game/vote") && init?.method === "DELETE") { voteCalls += 1; return json({ message: "已取消投票", vote_counts: { love: 0, funny: 0 }, my_votes: [], love_vote_quota: { below_14: { used: 3, limit: 3, remaining: 0 }, at_least_14: { used: 0, limit: 1, remaining: 1 } } }); }
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByText("14 以下：已用 3/3，剩余 0")).toBeInTheDocument();
    expect(screen.getByText("14 及以上：已用 1/1，剩余 0")).toBeInTheDocument();

    fireEvent.click(screen.getByText("低难度谱面"));
    let dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "真爱票 0" })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "关闭谱面详情" }));

    fireEvent.click(screen.getByText("高难度谱面"));
    dialog = await screen.findByRole("dialog");
    const removeVote = within(dialog).getByRole("button", { name: "真爱票 1" });
    expect(removeVote).toBeEnabled();
    fireEvent.click(removeVote);
    await waitFor(() => expect(voteCalls).toBe(1));
    expect(await screen.findByText("14 及以上：已用 0/1，剩余 1")).toBeInTheDocument();
    expect(quotaCalls).toBe(1);
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
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, participant));
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
    });

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
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, participant));
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
    });

    render(<App />);
    const jButtons = await screen.findAllByRole("button", { name: "J赛道" });
    fireEvent.click(jButtons[1]);
    expect(jButtons[0]).toHaveAttribute("aria-pressed", "false");
    expect(jButtons[1]).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(patchBodies).toEqual([{ track: "j" }]));
    await waitFor(() => expect(screen.getAllByRole("button", { name: "J赛道" })[1]).toHaveAttribute("aria-pressed", "true"));
  });

  it("lets participants roll any number of songs immediately", async () => {
    window.history.pushState({}, "", "/draw");
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
    const songs = [1, 2, 3, 4].map((id) => ({ id, song_name: `换曲原曲${id}`, artist: "曲师", song_type: "A", remark: "", submitter: participant, created_at: "2026-07-04T00:00:00" }));
    const assignments = songs.map((song, index) => ({ id: 31 + index, assigned_to: participant, song, created_at: "2026-07-04T00:00:00", status: "active", draw_kind: "initial", replaces_assignment_id: null }));
    const phases = { ...phasesPayload, phase_mode: "manual", manual_phase: "submission_2", active_phase: "submission_2", capabilities: { song_pool_edit: false, submission: true, swap: true, normal_submission_public: false, author_guess: false, quality_vote: false } };
    const round = { id: 1, status: "open", round_kind: "continuous", starts_at: "2026-07-04T00:00:00", ends_at: "2026-07-05T00:00:00", roll_count: 0, finalized_at: null };
    let currentSwap = { is_open: true, active_phase: "submission_2" as const, round, assignments: assignments.map((assignment) => ({ ...assignment, selected: false, can_swap: true, has_submission: false })), last_roll: null };
    const rollBodies: { assignment_ids: number[]; mode?: string }[] = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, participant, { phases }));
      if (path.endsWith("/draw/results")) return json(assignments);
      if (path.endsWith("/swap/me/roll") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { assignment_ids: number[]; mode?: string };
        rollBodies.push(body);
        currentSwap = { ...currentSwap, round: { ...round, roll_count: 1 }, last_roll: { id: 41, status: "completed", created_at: "2026-07-04T00:01:00", items: assignments.map((assignment, index) => ({ id: index + 1, position: index, original: assignment, replacement: { ...assignment, id: 51 + index, song: { ...assignment.song, id: 101 + index, song_name: `新曲${index + 1}` }, draw_kind: "swap", replaces_assignment_id: assignment.id } })) } };
        return json(currentSwap);
      }
      if (path.endsWith("/swap/me")) return json(currentSwap);
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "Stage2 投稿与换曲" })).toBeInTheDocument();
    const checkboxes = await screen.findAllByRole("checkbox");
    checkboxes.forEach((checkbox) => fireEvent.click(checkbox));
    fireEvent.click(await screen.findByRole("button", { name: "放回并抽取（4 首）" }));
    await waitFor(() => expect(rollBodies).toEqual([{ assignment_ids: [31, 32, 33, 34], mode: "return_and_draw" }]));
    expect(await screen.findByText("最近一次换曲结果")).toBeInTheDocument();
  });

  it("lets participants return songs without drawing replacements", async () => {
    window.history.pushState({}, "", "/draw");
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
    const songs = [1, 2].map((id) => ({ id, song_name: `待放回曲${id}`, artist: "曲师", song_type: "A", remark: "", submitter: participant, created_at: "2026-07-04T00:00:00" }));
    const assignments = songs.map((song, index) => ({ id: 31 + index, assigned_to: participant, song, created_at: "2026-07-04T00:00:00", status: "active", draw_kind: "initial", replaces_assignment_id: null }));
    const phases = { ...phasesPayload, phase_mode: "manual", manual_phase: "submission_2", active_phase: "submission_2", capabilities: { song_pool_edit: false, submission: true, swap: true, normal_submission_public: false, author_guess: false, quality_vote: false } };
    const round = { id: 1, status: "open", round_kind: "continuous", starts_at: "2026-07-04T00:00:00", ends_at: "2026-07-05T00:00:00", roll_count: 0, finalized_at: null };
    let currentSwap = { is_open: true, active_phase: "submission_2" as const, round, assignments: assignments.map((assignment) => ({ ...assignment, selected: false, can_swap: true, has_submission: false })), last_roll: null };
    const rollBodies: { assignment_ids: number[]; mode?: string }[] = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, participant, { phases }));
      if (path.endsWith("/draw/results")) return json(assignments);
      if (path.endsWith("/swap/me/roll") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { assignment_ids: number[]; mode?: string };
        rollBodies.push(body);
        currentSwap = {
          ...currentSwap,
          assignments: currentSwap.assignments.filter((row) => !body.assignment_ids.includes(row.id)),
          last_roll: {
            id: 42,
            status: "completed",
            created_at: "2026-07-04T00:01:00",
            items: body.assignment_ids.map((assignmentId, index) => ({
              id: index + 1,
              position: index,
              original: assignments.find((row) => row.id === assignmentId)!,
              replacement: null,
            })),
          },
        };
        return json(currentSwap);
      }
      if (path.endsWith("/swap/me")) return json(currentSwap);
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "Stage2 投稿与换曲" })).toBeInTheDocument();
    fireEvent.click((await screen.findAllByRole("checkbox"))[0]);
    fireEvent.click(await screen.findByRole("button", { name: "放回并不抽取（1 首）" }));
    await waitFor(() => expect(rollBodies).toEqual([{ assignment_ids: [31], mode: "return_only" }]));
    expect(await screen.findByText("待放回曲1 已放回，未抽取新曲")).toBeInTheDocument();
  });

  it("keeps swap audit history read-only for administrators", async () => {
    window.history.pushState({}, "", "/admin/phases");
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
    const applicant = { ...admin, id: 9, user_code: "player", qq_id: "9", display_name: "参赛者", roles: ["participant"], is_admin: false, is_pool_editor: false };
    const song = { id: 1, song_name: "待更换曲目", artist: "曲师", song_type: "A", remark: "", submitter: applicant, created_at: "2026-07-04T00:00:00" };
    let phases = { ...phasesPayload, phase_mode: "manual", manual_phase: "submission_2" as string | null, active_phase: "submission_2" as string | null, capabilities: { song_pool_edit: false, submission: true, swap: true, normal_submission_public: false, author_guess: false, quality_vote: false } };
    const cachedPhases = phases;
    const request = { id: 41, round_id: 1, user: applicant, status: "completed", created_at: "2026-07-04T00:01:00", items: [{ position: 0, original: { id: 31, song, status: "returned", draw_kind: "initial", created_at: "2026-07-04T00:00:00" }, replacement: { id: 51, song: { ...song, id: 2, song_name: "新曲" }, status: "active", draw_kind: "swap", created_at: "2026-07-04T00:01:00" } }] };
    const auditRound = { id: 1, status: "open", round_kind: "continuous", starts_at: "2026-07-04T00:00:00", ends_at: "2026-07-05T00:00:00", random_seed: "seed", finalized_at: null, roll_count: 1 };
    const audit = { round: auditRound, rounds: [auditRound], requests: [request], message: "连续换曲记录" };
    const phaseUpdates: Array<Record<string, unknown>> = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) {
        if (init?.cache === "no-store") {
          return json(bootstrapPayload(eventPayload, admin, { phases }));
        }
        return json(bootstrapPayload(eventPayload, admin, { phases: cachedPhases }));
      }
      if (path.endsWith("/admin/event/phases") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        phaseUpdates.push(body);
        phases = { ...phases, phase_mode: "auto", manual_phase: null, active_phase: null };
        return json(phases);
      }
      if (path.endsWith("/admin/swap/audit")) return json(audit);
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "赛事阶段" }, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getAllByText("开始", { selector: "label" })).toHaveLength(4);
    expect(screen.getAllByText("结束", { selector: "label" })).toHaveLength(4);
    expect(screen.queryByText("揭晓")).not.toBeInTheDocument();
    expect(screen.queryByText("已结束")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "恢复自动" }));
    await waitFor(() => expect(phaseUpdates).toEqual([
      { phase_mode: "auto", manual_phase: null, phases: [] },
    ]));
    await waitFor(() => expect(screen.getByRole("button", { name: "恢复自动" })).toBeDisabled());
    expect(await screen.findByText("连续换曲轮次")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finalize" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "驳回申请" })).not.toBeInTheDocument();
  });

  it("limits pool editors to the song pool admin tab", async () => {
    window.history.pushState({}, "", "/admin/overview");
    const editor = {
      id: 2,
      user_code: "editor",
      qq_id: "2",
      identity: "participant",
      display_name: "曲池编辑",
      roles: ["pool_editor", "participant"],
      is_admin: false,
      is_pool_editor: true,
      is_active: true,
    };
    const song = { id: 1, song_name: "曲池曲目", artist: "曲师", song_type: "A", remark: "", submitter: editor, created_at: "2026-07-04T00:00:00" };
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, editor));
      if (path.endsWith("/admin/song-pool")) return json([song]);
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByRole("tab", { name: "曲池" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "总览" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "阶段与换曲" })).not.toBeInTheDocument();
    await waitFor(() => expect(window.location.pathname).toBe("/admin/songs"));
    expect(await screen.findByText("曲池曲目")).toBeInTheDocument();
  });

  it("does not expose legacy phase controls or submit legacy event fields", async () => {
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
    let currentEvent = eventPayload;
    const updates: Array<Record<string, unknown>> = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(currentEvent, admin));
      if (path.endsWith("/admin/events/current") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown> & { name: string };
        updates.push(body);
        currentEvent = { ...currentEvent, name: body.name, settings: { ...currentEvent.settings, ...body } };
        return json(currentEvent);
      }
      if (path.endsWith("/events/current")) return json(currentEvent);
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByRole("link", { name: "猜谱" })).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "向用户显示猜谱入口" })).not.toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "开放投稿" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "投稿截止" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "猜谱开放" })).not.toBeInTheDocument();
    expect(await screen.findByRole("spinbutton", { name: "14 以下真爱票上限" })).toHaveValue(3);
    expect(screen.getByRole("spinbutton", { name: "14 及以上真爱票上限" })).toHaveValue(2);
    fireEvent.click(await screen.findByRole("button", { name: "保存设置" }));
    await waitFor(() => expect(updates).toHaveLength(1));
    for (const legacyField of ["registration_deadline", "submission_deadline", "guess_game_open_at", "submissions_open", "guess_game_visible"]) {
      expect(updates[0]).not.toHaveProperty(legacyField);
    }
    expect(updates[0]).not.toHaveProperty("true_love_vote_limit");
    expect(updates[0]).toMatchObject({ true_love_vote_limit_below_14: 3, true_love_vote_limit_at_least_14: 2 });
  });

  it("requires an exact confirmation before resetting all data and then logs out", async () => {
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
    let resetCalls = 0;
    let logoutCalls = 0;
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, admin, { available: false }));
      if (path.endsWith("/admin/reset") && init?.method === "POST") {
        resetCalls += 1;
        expect(JSON.parse(String(init.body))).toEqual({ confirmation: "清除全部数据" });
        return json({ message: "全部数据已清除，当前赛事已重置为报名阶段", event_id: 1, event_name: "测试赛事", event_slug: "test", deleted: {}, file_cleanup_warnings: [] });
      }
      if (path.endsWith("/auth/logout") && init?.method === "POST") {
        logoutCalls += 1;
        return json({ message: "已退出登录" });
      }
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "清除全部数据" }));
    const dialog = await screen.findByRole("dialog", { name: "确认清除全部数据" });
    const confirmButton = within(dialog).getByRole("button", { name: "确认清除" });
    expect(confirmButton).toBeDisabled();
    fireEvent.change(within(dialog).getByRole("textbox", { name: "输入确认词" }), { target: { value: "清除全部数据" } });
    expect(confirmButton).toBeEnabled();
    fireEvent.click(confirmButton);

    await waitFor(() => expect(resetCalls).toBe(1));
    expect(await within(dialog).findByText("全部数据已清除，当前赛事已重置为报名阶段")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "重新登录" }));
    await waitFor(() => expect(logoutCalls).toBe(1));
    await waitFor(() => expect(window.location.pathname).toBe("/login"));
  });

  it("submits the administrator role from user management", async () => {
    window.history.pushState({}, "", "/admin/users");
    const admin = {
      id: 1,
      user_code: "admin",
      qq_id: "1",
      identity: "participant",
      display_name: "赛事管理员",
      roles: ["owner", "admin", "pool_editor", "participant"],
      is_admin: true,
      is_owner: true,
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
      is_owner: false,
      is_pool_editor: false,
      is_active: true,
    };
    const updateBodies: Array<{ roles: string[] }> = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, admin));
      if (path.endsWith("/auth/me")) return json({ user: admin });
      if (path.endsWith("/events/current")) return json(eventPayload);
      if (path.endsWith("/admin/users") && (init?.method || "GET") === "GET") return json([member]);
      if (path.endsWith("/admin/users/2") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as { roles: string[] };
        updateBodies.push(body);
        return json({ ...member, roles: body.roles, is_admin: body.roles.includes("admin"), is_owner: false });
      }
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByText("2", {}, { timeout: 3000 })).toBeInTheDocument();
    const displayNameInput = await screen.findByRole("textbox", { name: "显示名 member" });
    expect(displayNameInput.closest(".MuiDataGrid-cell")?.firstElementChild).toHaveStyle({
      display: "flex",
      alignItems: "center",
      width: "100%",
      height: "100%",
    });
    fireEvent.click(await screen.findByRole("checkbox", { name: "管理员" }));

    await waitFor(() => expect(updateBodies).toHaveLength(1));
    expect(updateBodies[0].roles).toContain("admin");
  });

  it("disables administrator changes for a regular administrator", async () => {
    window.history.pushState({}, "", "/admin/users");
    const admin = {
      id: 1,
      user_code: "admin",
      qq_id: "1",
      identity: "participant",
      display_name: "赛事管理员",
      roles: ["admin", "pool_editor", "participant"],
      is_admin: true,
      is_owner: false,
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
      is_owner: false,
      is_pool_editor: false,
      is_active: true,
    };
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, admin));
      if (path.endsWith("/auth/me")) return json({ user: admin });
      if (path.endsWith("/events/current")) return json(eventPayload);
      if (path.endsWith("/admin/users")) return json([member]);
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByRole("checkbox", { name: "管理员" })).toBeDisabled();
  });

  it("shows owner status without exposing an owner grant control", async () => {
    window.history.pushState({}, "", "/admin/users");
    const owner = {
      id: 1,
      user_code: "owner-account",
      qq_id: "1",
      identity: "participant",
      display_name: "最高权限账号",
      roles: ["owner", "participant"],
      is_admin: true,
      is_owner: true,
      is_pool_editor: true,
      is_active: true,
    };
    mockApi(async (path) => {
      if (path.endsWith("/bootstrap")) return json(bootstrapPayload(eventPayload, owner));
      if (path.endsWith("/auth/me")) return json({ user: owner });
      if (path.endsWith("/events/current")) return json(eventPayload);
      if (path.endsWith("/admin/users")) return json([owner]);
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByText("Owner / 最高权限")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "管理员" })).toBeDisabled();
    expect(screen.queryByRole("checkbox", { name: "Owner / 最高权限" })).not.toBeInTheDocument();
  });
});
