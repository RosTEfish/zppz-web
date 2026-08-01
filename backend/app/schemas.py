from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


EventPhaseName = Literal[
    "registration",
    "submission_1",
    "submission_2",
    "guess",
]


class ApiMessage(BaseModel):
    message: str


class UserRead(BaseModel):
    id: int
    user_code: str
    qq_id: str
    identity: str
    display_name: str = ""
    roles: list[str] = []
    is_admin: bool = False
    is_owner: bool = False
    is_pool_editor: bool = False
    is_active: bool = True


class RegisterRequest(BaseModel):
    user_code: str = Field(min_length=2, max_length=64)
    qq_id: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    identity: str = "audience"


class LoginRequest(BaseModel):
    user_code: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class UpdateProfileRequest(BaseModel):
    display_name: str
    identity: Literal["participant", "audience"]

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_display_name(cls, value):
        if not isinstance(value, str):
            raise ValueError("显示名必须是文本")
        normalized = value.strip()
        if not normalized:
            raise ValueError("显示名不能为空")
        if len(normalized) > 100:
            raise ValueError("显示名不能超过 100 个字符")
        return normalized


class AuthResponse(BaseModel):
    user: UserRead


class EventSettingsRead(BaseModel):
    participant_song_limit: int
    audience_song_limit: int
    draw_songs_per_participant: int
    true_love_vote_limit_below_14: int
    true_love_vote_limit_at_least_14: int
    funny_vote_limit: int
    announcement_text: str
    phase_mode: Literal["auto", "manual"] = "auto"
    manual_phase: EventPhaseName | None = None

    model_config = {"from_attributes": True}


class EventRead(BaseModel):
    id: int
    name: str
    slug: str
    is_current: bool
    settings: EventSettingsRead

    model_config = {"from_attributes": True}


class BootstrapRead(BaseModel):
    event: EventRead
    user: UserRead | None = None


class EventUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    participant_song_limit: int = Field(ge=0, le=50)
    audience_song_limit: int = Field(ge=0, le=50)
    draw_songs_per_participant: int = Field(ge=1, le=10)
    true_love_vote_limit_below_14: int = Field(ge=0, le=50)
    true_love_vote_limit_at_least_14: int = Field(ge=0, le=50)
    funny_vote_limit: int = Field(ge=0, le=50)
    announcement_text: str = ""
    model_config = {"extra": "forbid"}


class GuessAvailabilityRead(BaseModel):
    available: bool


class EventPhaseWrite(BaseModel):
    phase: EventPhaseName
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_window(self):
        starts_at = self.starts_at if self.starts_at.tzinfo is None else self.starts_at.astimezone(timezone.utc).replace(tzinfo=None)
        ends_at = self.ends_at if self.ends_at.tzinfo is None else self.ends_at.astimezone(timezone.utc).replace(tzinfo=None)
        if starts_at >= ends_at:
            raise ValueError("starts_at must be earlier than ends_at")
        return self


class EventPhaseRead(EventPhaseWrite):
    id: int

    model_config = {"from_attributes": True}


class EventPhaseSnapshotRead(BaseModel):
    id: int
    original_phase: str
    starts_at: datetime
    ends_at: datetime
    source_id: int | None = None
    migration_revision: str
    created_at: datetime | None = None


class PhaseCapabilitiesRead(BaseModel):
    song_pool_edit: bool = False
    submission: bool = False
    swap: bool = False
    normal_submission_public: bool = False
    author_guess: bool = False
    quality_vote: bool = False


class EventPhasesUpdate(BaseModel):
    phase_mode: Literal["auto", "manual"] = "auto"
    manual_phase: EventPhaseName | None = None
    phases: list[EventPhaseWrite]

    @model_validator(mode="after")
    def validate_manual_phase(self):
        if self.phase_mode == "manual" and self.manual_phase is None:
            raise ValueError("manual_phase is required in manual mode")
        if self.phase_mode == "auto" and self.manual_phase is not None:
            raise ValueError("manual_phase must be null in auto mode")
        return self


class EventPhasesRead(BaseModel):
    event_id: int
    phase_mode: Literal["auto", "manual"]
    manual_phase: EventPhaseName | None = None
    active_phase: EventPhaseName | None = None
    timezone: str = "Asia/Shanghai"
    server_time: datetime
    next_transition_at: datetime | None = None
    phases: list[EventPhaseRead]
    phase_snapshots: list[EventPhaseSnapshotRead] = Field(default_factory=list)
    capabilities: PhaseCapabilitiesRead


