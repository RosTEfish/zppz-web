from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


EventPhaseName = Literal[
    "registration",
    "draw",
    "submission_1",
    "swap",
    "submission_2",
    "guess",
    "reveal",
    "closed",
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


class AuthResponse(BaseModel):
    user: UserRead


class EventSettingsRead(BaseModel):
    participant_song_limit: int
    audience_song_limit: int
    draw_songs_per_participant: int
    true_love_vote_limit: int
    funny_vote_limit: int
    announcement_text: str
    registration_deadline: datetime | None = None
    submission_deadline: datetime | None = None
    guess_game_open_at: datetime | None = None
    submissions_open: bool = False
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
    true_love_vote_limit: int = Field(ge=0, le=50)
    funny_vote_limit: int = Field(ge=0, le=50)
    announcement_text: str = ""
    registration_deadline: datetime | None = None
    submission_deadline: datetime | None = None
    guess_game_open_at: datetime | None = None
    submissions_open: bool = False


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


class PhaseCapabilitiesRead(BaseModel):
    song_pool_edit: bool = False
    draw: bool = False
    submission: bool = False
    swap: bool = False
    normal_submission_public: bool = False
    author_guess: bool = False
    quality_vote: bool = False
    answers_visible: bool = False


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
    active_phase: EventPhaseName
    timezone: str = "Asia/Shanghai"
    server_time: datetime
    next_transition_at: datetime | None = None
    phases: list[EventPhaseRead]
    capabilities: PhaseCapabilitiesRead


class SongCreate(BaseModel):
    song_name: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=100)
    song_type: str = Field(default="A", max_length=1)
    remark: str = Field(default="", max_length=500)


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
    validation: dict[str, bool] = Field(default_factory=dict)
    source_song: SongRead | None = None
    user: UserRead | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


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
    assignment_ids: list[int] = Field(min_length=1, max_length=3)

    @field_validator("assignment_ids")
    @classmethod
    def assignment_ids_are_unique(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("assignment_ids must be unique")
        return value


class SwapItemRead(BaseModel):
    id: int
    position: int
    original_assignment: DrawAssignmentRead
    replacement_assignment: DrawAssignmentRead | None = None

    model_config = {"from_attributes": True}


class SwapOverviewRead(BaseModel):
    round_id: int | None = None
    round_number: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    round_status: str | None = None
    request_id: int | None = None
    request_status: str | None = None
    error_message: str = ""
    items: list[SwapItemRead] = Field(default_factory=list)


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

    model_config = {"from_attributes": True}


class PublicGuessChartRead(BaseModel):
    id: int
    title: str
    author: str
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
    love_votes: int = 0
    funny_votes: int = 0
    my_votes: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RevealedGuessChartRead(PublicGuessChartRead):
    designer: str


class AdminGuessChartRead(GuessChartRead):
    track_duration_seconds: float | None = None
    is_long_track: bool = False


class VoteRequest(BaseModel):
    chart_id: int
    vote_type: str


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
    identity: str
    roles: list[str]
    display_name: str = ""
    is_active: bool = True


class ResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str = Field(min_length=6, max_length=128)
