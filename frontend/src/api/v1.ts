export type Track = "normal" | "j";

export interface UserRead {
  id: number;
  user_code: string;
  qq_id: string;
  identity: "participant" | "audience" | string;
  display_name: string;
  roles: string[];
  is_admin: boolean;
  is_pool_editor: boolean;
  is_active?: boolean;
}

export interface EventRead {
  id: number;
  name: string;
  slug: string;
  is_current: boolean;
  settings: EventUpdatePayload;
}

export interface EventUpdatePayload {
  name: string;
  participant_song_limit: number;
  audience_song_limit: number;
  draw_songs_per_participant: number;
  true_love_vote_limit: number;
  funny_vote_limit: number;
  announcement_text: string;
  registration_deadline?: string | null;
  submission_deadline?: string | null;
  guess_game_open_at?: string | null;
  submissions_open: boolean;
  guess_game_visible: boolean;
}

export interface BootstrapRead {
  event: EventRead;
  user: UserRead | null;
}

export interface DownloadPreparation {
  download_url: string;
  file_name: string;
  file_size: number;
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

export interface SongPayload {
  song_name: string;
  artist: string;
  song_type: string;
  remark: string;
}

export interface StoredFileRead {
  id: number;
  file_name: string;
  file_size: number;
  review_status: string;
  review_note: string;
  source_kind: "self" | "assigned" | string;
  track: Track;
  source_song?: SongRead | null;
  user?: UserRead | null;
  created_at: string;
}

export interface SubmissionTargetRead {
  song: SongRead;
  source_kind: "self" | "assigned";
  submission?: StoredFileRead | null;
}

export interface SubmissionTargetsResponse {
  is_open: boolean;
  targets: SubmissionTargetRead[];
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
  designer: string;
  level: string;
  lane: Track | string;
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

export interface AuthorGuessState {
  can_guess: boolean;
  candidates: Array<{ user_id: number; display_id: string }>;
  my_guess_user_id?: number | null;
}

export interface AuthorCandidateAdmin {
  user: UserRead;
  song_count: number;
  selected: boolean;
  display_id: string;
}

export interface GuessImportIssueRead {
  id: number;
  source_type: string;
  file_name: string;
  issue_type: string;
  message: string;
  created_at: string;
}

export interface GuessImportSummary {
  message: string;
  scanned: number;
  created: number;
  updated: number;
  deleted: number;
  issues: number;
}

export interface GuessStats {
  scope: "all" | "j";
  overview: {
    charts: number;
    views: number;
    love_votes: number;
    funny_votes: number;
    guess_records: number;
    counted_guesses: number;
    correct_guesses: number;
    accuracy: number | null;
    users_guessing: number;
    users_guessed: number;
  };
  chart_stats: Array<Record<string, unknown>>;
  user_stats: Array<Record<string, unknown>>;
  candidate_stats: Array<Record<string, unknown>>;
  guess_details: Array<Record<string, unknown>>;
}

const API_PREFIX = "/api/v1";
const pendingGetRequests = new Map<string, Promise<unknown>>();

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json().catch(() => ({})) : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "object" && payload && "detail" in payload ? payload.detail : "请求失败";
    const message = Array.isArray(detail)
      ? detail.map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item))).join("；")
      : String(detail);
    throw new Error(message);
  }
  return payload as T;
}

