from datetime import datetime

from pydantic import BaseModel, Field


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

    model_config = {"from_attributes": True}


class EventRead(BaseModel):
    id: int
    name: str
    slug: str
    is_current: bool
    settings: EventSettingsRead

    model_config = {"from_attributes": True}


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
    created_at: datetime

    model_config = {"from_attributes": True}


class StoredFileRead(BaseModel):
    id: int
    file_name: str
    file_size: int
    review_status: str
    review_note: str
    user: UserRead | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GuessChartCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=100)
    level: str = Field(min_length=1, max_length=20)
    lane: str = "normal"
    guess_group_key: str = ""
    is_self_selected: bool = False


class GuessChartRead(BaseModel):
    id: int
    title: str
    author: str
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


class AdminUserUpdate(BaseModel):
    identity: str
    roles: list[str]
    display_name: str = ""
    is_active: bool = True


class ResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str = Field(min_length=6, max_length=128)