class SongCreate(BaseModel):
    song_name: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=100)
    song_type: str = Field(default="A", max_length=1)
    remark: str = Field(default="", max_length=500)
    acknowledge_ban_warning: bool = False


class BanCheckRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=200)


class BanMatchRead(BaseModel):
    entry_id: int
    title: str
    artist: str
    round: str
    note: str = ""
    match_type: str
    score: float | None = None
    reason: str


class BanCheckResponse(BaseModel):
    status: str
    matches: list[BanMatchRead] = Field(default_factory=list)
    import_id: int | None = None


class BanSearchResponse(BaseModel):
    items: list[BanMatchRead] = Field(default_factory=list)
    import_id: int | None = None


class BanEntryRead(BaseModel):
    id: int
    round: str
    title: str
    artist: str
    note: str = ""


class BanImportRead(BaseModel):
    id: int
    file_name: str
    file_sha256: str
    status: str
    entry_count: int
    issue_count: int
    uploaded_by_id: int | None = None
    published_at: datetime | None = None
    created_at: datetime


class BanImportPreview(BanImportRead):
    entries: list[BanEntryRead] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class BanAliasCreate(BaseModel):
    entry_id: int
    title: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=200)


class SongRead(BaseModel):
    id: int
    song_name: str
    artist: str
    song_type: str
    remark: str
    submitter: UserRead | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DrawAssignmentRead(BaseModel):
    id: int
    assigned_to: UserRead
    song: SongRead
    status: str = "active"
    draw_kind: str = "initial"
    replaces_assignment_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class StoredFileRead(BaseModel):
    id: int
    file_name: str
    file_size: int
    review_status: str
    review_note: str
    source_kind: str = ""
    track: str = "normal"
    track_duration_seconds: float | None = None
    is_long_track: bool = False
    public_package_ready: bool = False
    public_package_status: Literal["processing", "ready", "failed"] = "processing"
    public_package_message: str = ""
    validation: dict[str, bool] = Field(default_factory=dict)
    preview_status: Literal["processing", "ready", "unsupported", "failed"] | None = None
    preview_message: str = ""
    video_status: Literal["none", "processing", "ready", "failed"] = "none"
    video_message: str = ""
    source_song: SongRead | None = None
    user: UserRead | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SubmissionUploadIntentCreate(BaseModel):
    song_id: int | None = None
    submission_id: int | None = None
    track: Literal["normal", "j", "exhibition"] = "normal"
    file_name: str = Field(min_length=1, max_length=255)
    file_size: int = Field(gt=0)
    content_type: str = Field(min_length=1, max_length=100)
    acknowledge_ban_warning: bool = False


class AdminSubmissionUploadIntentCreate(BaseModel):
    track: Literal["normal", "j", "exhibition"] | None = None
    file_name: str = Field(min_length=1, max_length=255)
    file_size: int = Field(gt=0)
    content_type: str = Field(min_length=1, max_length=100)


class SubmissionUploadIntentRead(BaseModel):
    id: str
    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    expires_at: datetime


class SubmissionProcessingJobRead(BaseModel):
    id: str
    intent_id: str | None = None
    status: Literal["queued", "processing", "completed", "failed", "cancelled"]
    stage: Literal[
        "uploaded",
        "validating",
        "accepted",
        "preview_core",
        "public_package",
        "video",
        "cleanup",
        "complete",
    ]
    message: str = ""
    file_name: str
    file_size: int
    source_song_id: int | None = None
    replace_submission_id: int | None = None
    submission: StoredFileRead | None = None
    created_at: datetime
    updated_at: datetime


class SubmissionTargetRead(BaseModel):
    song: SongRead
    source_kind: str
    submission: StoredFileRead | None = None


class SubmissionTargetsResponse(BaseModel):
    is_open: bool
    targets: list[SubmissionTargetRead]


class SubmissionTrackUpdate(BaseModel):
    track: str = Field(pattern="^(normal|j|exhibition)$")