async function performRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_PREFIX}${path}`, { ...options, headers, credentials: "include" });
  return parseResponse<T>(response);
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  if (method !== "GET" || options.signal) {
    const result = await performRequest<T>(path, options);
    if (method !== "GET") pendingGetRequests.clear();
    return result;
  }
  const pending = pendingGetRequests.get(path);
  if (pending) return pending as Promise<T>;
  const task = performRequest<T>(path, options).finally(() => pendingGetRequests.delete(path));
  pendingGetRequests.set(path, task);
  return task;
}

function triggerBrowserDownload(preparation: DownloadPreparation): void {
  const anchor = document.createElement("a");
  anchor.href = preparation.download_url;
  anchor.download = preparation.file_name;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

async function downloadDirect(path: string, fileName: string): Promise<void> {
  triggerBrowserDownload({ download_url: `${API_PREFIX}${path}`, file_name: fileName, file_size: 0 });
}

async function downloadPrepared(metadataPath: string): Promise<void> {
  triggerBrowserDownload(await apiRequest<DownloadPreparation>(metadataPath));
}

function submissionForm(file: File, songId?: number, track?: Track): FormData {
  const form = new FormData();
  form.set("file", file);
  if (songId !== undefined) form.set("song_id", String(songId));
  if (track) form.set("track", track);
  return form;
}

export const api = {
  bootstrap: () => apiRequest<BootstrapRead>("/bootstrap"),
  me: () => apiRequest<{ user: UserRead }>("/auth/me"),
  login: (user_code: string, password: string) => apiRequest<{ user: UserRead }>("/auth/login", { method: "POST", body: JSON.stringify({ user_code, password }) }),
  register: (user_code: string, qq_id: string, password: string, identity = "audience") => apiRequest<{ user: UserRead }>("/auth/register", { method: "POST", body: JSON.stringify({ user_code, qq_id, password, identity }) }),
  logout: () => apiRequest<{ message: string }>("/auth/logout", { method: "POST" }),
  changePassword: (old_password: string, new_password: string) => apiRequest<{ message: string }>("/auth/change-password", { method: "POST", body: JSON.stringify({ old_password, new_password }) }),
  currentEvent: () => apiRequest<EventRead>("/events/current"),
  updateEvent: (payload: EventUpdatePayload) => apiRequest<EventRead>("/admin/events/current", { method: "PUT", body: JSON.stringify(payload) }),

  mySongs: () => apiRequest<SongRead[]>("/song-pool/me"),
  createSong: (payload: SongPayload) => apiRequest<SongRead>("/song-pool/me", { method: "POST", body: JSON.stringify(payload) }),
  updateMySong: (id: number, payload: SongPayload) => apiRequest<SongRead>(`/song-pool/me/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteSong: (id: number) => apiRequest<{ message: string }>(`/song-pool/me/${id}`, { method: "DELETE" }),
  adminSongs: () => apiRequest<SongRead[]>("/admin/song-pool"),
  updateSong: (id: number, payload: SongPayload) => apiRequest<SongRead>(`/admin/song-pool/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteAdminSong: (id: number) => apiRequest<{ message: string }>(`/admin/song-pool/${id}`, { method: "DELETE" }),
  exportSongs: () => downloadDirect("/admin/song-pool/export.csv", "song-pool.csv"),
  importSongs: (file: File) => {
    const form = new FormData();
    form.set("file", file);
    return apiRequest<{ message: string; updated: number }>("/admin/song-pool/import.csv", { method: "POST", body: form });
  },

  myDraw: () => apiRequest<DrawAssignmentRead[]>("/draw/results"),
  drawMine: () => apiRequest<DrawAssignmentRead[]>("/draw/me", { method: "POST" }),
  runDraw: () => apiRequest<DrawAssignmentRead[]>("/admin/draw", { method: "POST" }),
  adminDrawResults: () => apiRequest<DrawAssignmentRead[]>("/admin/draw/results"),

  submissionTargets: () => apiRequest<SubmissionTargetsResponse>("/submissions/targets"),
  mySubmissions: () => apiRequest<StoredFileRead[]>("/submissions"),
  uploadSubmission: (songId: number, track: Track, file: File) => apiRequest<StoredFileRead>("/submissions", { method: "POST", body: submissionForm(file, songId, track) }),
  replaceSubmission: (id: number, track: Track, file: File) => apiRequest<StoredFileRead>(`/submissions/${id}/replace`, { method: "POST", body: submissionForm(file, undefined, track) }),
  updateSubmissionTrack: (id: number, track: Track) => apiRequest<StoredFileRead>(`/submissions/${id}/track`, { method: "PATCH", body: JSON.stringify({ track }) }),
  deleteSubmission: (id: number) => apiRequest<{ message: string }>(`/submissions/${id}`, { method: "DELETE" }),
  adminSubmissions: (track?: Track | "all") => apiRequest<StoredFileRead[]>(`/admin/submissions${track && track !== "all" ? `?track=${track}` : ""}`),
  replaceAdminSubmission: (id: number, file: File, track?: Track) => apiRequest<StoredFileRead>(`/admin/submissions/${id}/replace`, { method: "POST", body: submissionForm(file, undefined, track) }),
  deleteAdminSubmission: (id: number) => apiRequest<{ message: string }>(`/admin/submissions/${id}`, { method: "DELETE" }),
  downloadAdminSubmission: (id: number) => downloadPrepared(`/admin/submissions/${id}/download-metadata`),
  downloadAdminSubmissions: (ids?: number[], track?: Track | "all") => {
    const params = new URLSearchParams();
    if (ids?.length) params.set("ids", ids.join(","));
    if (track && track !== "all") params.set("track", track);
    return downloadPrepared(`/admin/submissions/download-metadata${params.size ? `?${params}` : ""}`);
  },

  guessCharts: () => apiRequest<GuessChartRead[]>("/guess-game/charts"),
  guessChart: (id: number) => apiRequest<GuessChartRead>(`/guess-game/charts/${id}`),
  downloadChart: (id: number) => downloadPrepared(`/guess-game/charts/${id}/download-metadata`),
  downloadCharts: (ids: number[]) => downloadPrepared(`/guess-game/charts/download-metadata?ids=${ids.join(",")}`),
  vote: (chart_id: number, vote_type: "love" | "funny") => apiRequest<{ message: string }>("/guess-game/vote", { method: "POST", body: JSON.stringify({ chart_id, vote_type }) }),
  unvote: (chart_id: number, vote_type: "love" | "funny") => apiRequest<{ message: string }>("/guess-game/vote", { method: "DELETE", body: JSON.stringify({ chart_id, vote_type }) }),
  comments: (chartId: number) => apiRequest<GuessCommentRead[]>(`/guess-game/charts/${chartId}/comments`),
  createComment: (chartId: number, content: string) => apiRequest<GuessCommentRead>(`/guess-game/charts/${chartId}/comments`, { method: "POST", body: JSON.stringify({ content }) }),
  authorGuess: (chartId: number) => apiRequest<AuthorGuessState>(`/guess-game/charts/${chartId}/author-guess`),
  saveAuthorGuess: (chartId: number, guessed_user_id: number) => apiRequest<{ message: string }>(`/guess-game/charts/${chartId}/author-guess`, { method: "PUT", body: JSON.stringify({ guessed_user_id }) }),
  clearAuthorGuess: (chartId: number) => apiRequest<{ message: string }>(`/guess-game/charts/${chartId}/author-guess`, { method: "DELETE" }),

  adminCharts: () => apiRequest<GuessChartRead[]>("/admin/guess-game/charts"),
  importCharts: (file: File) => {
    const form = new FormData();
    form.set("file", file);
    return apiRequest<{ archive_id: number; charts: GuessChartRead[] }>("/admin/guess-game/charts/import", { method: "POST", body: form });
  },
  updateChart: (id: number, payload: { title: string; author: string; designer: string; level: string; lane: string; guess_group_key: string; is_self_selected: boolean }) => apiRequest<GuessChartRead>(`/admin/guess-game/charts/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteChart: (id: number) => apiRequest<{ message: string }>(`/admin/guess-game/charts/${id}`, { method: "DELETE" }),
  parseSubmissions: () => apiRequest<GuessImportSummary>("/admin/guess-game/parse-submissions", { method: "POST" }),
  importIssues: () => apiRequest<GuessImportIssueRead[]>("/admin/guess-game/import-issues"),
  authorCandidates: () => apiRequest<AuthorCandidateAdmin[]>("/admin/guess-game/author-candidates"),
  saveAuthorCandidates: (rows: Array<{ user_id: number; display_id: string }>) => apiRequest<{ message: string; count: number }>("/admin/guess-game/author-candidates", { method: "PUT", body: JSON.stringify({ rows }) }),
  guessStats: (scope: "all" | "j") => apiRequest<GuessStats>(`/admin/guess-game/stats?scope=${scope}`),

  users: () => apiRequest<UserRead[]>("/admin/users"),
  updateUser: (id: number, payload: { identity: string; roles: string[]; display_name: string; is_active: boolean }) => apiRequest<UserRead>(`/admin/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  siteStats: () => apiRequest<Record<string, number>>("/admin/stats"),
};

export function formatMB(size: number): string {
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

export function formatTime(value?: string | null): string {
  if (!value) return "未设置";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
