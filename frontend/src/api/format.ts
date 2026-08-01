export function formatMB(size: number): string {
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

export function formatTime(value?: string | null): string {
  if (!value) return "未设置";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

export function formatDuration(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value) || value <= 0) return "--:--";
  const totalSeconds = Math.floor(value);
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, "0")}`;
}
