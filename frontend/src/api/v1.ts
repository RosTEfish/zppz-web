import type { components } from "./generated";
import { apiRequest } from "./base";
import { downloadDirect, downloadPrepared } from "./downloads";
import { uploadSubmissionThroughIntent } from "./uploads";
import type { SubmissionUploadOptions } from "./uploads";
import type { Identity } from "../identity";
export { apiRequest } from "./base";
export { ApiError } from "./client";
export type { components as OpenApiComponents, paths as OpenApiPaths } from "./generated";
export { formatDuration, formatMB, formatTime } from "./format";
export { submissionContentType } from "./uploads";
export type { SubmissionUploadOptions, SubmissionUploadProgress } from "./uploads";

export type Track = "normal" | "j" | "exhibition";
export type EventPhaseName = "registration" | "submission_1" | "submission_2" | "guess";

export type PhaseCapabilities = components["schemas"]["PhaseCapabilitiesRead"];
export type EventPhaseWindow = components["schemas"]["EventPhaseRead"];
export type EventPhaseSnapshotRead = components["schemas"]["EventPhaseSnapshotRead"];
export type EventPhasesRead = components["schemas"]["EventPhasesRead"];
export type EventPhasesUpdate = components["schemas"]["EventPhasesUpdate"];

export type UserRead = components["schemas"]["UserRead"];
export type EventRead = components["schemas"]["EventRead"];
export type EventSettingsRead = components["schemas"]["EventSettingsRead"];

export interface WebhookEndpointRead {
  id: string;
  callback_url: string;
  events: Array<"chart.published" | "chart.updated">;
  schema_version: number;
  status: string;
  activated_at?: string | null;
  verified_at?: string | null;
  consecutive_failures: number;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  last_error: string;
}

export interface WebhookIntegrationRead {
  id: string;
  name: string;
  token_prefix: string;
  is_active: boolean;
  created_at: string;
  revoked_at?: string | null;
  endpoint?: WebhookEndpointRead | null;
  pending_deliveries: number;
  failed_deliveries: number;
}

