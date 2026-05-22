export type RoleName = "admin" | "pool_editor" | "participant" | "audience";

export interface UserRead {
  id: number;
  user_code: string;
  qq_id: string;
  identity: "participant" | "audience" | string;
  display_name: string;
  roles: string[];
  is_admin: boolean;
  is_pool_editor: boolean;
}

export interface EventRead {
  id: number;
  name: string;
  slug: string;
  is_current: boolean;
  settings: {
    participant_song_limit: number;
    audience_song_limit: number;
    draw_songs_per_participant: number;
    true_love_vote_limit: number;
    funny_vote_limit: number;
    announcement_text: string;
    registration_deadline?: string | null;
    submission_deadline?: string | null;
    guess_game_open_at?: string | null;
  };
}

export interface SongRead {
  id: number;
  song_name: string;
  artist: string;
  song_type: string;
  remark: string;
  submitter?: UserRead | null;
  created_at: string;
}

export interface StoredFileRead {
  id: number;
  file_name: string;
  file_size: number;
  review_status: string;
  review_note: string;
  user?: UserRead | null;
  created_at: string;
}

export interface DrawAssignmentRead {
  id: number;
  assigned_to: UserRead;
  song: SongRead;
  created_at: string;
}

export interface GuessChartRead {
  id: number;
  title: string;
  author: string;
  level: string;
  lane: string;
  guess_group_key: string;
  source_submission_type: string;
  source_submission_id?: number | null;
  source_level_slot: string;
  cover_path: string;
  storage_path: string;
  is_self_selected: boolean;
  plays: number;
  created_at: string;
  love_votes: number;
  funny_votes: number;
  my_votes: string[];
}

export interface GuessCommentRead {
  id: number;
  content: string;
  user: UserRead;
  created_at: string;
}

const API_PREFIX = "/api/v1";

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const hasBody = options.body !== undefined && !(options.body instanceof FormData);
  if (hasBody && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json().catch(() => ({})) : await response.text();
  if (!response.ok) {
    const message = typeof payload === "object" && payload && "detail" in payload ? String(payload.detail) : "请求失败";
    throw new Error(message);
  }
  return payload as T;
}

export const api = {
  me: () => apiRequest<{ user: UserRead }>("/auth/me"),
  login: (user_code: string, password: string) => apiRequest<{ user: UserRead }>("/auth/login", { method: "POST", body: JSON.stringify({ user_code, password }) }),
  register: (user_code: string, qq_id: string, password: string, identity = "audience") =>
    apiRequest<{ user: UserRead }>("/auth/register", { method: "POST", body: JSON.stringify({ user_code, qq_id, password, identity }) }),
  logout: () => apiRequest<{ message: string }>("/auth/logout", { method: "POST" }),
  changePassword: (old_password: string, new_password: string) =>
    apiRequest<{ message: string }>("/auth/change-password", { method: "POST", body: JSON.stringify({ old_password, new_password }) }),
  currentEvent: () => apiRequest<EventRead>("/events/current"),
  updateEvent: (payload: unknown) => apiRequest<EventRead>("/admin/events/current", { method: "PUT", body: JSON.stringify(payload) }),
  mySongs: () => apiRequest<SongRead[]>("/song-pool/me"),
  createSong: (payload: { song_name: string; artist: string; song_type: string; remark: string }) =>
    apiRequest<SongRead>("/song-pool/me", { method: "POST", body: JSON.stringify(payload) }),
  deleteSong: (id: number) => apiRequest<{ message: string }>(`/song-pool/me/${id}`, { method: "DELETE" }),
  adminSongs: () => apiRequest<SongRead[]>("/admin/song-pool"),
  updateSong: (id: number, payload: { song_name: string; artist: string; song_type: string; remark: string }) =>
    apiRequest<SongRead>(`/admin/song-pool/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  myDraw: () => apiRequest<DrawAssignmentRead[]>("/draw/results"),
  runDraw: () => apiRequest<DrawAssignmentRead[]>("/admin/draw", { method: "POST" }),
  adminDrawResults: () => apiRequest<DrawAssignmentRead[]>("/admin/draw/results"),
  mySubmissions: () => apiRequest<StoredFileRead[]>("/submissions"),
  uploadSubmission: (file: File) => {
    const form = new FormData();
    form.set("file", file);
    return apiRequest<StoredFileRead>("/submissions", { method: "POST", body: form });
  },
  adminSubmissions: () => apiRequest<StoredFileRead[]>("/admin/submissions"),
  guessCharts: () => apiRequest<GuessChartRead[]>("/guess-game/charts"),
  guessChart: (id: number) => apiRequest<GuessChartRead>(`/guess-game/charts/${id}`),
  vote: (chart_id: number, vote_type: "love" | "funny") => apiRequest<{ message: string }>("/guess-game/vote", { method: "POST", body: JSON.stringify({ chart_id, vote_type }) }),
  unvote: (chart_id: number, vote_type: "love" | "funny") => apiRequest<{ message: string }>("/guess-game/vote", { method: "DELETE", body: JSON.stringify({ chart_id, vote_type }) }),
  comments: (chartId: number) => apiRequest<GuessCommentRead[]>(`/guess-game/charts/${chartId}/comments`),
  createComment: (chartId: number, content: string) => apiRequest<GuessCommentRead>(`/guess-game/charts/${chartId}/comments`, { method: "POST", body: JSON.stringify({ content }) }),
  adminCharts: () => apiRequest<GuessChartRead[]>("/admin/guess-game/charts"),
  createChart: (payload: { title: string; author: string; level: string; lane: string; guess_group_key: string; is_self_selected: boolean }) =>
    apiRequest<GuessChartRead>("/admin/guess-game/charts", { method: "POST", body: JSON.stringify(payload) }),
  users: () => apiRequest<UserRead[]>("/admin/users"),
  updateUser: (id: number, payload: { identity: string; roles: string[]; display_name: string; is_active: boolean }) =>
    apiRequest<UserRead>(`/admin/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  adminStats: () => apiRequest<Record<string, number>>("/admin/stats"),
};

export function formatMB(size: number): string {
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

export function formatTime(value?: string | null): string {
  if (!value) return "未设置";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

