import { afterEach, describe, expect, it, vi } from "vitest";
import { api, formatDuration, formatMB, formatTime, submissionContentType } from "./v1";

type XhrHandler = (xhr: TestXMLHttpRequest, body: Document | XMLHttpRequestBodyInit | null) => void;

class TestXMLHttpRequest {
  method = "";
  url = "";
  async = true;
  status = 0;
  responseText = "";
  withCredentials = false;
  requestHeaders: Record<string, string> = {};
  upload = { onprogress: null as ((event: ProgressEvent) => void) | null };
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;
  onload: (() => void) | null = null;

  constructor(private readonly handler: XhrHandler) {}

  open(method: string, url: string, async = true) {
    this.method = method;
    this.url = url;
    this.async = async;
  }

  setRequestHeader(name: string, value: string) {
    this.requestHeaders[name] = value;
  }

  send(body: Document | XMLHttpRequestBodyInit | null) {
    this.handler(this, body);
  }

  abort() {
    this.onabort?.();
  }
}

function installXhr(handler: XhrHandler) {
  const instances: TestXMLHttpRequest[] = [];
  vi.stubGlobal("XMLHttpRequest", class {
    constructor() {
      const xhr = new TestXMLHttpRequest(handler);
      instances.push(xhr);
      return xhr;
    }
  });
  return instances;
}

