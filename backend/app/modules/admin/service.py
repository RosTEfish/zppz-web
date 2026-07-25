from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import shutil
from threading import RLock
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import ADMIN_ROLE, OWNER_ROLE
from app.models import (
    DrawAssignment,
    Event,
    EventPhase,
    EventPhaseSnapshot,
    EventSetting,
    AdminGuessArchive,
    GuessAuthorCandidate,
    GuessAuthorGuess,
    GuessChart,
    GuessComment,
    GuessVote,
    ImportIssue,
    JTrackSubmission,
    PreviewBundle,
    Role,
    Song,
    Submission,
    SubmissionUploadIntent,
    SwapRequest,
    SwapRequestItem,
    SwapRound,
    SwapExcludedSong,
    User,
    UserRole,
    UserSession,
)
from app.modules.submissions.service import drain_storage_deletions, enqueue_storage_deletion


logger = logging.getLogger(__name__)
RESET_LOCK = RLock()
RESET_CONFIRMATION = "清除全部数据"


@dataclass
class FileQuarantine:
    root: Path | None = None
    moved: list[tuple[Path, Path]] = field(default_factory=list)

    def stage(self) -> None:
        settings = get_settings()
        self.root = settings.data_dir / f".reset-quarantine-{uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        try:
            for source, relative in (
                (settings.uploads_dir / "events", Path("uploads") / "events"),
                (settings.assets_dir / "guess-covers", Path("assets") / "guess-covers"),
            ):
                if source.exists():
                    destination = self.root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(destination))
                    self.moved.append((source, destination))
                source.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.restore()
            raise

    def restore(self) -> None:
        for source, destination in reversed(self.moved):
            try:
                if source.exists():
                    shutil.rmtree(source)
                if destination.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destination), str(source))
            except OSError:
                logger.exception("Failed to restore reset quarantine path %s", source)
        self.moved.clear()
        self._remove_root()

    def finalize(self) -> list[str]:
        warnings: list[str] = []
        try:
            self._remove_root()
        except OSError as exc:
            warnings.append(f"临时文件清理失败：{exc}")
        return warnings

    def _remove_root(self) -> None:
        if self.root and self.root.exists():
            shutil.rmtree(self.root)
        self.root = None


def _delete_rows(db: Session, statement) -> int:
    result = db.execute(statement)
    return int(result.rowcount or 0)


def _prune_permissions_file(privileged_codes: set[str]) -> tuple[int, list[str]]:
    path = get_settings().data_dir / "permissions.json"
    if not path.exists():
        return 0, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return 0, [f"权限配置未清理：{exc}"]

    rows = payload.get("users")
    if not isinstance(rows, list):
        return 0, ["权限配置未清理：users 不是数组"]
    kept = [row for row in rows if isinstance(row, dict) and str(row.get("user_code") or "").strip() in privileged_codes]
    removed = len(rows) - len(kept)
    if removed == 0:
        return 0, []
    payload["users"] = kept
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        return 0, [f"权限配置未清理：{exc}"]
    return removed, []


