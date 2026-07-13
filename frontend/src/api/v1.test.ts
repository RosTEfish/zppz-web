import { afterEach, describe, expect, it, vi } from "vitest";
import { api, formatDuration, formatMB, formatTime } from "./v1";

describe("v1 API helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("formats file sizes", () => {
    expect(formatMB(1024 * 1024)).toBe("1.00 MB");
  });

  it("handles empty timestamps", () => {
    expect(formatTime(null)).toBe("未设置");
  });

  it("formats parsed track durations as m:ss", () => {
    expect(formatDuration(240)).toBe("4:00");
    expect(formatDuration(240.001)).toBe("4:00");
    expect(formatDuration(252.9)).toBe("4:12");
    expect(formatDuration(null)).toBe("--:--");
  });

  it("prepares large downloads and starts a native browser download", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      download_url: "/api/v1/guess-game/charts/7/download",
      file_name: "chart-7.zip",
      file_size: 1024,
    }), { status: 200, headers: { "content-type": "application/json" } })));
    let clickedHref = "";
    let clickedName = "";
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      clickedHref = this.getAttribute("href") || "";
      clickedName = this.download;
    });

    await api.downloadChart(7);

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/guess-game/charts/7/download-metadata",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(clickedHref).toBe("/api/v1/guess-game/charts/7/download");
    expect(clickedName).toBe("chart-7.zip");
  });

  it("sends atomic batch delete requests to each admin resource", async () => {
    const requests: Array<{ path: string; method?: string; body?: string }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), method: init?.method, body: String(init?.body) });
      return new Response(JSON.stringify({ deleted: 2, message: "deleted" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }));

    await api.batchDeleteAdminSongs([1, 2]);
    await api.batchDeleteAdminSubmissions([3, 4]);
    await api.batchDeleteAdminCharts([5, 6]);

    expect(requests).toEqual([
      { path: "/api/v1/admin/song-pool/batch-delete", method: "POST", body: JSON.stringify({ ids: [1, 2] }) },
      { path: "/api/v1/admin/submissions/batch-delete", method: "POST", body: JSON.stringify({ ids: [3, 4] }) },
      { path: "/api/v1/admin/guess-game/charts/batch-delete", method: "POST", body: JSON.stringify({ ids: [5, 6] }) },
    ]);
  });
});
