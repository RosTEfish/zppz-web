import { afterEach, describe, expect, it, vi } from "vitest";
import { api, formatMB, formatTime } from "./v1";

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
});