describe("v1 API helpers", () => {
  afterEach(() => {
    document.cookie.split(";").forEach((item) => {
      const name = item.split("=")[0]?.trim();
      if (name) document.cookie = `${name}=; Max-Age=0; Path=/`;
    });
    vi.useRealTimers();
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

  it("maps submission extensions to stable signed content types", () => {
    expect(submissionContentType("entry.ZIP")).toBe("application/zip");
    expect(submissionContentType("entry.7z")).toBe("application/x-7z-compressed");
    expect(submissionContentType("entry.rar")).toBe("application/vnd.rar");
    expect(() => submissionContentType("entry.exe")).toThrow("仅支持 ZIP、7Z 和 RAR");
  });

  it("uploads submissions through a signed PUT before completing", async () => {
    const calls: Array<{ path: string; method?: string; body?: BodyInit | null; headers?: HeadersInit }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      calls.push({ path, method: init?.method, body: init?.body, headers: init?.headers });
      if (path.endsWith("/upload-intents")) {
        return new Response(JSON.stringify({
          id: "intent-1",
          upload_url: "https://example.r2.cloudflarestorage.com/object?signed=1",
          method: "PUT",
          headers: { "Content-Type": "application/zip" },
          expires_at: "2026-07-17T12:00:00Z",
        }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response(JSON.stringify({
        id: "job-1",
        intent_id: "intent-1",
        status: "queued",
        stage: "uploaded",
        message: "等待后台校验",
        file_name: "entry.zip",
        file_size: 3,
        source_song_id: 4,
        replace_submission_id: null,
        submission: null,
        created_at: "2026-07-17T12:00:00Z",
        updated_at: "2026-07-17T12:00:00Z",
      }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }));
    const xhrs = installXhr((xhr) => {
      xhr.status = 200;
      xhr.onload?.();
    });
    const file = new File([new Uint8Array([1, 2, 3])], "entry.zip");

    await expect(api.uploadSubmission(4, "normal", file)).resolves.toMatchObject({ id: "job-1", status: "queued" });
    expect(calls.map((call) => [call.path, call.method])).toEqual([
      ["/api/v1/submissions/upload-intents", "POST"],
      ["/api/v1/submissions/upload-intents/intent-1/complete", "POST"],
    ]);
    expect(xhrs).toHaveLength(1);
    expect(xhrs[0]).toMatchObject({
      method: "PUT",
      url: "https://example.r2.cloudflarestorage.com/object?signed=1",
      requestHeaders: { "Content-Type": "application/zip" },
      withCredentials: false,
    });
  });

  it("reports XHR progress and returns immediately after the enqueue confirmation", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      calls.push(path);
      if (path.endsWith("/upload-intents")) {
        return new Response(JSON.stringify({
          id: "intent-background",
          upload_url: "https://example.r2.cloudflarestorage.com/background",
          method: "PUT",
          headers: { "Content-Type": "application/zip" },
          expires_at: "2026-07-17T12:00:00Z",
        }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response(JSON.stringify({
        id: "job-background",
        intent_id: "intent-background",
        status: "queued",
        stage: "uploaded",
        message: "等待后台校验",
        file_name: "new-entry.zip",
        file_size: 3,
        source_song_id: 4,
        replace_submission_id: null,
        submission: null,
        created_at: "2026-07-17T12:00:00Z",
        updated_at: "2026-07-17T12:00:00Z",
      }), { status: 200, headers: { "content-type": "application/json" } });
    }));
    vi.spyOn(performance, "now").mockReturnValueOnce(0).mockReturnValueOnce(1000);
    installXhr((xhr) => {
      xhr.upload.onprogress?.({ loaded: 1, total: 3, lengthComputable: true } as ProgressEvent);
      xhr.upload.onprogress?.({ loaded: 3, total: 3, lengthComputable: true } as ProgressEvent);
      xhr.status = 200;
      xhr.onload?.();
    });
    const progress = vi.fn();

    const result = await api.uploadSubmission(
      4,
      "normal",
      new File([new Uint8Array([1, 2, 3])], "new-entry.zip"),
      false,
      { onProgress: progress },
    );

    expect(result).toMatchObject({ id: "job-background", status: "queued" });
    expect(calls).toEqual([
      "/api/v1/submissions/upload-intents",
      "/api/v1/submissions/upload-intents/intent-background/complete",
    ]);
    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ phase: "preparing", percent: 0 }));
    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ phase: "uploading", percent: 100 }));
    expect(progress).toHaveBeenLastCalledWith(expect.objectContaining({ phase: "confirming", percent: 100 }));
  });

  it("does not complete an upload when the signed PUT fails", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/upload-intents")) {
        return new Response(JSON.stringify({
          id: "intent-failed",
          upload_url: "https://example.r2.cloudflarestorage.com/fail",
          method: "PUT",
          headers: { "Content-Type": "application/zip" },
          expires_at: "2026-07-17T12:00:00Z",
        }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response(null, { status: 204 });
    });
    vi.stubGlobal("fetch", fetchMock);
    installXhr((xhr) => {
      xhr.status = 403;
      xhr.responseText = "denied";
      xhr.onload?.();
    });

    await expect(api.uploadSubmission(4, "normal", new File(["zip"], "entry.zip"))).rejects.toThrow("denied");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/submissions/upload-intents/intent-failed",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("aborts the XHR and deletes the intent without calling complete", async () => {
    const paths: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      paths.push(path);
      if (path.endsWith("/upload-intents")) {
        return new Response(JSON.stringify({
          id: "intent-cancel",
          upload_url: "https://example.r2.cloudflarestorage.com/cancel",
          method: "PUT",
          headers: { "Content-Type": "application/zip" },
          expires_at: "2026-07-17T12:00:00Z",
        }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response(null, { status: 204 });
    }));
    const xhrs = installXhr(() => undefined);
    const controller = new AbortController();
    const upload = api.uploadSubmission(
      4,
      "normal",
      new File(["zip"], "entry.zip"),
      false,
      { signal: controller.signal },
    );
    await vi.waitFor(() => expect(xhrs).toHaveLength(1));
    controller.abort();

    await expect(upload).rejects.toMatchObject({ name: "AbortError" });
    expect(paths).toEqual([
      "/api/v1/submissions/upload-intents",
      "/api/v1/submissions/upload-intents/intent-cancel",
    ]);
  });

  it("deduplicates concurrent bootstrap requests", async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    const response = new Promise<Response>((resolve) => { resolveResponse = resolve; });
    const fetchMock = vi.fn(() => response);
    vi.stubGlobal("fetch", fetchMock);

    const first = api.bootstrap();
    const second = api.bootstrap();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolveResponse?.(new Response(JSON.stringify({ event: {}, user: null }), { status: 200, headers: { "content-type": "application/json" } }));

    await expect(Promise.all([first, second])).resolves.toHaveLength(2);
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

  it("keeps a batch download pending until its isolated confirmation cookie arrives", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      download_url: "/api/v1/guess-game/charts/download.zip?ids=7",
      file_name: "guess-charts.zip",
      file_size: 1024,
    }), { status: 200, headers: { "content-type": "application/json" } })));
    let clickedHref = "";
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      clickedHref = this.getAttribute("href") || "";
      const token = new URL(this.href).searchParams.get("download_token");
      document.cookie = `zppz_download_${token}=1; Path=/; SameSite=Lax`;
    });

    await expect(api.downloadCharts([7])).resolves.toBeUndefined();

    const token = new URL(clickedHref, window.location.origin).searchParams.get("download_token");
    expect(token).toMatch(/^[a-f0-9]{32}$/);
    expect(clickedHref).toContain("ids=7&download_token=");
    expect(document.cookie).not.toContain(`zppz_download_${token}=1`);
  });

  it("fails a batch download after five minutes without browser confirmation", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      download_url: "/api/v1/admin/submissions/download.zip?ids=11",
      file_name: "submissions.zip",
      file_size: 2048,
    }), { status: 200, headers: { "content-type": "application/json" } })));
    let clicked = false;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => { clicked = true; });

    const download = api.downloadAdminSubmissions([11]);
    const rejection = expect(download).rejects.toThrow("浏览器未确认下载开始，请检查下载拦截设置后重试");
    await vi.waitFor(() => expect(clicked).toBe(true));
    await vi.advanceTimersByTimeAsync(5 * 60 * 1000);
    await rejection;
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

  it("sends the exact confirmation for the destructive admin reset", async () => {
    const requests: Array<{ path: string; method?: string; body?: string }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ path: String(input), method: init?.method, body: String(init?.body) });
      return new Response(JSON.stringify({
        message: "reset",
        event_id: 1,
        event_name: "Current",
        event_slug: "current",
        deleted: {},
        file_cleanup_warnings: [],
      }), { status: 200, headers: { "content-type": "application/json" } });
    }));

    await api.resetAllData("清除全部数据");

    expect(requests).toEqual([
      { path: "/api/v1/admin/reset", method: "POST", body: JSON.stringify({ confirmation: "清除全部数据" }) },
    ]);
  });
});
