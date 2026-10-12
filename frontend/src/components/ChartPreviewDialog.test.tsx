import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type PreviewManifest } from "../api/v1";
import {
  ChartPreviewStage,
  setMiaViewCreatePreviewLoader,
  type CreateMiaViewPreview,
  type MiaViewPreview,
} from "./ChartPreviewDialog";


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
  player_url: "https://preview.przppz.club/miaview/test/sdk/index.mjs",
  renderer_url: "https://preview.przppz.club/miaview/test/renderer/index.html",
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

function createFakePreview(overrides: Partial<MiaViewPreview> = {}): MiaViewPreview {
  return {
    ready: Promise.resolve(),
    load: vi.fn().mockResolvedValue({ title: "测试歌曲" }),
    selectDifficulty: vi.fn().mockResolvedValue({ title: "测试歌曲" }),
    destroy: vi.fn(),
    on: vi.fn().mockReturnValue(() => undefined),
    ...overrides,
  };
}


describe("ChartPreviewStage", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    vi.restoreAllMocks();
    setMiaViewCreatePreviewLoader(null);
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
    expect(screen.getByText("MiaView 实时渲染")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "开始在线预览" }));
    expect(activate).toHaveBeenCalledTimes(1);
    expect(manifest).not.toHaveBeenCalled();
  });

  it("loads the chart through createPreview after the SDK is ready", async () => {
    vi.spyOn(api, "guessPreviewManifest").mockResolvedValue(READY_MANIFEST);
    const preview = createFakePreview();
    const createPreview = vi.fn<CreateMiaViewPreview>().mockReturnValue(preview);
    setMiaViewCreatePreviewLoader(async (sdkUrl) => {
      expect(sdkUrl).toBe(READY_MANIFEST.player_url);
      return createPreview;
    });

    render(
      <ChartPreviewStage
        active
        source="guess"
        sourceId={9}
        title="测试歌曲"
        onDownload={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    await waitFor(() => expect(createPreview).toHaveBeenCalledTimes(1));
    expect(createPreview).toHaveBeenCalledWith(
      expect.any(HTMLElement),
      expect.objectContaining({
        rendererUrl: READY_MANIFEST.renderer_url,
        diagnostics: false,
        resolution: { width: 1080, height: 1080 },
      }),
    );
    await waitFor(() => expect(preview.load).toHaveBeenCalledTimes(1));
    expect(preview.load).toHaveBeenCalledWith({
      maidata: { url: READY_MANIFEST.assets!.maidata_url },
      audio: READY_MANIFEST.assets!.track_url,
      cover: READY_MANIFEST.assets!.background_url,
      video: undefined,
      difficulty: 4,
    });
    expect(await screen.findByTitle("测试歌曲 MiaView 在线预览")).toBeInTheDocument();
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

  it("manual retry destroys the failed player and creates a new instance", async () => {
    const manifest = vi.spyOn(api, "guessPreviewManifest").mockResolvedValue(READY_MANIFEST);
    const first = createFakePreview({
      load: vi.fn().mockRejectedValue(new Error("谱面接收器初始化失败")),
    });
    const second = createFakePreview();
    const createPreview = vi.fn<CreateMiaViewPreview>()
      .mockReturnValueOnce(first)
      .mockReturnValueOnce(second);
    setMiaViewCreatePreviewLoader(async () => createPreview);

    render(
      <ChartPreviewStage
        active
        source="guess"
        sourceId={9}
        title="测试歌曲"
        onDownload={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    await waitFor(() => expect(screen.getByRole("button", { name: "重新加载预览" })).toBeInTheDocument());
    expect(first.destroy).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "重新加载预览" }));
    await waitFor(() => expect(second.load).toHaveBeenCalledTimes(1));
    expect(manifest).toHaveBeenCalledTimes(2);
  });

  it("destroys the player across ten activate/deactivate cycles", async () => {
    vi.spyOn(api, "guessPreviewManifest").mockResolvedValue(READY_MANIFEST);
    const previews: MiaViewPreview[] = [];
    const createPreview = vi.fn<CreateMiaViewPreview>().mockImplementation(() => {
      const preview = createFakePreview();
      previews.push(preview);
      return preview;
    });
    setMiaViewCreatePreviewLoader(async () => createPreview);

    const props = {
      source: "guess" as const,
      sourceId: 9,
      title: "测试歌曲",
      onDownload: vi.fn().mockResolvedValue(undefined),
    };
    const view = render(<ChartPreviewStage active {...props} />);

    for (let cycle = 0; cycle < 10; cycle += 1) {
      await waitFor(() => expect(previews.length).toBe(cycle + 1));
      await waitFor(() => expect(previews[cycle].load).toHaveBeenCalled());
      view.rerender(<ChartPreviewStage active={false} {...props} />);
      expect(previews[cycle].destroy).toHaveBeenCalled();
      expect(screen.queryByTitle("测试歌曲 MiaView 在线预览")).not.toBeInTheDocument();
      if (cycle < 9) view.rerender(<ChartPreviewStage active {...props} />);
    }

    expect(createPreview).toHaveBeenCalledTimes(10);
    expect(screen.getByRole("button", { name: "开始在线预览" })).toBeInTheDocument();
  });
});
