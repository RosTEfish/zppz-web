import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UserRead } from "../api/v1";
import type { Identity } from "../identity";

const auth = vi.hoisted(() => ({
  user: null as UserRead | null,
  updateProfile: vi.fn(async (displayName: string, identity: Identity) => ({
    user: { display_name: displayName, identity } as UserRead,
  })),
  changePassword: vi.fn(),
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: auth.user,
    updateProfile: auth.updateProfile,
    changePassword: auth.changePassword,
  }),
}));

vi.mock("../contexts/ConfigContext", () => ({
  useConfig: () => ({
    phases: { active_phase: "registration" },
    loading: false,
  }),
}));

import AccountPage from "./AccountPage";

function accountUser(patch: Partial<UserRead> = {}): UserRead {
  return {
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
    ...patch,
  } as UserRead;
}

describe("Account profile draft", () => {
  beforeEach(() => {
    auth.user = accountUser();
    auth.updateProfile.mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it("applies a server profile before the form is edited", () => {
    const { rerender } = render(<AccountPage />);
    expect(screen.getByRole("textbox", { name: /显示名/ })).toHaveValue("原显示名");

    auth.user = accountUser({ display_name: "服务器名", identity: "audience" });
    rerender(<AccountPage />);

    expect(screen.getByRole("textbox", { name: /显示名/ })).toHaveValue("服务器名");
    expect(screen.getByRole("radio", { name: /观众/ })).toBeChecked();
  });

  it("submits the typed profile after the server user object is replaced", async () => {
    const { rerender } = render(<AccountPage />);
    fireEvent.change(screen.getByRole("textbox", { name: /显示名/ }), { target: { value: "新显示名" } });
    fireEvent.click(screen.getByRole("radio", { name: /访客/ }));

    auth.user = accountUser({ qq_id: "654321" });
    rerender(<AccountPage />);

    expect(screen.getByRole("textbox", { name: /显示名/ })).toHaveValue("新显示名");
    expect(screen.getByRole("radio", { name: /访客/ })).toBeChecked();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "保存资料" }));
    });
    expect(auth.updateProfile).toHaveBeenCalledWith("新显示名", "guest");
  });
});
