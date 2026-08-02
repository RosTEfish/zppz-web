import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SnackbarProvider } from "notistack";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../testServer";
import AdminWebhooks from "./AdminWebhooks";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("AdminWebhooks", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("creates an integration and exposes its credentials only in the one-time dialog", async () => {
    let created = false;
    const clipboard = { writeText: vi.fn().mockResolvedValue(undefined) };
    vi.stubGlobal("navigator", { ...navigator, clipboard });
    mockApi((url, init) => {
      const path = new URL(url).pathname;
      if (path.endsWith("/admin/webhook-integrations") && init.method === "POST") {
        created = true;
        return json({
          id: "integration-1",
          name: "主群通知 Bot",
          integration_token: "zppz_whk_one_time_token",
          webhook_secret: "one-time-secret",
          created_at: "2026-08-02T12:00:00Z",
        });
      }
      if (path.endsWith("/admin/webhook-integrations")) {
        return json(created ? [{
          id: "integration-1",
          name: "主群通知 Bot",
          token_prefix: "zppz_whk_one_",
          is_active: true,
          secret_generation: 1,
          created_at: "2026-08-02T12:00:00Z",
          revoked_at: null,
          endpoint: null,
          pending_deliveries: 0,
          failed_deliveries: 0,
        }] : []);
      }
      return json({ detail: "not found" }, 404);
    });

    render(
      <SWRConfig value={{ provider: () => new Map(), shouldRetryOnError: false }}>
        <SnackbarProvider><AdminWebhooks /></SnackbarProvider>
      </SWRConfig>,
    );

    expect(await screen.findByText("尚未创建接入方")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "创建接入方" }));
    fireEvent.change(screen.getByLabelText("接入方名称"), { target: { value: "主群通知 Bot" } });
    fireEvent.click(screen.getByRole("button", { name: "创建并生成凭据" }));

    const dialog = await screen.findByRole("dialog", { name: "保存一次性接入凭据" });
    expect(dialog).toHaveTextContent("zppz_whk_one_time_token");
    expect(dialog).toHaveTextContent("one-time-secret");
    fireEvent.click(screen.getAllByRole("button", { name: "复制" })[0]);
    await waitFor(() => expect(clipboard.writeText).toHaveBeenCalledWith("zppz_whk_one_time_token"));

    fireEvent.click(screen.getByRole("button", { name: "我已安全保存" }));
    await waitFor(() => expect(screen.queryByText("zppz_whk_one_time_token")).not.toBeInTheDocument());
    expect(await screen.findByText("主群通知 Bot")).toBeInTheDocument();
  });
});
