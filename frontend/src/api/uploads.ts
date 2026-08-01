import { apiRequest } from "./base";
import type { components } from "./generated";

type SubmissionUploadIntent = components["schemas"]["SubmissionUploadIntentRead"];
type SubmissionProcessingJob = components["schemas"]["SubmissionProcessingJobRead"];

export interface SubmissionUploadProgress {
  phase: "preparing" | "uploading" | "confirming";
  loaded: number;
  total: number;
  percent: number;
  bytesPerSecond: number;
  etaSeconds: number | null;
}

export interface SubmissionUploadOptions {
  signal?: AbortSignal;
  onProgress?: (progress: SubmissionUploadProgress) => void;
}

const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
const ARCHIVE_CONTENT_TYPES: Record<string, string> = {
  ".zip": "application/zip",
  ".7z": "application/x-7z-compressed",
  ".rar": "application/vnd.rar",
};

export function submissionContentType(fileName: string): string {
  const dot = fileName.lastIndexOf(".");
  const extension = dot >= 0 ? fileName.slice(dot).toLowerCase() : "";
  const contentType = ARCHIVE_CONTENT_TYPES[extension];
  if (!contentType) throw new Error("仅支持 ZIP、7Z 和 RAR 投稿压缩包");
  return contentType;
}

function validateSubmissionFile(file: File): string {
  const contentType = submissionContentType(file.name);
  if (file.size <= 0) throw new Error("投稿文件不能为空");
  if (file.size > MAX_UPLOAD_BYTES) throw new Error("投稿文件不能超过 100 MB");
  return contentType;
}

function abortedUploadError(): DOMException {
  return new DOMException("上传已取消", "AbortError");
}

function putSubmissionFile(
  intent: SubmissionUploadIntent,
  file: File,
  options: SubmissionUploadOptions,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const samples: Array<{ at: number; loaded: number }> = [];
    let lastUiUpdate = 0;
    let settled = false;
    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      options.signal?.removeEventListener("abort", abort);
      callback();
    };
    const abort = () => {
      xhr.abort();
      finish(() => reject(abortedUploadError()));
    };
    xhr.open(intent.method, intent.upload_url, true);
    xhr.timeout = 30 * 60 * 1000;
    xhr.withCredentials = intent.upload_url.startsWith("/");
    Object.entries(intent.headers).forEach(([name, value]) => xhr.setRequestHeader(name, value));
    xhr.upload.onprogress = (event) => {
      const now = performance.now();
      samples.push({ at: now, loaded: event.loaded });
      while (samples.length > 1 && samples[0].at < now - 3000) samples.shift();
      if (now - lastUiUpdate < 250 && event.loaded < event.total) return;
      lastUiUpdate = now;
      const first = samples[0];
      const elapsedSeconds = first ? Math.max((now - first.at) / 1000, 0.001) : 0;
      const bytesPerSecond = first ? Math.max((event.loaded - first.loaded) / elapsedSeconds, 0) : 0;
      const total = event.lengthComputable ? event.total : file.size;
      const remaining = Math.max(total - event.loaded, 0);
      options.onProgress?.({
        phase: "uploading",
        loaded: event.loaded,
        total,
        percent: total > 0 ? Math.min((event.loaded / total) * 100, 100) : 0,
        bytesPerSecond,
        etaSeconds: bytesPerSecond > 0 ? remaining / bytesPerSecond : null,
      });
    };
    xhr.onerror = () => finish(() => reject(new Error("对象存储上传网络中断，请检查网络后重试")));
    xhr.ontimeout = () => finish(() => reject(new Error("对象存储上传超时，请重新上传")));
    xhr.onabort = () => finish(() => reject(abortedUploadError()));
    xhr.onload = () => finish(() => {
      if (xhr.status >= 200 && xhr.status < 300) {
        options.onProgress?.({
          phase: "confirming",
          loaded: file.size,
          total: file.size,
          percent: 100,
          bytesPerSecond: 0,
          etaSeconds: null,
        });
        resolve();
        return;
      }
      reject(new Error(xhr.responseText || `对象存储上传失败（HTTP ${xhr.status}）`));
    });
    if (options.signal?.aborted) {
      abort();
      return;
    }
    options.signal?.addEventListener("abort", abort, { once: true });
    xhr.send(file);
  });
}

export async function uploadSubmissionThroughIntent(
  payload: Record<string, unknown>,
  file: File,
  adminSubmissionId?: number,
  options: SubmissionUploadOptions = {},
): Promise<SubmissionProcessingJob> {
  const content_type = validateSubmissionFile(file);
  options.onProgress?.({
    phase: "preparing",
    loaded: 0,
    total: file.size,
    percent: 0,
    bytesPerSecond: 0,
    etaSeconds: null,
  });
  const metadata = { ...payload, file_name: file.name, file_size: file.size, content_type };
  const base = adminSubmissionId === undefined
    ? "/submissions/upload-intents"
    : `/admin/submissions/${adminSubmissionId}/upload-intents`;
  const intent = await apiRequest<SubmissionUploadIntent>(base, { method: "POST", body: JSON.stringify(metadata) });
  try {
    await putSubmissionFile(intent, file, options);
  } catch (error) {
    const cancelPath = adminSubmissionId === undefined
      ? `/submissions/upload-intents/${intent.id}`
      : `/admin/submissions/upload-intents/${intent.id}`;
    await apiRequest<void>(cancelPath, { method: "DELETE" }).catch(() => undefined);
    throw error;
  }
  const completePath = adminSubmissionId === undefined
    ? `/submissions/upload-intents/${intent.id}/complete`
    : `/admin/submissions/upload-intents/${intent.id}/complete`;
  try {
    return await apiRequest<SubmissionProcessingJob>(completePath, { method: "POST" });
  } catch (completionError) {
    const statusPath = adminSubmissionId === undefined
      ? `/submissions/upload-intents/${intent.id}/status`
      : `/admin/submissions/upload-intents/${intent.id}/status`;
    try {
      return await apiRequest<SubmissionProcessingJob>(statusPath, { cache: "no-store" });
    } catch {
      const cancelPath = adminSubmissionId === undefined
        ? `/submissions/upload-intents/${intent.id}`
        : `/admin/submissions/upload-intents/${intent.id}`;
      await apiRequest<void>(cancelPath, { method: "DELETE" }).catch(() => undefined);
      throw completionError;
    }
  }
}
