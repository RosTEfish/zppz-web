export type Track = "normal" | "j" | "exhibition";
export type EventPhaseName = "registration" | "draw" | "submission_1" | "swap" | "submission_2" | "guess";

export interface PhaseCapabilities {
  song_pool_edit: boolean;
  draw: boolean;
  submission: boolean;
  swap: boolean;
  normal_submission_public: boolean;
  author_guess: boolean;
  quality_vote: boolean;
}

export interface EventPhaseWindow {
  phase: EventPhaseName;
  starts_at: string;
  ends_at: string;
}

export interface EventPhasesRead {
  phase_mode: "auto" | "manual";
  manual_phase?: EventPhaseName | null;
  active_phase: EventPhaseName | null;
  phases: EventPhaseWindow[];
  capabilities: PhaseCapabilities;
  next_transition_at?: string | null;
  /** UTC timestamp captured by the API, used to correct an inaccurate client clock. */
  server_time?: string;
}

export interface EventPhasesUpdate {
  phase_mode: "auto" | "manual";
  manual_phase?: EventPhaseName | null;
  phases: EventPhaseWindow[];
}

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
  settings: EventSettingsRead;
}

export interface EventSettingsRead {
  participant_song_limit: number;
  audience_song_limit: number;
  draw_songs_per_participant: number;
  true_love_vote_limit_below_14: number;
  true_love_vote_limit_at_least_14: number;
  funny_vote_limit: number;
  announcement_text: string;
}

export interface EventUpdatePayload {
  name: string;
  participant_song_limit: number;
  audience_song_limit: number;
  draw_songs_per_participant: number;
  true_love_vote_limit_below_14: number;
  true_love_vote_limit_at_least_14: number;
  funny_vote_limit: number;
  announcement_text: string;
}

export interface BootstrapRead {
  event: EventRead;
  user: UserRead | null;
}

export interface GuessAvailabilityRead {
  available: boolean;
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
  acknowledge_ban_warning?: boolean;
}

export type BanCheckStatus = "exact" | "review" | "clear" | "unavailable";

export interface BanMatchRead {
  entry_id: number;
  title: string;
  artist: string;
  round: string;
  note: string;
  match_type: "exact" | "fuzzy" | "alias" | string;
  score?: number | null;
  reason: string;
}

export interface BanCheckRead {
  status: BanCheckStatus;
  matches: BanMatchRead[];
  import_id?: number | null;
}

export interface BanSearchRead {
  items: BanMatchRead[];
  import_id?: number | null;
}

export interface BanImportRead {
  id: number;
  file_name: string;
  file_sha256: string;
  status: "draft" | "published" | "superseded" | string;
  entry_count: number;
  issue_count: number;
  uploaded_by_id?: number | null;
  published_at?: string | null;
  created_at: string;
}

export interface BanImportPreviewRead extends BanImportRead {
  entries: Array<{ id: number; round: string; title: string; artist: string; note: string }>;
  issues: string[];
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
  track_duration_seconds?: number | null;
  public_package_ready?: boolean;
  validation?: { maidata: boolean; track: boolean; background: boolean; duration: boolean };
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
  status?: "active" | "returned" | "replaced";
  draw_kind?: "initial" | "swap";
  replaces_assignment_id?: number | null;
}

export interface SwapMeRead {
  is_open: boolean;
  active_phase: EventPhaseName | null;
  max_selections: number;
  round?: { id: number; status: string; starts_at: string; ends_at: string; finalized_at?: string | null } | null;
  request?: { id: number; status: string; assignment_ids: number[] } | null;
  assignments: Array<DrawAssignmentRead & { selected: boolean }>;
  results: Array<{ original: DrawAssignmentRead; replacement?: DrawAssignmentRead | null }>;
}

export interface SwapValidationRead {
  ok: boolean;
  message: string;
  request_count?: number;
  item_count?: number;
  pool_size?: number;
}

export interface SwapAuditAssignmentRead {
  id: number;
  song: SongRead;
  status: "active" | "returned" | "replaced" | string;
  draw_kind: "initial" | "swap" | string;
  created_at: string;
}

