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

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function phases(activePhase: "registration" | "guess", registrationEnded: boolean) {
  return {
    phase_mode: "auto",
    manual_phase: null,
    active_phase: activePhase,
    server_time: "2026-08-22T00:00:00Z",
    phases: [
      {
        id: 1,
        phase: "registration",
        starts_at: "2026-08-01T00:00:00Z",
        ends_at: registrationEnded ? "2026-08-15T00:00:00Z" : "2026-08-30T00:00:00Z",
      },
    ],
    capabilities: {
      song_pool_edit: activePhase === "registration",
      submission: false,
      swap: false,
      normal_submission_public: activePhase === "guess",
      author_guess: false,
      quality_vote: false,
    },
  };
}

describe("Auth registration page", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows a reminder and locks identity to guest when registration has closed", async () => {
    window.history.pushState({}, "", "/login");
    const registerBodies: unknown[] = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json({ event: eventPayload, user: null });
      if (path.endsWith("/event/phases")) return json(phases("guess", true));
      if (path.endsWith("/guess-game/availability")) return json({ available: false });
      if (path.endsWith("/auth/register")) {
        const body = JSON.parse(String(init.body));
        registerBodies.push(body);
        return json({
          user: {
            id: 8,
            user_code: body.user_code,
            qq_id: body.qq_id,
            identity: "guest",
            display_name: body.user_code,
            roles: ["guest"],
            is_admin: false,
            is_owner: false,
            is_pool_editor: false,
            is_active: true,
          },
        });
      }
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "赛事账号" }, { timeout: 3000 })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "注册" }));
    expect(await screen.findByText("报名阶段已结束，新注册账号将分配为访客身份。")).toBeInTheDocument();
    const identitySelect = screen.getByRole("combobox", { name: "身份" });
    expect(identitySelect).toHaveAttribute("aria-disabled", "true");
    expect(identitySelect).toHaveTextContent("访客");

    fireEvent.change(screen.getByRole("textbox", { name: "账号" }), { target: { value: "late-user" } });
    fireEvent.change(screen.getByRole("textbox", { name: "QQ" }), { target: { value: "late-user" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("button", { name: "注册并登录" }));

    await waitFor(() => expect(registerBodies).toEqual([{ user_code: "late-user", qq_id: "late-user", password: "secret123", identity: "guest" }]));
  });

  it("keeps the identity selector open while registration is still active", async () => {
    window.history.pushState({}, "", "/login");
    const registerBodies: unknown[] = [];
    mockApi(async (path, init) => {
      if (path.endsWith("/bootstrap")) return json({ event: eventPayload, user: null });
      if (path.endsWith("/event/phases")) return json(phases("registration", false));
      if (path.endsWith("/guess-game/availability")) return json({ available: false });
      if (path.endsWith("/auth/register")) {
        const body = JSON.parse(String(init.body));
        registerBodies.push(body);
        return json({
          user: {
            id: 9,
            user_code: body.user_code,
            qq_id: body.qq_id,
            identity: body.identity,
            display_name: body.user_code,
            roles: [body.identity],
            is_admin: false,
            is_owner: false,
            is_pool_editor: false,
            is_active: true,
          },
        });
      }
      return json({ detail: "not found" }, 404);
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "赛事账号" }, { timeout: 3000 })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "注册" }));
    const identitySelect = await screen.findByRole("combobox", { name: "身份" });
    expect(identitySelect).toBeEnabled();
    expect(identitySelect).toHaveTextContent("参赛者（投曲并参与抽取）");

    fireEvent.change(screen.getByRole("textbox", { name: "账号" }), { target: { value: "early-user" } });
    fireEvent.change(screen.getByRole("textbox", { name: "QQ" }), { target: { value: "early-user" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("button", { name: "注册并登录" }));

    await waitFor(() => expect(registerBodies).toEqual([{ user_code: "early-user", qq_id: "early-user", password: "secret123", identity: "participant" }]));
  });
});
