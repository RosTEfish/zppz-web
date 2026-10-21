export function displayPersonName(
  person: { display_name?: string | null } | null | undefined,
  fallback = "",
): string {
  const name = person?.display_name?.trim();
  if (name) return name;
  if (person && "user_code" in person && typeof person.user_code === "string" && person.user_code.trim()) {
    return person.user_code.trim();
  }
  return fallback;
}

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
