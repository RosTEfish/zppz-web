import type { components } from "./generated";
import { API_PREFIX, apiRequest } from "./base";

type DownloadPreparation = components["schemas"]["DownloadPreparation"];

function triggerBrowserDownload(preparation: DownloadPreparation): void {
  const anchor = document.createElement("a");
  anchor.href = preparation.download_url;
  anchor.download = preparation.file_name;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

const DOWNLOAD_COOKIE_PREFIX = "zppz_download_";
const DOWNLOAD_START_TIMEOUT_MS = 5 * 60 * 1000;
const DOWNLOAD_COOKIE_POLL_MS = 100;

function createDownloadToken(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function addDownloadToken(downloadUrl: string, token: string): string {
  const url = new URL(downloadUrl, window.location.origin);
  url.searchParams.set("download_token", token);
  return url.origin === window.location.origin ? `${url.pathname}${url.search}${url.hash}` : url.toString();
}

function clearDownloadConfirmation(cookieName: string): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${cookieName}=; Max-Age=0; Path=/; SameSite=Lax${secure}`;
}

function waitForDownloadConfirmation(token: string): Promise<void> {
  const cookieName = `${DOWNLOAD_COOKIE_PREFIX}${token}`;
  return new Promise((resolve, reject) => {
    let intervalId: number | undefined;
    let timeoutId: number | undefined;
    const cleanup = () => {
      if (intervalId !== undefined) window.clearInterval(intervalId);
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
    const check = () => {
      const confirmed = document.cookie.split("; ").some((item) => item === `${cookieName}=1`);
      if (!confirmed) return;
      cleanup();
      clearDownloadConfirmation(cookieName);
      resolve();
    };
    intervalId = window.setInterval(check, DOWNLOAD_COOKIE_POLL_MS);
    timeoutId = window.setTimeout(() => {
      cleanup();
      clearDownloadConfirmation(cookieName);
      reject(new Error("浏览器未确认下载开始，请检查下载拦截设置后重试"));
    }, DOWNLOAD_START_TIMEOUT_MS);
    check();
  });
}

export async function downloadDirect(path: string, fileName: string): Promise<void> {
  triggerBrowserDownload({ download_url: `${API_PREFIX}${path}`, file_name: fileName, file_size: 0 });
}

export async function downloadPrepared(metadataPath: string, waitForBrowserStart = false): Promise<void> {
  const preparation = await apiRequest<DownloadPreparation>(metadataPath);
  if (!waitForBrowserStart) {
    triggerBrowserDownload(preparation);
    return;
  }
  const token = createDownloadToken();
  triggerBrowserDownload({ ...preparation, download_url: addDownloadToken(preparation.download_url, token) });
  await waitForDownloadConfirmation(token);
}
