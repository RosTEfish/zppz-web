export function announcementSignature(markdown: string): string {
  let hash = 2166136261;
  for (let index = 0; index < markdown.length; index += 1) {
    hash ^= markdown.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `${markdown.length}:${(hash >>> 0).toString(36)}`;
}

export function announcementStorageKey(eventId: number): string {
  return `zppz:announcement:last-seen:${eventId}`;
}

export function shouldShowAnnouncement(eventId: number, markdown: string): boolean {
  const content = markdown.trim();
  if (!content) return false;
  try {
    return window.localStorage.getItem(announcementStorageKey(eventId)) !== announcementSignature(content);
  } catch {
    return true;
  }
}
