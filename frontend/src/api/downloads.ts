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

export async function downloadRemoteFiles(metadataPath: string): Promise<void> {
  const preparation = await apiRequest<DownloadPreparation>(metadataPath);
  if (preparation.files?.length) {
    const entries: { name: string; data: Uint8Array }[] = [];
    for (const file of preparation.files) {
      const response = await fetch(file.download_url);
      if (!response.ok) throw new Error("谱面下载失败，请稍后重试");
      entries.push({ name: file.file_name, data: new Uint8Array(await response.arrayBuffer()) });
    }
    const blob = storedZip(entries);
    const url = URL.createObjectURL(blob);
    triggerBrowserDownload({
      download_url: url,
      file_name: preparation.file_name.endsWith(".zip") ? preparation.file_name : "guess-charts.zip",
      file_size: blob.size,
    });
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    return;
  }
  const token = createDownloadToken();
  triggerBrowserDownload({ ...preparation, download_url: addDownloadToken(preparation.download_url, token) });
  await waitForDownloadConfirmation(token);
}

const CRC_TABLE = new Uint32Array(256);
for (let index = 0; index < 256; index += 1) {
  let value = index;
  for (let bit = 0; bit < 8; bit += 1) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  CRC_TABLE[index] = value >>> 0;
}

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function storedZip(entries: { name: string; data: Uint8Array }[]): Blob {
  const encoder = new TextEncoder();
  const parts: BlobPart[] = [];
  const central: BlobPart[] = [];
  let offset = 0;
  let centralSize = 0;
  for (const entry of entries) {
    const name = encoder.encode(entry.name);
    const size = entry.data.byteLength;
    if (size > 0xffffffff || offset > 0xffffffff) throw new Error("批量下载过大，无法在浏览器中打包");
    const crc = crc32(entry.data);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true);
    local.setUint16(6, 0x800, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, size, true);
    local.setUint32(22, size, true);
    local.setUint16(26, name.length, true);
    const directory = new DataView(new ArrayBuffer(46));
    directory.setUint32(0, 0x02014b50, true);
    directory.setUint16(4, 20, true);
    directory.setUint16(6, 20, true);
    directory.setUint16(8, 0x800, true);
    directory.setUint32(16, crc, true);
    directory.setUint32(20, size, true);
    directory.setUint32(24, size, true);
    directory.setUint16(28, name.length, true);
    directory.setUint32(42, offset, true);
    parts.push(new Uint8Array(local.buffer), name, entry.data);
    central.push(new Uint8Array(directory.buffer), name);
    offset += 30 + name.length + size;
    centralSize += 46 + name.length;
  }
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, entries.length, true);
  end.setUint16(10, entries.length, true);
  end.setUint32(12, centralSize, true);
  end.setUint32(16, offset, true);
  return new Blob([...parts, ...central, new Uint8Array(end.buffer)], { type: "application/zip" });
}
