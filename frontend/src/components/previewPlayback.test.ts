import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PREVIEW_VIDEO_MAX_BYTES,
  fetchCappedBlob,
  previewPlaybackProfile,
  previewVideoSkipMessage,
} from "./previewPlayback";

describe("previewPlaybackProfile", () => {
  it("keeps 1080 and unlimited fps on a roomy desktop", () => {
    expect(previewPlaybackProfile({
      narrowViewport: false,
      coarsePointer: false,
      deviceMemoryGb: 8,
    })).toEqual({
      resolution: { width: 1080, height: 1080 },
      maxFps: "unlimited",
    });
  });

  it("drops to 720 and 30 fps on a narrow viewport", () => {
    expect(previewPlaybackProfile({
      narrowViewport: true,
      coarsePointer: false,
    })).toEqual({
      resolution: { width: 720, height: 720 },
      maxFps: 30,
    });
  });

  it("drops to 720 and 30 fps for a coarse pointer", () => {
    expect(previewPlaybackProfile({
      narrowViewport: false,
      coarsePointer: true,
      deviceMemoryGb: 8,
    })).toEqual({
      resolution: { width: 720, height: 720 },
      maxFps: 30,
    });
  });

  it("drops to 720 and 30 fps when device memory is 4 GB or less", () => {
    expect(previewPlaybackProfile({
      narrowViewport: false,
      coarsePointer: false,
      deviceMemoryGb: 4,
    }).maxFps).toBe(30);
    expect(previewPlaybackProfile({
      narrowViewport: false,
      coarsePointer: false,
      deviceMemoryGb: 0.5,
    }).resolution).toEqual({ width: 720, height: 720 });
  });
});

describe("fetchCappedBlob", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("skips a video whose Content-Length is over the cap without buffering the body", async () => {
    let pulls = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        pulls += 1;
        controller.enqueue(new Uint8Array(8));
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(stream, {
      status: 200,
      headers: {
        "Content-Type": "video/mp4",
        "Content-Length": String(PREVIEW_VIDEO_MAX_BYTES + 1),
      },
    }));

    const result = await fetchCappedBlob("https://assets.example/video.mp4", new AbortController().signal);

    expect(result).toEqual({ blob: null, skipped: true });
    // Cancelling the body can still deliver a chunk that was already queued.
    expect(pulls).toBeLessThanOrEqual(2);
  });

  it("stops reading when the body grows past the cap and Content-Length is missing", async () => {
    let pulls = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        pulls += 1;
        if (pulls > 10) {
          controller.close();
          return;
        }
        controller.enqueue(new Uint8Array(32));
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(stream, {
      status: 200,
      headers: { "Content-Type": "video/mp4" },
    }));

    const result = await fetchCappedBlob("https://assets.example/video.mp4", new AbortController().signal, 40);

    expect(result.skipped).toBe(true);
    expect(result.blob).toBeNull();
    expect(pulls).toBeLessThanOrEqual(3);
  });

  it("returns an in-cap video blob", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(new Uint8Array([9, 8, 7]), {
      status: 200,
      headers: { "Content-Type": "video/mp4", "Content-Length": "3" },
    }));

    const result = await fetchCappedBlob("https://assets.example/video.mp4", new AbortController().signal, 40);

    expect(result.skipped).toBe(false);
    expect(result.blob).toEqual(expect.objectContaining({ size: 3, type: "video/mp4" }));
  });

  it("throws when the video response is not ok", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("nope", { status: 403 }));

    await expect(fetchCappedBlob("https://assets.example/video.mp4", new AbortController().signal))
      .rejects.toThrow("素材下载失败 (403)");
  });
});

describe("previewVideoSkipMessage", () => {
  it("names the 40 MB cap", () => {
    expect(PREVIEW_VIDEO_MAX_BYTES).toBe(40 * 1024 * 1024);
    expect(previewVideoSkipMessage()).toContain("40 MB");
    expect(previewVideoSkipMessage()).toContain("封面");
  });
});
