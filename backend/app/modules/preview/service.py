from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import AdminGuessArchive, GuessChart, PreviewBundle, Submission
from app.modules.guess_game.importer import (
    ArchiveParseError,
    ParsedArchive,
    extract_public_files,
    parse_archive,
)
from app.modules.object_storage import get_object_store, materialized_object
from app.modules.submissions.service import enqueue_storage_deletion


logger = logging.getLogger(__name__)
ASSET_FIELDS = ("maidata_key", "track_key", "background_key", "video_key")
MIME_FIELDS = ("maidata_mime", "track_mime", "background_mime", "video_mime")


def _source_prefix(source_type: str, source_id: int) -> str:
    folder = "submission" if source_type == "submission" else "admin-archive"
    return f"{folder}/{source_id}"


def _bundle(db: Session, event_id: int, source_type: str, source_id: int) -> PreviewBundle | None:
    return db.scalar(
        select(PreviewBundle).where(
            PreviewBundle.event_id == event_id,
            PreviewBundle.source_type == source_type,
            PreviewBundle.source_id == source_id,
        ).with_for_update()
    )


def _asset_keys(bundle: PreviewBundle) -> set[str]:
    return {
        value
        for field in ASSET_FIELDS
        if (value := getattr(bundle, field))
    }


def _clear_assets(bundle: PreviewBundle) -> None:
    for field in (*ASSET_FIELDS, *MIME_FIELDS):
        setattr(bundle, field, None)


def _normalized_files(parsed: ParsedArchive) -> tuple[str, str, str, str | None]:
    names = {member.output_name for member in parsed.public_files}
    track = next((name for name in names if name.startswith("track.")), "")
    background = next((name for name in names if name.startswith("bg.")), "")
    video = next((name for name in ("bg.mp4", "mv.mp4", "video.mp4") if name in names), None)
    return "maidata.txt", track, background, video


def create_processing_bundle(
    db: Session,
    *,
    event_id: int,
    source_type: str,
    source_id: int,
    source_storage_path: str,
    force: bool = False,
) -> tuple[PreviewBundle, bool]:
    bundle = _bundle(db, event_id, source_type, source_id)
    should_build = force or bundle is None or bundle.source_storage_path != source_storage_path
    if bundle is None:
        bundle = PreviewBundle(
            event_id=event_id,
            source_type=source_type,
            source_id=source_id,
            source_storage_path=source_storage_path,
            status="processing",
        )
        db.add(bundle)
        db.flush()
    elif should_build:
        bundle.source_storage_path = source_storage_path
        bundle.status = "processing"
        bundle.error_code = ""
        bundle.error_message = ""
    return bundle, should_build


def build_preview_bundle(
    db: Session,
    *,
    event_id: int,
    source_type: str,
    source_id: int,
    source_storage_path: str,
    parsed: ParsedArchive | None = None,
) -> PreviewBundle:
    settings = get_settings()
    bundle, _ = create_processing_bundle(
        db,
        event_id=event_id,
        source_type=source_type,
        source_id=source_id,
        source_storage_path=source_storage_path,
        force=True,
    )
    stale_keys = _asset_keys(bundle)
    created_keys: list[str] = []
    try:
        if not settings.preview_enabled:
            raise ArchiveParseError("在线预览当前未启用")
        if parsed is None:
            suffix = Path(source_storage_path).suffix.lower()
            with materialized_object(source_storage_path, suffix) as archive_path:
                parsed = parse_archive(archive_path)
                return _build_from_parsed(db, bundle, parsed, stale_keys, created_keys)
        return _build_from_parsed(db, bundle, parsed, stale_keys, created_keys)
    except ArchiveParseError as exc:
        for key in created_keys:
            try:
                get_object_store().delete(key)
            except Exception:
                logger.exception("Failed to remove incomplete preview object")
        for key in stale_keys:
            enqueue_storage_deletion(db, key)
        _clear_assets(bundle)
        message = str(exc)
        if "暂不支持在线预览" in message:
            bundle.status = "unsupported"
            bundle.error_code = "unsupported_format"
            bundle.error_message = message[:500]
        else:
            logger.warning(
                "Preview archive rejected for event=%s source=%s/%s: %s",
                event_id,
                source_type,
                source_id,
                message,
            )
            bundle.status = "failed"
            bundle.error_code = "preview_build_failed"
            bundle.error_message = "预览素材生成失败，请重新生成"
        return bundle
    except Exception:
        logger.exception(
            "Preview build failed for event=%s source=%s/%s",
            event_id,
            source_type,
            source_id,
        )
        for key in created_keys:
            try:
                get_object_store().delete(key)
            except Exception:
                logger.exception("Failed to remove incomplete preview object")
        for key in stale_keys:
            enqueue_storage_deletion(db, key)
        _clear_assets(bundle)
        bundle.status = "failed"
        bundle.error_code = "preview_build_failed"
        bundle.error_message = "预览素材生成失败，请稍后重试"
        return bundle


