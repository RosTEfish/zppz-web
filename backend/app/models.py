from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)

    users: Mapped[list["User"]] = relationship(secondary="user_roles", back_populates="roles")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    qq_id: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    identity: Mapped[str] = mapped_column(String(20), default="audience", nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    roles: Mapped[list[Role]] = relationship(secondary="user_roles", back_populates="users")

    def has_role(self, role: str) -> bool:
        return any(item.name == role for item in self.roles)


class UserSession(Base, TimestampMixin):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_expires_at", "expires_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped[User] = relationship()


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)

    settings: Mapped["EventSetting"] = relationship(back_populates="event", uselist=False, cascade="all, delete-orphan")
    phases: Mapped[list["EventPhase"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="EventPhase.starts_at"
    )
    swap_rounds: Mapped[list["SwapRound"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="SwapRound.round_number"
    )


class EventSetting(Base, TimestampMixin):
    __tablename__ = "event_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), unique=True, nullable=False)
    participant_song_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    audience_song_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    draw_songs_per_participant: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    true_love_vote_limit_below_14: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    true_love_vote_limit_at_least_14: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    funny_vote_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    announcement_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    guess_chart_metadata_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    phase_mode: Mapped[str] = mapped_column(String(10), default="auto", nullable=False)
    manual_phase: Mapped[str | None] = mapped_column(String(30), nullable=True)

    event: Mapped[Event] = relationship(back_populates="settings")


class EventPhase(Base, TimestampMixin):
    __tablename__ = "event_phases"
    __table_args__ = (UniqueConstraint("event_id", "phase", name="uq_event_phase_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    phase: Mapped[str] = mapped_column(String(30), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    event: Mapped[Event] = relationship(back_populates="phases")


class Song(Base, TimestampMixin):
    __tablename__ = "songs"
    __table_args__ = (Index("ix_songs_event_submitter", "event_id", "submitted_by_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    song_name: Mapped[str] = mapped_column(String(200), nullable=False)
    artist: Mapped[str] = mapped_column(String(100), nullable=False)
    song_type: Mapped[str] = mapped_column(String(1), default="A", nullable=False)
    remark: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    submitter: Mapped[User] = relationship()


class DrawAssignment(Base, TimestampMixin):
    __tablename__ = "draw_assignments"
    __table_args__ = (
        Index(
            "uq_draw_event_active_song",
            "event_id",
            "song_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index("ix_draw_assignments_event_assignee_status", "event_id", "assigned_to_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    assigned_to_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    draw_kind: Mapped[str] = mapped_column(String(20), default="initial", nullable=False)
    replaces_assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("draw_assignments.id", ondelete="SET NULL"), index=True, nullable=True
    )

    assigned_to: Mapped[User] = relationship(foreign_keys=[assigned_to_id])
    song: Mapped[Song] = relationship()
    replaces_assignment: Mapped["DrawAssignment | None"] = relationship(
        remote_side="DrawAssignment.id", foreign_keys=[replaces_assignment_id]
    )


class SwapRound(Base, TimestampMixin):
    __tablename__ = "swap_rounds"
    __table_args__ = (
        UniqueConstraint("event_id", "round_number", name="uq_swap_round_event_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    random_seed: Mapped[str] = mapped_column(String(128), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    event: Mapped[Event] = relationship(back_populates="swap_rounds")
    requests: Mapped[list["SwapRequest"]] = relationship(back_populates="round", cascade="all, delete-orphan")


class SwapRequest(Base, TimestampMixin):
    __tablename__ = "swap_requests"
    __table_args__ = (UniqueConstraint("round_id", "user_id", name="uq_swap_request_round_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("swap_rounds.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error_message: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    round: Mapped[SwapRound] = relationship(back_populates="requests")
    user: Mapped[User] = relationship()
    items: Mapped[list["SwapRequestItem"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="SwapRequestItem.position"
    )


class SwapRequestItem(Base, TimestampMixin):
    __tablename__ = "swap_request_items"
    __table_args__ = (
        UniqueConstraint("request_id", "original_assignment_id", name="uq_swap_item_request_assignment"),
        UniqueConstraint("request_id", "position", name="uq_swap_item_request_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("swap_requests.id", ondelete="CASCADE"), index=True, nullable=False)
    original_assignment_id: Mapped[int] = mapped_column(
        ForeignKey("draw_assignments.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    replacement_assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("draw_assignments.id", ondelete="SET NULL"), index=True, nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    request: Mapped[SwapRequest] = relationship(back_populates="items")
    original_assignment: Mapped[DrawAssignment] = relationship(foreign_keys=[original_assignment_id])
    replacement_assignment: Mapped[DrawAssignment | None] = relationship(foreign_keys=[replacement_assignment_id])


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", "source_song_id", name="uq_submission_event_user_song"),
        CheckConstraint(
            "track IN ('normal', 'j', 'exhibition')",
            name="ck_submission_track_type",
        ),
        CheckConstraint(
            "track = 'exhibition' OR source_song_id IS NOT NULL",
            name="ck_submission_source_song_required",
        ),
        Index(
            "uq_submission_event_user_j_track",
            "event_id",
            "user_id",
            unique=True,
            postgresql_where=text("track = 'j'"),
            sqlite_where=text("track = 'j'"),
        ),
        Index("ix_submissions_event_user_track", "event_id", "user_id", "track"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    source_song_id: Mapped[int | None] = mapped_column(
        ForeignKey("songs.id", ondelete="RESTRICT", name="fk_submissions_source_song_id"),
        index=True,
        nullable=True,
    )
    source_kind: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    track: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    public_storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    track_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="approved", nullable=False)
    review_note: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    user: Mapped[User] = relationship()
    source_song: Mapped[Song | None] = relationship()

    @property
    def is_long_track(self) -> bool:
        return self.track_duration_seconds is not None and self.track_duration_seconds > 240


class JTrackSubmission(Base, TimestampMixin):
    __tablename__ = "j_track_submissions"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_j_track_event_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped[User] = relationship()


class AdminGuessArchive(Base, TimestampMixin):
    __tablename__ = "admin_guess_archives"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)

    uploaded_by: Mapped[User | None] = relationship()


class GuessChart(Base, TimestampMixin):
    __tablename__ = "guess_charts"
    __table_args__ = (
        Index(
            "ix_guess_charts_event_source",
            "event_id",
            "source_submission_type",
            "source_submission_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    designer: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    lane: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    guess_group_key: Mapped[str] = mapped_column(String(300), default="", index=True, nullable=False)
    source_submission_type: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    source_submission_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_level_slot: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    cover_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    is_self_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    plays: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GuessVote(Base, TimestampMixin):
    __tablename__ = "guess_votes"
    __table_args__ = (
        UniqueConstraint("chart_id", "user_id", "vote_type", name="uq_guess_vote_chart_user_type"),
        Index("ix_guess_votes_user_type", "user_id", "vote_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chart_id: Mapped[int] = mapped_column(ForeignKey("guess_charts.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    vote_type: Mapped[str] = mapped_column(String(20), nullable=False)


class GuessComment(Base, TimestampMixin):
    __tablename__ = "guess_comments"
    __table_args__ = (Index("ix_guess_comments_chart_created", "chart_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chart_id: Mapped[int] = mapped_column(ForeignKey("guess_charts.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    content: Mapped[str] = mapped_column(String(500), nullable=False)

    user: Mapped[User] = relationship()


class GuessAuthorCandidate(Base, TimestampMixin):
    __tablename__ = "guess_author_candidates"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_author_candidate_event_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    display_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    user: Mapped[User] = relationship()


class GuessAuthorGuess(Base, TimestampMixin):
    __tablename__ = "guess_author_guesses"
    __table_args__ = (UniqueConstraint("chart_id", "user_id", name="uq_author_guess_chart_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chart_id: Mapped[int] = mapped_column(ForeignKey("guess_charts.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    guessed_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)


class ImportIssue(Base, TimestampMixin):
    __tablename__ = "import_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