def _reset_database(db: Session, current_event_id: int) -> dict[str, int]:
    event_ids = list(db.scalars(select(Event.id)).all())
    other_event_ids = [event_id for event_id in event_ids if event_id != current_event_id]

    chart_ids = list(db.scalars(select(GuessChart.id).where(GuessChart.event_id.in_(event_ids))).all()) if event_ids else []
    swap_round_ids = list(db.scalars(select(SwapRound.id).where(SwapRound.event_id.in_(event_ids))).all()) if event_ids else []
    request_ids = (
        list(db.scalars(select(SwapRequest.id).where(SwapRequest.round_id.in_(swap_round_ids))).all())
        if swap_round_ids
        else []
    )

    deleted: dict[str, int] = {}
    if request_ids:
        deleted["swap_request_items"] = _delete_rows(
            db,
            delete(SwapRequestItem).where(SwapRequestItem.request_id.in_(request_ids)),
        )
    else:
        deleted["swap_request_items"] = 0
    if swap_round_ids:
        deleted["swap_requests"] = _delete_rows(db, delete(SwapRequest).where(SwapRequest.round_id.in_(swap_round_ids)))
        deleted["swap_rounds"] = _delete_rows(db, delete(SwapRound).where(SwapRound.id.in_(swap_round_ids)))
    else:
        deleted["swap_requests"] = 0
        deleted["swap_rounds"] = 0

    deleted["swap_excluded_songs"] = (
        _delete_rows(db, delete(SwapExcludedSong).where(SwapExcludedSong.event_id.in_(event_ids)))
        if event_ids
        else 0
    )
    deleted["event_phase_snapshots"] = (
        _delete_rows(db, delete(EventPhaseSnapshot).where(EventPhaseSnapshot.event_id.in_(event_ids)))
        if event_ids
        else 0
    )

    if chart_ids:
        deleted["guess_votes"] = _delete_rows(db, delete(GuessVote).where(GuessVote.chart_id.in_(chart_ids)))
        deleted["guess_comments"] = _delete_rows(db, delete(GuessComment).where(GuessComment.chart_id.in_(chart_ids)))
        deleted["guess_author_guesses"] = _delete_rows(
            db,
            delete(GuessAuthorGuess).where(GuessAuthorGuess.chart_id.in_(chart_ids)),
        )
    else:
        deleted["guess_votes"] = 0
        deleted["guess_comments"] = 0
        deleted["guess_author_guesses"] = 0

    deleted["guess_charts"] = (
        _delete_rows(db, delete(GuessChart).where(GuessChart.id.in_(chart_ids))) if chart_ids else 0
    )
    deleted["guess_author_candidates"] = (
        _delete_rows(db, delete(GuessAuthorCandidate).where(GuessAuthorCandidate.event_id.in_(event_ids)))
        if event_ids
        else 0
    )
    deleted["import_issues"] = (
        _delete_rows(db, delete(ImportIssue).where(ImportIssue.event_id.in_(event_ids))) if event_ids else 0
    )
    deleted["submission_upload_intents"] = (
        _delete_rows(db, delete(SubmissionUploadIntent).where(SubmissionUploadIntent.event_id.in_(event_ids)))
        if event_ids
        else 0
    )
    deleted["preview_bundles"] = (
        _delete_rows(db, delete(PreviewBundle).where(PreviewBundle.event_id.in_(event_ids)))
        if event_ids
        else 0
    )
    deleted["submissions"] = (
        _delete_rows(db, delete(Submission).where(Submission.event_id.in_(event_ids))) if event_ids else 0
    )
    deleted["j_track_submissions"] = (
        _delete_rows(db, delete(JTrackSubmission).where(JTrackSubmission.event_id.in_(event_ids))) if event_ids else 0
    )
    deleted["admin_guess_archives"] = (
        _delete_rows(db, delete(AdminGuessArchive).where(AdminGuessArchive.event_id.in_(event_ids)))
        if event_ids
        else 0
    )
    deleted["draw_assignments"] = (
        _delete_rows(db, delete(DrawAssignment).where(DrawAssignment.event_id.in_(event_ids))) if event_ids else 0
    )
    deleted["songs"] = _delete_rows(db, delete(Song).where(Song.event_id.in_(event_ids))) if event_ids else 0
    deleted["event_phases"] = (
        _delete_rows(db, delete(EventPhase).where(EventPhase.event_id.in_(event_ids))) if event_ids else 0
    )
    deleted["event_settings"] = (
        _delete_rows(db, delete(EventSetting).where(EventSetting.event_id.in_(event_ids))) if event_ids else 0
    )
    if other_event_ids:
        deleted["events"] = _delete_rows(db, delete(Event).where(Event.id.in_(other_event_ids)))
    else:
        deleted["events"] = 0

    db.add(
        EventSetting(
            event_id=current_event_id,
            phase_mode="manual",
            manual_phase="registration",
        )
    )

    admin_ids = list(
        db.scalars(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name.in_((ADMIN_ROLE, OWNER_ROLE)))
        ).all()
    )
    deleted["sessions"] = _delete_rows(db, delete(UserSession))
    if admin_ids:
        non_admin_user_ids = list(db.scalars(select(User.id).where(User.id.not_in(admin_ids))).all())
    else:
        non_admin_user_ids = list(db.scalars(select(User.id)).all())
    if non_admin_user_ids:
        deleted["user_roles"] = _delete_rows(db, delete(UserRole).where(UserRole.user_id.in_(non_admin_user_ids)))
        deleted["users"] = _delete_rows(db, delete(User).where(User.id.in_(non_admin_user_ids)))
    else:
        deleted["user_roles"] = 0
        deleted["users"] = 0
    return deleted


def reset_all_data(db: Session) -> dict:
    with RESET_LOCK:
        current_event = db.scalar(select(Event).where(Event.is_current.is_(True)))
        if current_event is None:
            raise RuntimeError("当前赛事不存在")
        current_event_id = current_event.id
        current_event_name = current_event.name
        current_event_slug = current_event.slug
        quarantine = FileQuarantine()
        quarantine.stage()
        try:
            submission_objects = list(
                db.execute(
                    select(Submission.storage_path, Submission.public_storage_path).where(
                        Submission.event_id.in_(select(Event.id))
                    )
                ).all()
            )
            for storage_path, public_storage_path in submission_objects:
                enqueue_storage_deletion(db, storage_path)
                enqueue_storage_deletion(db, public_storage_path)
            preview_objects = list(
                db.execute(
                    select(
                        PreviewBundle.maidata_key,
                        PreviewBundle.track_key,
                        PreviewBundle.background_key,
                        PreviewBundle.video_key,
                    ).where(PreviewBundle.event_id.in_(select(Event.id)))
                ).all()
            )
            for keys in preview_objects:
                for object_key in keys:
                    enqueue_storage_deletion(db, object_key)
            admin_archive_objects = list(
                db.scalars(
                    select(AdminGuessArchive.storage_path).where(
                        AdminGuessArchive.event_id.in_(select(Event.id))
                    )
                ).all()
            )
            for object_key in admin_archive_objects:
                enqueue_storage_deletion(db, object_key)
            pending_objects = list(
                db.scalars(
                    select(SubmissionUploadIntent.object_key).where(
                        SubmissionUploadIntent.event_id.in_(select(Event.id))
                    )
                ).all()
            )
            for object_key in pending_objects:
                enqueue_storage_deletion(db, object_key)
            deleted = _reset_database(db, current_event_id)
            db.commit()
        except Exception:
            db.rollback()
            quarantine.restore()
            raise

        warnings = quarantine.finalize()
        drain_storage_deletions(db)
        privileged_codes = set(
            db.scalars(
                select(User.user_code)
                .join(User.roles)
                .where(Role.name.in_((ADMIN_ROLE, OWNER_ROLE)))
            ).all()
        )
        removed_permission_rows, permission_warnings = _prune_permissions_file(privileged_codes)
        warnings.extend(permission_warnings)
        deleted["permissions_users"] = removed_permission_rows
        return {
            "message": "全部数据已清除，当前赛事已重置为报名阶段",
            "event_id": current_event_id,
            "event_name": current_event_name,
            "event_slug": current_event_slug,
            "deleted": deleted,
            "file_cleanup_warnings": warnings,
        }
