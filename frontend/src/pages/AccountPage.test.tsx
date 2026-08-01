import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { mockApi } from "../testServer";

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

const participant = {
  id: 9,
  user_code: "player",
  qq_id: "123456",
  identity: "participant",
  display_name: "原显示名",
  roles: ["participant"],
  is_admin: false,
  is_owner: false,
  is_pool_editor: false,
  is_active: true,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function phases(activePhase: "registration" | "submission_1") {
  return {
    phase_mode: "manual",
    manual_phase: activePhase,
    active_phase: activePhase,
    phases: [],
    capabilities: {
      song_pool_edit: activePhase === "registration",
      submission: activePhase === "submission_1",
      swap: false,
      normal_submission_public: false,
      author_guess: false,
      quality_vote: false,
    },
  };
}

describe("Account settings page", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("updates profile state and changes the password", async () => {
    window.history.pushState({}, "", "/account");
    const profileBodies: unknown[] = [];
    const passwordBodies: unknown[] = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json({ event: eventPayload, user: participant });
      if (path.endsWith("/event/phases")) return json(phases("registration"));
      if (path.endsWith("/guess-game/availability")) return json({ available: false });
      if (path.endsWith("/auth/me") && init.method === "PUT") {
        const body = JSON.parse(String(init.body));
        profileBodies.push(body);
        return json({ user: { ...participant, ...body, roles: [body.identity] } });
      }
      if (path.endsWith("/auth/change-password") && init.method === "POST") {
        passwordBodies.push(JSON.parse(String(init.body)));
        return json({ message: "密码已更新" });
      }
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "账号设置" }, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /账号设置/ })).toHaveAttribute("href", "/account");
    expect(screen.getByLabelText("登录账号")).toBeDisabled();
    expect(screen.getByLabelText("注册 QQ")).toBeDisabled();

    fireEvent.change(screen.getByRole("textbox", { name: /显示名/ }), { target: { value: "新显示名" } });
    fireEvent.click(screen.getByRole("radio", { name: /观众/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存资料" }));

    await waitFor(() => expect(profileBodies).toEqual([{ display_name: "新显示名", identity: "audience" }]));
    expect(await screen.findByText("个人资料已保存")).toBeInTheDocument();
    expect((await screen.findAllByText("新显示名")).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText(/当前密码/), { target: { value: "secret123" } });
    fireEvent.change(screen.getByLabelText(/^新密码/), { target: { value: "new-secret-456" } });
    fireEvent.change(screen.getByLabelText(/确认新密码/), { target: { value: "different-456" } });
    fireEvent.click(screen.getByRole("button", { name: "更新密码" }));
    expect(await screen.findByText("两次输入的新密码不一致")).toBeInTheDocument();
    expect(passwordBodies).toHaveLength(0);

    fireEvent.change(screen.getByLabelText(/确认新密码/), { target: { value: "new-secret-456" } });
    fireEvent.click(screen.getByRole("button", { name: "更新密码" }));
    await waitFor(() => expect(passwordBodies).toEqual([{ old_password: "secret123", new_password: "new-secret-456" }]));
    expect(await screen.findByText("密码已更新，其他设备上的登录已注销")).toBeInTheDocument();
    expect(screen.getByLabelText(/当前密码/)).toHaveValue("");
  });

  it("locks identity outside registration while allowing display-name updates", async () => {
    window.history.pushState({}, "", "/account");
    const profileBodies: unknown[] = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json({ event: eventPayload, user: participant });
      if (path.endsWith("/event/phases")) return json(phases("submission_1"));
      if (path.endsWith("/guess-game/availability")) return json({ available: false });
      if (path.endsWith("/auth/me") && init.method === "PUT") {
        const body = JSON.parse(String(init.body));
        profileBodies.push(body);
        return json({ user: { ...participant, ...body } });
      }
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByText("身份仅可在报名阶段修改；当前仍可保存显示名。")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /参赛者/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /观众/ })).toBeDisabled();

    fireEvent.change(screen.getByRole("textbox", { name: /显示名/ }), { target: { value: "赛中改名" } });
    fireEvent.click(screen.getByRole("button", { name: "保存资料" }));
    await waitFor(() => expect(profileBodies).toEqual([{ display_name: "赛中改名", identity: "participant" }]));
  });
});
