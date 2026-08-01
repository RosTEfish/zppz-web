import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type PreviewManifest } from "../api/v1";
import { ChartPreviewStage } from "./ChartPreviewDialog";


const READY_MANIFEST: PreviewManifest = {
  status: "ready",
  message: "预览已就绪",
  source_version: "source-v1",
  expires_at: "2026-07-25T12:00:00Z",
  selected_level_slot: 4,
  levels: [{ slot: 4, difficulty_index: 3, level: "13+" }],
  assets: {
    maidata_url: "https://assets.example/maidata.txt?signature=1",
    track_url: "https://assets.example/track.mp3?signature=1",
    background_url: "https://assets.example/bg.jpg?signature=1",
    video_url: null,
  },
  player_url: "https://preview.przppz.club/majdata/bridge2/player.html",
  player_origin: "https://preview.przppz.club",
};


function matchMedia(matches: boolean) {
  return (query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  });
}

function previewMessage(
  source: Window,
  data: Record<string, unknown>,
): MessageEvent {
  const event = new Event("message");
  Object.defineProperties(event, {
    origin: { value: READY_MANIFEST.player_origin },
    source: { value: source },
    data: { value: data },
  });
  return event as MessageEvent;
}


describe("ChartPreviewStage", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    vi.restoreAllMocks();
    window.matchMedia = matchMedia(false);
  });

  it("does not request a manifest before preview activation", () => {
    const manifest = vi.spyOn(api, "guessPreviewManifest").mockResolvedValue(READY_MANIFEST);
    const activate = vi.fn();

    render(
      <ChartPreviewStage
        active={false}
        source="guess"
        sourceId={9}
        title="测试歌曲"
        levelLabel="13+"
        onActivate={activate}
        onDownload={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(manifest).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "开始在线预览" }));
    expect(activate).toHaveBeenCalledTimes(1);
    expect(manifest).not.toHaveBeenCalled();
  });

  it("sends one stable load message only after a trusted ready event", async () => {
    vi.spyOn(api, "guessPreviewManifest").mockResolvedValue(READY_MANIFEST);
    render(
      <ChartPreviewStage
        active
        source="guess"
        sourceId={9}
        title="测试歌曲"
        onDownload={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const iframe = await screen.findByTitle("测试歌曲 Majdata 在线预览") as HTMLIFrameElement;
    const sessionId = new URL(iframe.src).searchParams.get("zppz_session");
    expect(sessionId).toBeTruthy();
    const postMessage = vi.spyOn(iframe.contentWindow!, "postMessage");

    const ready = previewMessage(iframe.contentWindow!, {
      type: "zppz.preview.ready",
      version: 2,
      session_id: sessionId,
    });
    act(() => window.dispatchEvent(ready));

    await waitFor(() => expect(postMessage).toHaveBeenCalledTimes(1), { timeout: 3000 });
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "zppz.preview.load",
        version: 2,
        session_id: sessionId,
        request_id: expect.stringContaining("source-v1:4"),
      }),
      READY_MANIFEST.player_origin,
    );

    act(() => window.dispatchEvent(ready));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(postMessage).toHaveBeenCalledTimes(1);
  });

  it("requires mobile confirmation before requesting the manifest", async () => {
    window.matchMedia = matchMedia(true);
    const manifest = vi.spyOn(api, "guessPreviewManifest").mockResolvedValue(READY_MANIFEST);

    render(
      <ChartPreviewStage
        active
        source="guess"
        sourceId={9}
        title="测试歌曲"
        onDownload={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(await screen.findByText("播放器首次加载约几十 MB")).toBeInTheDocument();
    expect(manifest).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "继续加载预览" }));
    await waitFor(() => expect(manifest).toHaveBeenCalledTimes(1));
  });

  it("manual retry destroys the failed iframe and creates a new session", async () => {
    const manifest = vi.spyOn(api, "guessPreviewManifest").mockResolvedValue(READY_MANIFEST);
    render(
      <ChartPreviewStage
        active
        source="guess"
        sourceId={9}
        title="测试歌曲"
        onDownload={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const first = await screen.findByTitle("测试歌曲 Majdata 在线预览") as HTMLIFrameElement;
    const firstSession = new URL(first.src).searchParams.get("zppz_session");
    const playerError = previewMessage(first.contentWindow!, {
      type: "zppz.preview.error",
      version: 2,
      session_id: firstSession,
      message: "谱面接收器初始化失败",
    });
    await waitFor(() => {
      act(() => window.dispatchEvent(playerError));
      expect(screen.getByRole("button", { name: "重新加载预览" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "重新加载预览" }));
    const second = await screen.findByTitle("测试歌曲 Majdata 在线预览") as HTMLIFrameElement;
    await waitFor(() => expect(new URL(second.src).searchParams.get("zppz_session")).not.toBe(firstSession));
    expect(manifest).toHaveBeenCalledTimes(2);
  });

  it("unmounts the iframe and creates a fresh session through ten preview cycles", async () => {
    vi.spyOn(api, "guessPreviewManifest").mockResolvedValue(READY_MANIFEST);
    const props = {
      source: "guess" as const,
      sourceId: 9,
      title: "测试歌曲",
      onDownload: vi.fn().mockResolvedValue(undefined),
    };
    const view = render(<ChartPreviewStage active {...props} />);
    const sessions = new Set<string>();

    for (let cycle = 0; cycle < 10; cycle += 1) {
      const iframe = await screen.findByTitle("测试歌曲 Majdata 在线预览") as HTMLIFrameElement;
      sessions.add(new URL(iframe.src).searchParams.get("zppz_session") ?? "");
      view.rerender(<ChartPreviewStage active={false} {...props} />);
      expect(screen.queryByTitle("测试歌曲 Majdata 在线预览")).not.toBeInTheDocument();
      if (cycle < 9) view.rerender(<ChartPreviewStage active {...props} />);
    }

    expect(sessions).toHaveLength(10);
    expect(screen.getByRole("button", { name: "开始在线预览" })).toBeInTheDocument();
  });
});
