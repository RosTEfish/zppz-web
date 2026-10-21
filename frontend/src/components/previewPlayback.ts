/** Separate from the 512 MB archive-member limit. A preview tab should not blob a full MV. */
export const PREVIEW_VIDEO_MAX_BYTES = 40 * 1024 * 1024;

const PREVIEW_RESOLUTION_FULL = { width: 1080, height: 1080 } as const;
const PREVIEW_RESOLUTION_SAVER = { width: 720, height: 720 } as const;
/** MUI `md` starts at 900px; phones in landscape sit under this even when they clear `sm`. */
const NARROW_PREVIEW_QUERY = "(max-width: 899.95px)";
const COARSE_POINTER_QUERY = "(pointer: coarse)";
/** Chromium reports deviceMemory in buckets ending at 4, then 8. */
const LOW_MEMORY_GB = 4;

export interface PreviewDeviceHints {
  narrowViewport: boolean;
  coarsePointer: boolean;
  deviceMemoryGb?: number;
}

export function readPreviewDeviceHints(): PreviewDeviceHints {
  const memory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory;
  return {
    narrowViewport: window.matchMedia(NARROW_PREVIEW_QUERY).matches,
    coarsePointer: window.matchMedia(COARSE_POINTER_QUERY).matches,
    deviceMemoryGb: typeof memory === "number" && Number.isFinite(memory) ? memory : undefined,
  };
}

export function previewPlaybackProfile(hints: PreviewDeviceHints): {
  resolution: { width: number; height: number };
  maxFps: number | "unlimited";
} {
  const lowMemory = hints.deviceMemoryGb !== undefined && hints.deviceMemoryGb > 0 && hints.deviceMemoryGb <= LOW_MEMORY_GB;
  if (hints.narrowViewport || hints.coarsePointer || lowMemory) {
    return { resolution: { ...PREVIEW_RESOLUTION_SAVER }, maxFps: 30 };
  }
  return { resolution: { ...PREVIEW_RESOLUTION_FULL }, maxFps: "unlimited" };
}

export function previewVideoSkipMessage(maxBytes = PREVIEW_VIDEO_MAX_BYTES): string {
  const megabytes = Math.round(maxBytes / (1024 * 1024));
  return `预览视频超过 ${megabytes} MB，已跳过以免占满设备内存。画面改用封面，音乐仍会播放；完整视频请下载投稿查看。`;
}

function declaredLength(response: Response): number | null {
  const raw = response.headers.get("content-length");
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) return null;
  return value;
}

function mediaType(response: Response): string {
  const raw = response.headers.get("content-type");
  if (!raw) return "application/octet-stream";
  return raw.split(";")[0]?.trim() || "application/octet-stream";
}

/**
 * Download a preview asset, but stop once `maxBytes` is exceeded.
 * Content-Length is trusted only as an early exit; the body is still counted
 * so a missing or short header cannot buffer a 512 MB MV.
 */
export async function fetchCappedBlob(
  url: string,
  signal: AbortSignal,
  maxBytes = PREVIEW_VIDEO_MAX_BYTES,
): Promise<{ blob: Blob | null; skipped: boolean }> {
  const response = await fetch(url, { signal, credentials: "omit", cache: "no-store" });
  if (!response.ok) {
    throw new Error(`素材下载失败 (${response.status})`);
  }
  const declared = declaredLength(response);
  if (declared !== null && declared > maxBytes) {
    await response.body?.cancel().catch(() => undefined);
    return { blob: null, skipped: true };
  }
  if (!response.body) {
    const blob = await response.blob();
    if (blob.size > maxBytes) return { blob: null, skipped: true };
    return { blob, skipped: false };
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (!value?.byteLength) continue;
    received += value.byteLength;
    if (received > maxBytes) {
      await reader.cancel().catch(() => undefined);
      return { blob: null, skipped: true };
    }
    chunks.push(value);
  }

  const merged = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return { blob: new Blob([merged], { type: mediaType(response) }), skipped: false };
}