def _build_from_parsed(
    db: Session,
    bundle: PreviewBundle,
    parsed: ParsedArchive,
    stale_keys: set[str],
    created_keys: list[str],
) -> PreviewBundle:
    maidata_name, track_name, background_name, video_name = _normalized_files(parsed)
    if track_name != "track.mp3":
        raise ArchiveParseError("track.ogg 当前格式暂不支持在线预览")
    if background_name not in {"bg.png", "bg.jpg"}:
        raise ArchiveParseError("bg.webp 当前格式暂不支持在线预览")

    version = uuid4().hex
    prefix = (
        f"events/{bundle.event_id}/preview/"
        f"{_source_prefix(bundle.source_type, bundle.source_id)}/{version}"
    )
    content_types = {
        maidata_name: "text/plain; charset=utf-8",
        track_name: "audio/mpeg",
        background_name: "image/png" if background_name.endswith(".png") else "image/jpeg",
        video_name or "video.mp4": "video/mp4",
    }
    store = get_object_store()
    with TemporaryDirectory(prefix="zppz-preview-") as directory:
        files = extract_public_files(parsed, Path(directory))
        uploaded: dict[str, str] = {}
        for name in (maidata_name, track_name, background_name, video_name):
            if not name:
                continue
            key_name = (
                "maidata.txt"
                if name == maidata_name
                else "track.mp3"
                if name == track_name
                else f"bg{Path(name).suffix.lower()}"
                if name == background_name
                else "video.mp4"
            )
            key = f"{prefix}/{key_name}"
            store.put_file(key, files[name], content_type=content_types[name])
            created_keys.append(key)
            uploaded[name] = key

    for key in stale_keys - set(created_keys):
        enqueue_storage_deletion(db, key)
    bundle.status = "ready"
    bundle.maidata_key = uploaded[maidata_name]
    bundle.track_key = uploaded[track_name]
    bundle.background_key = uploaded[background_name]
    bundle.video_key = uploaded.get(video_name or "")
    bundle.maidata_mime = content_types[maidata_name]
    bundle.track_mime = content_types[track_name]
    bundle.background_mime = content_types[background_name]
    bundle.video_mime = content_types[video_name] if video_name else None
    bundle.error_code = ""
    bundle.error_message = ""
    return bundle


def delete_preview_bundle(db: Session, event_id: int, source_type: str, source_id: int) -> None:
    bundle = _bundle(db, event_id, source_type, source_id)
    if not bundle:
        return
    for key in _asset_keys(bundle):
        enqueue_storage_deletion(db, key)
    db.delete(bundle)


def commit_preview_nonfatal(db: Session, bundle: PreviewBundle) -> bool:
    """Commit preview state without turning a valid submission into a failed upload."""
    newly_referenced_keys = _asset_keys(bundle)
    identity = (bundle.event_id, bundle.source_type, bundle.source_id)
    try:
        db.commit()
        return True
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to persist preview bundle event=%s source=%s/%s",
            identity[0],
            identity[1],
            identity[2],
        )
        for key in newly_referenced_keys:
            try:
                get_object_store().delete(key)
            except Exception:
                logger.exception("Failed to clean uncommitted preview object")
        return False