class SwapSelectionUpdate(BaseModel):
    assignment_ids: list[int] = Field(min_length=1)

    @field_validator("assignment_ids")
    @classmethod
    def assignment_ids_are_unique(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("assignment_ids must be unique")
        return value


class SwapItemRead(BaseModel):
    id: int
    position: int
    original: DrawAssignmentRead
    replacement: DrawAssignmentRead | None = None

    model_config = {"from_attributes": True}


class SwapAssignmentRead(DrawAssignmentRead):
    can_swap: bool = False
    has_submission: bool = False


class SwapRollRead(BaseModel):
    id: int
    round_id: int | None = None
    status: str
    created_at: datetime
    items: list[SwapItemRead] = Field(default_factory=list)


class SwapOverviewRead(BaseModel):
    round_id: int | None = None
    round_number: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    round_status: str | None = None
    round_kind: str | None = None
    roll_count: int = 0
    assignments: list[SwapAssignmentRead] = Field(default_factory=list)
    last_roll: SwapRollRead | None = None


class SwapValidationRead(BaseModel):
    valid: bool
    request_count: int = 0
    item_count: int = 0
    available_song_count: int = 0
    errors: list[str] = Field(default_factory=list)


class DownloadPreparation(BaseModel):
    download_url: str
    file_name: str
    file_size: int


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class BatchDeleteResponse(BaseModel):
    deleted: int
    message: str


class AdminResetRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=100)


class AdminResetResponse(BaseModel):
    message: str
    event_id: int
    event_name: str
    event_slug: str
    deleted: dict[str, int] = Field(default_factory=dict)
    file_cleanup_warnings: list[str] = Field(default_factory=list)


class GuessChartCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=100)
    designer: str = Field(default="", max_length=200)
    level: str = Field(min_length=1, max_length=20)
    lane: str = "normal"
    guess_group_key: str = ""
    is_self_selected: bool = False


class GuessChartRead(BaseModel):
    id: int
    title: str
    author: str
    designer: str
    level: str
    lane: str
    guess_group_key: str
    source_submission_type: str
    source_submission_id: int | None
    source_level_slot: str
    cover_path: str
    storage_path: str
    is_self_selected: bool
    plays: int
    created_at: datetime
    love_votes: int = 0
    funny_votes: int = 0
    my_votes: list[str] = []
    love_vote_bucket: Literal["below_14", "at_least_14"]
    can_preview: bool = False

    model_config = {"from_attributes": True}


class PublicGuessChartRead(BaseModel):
    id: int
    title: str
    author: str
    designer: str
    level: str
    lane: str
    guess_group_key: str
    source_submission_type: str
    source_level_slot: str
    cover_path: str
    is_self_selected: bool
    plays: int
    created_at: datetime
    track_duration_seconds: float | None = None
    is_long_track: bool = False
    can_download: bool = True
    can_vote: bool = False
    can_comment: bool = False
    can_author_guess: bool = False
    can_preview: bool = False
    love_votes: int = 0
    funny_votes: int = 0
    my_votes: list[str] = Field(default_factory=list)
    love_vote_bucket: Literal["below_14", "at_least_14"]

    model_config = {"from_attributes": True}


class AdminGuessChartRead(GuessChartRead):
    track_duration_seconds: float | None = None
    is_long_track: bool = False


class PreviewLevelRead(BaseModel):
    slot: int = Field(ge=1, le=7)
    difficulty_index: int = Field(ge=0, le=6)
    level: str


class PreviewAssetsRead(BaseModel):
    maidata_url: str
    track_url: str
    background_url: str
    video_url: str | None = None


class PreviewManifestRead(BaseModel):
    status: Literal["ready", "processing", "unsupported", "failed"]
    message: str
    source_version: str
    expires_at: datetime | None = None
    selected_level_slot: int | None = None
    levels: list[PreviewLevelRead] = Field(default_factory=list)
    assets: PreviewAssetsRead | None = None
    player_url: str = ""
    player_origin: str = ""


class VoteRequest(BaseModel):
    chart_id: int
    vote_type: str


class LoveVoteQuotaBucketRead(BaseModel):
    used: int
    limit: int
    remaining: int


class LoveVoteQuotaRead(BaseModel):
    below_14: LoveVoteQuotaBucketRead
    at_least_14: LoveVoteQuotaBucketRead


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class GuessCommentRead(BaseModel):
    id: int
    content: str
    user: UserRead
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthorGuessRequest(BaseModel):
    guessed_user_id: int


class AuthorCandidateInput(BaseModel):
    user_id: int
    display_id: str = Field(default="", max_length=64)


class AuthorCandidatesUpdate(BaseModel):
    rows: list[AuthorCandidateInput]


class AdminUserUpdate(BaseModel):
    identity: Literal["participant", "audience"]
    roles: list[str]
    display_name: str = ""
    is_active: bool = True


class ResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str = Field(min_length=6, max_length=128)
