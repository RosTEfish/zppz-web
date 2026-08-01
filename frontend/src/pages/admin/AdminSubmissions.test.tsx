import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdminSubmissions from "./AdminSubmissions";
import { SnackbarProvider } from "notistack";


function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}


describe("AdminSubmissions", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("reports preparation, success, and a later batch download failure", async () => {
    let metadataAttempt = 0;
    let resolveMetadata: ((response: Response) => void) | undefined;
    const metadata = new Promise<Response>((resolve) => { resolveMetadata = resolve; });
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/admin/submissions")) {
        return Promise.resolve(json([{
          id: 11,
          file_name: "source.zip",
          file_size: 2048,
          review_status: "approved",
          review_note: "",
          source_kind: "self",
          track: "normal",
          source_song: { id: 3, song_name: "测试曲目", artist: "测试曲师", song_type: "A", remark: "", created_at: "2026-07-17T00:00:00" },
          user: { id: 4, user_code: "player", qq_id: "4", identity: "participant", display_name: "参赛者", roles: [], is_admin: false, is_owner: false, is_pool_editor: false },
          created_at: "2026-07-17T00:00:00",
        }]));
      }
      if (path.includes("/admin/submissions/download-metadata")) {
        metadataAttempt += 1;
        if (metadataAttempt === 1) return metadata;
        return Promise.resolve(json({ detail: "批量下载准备失败" }, 503));
      }
      return Promise.resolve(json({ detail: "not found" }, 404));
    }));
    let clickCount = 0;
    let clickedHref = "";
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      clickCount += 1;
      clickedHref = this.getAttribute("href") || "";
    });

    render(<SnackbarProvider><AdminSubmissions /></SnackbarProvider>);
    expect(await screen.findByText("测试曲目")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "全选" }));
    fireEvent.click(screen.getByRole("button", { name: "下载 1 份" }));

    expect(screen.getByRole("dialog", { name: "正在准备批量下载" })).toHaveTextContent("1 份投稿");
    expect(screen.getByText("正在准备…").closest("button")).toBeDisabled();

    resolveMetadata?.(json({
      download_url: "/api/v1/admin/submissions/download.zip?ids=11",
      file_name: "submissions.zip",
      file_size: 2300,
    }));
    await waitFor(() => expect(clickedHref).toContain("download_token="));
    expect(screen.getByRole("dialog", { name: "正在准备批量下载" })).toBeInTheDocument();
    expect(document.querySelector('input[type="checkbox"][aria-label="取消选择投稿"]')).toBeDisabled();

    const token = new URL(clickedHref, window.location.origin).searchParams.get("download_token");
    document.cookie = `zppz_download_${token}=1; Path=/; SameSite=Lax`;
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "正在准备批量下载" })).not.toBeInTheDocument());
    expect(await screen.findByText("下载请求已开始，请查看浏览器下载列表")).toBeInTheDocument();
    expect(clickCount).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: "下载 1 份" }));
    expect(await screen.findByText("批量下载准备失败")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "正在准备批量下载" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "下载 1 份" })).toBeEnabled();
  });
});