export interface SwapAuditItemRead {
  position: number;
  original: SwapAuditAssignmentRead;
  replacement?: SwapAuditAssignmentRead | null;
}

export interface SwapAuditRequestRead {
  id: number;
  user: UserRead;
  status: string;
  error_message: string;
  items: SwapAuditItemRead[];
}

export interface SwapAuditRoundRead {
  id: number;
  status: string;
  starts_at: string;
  ends_at: string;
  random_seed?: string;
  finalized_at?: string | null;
}

export interface SwapAuditRead {
  round: SwapAuditRoundRead | null;
  requests: SwapAuditRequestRead[];
  message?: string;
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
  source_level_slot?: string;
  cover_path: string;
  storage_path?: string;
  is_self_selected: boolean;
  plays: number;
  created_at: string;
  love_votes: number;
  funny_votes: number;
  my_votes: string[];
  love_vote_bucket: LoveVoteBucket;
  track_duration_seconds?: number | null;
  is_long_track?: boolean;
  can_download?: boolean;
  can_vote?: boolean;
  can_comment?: boolean;
  can_author_guess?: boolean;
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

export interface DesignerGuessOverview {
  can_guess: boolean;
  candidates: Array<{ user_id: number; display_id: string }>;
  states: Array<{ chart_id: number; guessed_user_id?: number | null }>;
}

export interface BatchDeleteResponse {
  deleted: number;
  message: string;
}

export interface AdminResetResponse {
  message: string;
  event_id: number;
  event_name: string;
  event_slug: string;
  deleted: Record<string, number>;
  file_cleanup_warnings: string[];
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
  author_stats: Array<Record<string, unknown>>;
  guess_details?: Array<Record<string, unknown>>;
}

export interface GuessStatsDetails {
  items: Array<Record<string, unknown>>;
  total: number;
  limit: number;
  offset: number;
}

export interface VoteMutationResponse {
  message: string;
  vote_counts?: { love: number; funny: number };
  my_votes?: string[];
  love_vote_quota?: LoveVoteQuotaRead;
}

export type LoveVoteBucket = "below_14" | "at_least_14";

export interface LoveVoteQuotaTier {
  used: number;
  limit: number;
  remaining: number;
}

export interface LoveVoteQuotaRead {
  below_14: LoveVoteQuotaTier;
  at_least_14: LoveVoteQuotaTier;
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

function submissionForm(file: File, songId?: number, track?: Track, acknowledgeBanWarning = false): FormData {
  const form = new FormData();
  form.set("file", file);
  if (songId !== undefined) form.set("song_id", String(songId));
  if (track) form.set("track", track);
  if (acknowledgeBanWarning) form.set("acknowledge_ban_warning", "true");
  return form;
}

export const api = {
  bootstrap: () => apiRequest<BootstrapRead>("/bootstrap"),
  login: (user_code: string, password: string) => apiRequest<{ user: UserRead }>("/auth/login", { method: "POST", body: JSON.stringify({ user_code, password }) }),
  register: (user_code: string, qq_id: string, password: string, identity = "audience") => apiRequest<{ user: UserRead }>("/auth/register", { method: "POST", body: JSON.stringify({ user_code, qq_id, password, identity }) }),
  logout: () => apiRequest<{ message: string }>("/auth/logout", { method: "POST" }),
  changePassword: (old_password: string, new_password: string) => apiRequest<{ message: string }>("/auth/change-password", { method: "POST", body: JSON.stringify({ old_password, new_password }) }),
  currentEvent: () => apiRequest<EventRead>("/events/current"),
  updateEvent: (payload: EventUpdatePayload) => apiRequest<EventRead>("/admin/events/current", { method: "PUT", body: JSON.stringify(payload) }),
  resetAllData: (confirmation: string) => apiRequest<AdminResetResponse>("/admin/reset", { method: "POST", body: JSON.stringify({ confirmation }) }),
  eventPhases: () => apiRequest<EventPhasesRead>("/event/phases"),
  updateEventPhases: (payload: EventPhasesUpdate) => apiRequest<EventPhasesRead>("/admin/event/phases", { method: "PUT", body: JSON.stringify(payload) }),
  guessAvailability: () => apiRequest<GuessAvailabilityRead>("/guess-game/availability"),

  mySongs: (signal?: AbortSignal) => apiRequest<SongRead[]>("/song-pool/me", { signal }),
  createSong: (payload: SongPayload) => apiRequest<SongRead>("/song-pool/me", { method: "POST", body: JSON.stringify(payload) }),
  updateMySong: (id: number, payload: SongPayload) => apiRequest<SongRead>(`/song-pool/me/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteSong: (id: number) => apiRequest<{ message: string }>(`/song-pool/me/${id}`, { method: "DELETE" }),
  adminSongs: (signal?: AbortSignal) => apiRequest<SongRead[]>("/admin/song-pool", { signal }),
  updateSong: (id: number, payload: SongPayload) => apiRequest<SongRead>(`/admin/song-pool/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteAdminSong: (id: number) => apiRequest<{ message: string }>(`/admin/song-pool/${id}`, { method: "DELETE" }),
  batchDeleteAdminSongs: (ids: number[]) => apiRequest<BatchDeleteResponse>("/admin/song-pool/batch-delete", { method: "POST", body: JSON.stringify({ ids }) }),
  exportSongs: () => downloadDirect("/admin/song-pool/export.csv", "song-pool.csv"),
  importSongs: (file: File) => {
    const form = new FormData();
    form.set("file", file);
    return apiRequest<{ message: string; updated: number }>("/admin/song-pool/import.csv", { method: "POST", body: form });
  },
  checkBan: (title: string, artist: string, signal?: AbortSignal) => apiRequest<BanCheckRead>("/banlist/check", { method: "POST", body: JSON.stringify({ title, artist }), signal }),
  searchBan: (title: string, artist: string, signal?: AbortSignal) => {
    const params = new URLSearchParams();
    if (title.trim()) params.set("title", title.trim());
    if (artist.trim()) params.set("artist", artist.trim());
    return apiRequest<BanSearchRead>(`/banlist/search?${params.toString()}`, { signal });
  },
  adminBanlistImports: (signal?: AbortSignal) => apiRequest<BanImportRead[]>("/admin/banlist", { signal }),
  importBanlist: (file: File) => {
    const form = new FormData();
    form.set("file", file);
    return apiRequest<BanImportPreviewRead>("/admin/banlist/import", { method: "POST", body: form });
  },
  previewBanlist: (id: number) => apiRequest<BanImportPreviewRead>(`/admin/banlist/${id}/preview`),
  publishBanlist: (id: number) => apiRequest<BanImportRead>(`/admin/banlist/${id}/publish`, { method: "POST" }),
  addBanAlias: (entry_id: number, title: string, artist: string) => apiRequest<{ message: string; entry_id: number }>("/admin/banlist/aliases", { method: "POST", body: JSON.stringify({ entry_id, title, artist }) }),

  myDraw: (signal?: AbortSignal) => apiRequest<DrawAssignmentRead[]>("/draw/results", { signal }),
  drawMine: () => apiRequest<DrawAssignmentRead[]>("/draw/me", { method: "POST" }),
  runDraw: () => apiRequest<DrawAssignmentRead[]>("/admin/draw", { method: "POST" }),
  adminDrawResults: (signal?: AbortSignal) => apiRequest<DrawAssignmentRead[]>("/admin/draw/results", { signal }),
  mySwap: (signal?: AbortSignal) => apiRequest<SwapMeRead>("/swap/me", { signal }),
  updateMySwap: (assignment_ids: number[]) => apiRequest<SwapMeRead>("/swap/me", { method: "PUT", body: JSON.stringify({ assignment_ids }) }),
  cancelMySwap: () => apiRequest<SwapMeRead>("/swap/me", { method: "DELETE" }),
  validateSwaps: () => apiRequest<SwapValidationRead>("/admin/swap/validate", { method: "POST" }),
  finalizeSwaps: () => apiRequest<SwapAuditRead>("/admin/swap/finalize", { method: "POST" }),
  rejectSwapRequest: (requestId: number) => apiRequest<SwapAuditRead>(`/admin/swap/requests/${requestId}/reject`, { method: "POST" }),
  swapAudit: (signal?: AbortSignal) => apiRequest<SwapAuditRead>("/admin/swap/audit", { signal }),

  submissionTargets: (signal?: AbortSignal) => apiRequest<SubmissionTargetsResponse>("/submissions/targets", { signal }),
  mySubmissions: (signal?: AbortSignal) => apiRequest<StoredFileRead[]>("/submissions", { signal }),
  uploadSubmission: (songId: number, track: Track, file: File, acknowledgeBanWarning = false) => apiRequest<StoredFileRead>("/submissions", { method: "POST", body: submissionForm(file, songId, track, acknowledgeBanWarning) }),
  uploadExhibition: (file: File, acknowledgeBanWarning = false) => apiRequest<StoredFileRead>("/submissions", { method: "POST", body: submissionForm(file, undefined, "exhibition", acknowledgeBanWarning) }),
  replaceSubmission: (id: number, track: Track, file: File, acknowledgeBanWarning = false) => apiRequest<StoredFileRead>(`/submissions/${id}/replace`, { method: "POST", body: submissionForm(file, undefined, track, acknowledgeBanWarning) }),
  updateSubmissionTrack: (id: number, track: Track) => apiRequest<StoredFileRead>(`/submissions/${id}/track`, { method: "PATCH", body: JSON.stringify({ track }) }),
  deleteSubmission: (id: number) => apiRequest<{ message: string }>(`/submissions/${id}`, { method: "DELETE" }),
  adminSubmissions: (track?: Track | "all", signal?: AbortSignal) => apiRequest<StoredFileRead[]>(`/admin/submissions${track && track !== "all" ? `?track=${track}` : ""}`, { signal }),
  replaceAdminSubmission: (id: number, file: File, track?: Track) => apiRequest<StoredFileRead>(`/admin/submissions/${id}/replace`, { method: "POST", body: submissionForm(file, undefined, track) }),
  deleteAdminSubmission: (id: number) => apiRequest<{ message: string }>(`/admin/submissions/${id}`, { method: "DELETE" }),
  batchDeleteAdminSubmissions: (ids: number[]) => apiRequest<BatchDeleteResponse>("/admin/submissions/batch-delete", { method: "POST", body: JSON.stringify({ ids }) }),
  downloadAdminSubmission: (id: number) => downloadPrepared(`/admin/submissions/${id}/download-metadata`),
  downloadAdminSubmissions: (ids?: number[], track?: Track | "all") => {
    const params = new URLSearchParams();
    if (ids?.length) params.set("ids", ids.join(","));
    if (track && track !== "all") params.set("track", track);
    return downloadPrepared(`/admin/submissions/download-metadata${params.size ? `?${params}` : ""}`);
  },

  guessCharts: (signal?: AbortSignal) => apiRequest<GuessChartRead[]>("/guess-game/charts", { signal }),
  loveVoteQuota: (signal?: AbortSignal) => apiRequest<LoveVoteQuotaRead>("/guess-game/vote-quota", { signal }),
  guessChart: (id: number) => apiRequest<GuessChartRead>(`/guess-game/charts/${id}`),
  downloadChart: (id: number) => downloadPrepared(`/guess-game/charts/${id}/download-metadata`),
  downloadCharts: (ids: number[]) => downloadPrepared(`/guess-game/charts/download-metadata?ids=${ids.join(",")}`),
  vote: (chart_id: number, vote_type: "love" | "funny") => apiRequest<VoteMutationResponse>("/guess-game/vote", { method: "POST", body: JSON.stringify({ chart_id, vote_type }) }),
  unvote: (chart_id: number, vote_type: "love" | "funny") => apiRequest<VoteMutationResponse>("/guess-game/vote", { method: "DELETE", body: JSON.stringify({ chart_id, vote_type }) }),
  comments: (chartId: number) => apiRequest<GuessCommentRead[]>(`/guess-game/charts/${chartId}/comments`),
  createComment: (chartId: number, content: string) => apiRequest<GuessCommentRead>(`/guess-game/charts/${chartId}/comments`, { method: "POST", body: JSON.stringify({ content }) }),
  authorGuess: (chartId: number) => apiRequest<AuthorGuessState>(`/guess-game/charts/${chartId}/author-guess`),
  saveAuthorGuess: (chartId: number, guessed_user_id: number) => apiRequest<{ message: string }>(`/guess-game/charts/${chartId}/author-guess`, { method: "PUT", body: JSON.stringify({ guessed_user_id }) }),
  clearAuthorGuess: (chartId: number) => apiRequest<{ message: string }>(`/guess-game/charts/${chartId}/author-guess`, { method: "DELETE" }),
  designerGuesses: (signal?: AbortSignal) => apiRequest<DesignerGuessOverview>("/guess-game/designer-guesses", { signal }),
  saveDesignerGuess: (chartId: number, guessed_user_id: number) => apiRequest<{ message: string }>(`/guess-game/charts/${chartId}/designer-guess`, { method: "PUT", body: JSON.stringify({ guessed_user_id }) }),
  clearDesignerGuess: (chartId: number) => apiRequest<{ message: string }>(`/guess-game/charts/${chartId}/designer-guess`, { method: "DELETE" }),

  adminCharts: (signal?: AbortSignal) => apiRequest<GuessChartRead[]>("/admin/guess-game/charts", { signal }),
  importCharts: (file: File) => {
    const form = new FormData();
    form.set("file", file);
    return apiRequest<{ archive_id: number; charts: GuessChartRead[] }>("/admin/guess-game/charts/import", { method: "POST", body: form });
  },
  updateChart: (id: number, payload: { title: string; author: string; designer: string; level: string; lane: string; guess_group_key: string; is_self_selected: boolean }) => apiRequest<GuessChartRead>(`/admin/guess-game/charts/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteChart: (id: number) => apiRequest<{ message: string }>(`/admin/guess-game/charts/${id}`, { method: "DELETE" }),
  batchDeleteAdminCharts: (ids: number[]) => apiRequest<BatchDeleteResponse>("/admin/guess-game/charts/batch-delete", { method: "POST", body: JSON.stringify({ ids }) }),
  parseSubmissions: () => apiRequest<GuessImportSummary>("/admin/guess-game/parse-submissions", { method: "POST" }),
  importIssues: (signal?: AbortSignal) => apiRequest<GuessImportIssueRead[]>("/admin/guess-game/import-issues", { signal }),
  authorCandidates: (signal?: AbortSignal) => apiRequest<AuthorCandidateAdmin[]>("/admin/guess-game/author-candidates", { signal }),
  saveAuthorCandidates: (rows: Array<{ user_id: number; display_id: string }>) => apiRequest<{ message: string; count: number }>("/admin/guess-game/author-candidates", { method: "PUT", body: JSON.stringify({ rows }) }),
  guessStats: (scope: "all" | "j", includeDetails = true, signal?: AbortSignal) => apiRequest<GuessStats>(`/admin/guess-game/stats?scope=${scope}&include_details=${includeDetails}`, { signal }),
  guessStatsDetails: (scope: "all" | "j", limit = 50, offset = 0, signal?: AbortSignal) => apiRequest<GuessStatsDetails>(`/admin/guess-game/stats/details?scope=${scope}&limit=${limit}&offset=${offset}`, { signal }),

  users: (signal?: AbortSignal) => apiRequest<UserRead[]>("/admin/users", { signal }),
  updateUser: (id: number, payload: { identity: string; roles: string[]; display_name: string; is_active: boolean }) => apiRequest<UserRead>(`/admin/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  siteStats: (signal?: AbortSignal) => apiRequest<Record<string, number>>("/admin/stats", { signal }),
};

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
