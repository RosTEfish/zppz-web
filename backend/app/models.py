from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
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


class EventSetting(Base, TimestampMixin):
    __tablename__ = "event_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), unique=True, nullable=False)
    participant_song_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    audience_song_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    draw_songs_per_participant: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    true_love_vote_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    funny_vote_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    announcement_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    registration_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submission_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    guess_game_open_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submissions_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    guess_chart_metadata_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    event: Mapped[Event] = relationship(back_populates="settings")


class Song(Base, TimestampMixin):
    __tablename__ = "songs"

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
    __table_args__ = (UniqueConstraint("event_id", "song_id", name="uq_draw_event_song"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    assigned_to_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"), index=True, nullable=False)

    assigned_to: Mapped[User] = relationship(foreign_keys=[assigned_to_id])
    song: Mapped[Song] = relationship()


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", "source_song_id", name="uq_submission_event_user_song"),
        Index(
            "uq_submission_event_user_j_track",
            "event_id",
            "user_id",
            unique=True,
            postgresql_where=text("track = 'j'"),
            sqlite_where=text("track = 'j'"),
        ),
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
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="approved", nullable=False)
    review_note: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    user: Mapped[User] = relationship()
    source_song: Mapped[Song | None] = relationship()


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
    __table_args__ = (UniqueConstraint("chart_id", "user_id", "vote_type", name="uq_guess_vote_chart_user_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chart_id: Mapped[int] = mapped_column(ForeignKey("guess_charts.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    vote_type: Mapped[str] = mapped_column(String(20), nullable=False)


class GuessComment(Base, TimestampMixin):
    __tablename__ = "guess_comments"

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