def rebuild_preview_in_background(
    event_id: int,
    source_type: str,
    source_id: int,
    expected_storage_path: str,
) -> None:
    with SessionLocal() as db:
        source = (
            db.get(Submission, source_id)
            if source_type == "submission"
            else db.get(AdminGuessArchive, source_id)
        )
        if (
            source is None
            or source.event_id != event_id
            or source.storage_path != expected_storage_path
        ):
            return
        bundle = build_preview_bundle(
            db,
            event_id=event_id,
            source_type=source_type,
            source_id=source_id,
            source_storage_path=expected_storage_path,
        )
        commit_preview_nonfatal(db, bundle)


def preview_levels(
    db: Session,
    *,
    event_id: int,
    source_type: str,
    source_id: int,
) -> list[dict]:
    chart_source_types = {"normal", "j", "exhibition"} if source_type == "submission" else {"admin"}
    rows = db.execute(
        select(GuessChart.source_level_slot, GuessChart.level)
        .where(
            GuessChart.event_id == event_id,
            GuessChart.source_submission_type.in_(chart_source_types),
            GuessChart.source_submission_id == source_id,
        )
        .order_by(GuessChart.source_level_slot.asc())
    ).all()
    result = []
    for slot_value, level in rows:
        try:
            slot = int(slot_value)
        except (TypeError, ValueError):
            continue
        if 1 <= slot <= 7:
            result.append({"slot": slot, "difficulty_index": slot - 1, "level": level})
    return result


def _token(key: str, mime: str, expires_at: datetime) -> str:
    payload = json.dumps(
        {"key": key, "mime": mime, "exp": int(expires_at.timestamp())},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded = urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(get_settings().secret_key.encode(), encoded, hashlib.sha256).digest()
    return f"{encoded.decode()}.{urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def parse_local_asset_token(token: str) -> tuple[str, str]:
    try:
        encoded_text, signature_text = token.split(".", 1)
        encoded = encoded_text.encode()
        expected = hmac.new(get_settings().secret_key.encode(), encoded, hashlib.sha256).digest()
        supplied = urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError
        payload = json.loads(urlsafe_b64decode(encoded_text + "=" * (-len(encoded_text) % 4)))
        if int(payload["exp"]) < int(datetime.utcnow().timestamp()):
            raise TimeoutError
        return str(payload["key"]), str(payload["mime"])
    except TimeoutError:
        raise
    except Exception as exc:
        raise ValueError("invalid preview asset token") from exc


def manifest_payload(
    db: Session,
    bundle: PreviewBundle,
    *,
    base_url: str,
    selected_level_slot: int | None = None,
) -> dict:
    settings = get_settings()
    levels = preview_levels(
        db,
        event_id=bundle.event_id,
        source_type=bundle.source_type,
        source_id=bundle.source_id,
    )
    payload = {
        "status": bundle.status,
        "message": bundle.error_message or (
            "预览素材准备中" if bundle.status == "processing" else "预览已就绪"
        ),
        "source_version": hashlib.sha256(bundle.source_storage_path.encode()).hexdigest()[:16],
        "expires_at": None,
        "selected_level_slot": selected_level_slot,
        "levels": levels,
        "assets": None,
        "player_url": settings.preview_player_url,
        "player_origin": settings.preview_player_origin,
    }
    if bundle.status != "ready":
        return payload

    expires_at = datetime.utcnow() + timedelta(seconds=settings.preview_url_ttl_seconds)
    store = get_object_store()

    def asset_url(key: str | None, mime: str | None) -> str | None:
        if not key or not mime:
            return None
        direct = store.create_inline_url(key, mime, settings.preview_url_ttl_seconds)
        if direct:
            return direct
        return f"{base_url}{settings.api_prefix}/preview-assets/{_token(key, mime, expires_at)}"

    payload["expires_at"] = expires_at
    payload["assets"] = {
        "maidata_url": asset_url(bundle.maidata_key, bundle.maidata_mime),
        "track_url": asset_url(bundle.track_key, bundle.track_mime),
        "background_url": asset_url(bundle.background_key, bundle.background_mime),
        "video_url": asset_url(bundle.video_key, bundle.video_mime),
    }
    return payload