export interface WebhookCredentialsRead {
  integration_id: string;
  integration_token: string;
  webhook_secret: string;
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

export type BootstrapRead = components["schemas"]["BootstrapRead"];
export type PaginatedStoredFilesRead = components["schemas"]["PaginatedStoredFilesRead"];
export type GuessAvailabilityRead = components["schemas"]["GuessAvailabilityRead"];
export type DownloadPreparation = components["schemas"]["DownloadPreparation"];

export type SubmissionUploadIntent = components["schemas"]["SubmissionUploadIntentRead"];
export type SubmissionProcessingJob = components["schemas"]["SubmissionProcessingJobRead"];

export type SongRead = components["schemas"]["SongRead"];

export interface SongPayload {
  song_name: string;
  artist: string;
  song_type?: string;
  remark: string;
  acknowledge_ban_warning?: boolean;
}

export type BanCheckStatus = "exact" | "review" | "clear" | "unavailable";

export type BanMatchRead = components["schemas"]["BanMatchRead"];
export type BanCheckRead = Omit<components["schemas"]["BanCheckResponse"], "status"> & { status: BanCheckStatus };
export type BanSearchRead = components["schemas"]["BanSearchResponse"];
export type BanImportRead = components["schemas"]["BanImportRead"];
export type BanImportPreviewRead = components["schemas"]["BanImportPreview"];
export type StoredFileRead = components["schemas"]["StoredFileRead"];
export type SubmissionTargetRead = components["schemas"]["SubmissionTargetRead"];
export type SubmissionTargetsResponse = components["schemas"]["SubmissionTargetsResponse"];

export interface DrawAssignmentRead {
  id: number;
  assigned_to: UserRead;
  song: SongRead;
  created_at: string;
  status?: "active" | "returned" | "replaced";
  draw_kind?: "initial" | "swap";
  replaces_assignment_id?: number | null;
}

export interface SwapAssignmentRead extends DrawAssignmentRead {
  selected: boolean;
  can_swap: boolean;
  has_submission: boolean;
}

export interface AdminDrawStatsRead {
  assignments: number;
  assigned_users: number;
  has_submission: boolean;
  can_redraw: boolean;
}

export interface SwapRollItemRead {
  id: number;
  position: number;
  original: DrawAssignmentRead;
  replacement?: DrawAssignmentRead | null;
}

export interface SwapRollRead {
  id: number;
  round_id?: number;
  status: string;
  created_at: string;
  items: SwapRollItemRead[];
}

export interface SwapMeRead {
  is_open: boolean;
  active_phase: EventPhaseName | null;
  round?: {
    id: number;
    status: string;
    round_kind: string;
    starts_at: string;
    ends_at: string;
    roll_count: number;
    finalized_at?: string | null;
  } | null;
  assignments: SwapAssignmentRead[];
  last_roll?: SwapRollRead | null;
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
  round_id?: number;
  user: UserRead;
  status: string;
  created_at?: string;
  items: SwapAuditItemRead[];
}

export interface SwapAuditRoundRead {
  id: number;
  status: string;
  round_kind: string;
  starts_at: string;
  ends_at: string;
  random_seed?: string;
  finalized_at?: string | null;
  roll_count: number;
}

export interface SwapAuditRead {
  round: SwapAuditRoundRead | null;
  rounds: SwapAuditRoundRead[];
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
  can_preview?: boolean;
}

export type PreviewStatus = "ready" | "processing" | "unsupported" | "failed";

export interface PreviewManifest {
  status: PreviewStatus;
  message: string;
  source_version: string;
  expires_at: string | null;
  selected_level_slot: number | null;
  levels: Array<{ slot: number; difficulty_index: number; level: string }>;
  assets: null | {
    maidata_url: string;
    track_url: string;
    background_url: string;
    video_url: string | null;
  };
  player_url: string;
  player_origin: string;
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

export const api = {
  bootstrap: (options?: RequestInit) => apiRequest<BootstrapRead>("/bootstrap", options),
  login: (user_code: string, password: string) => apiRequest<{ user: UserRead }>("/auth/login", { method: "POST", body: JSON.stringify({ user_code, password }) }),
  register: (user_code: string, qq_id: string, password: string, identity = "audience") => apiRequest<{ user: UserRead }>("/auth/register", { method: "POST", body: JSON.stringify({ user_code, qq_id, password, identity }) }),
  logout: () => apiRequest<{ message: string }>("/auth/logout", { method: "POST" }),
  updateProfile: (display_name: string, identity: Identity) => apiRequest<{ user: UserRead }>("/auth/me", { method: "PUT", body: JSON.stringify({ display_name, identity }) }),
  changePassword: (old_password: string, new_password: string) => apiRequest<{ message: string }>("/auth/change-password", { method: "POST", body: JSON.stringify({ old_password, new_password }) }),
  currentEvent: (options?: RequestInit) => apiRequest<EventRead>("/events/current", options),
  updateEvent: (payload: EventUpdatePayload) => apiRequest<EventRead>("/admin/events/current", { method: "PUT", body: JSON.stringify(payload) }),
  resetAllData: (confirmation: string) => apiRequest<AdminResetResponse>("/admin/reset", { method: "POST", body: JSON.stringify({ confirmation }) }),
  eventPhases: (options?: RequestInit) => apiRequest<EventPhasesRead>("/event/phases", options),
  updateEventPhases: (payload: EventPhasesUpdate) => apiRequest<EventPhasesRead>("/admin/event/phases", { method: "PUT", body: JSON.stringify(payload) }),
  guessAvailability: (options?: RequestInit) => apiRequest<GuessAvailabilityRead>("/guess-game/availability", options),

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
  runDraw: () => apiRequest<DrawAssignmentRead[]>("/admin/draw", { method: "POST" }),
  adminDrawResults: (signal?: AbortSignal) => apiRequest<DrawAssignmentRead[]>("/admin/draw/results", { signal }),
  adminDrawStats: (signal?: AbortSignal) => apiRequest<AdminDrawStatsRead>("/admin/draw/stats", { signal }),
  mySwap: (signal?: AbortSignal) => apiRequest<SwapMeRead>("/swap/me", { signal }),
  rollMySwap: (assignment_ids: number[]) => apiRequest<SwapMeRead>("/swap/me/roll", { method: "POST", body: JSON.stringify({ assignment_ids }) }),
  swapAudit: (signal?: AbortSignal) => apiRequest<SwapAuditRead>("/admin/swap/audit", { signal }),

  submissionTargets: (signal?: AbortSignal) => apiRequest<SubmissionTargetsResponse>("/submissions/targets", { signal }),
  mySubmissions: (signal?: AbortSignal) => apiRequest<StoredFileRead[]>("/submissions", { signal }),
  uploadSubmission: (songId: number, track: Track, file: File, acknowledgeBanWarning = false, options?: SubmissionUploadOptions) => uploadSubmissionThroughIntent({ song_id: songId, track, acknowledge_ban_warning: acknowledgeBanWarning }, file, undefined, options),
  uploadExhibition: (file: File, acknowledgeBanWarning = false, options?: SubmissionUploadOptions) => uploadSubmissionThroughIntent({ track: "exhibition", acknowledge_ban_warning: acknowledgeBanWarning }, file, undefined, options),
  replaceSubmission: (id: number, track: Track, file: File, acknowledgeBanWarning = false, options?: SubmissionUploadOptions) => uploadSubmissionThroughIntent({ submission_id: id, track, acknowledge_ban_warning: acknowledgeBanWarning }, file, undefined, options),
  submissionProcessingJobs: (signal?: AbortSignal) => apiRequest<SubmissionProcessingJob[]>("/submissions/processing-jobs", { cache: "no-store", signal }),
  updateSubmissionTrack: (id: number, track: Track) => apiRequest<StoredFileRead>(`/submissions/${id}/track`, { method: "PATCH", body: JSON.stringify({ track }) }),
  deleteSubmission: (id: number) => apiRequest<{ message: string }>(`/submissions/${id}`, { method: "DELETE" }),
  submissionPreviewManifest: (id: number, signal?: AbortSignal) => apiRequest<PreviewManifest>(`/submissions/${id}/preview-manifest`, { signal }),
  downloadSubmission: (id: number) => downloadPrepared(`/submissions/${id}/download-metadata`),
  adminSubmissions: (track?: Track | "all", limit = 50, offset = 0, signal?: AbortSignal) => {
    const params = new URLSearchParams();
    if (track && track !== "all") params.set("track", track);
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    return apiRequest<PaginatedStoredFilesRead>(`/admin/submissions?${params.toString()}`, { signal });
  },
  replaceAdminSubmission: (id: number, file: File, track?: Track, options?: SubmissionUploadOptions) => uploadSubmissionThroughIntent({ track }, file, id, options),
  adminSubmissionProcessingJobs: (signal?: AbortSignal) => apiRequest<SubmissionProcessingJob[]>("/admin/submissions/processing-jobs", { cache: "no-store", signal }),
  rebuildSubmissionResources: (id: number) => apiRequest<SubmissionProcessingJob>(`/admin/submissions/${id}/resources/rebuild`, { method: "POST" }),
  deleteAdminSubmission: (id: number) => apiRequest<{ message: string }>(`/admin/submissions/${id}`, { method: "DELETE" }),
  batchDeleteAdminSubmissions: (ids: number[]) => apiRequest<BatchDeleteResponse>("/admin/submissions/batch-delete", { method: "POST", body: JSON.stringify({ ids }) }),
  downloadAdminSubmission: (id: number) => downloadPrepared(`/admin/submissions/${id}/download-metadata`),
  rebuildSubmissionPreview: (id: number) => apiRequest<PreviewManifest>(`/admin/submissions/${id}/preview/rebuild`, { method: "POST" }),
  downloadAdminSubmissions: (ids?: number[], track?: Track | "all") => {
    const params = new URLSearchParams();
    if (ids?.length) params.set("ids", ids.join(","));
    if (track && track !== "all") params.set("track", track);
    return downloadPrepared(`/admin/submissions/download-metadata${params.size ? `?${params}` : ""}`, true);
  },

  guessCharts: (signal?: AbortSignal) => apiRequest<GuessChartRead[]>("/guess-game/charts", { signal }),
  loveVoteQuota: (signal?: AbortSignal) => apiRequest<LoveVoteQuotaRead>("/guess-game/vote-quota", { signal }),
  guessChart: (id: number) => apiRequest<GuessChartRead>(`/guess-game/charts/${id}`),
  downloadChart: (id: number) => downloadPrepared(`/guess-game/charts/${id}/download-metadata`),
  guessPreviewManifest: (id: number, signal?: AbortSignal) => apiRequest<PreviewManifest>(`/guess-game/charts/${id}/preview-manifest`, { signal }),
  downloadCharts: (ids: number[]) => downloadPrepared(`/guess-game/charts/download-metadata?ids=${ids.join(",")}`, true),
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

  webhookIntegrations: (signal?: AbortSignal) => apiRequest<WebhookIntegrationRead[]>("/admin/webhook-integrations", { signal }),
  createWebhookIntegration: (name: string) => apiRequest<WebhookCredentialsRead>("/admin/webhook-integrations", { method: "POST", body: JSON.stringify({ name }) }),
  rotateWebhookCredentials: (id: string) => apiRequest<WebhookCredentialsRead>(`/admin/webhook-integrations/${id}/rotate-credentials`, { method: "POST" }),
  testWebhookIntegration: (id: string) => apiRequest<{ event_id: string; status: string }>(`/admin/webhook-integrations/${id}/test`, { method: "POST" }),
  retryWebhookDeliveries: (id: string) => apiRequest<{ message: string; retried: number }>(`/admin/webhook-integrations/${id}/retry-failed`, { method: "POST" }),
  revokeWebhookIntegration: (id: string) => apiRequest<void>(`/admin/webhook-integrations/${id}`, { method: "DELETE" }),

  users: (signal?: AbortSignal) => apiRequest<UserRead[]>("/admin/users", { signal }),
  updateUser: (id: number, payload: { identity: string; roles: string[]; display_name: string; is_active: boolean }) => apiRequest<UserRead>(`/admin/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  siteStats: (signal?: AbortSignal) => apiRequest<Record<string, number>>("/admin/stats", { signal }),
};
