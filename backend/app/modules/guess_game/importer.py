from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
from io import BytesIO
import stat
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from mutagen import File as MutagenFile

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AdminGuessArchive, GuessChart, ImportIssue, JTrackSubmission, Submission

try:
    import py7zr
except ImportError:  # pragma: no cover - exercised only in incomplete local installs
    py7zr = None

try:
    import rarfile
except ImportError:  # pragma: no cover - exercised only in incomplete local installs
    rarfile = None


SUPPORTED_ARCHIVE_SUFFIXES = {".zip", ".7z", ".rar"}
COVER_SUFFIXES = {".png", ".jpg", ".webp"}
AUDIO_SUFFIXES = {".mp3", ".ogg"}
LEVEL_PATTERN = re.compile(r"^&lv_([1-7])=(.+)$", re.IGNORECASE)
DESIGNER_PATTERN = re.compile(r"^&des([1-7])=(.*)$", re.IGNORECASE)
INOTE_PATTERN = re.compile(
    r"^&inote_([1-7])=(.*?)(?=^&[A-Za-z0-9_]+=|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
MAX_ARCHIVE_ENTRIES = 2048
MAX_MAIDATA_BYTES = 1024 * 1024
MAX_COVER_BYTES = 20 * 1024 * 1024
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


class ArchiveParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedLevel:
    slot: str
    level: str
    designer: str = ""


@dataclass(frozen=True)
class ImportWarning:
    issue_type: str
    message: str


@dataclass(frozen=True)
class ParsedArchive:
    title: str
    author: str
    levels: tuple[ParsedLevel, ...]
    cover_bytes: bytes | None = None
    cover_suffix: str = ""
    warnings: tuple[ImportWarning, ...] = ()
    track_duration_seconds: float = 0.0
    public_files: tuple[tuple[str, bytes], ...] = ()


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    new_cover_path: str = ""
    previous_cover_paths: set[str] = field(default_factory=set)

    @property
    def stale_cover_paths(self) -> set[str]:
        return self.previous_cover_paths - ({self.new_cover_path} if self.new_cover_path else set())


@dataclass
class RebuildResult:
    scanned: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    issues: int = 0

    def as_dict(self) -> dict[str, int | str]:
        return {
            "message": "投稿解析完成",
            "scanned": self.scanned,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "issues": self.issues,
        }


def normalize_group_key(title: str, author: str) -> str:
    return f"{title.strip().lower()}||{author.strip().lower()}"


def normalize_level(value: str) -> str:
    return re.sub(r"[\[\]【】()（）]", "", value).strip()


def decode_maidata(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "shift_jis", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ArchiveParseError("maidata.txt 编码无法识别")


def parse_maidata(text: str) -> tuple[str, str, tuple[ParsedLevel, ...]]:
    title = ""
    author = ""
    level_values: list[tuple[str, str]] = []
    global_designer = ""
    slot_designers: dict[str, str] = {}
    seen_slots: set[str] = set()
    playable_slots = {
        match.group(1)
        for match in INOTE_PATTERN.finditer(text)
        if match.group(2).strip()
    }

    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith("&title="):
            title = stripped.split("=", 1)[1].strip()
            continue
        if lowered.startswith("&artist="):
            author = stripped.split("=", 1)[1].strip()
            continue
        if lowered.startswith("&des="):
            global_designer = stripped.split("=", 1)[1].strip()
            continue

        designer_match = DESIGNER_PATTERN.match(stripped)
        if designer_match:
            slot_designers[designer_match.group(1)] = designer_match.group(2).strip()
            continue

        match = LEVEL_PATTERN.match(stripped)
        if not match or match.group(1) in seen_slots or match.group(1) not in playable_slots:
            continue
        level = normalize_level(match.group(2))
        if not level:
            continue
        seen_slots.add(match.group(1))
        level_values.append((match.group(1), level))

    if not title:
        raise ArchiveParseError("maidata.txt 缺少 &title= 字段")
    if not author:
        raise ArchiveParseError("maidata.txt 缺少 &artist= 字段")
    if not level_values:
        raise ArchiveParseError("maidata.txt 未找到同时包含难度和谱面内容的可生成条目")
    levels = tuple(
        ParsedLevel(
            slot=slot,
            level=level,
            designer=slot_designers.get(slot) or global_designer,
        )
        for slot, level in level_values
    )
    return title, author, levels


def _normalized_member_name(name: str) -> str:
    return str(name).replace("\\", "/")


def _validate_member_name(name: str) -> str:
    normalized = _normalized_member_name(name)
    path = PurePosixPath(normalized)
    if not normalized or "\x00" in normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ArchiveParseError("压缩包包含绝对路径")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ArchiveParseError("压缩包包含不安全路径")
    return normalized


def _member_sort_key(name: str) -> tuple[int, str]:
    normalized = _normalized_member_name(name)
    return len(PurePosixPath(normalized).parts), normalized.casefold()


def _select_members(names: list[str]) -> tuple[str, str, str]:
    if len(names) > MAX_ARCHIVE_ENTRIES:
        raise ArchiveParseError(f"压缩包文件数量不能超过 {MAX_ARCHIVE_ENTRIES}")

    normalized = [_validate_member_name(name) for name in names]
    maidata_names = [name for name in normalized if PurePosixPath(name).name.lower() == "maidata.txt"]
    if not maidata_names:
        raise ArchiveParseError("压缩包缺少 maidata.txt")
    maidata_name = min(maidata_names, key=_member_sort_key)

    cover_names = []
    track_names = []
    for name in normalized:
        basename = PurePosixPath(_normalized_member_name(name)).name
        path = Path(basename)
        if path.stem.lower() == "bg" and path.suffix.lower() in COVER_SUFFIXES:
            cover_names.append(name)
        if path.stem.lower() == "track" and path.suffix.lower() in AUDIO_SUFFIXES:
            track_names.append(name)
    if not cover_names:
        raise ArchiveParseError("压缩包缺少 bg.jpg、bg.png 或 bg.webp")
    if not track_names:
        raise ArchiveParseError("压缩包缺少 track.mp3 或 track.ogg")
    return maidata_name, min(track_names, key=_member_sort_key), min(cover_names, key=_member_sort_key)


def _validate_archive_sizes(entries: list[tuple[str, int, int]]) -> None:
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        raise ArchiveParseError(f"压缩包文件数量不能超过 {MAX_ARCHIVE_ENTRIES}")
    total = 0
    for name, unpacked, packed in entries:
        _validate_member_name(name)
        if unpacked < 0 or unpacked > MAX_MEMBER_BYTES:
            raise ArchiveParseError(f"{PurePosixPath(name).name} 大小超出限制")
        total += unpacked
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ArchiveParseError("压缩包解压后总大小超出限制")
        if unpacked and (packed <= 0 or unpacked / packed > MAX_COMPRESSION_RATIO):
            raise ArchiveParseError(f"{PurePosixPath(name).name} 压缩倍率过高")


def _audio_duration(raw: bytes, name: str) -> float:
    try:
        audio = MutagenFile(BytesIO(raw), filename=name)
        duration = float(audio.info.length) if audio is not None and getattr(audio, "info", None) else 0.0
    except Exception as exc:
        raise ArchiveParseError(f"{PurePosixPath(name).name} 音频损坏或无法解析") from exc
    if duration <= 0:
        raise ArchiveParseError(f"{PurePosixPath(name).name} 音频损坏或时长为 0")
    return duration


def _public_file_name(kind: str, original: str) -> str:
    return f"{kind}{Path(original).suffix.lower()}" if kind != "maidata" else "maidata.txt"


def write_public_package(event_id: int, submission_id: int, parsed: ParsedArchive) -> str:
    """Create a neutral, identity-safe ZIP while preserving maidata designer fields."""
    settings = get_settings()
    directory = settings.uploads_dir / "events" / str(event_id) / "public"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"submission-{submission_id}-{uuid4().hex[:12]}.zip"
    temporary = directory / f".{uuid4().hex}.tmp"
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            for name, payload in parsed.public_files:
                archive.writestr(name, payload)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return str(target.relative_to(settings.data_dir)).replace("\\", "/")


def _validate_target_size(name: str, size: int | None, maximum: int) -> None:
    if size is not None and size > maximum:
        raise ArchiveParseError(f"{PurePosixPath(_normalized_member_name(name)).name} 大小超出限制")


def _read_zip(path: Path) -> tuple[bytes, bytes, str, bytes, str, tuple[tuple[str, bytes], ...]]:
    from zipfile import BadZipFile

    try:
        with ZipFile(path, "r") as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if any(info.flag_bits & 0x1 for info in infos):
                raise ArchiveParseError("不支持加密压缩包")
            if any(stat.S_ISLNK(info.external_attr >> 16) for info in infos):
                raise ArchiveParseError("archive cannot contain symbolic links")
            _validate_archive_sizes([(info.filename, info.file_size, info.compress_size) for info in infos])
            by_name = {_validate_member_name(info.filename): info for info in infos}
            maidata_name, track_name, cover_name = _select_members(list(by_name))
            _validate_target_size(maidata_name, by_name[maidata_name].file_size, MAX_MAIDATA_BYTES)
            _validate_target_size(cover_name, by_name[cover_name].file_size, MAX_COVER_BYTES)
            maidata = archive.read(by_name[maidata_name])
            track = archive.read(by_name[track_name])
            cover = archive.read(by_name[cover_name])
            optional: list[tuple[str, bytes]] = []
            mv_names = [name for name in by_name if PurePosixPath(name).name.lower() == "mv.mp4"]
            if mv_names:
                mv_name = min(mv_names, key=_member_sort_key)
                optional.append(("mv.mp4", archive.read(by_name[mv_name])))
    except ArchiveParseError:
        raise
    except BadZipFile as exc:
        raise ArchiveParseError("ZIP 压缩包已损坏") from exc
    except Exception as exc:
        raise ArchiveParseError(f"ZIP 压缩包解析失败: {exc}") from exc
    public_files = (
        ("maidata.txt", maidata),
        (_public_file_name("track", track_name), track),
        (_public_file_name("bg", cover_name), cover),
        *optional,
    )
    return maidata, cover, Path(cover_name).suffix.lower(), track, track_name, public_files


def _read_7z(path: Path) -> tuple[bytes, bytes, str, bytes, str, tuple[tuple[str, bytes], ...]]:
    if py7zr is None:
        raise ArchiveParseError("服务器未安装 py7zr，无法解析 7z 文件")
    try:
        with py7zr.SevenZipFile(path, mode="r") as archive:
            if archive.needs_password():
                raise ArchiveParseError("不支持加密压缩包")
            infos = [info for info in archive.list() if not getattr(info, "is_directory", False)]
            if any(getattr(info, "is_symlink", False) for info in infos):
                raise ArchiveParseError("archive cannot contain symbolic links")
            _validate_archive_sizes([
                (
                    str(info.filename),
                    int(getattr(info, "uncompressed", 0) or 0),
                    int(
                        getattr(info, "compressed", 0)
                        or getattr(info, "uncompressed", 0)
                        or 1
                    ),
                )
                for info in infos
            ])
            total_uncompressed = sum(int(getattr(info, "uncompressed", 0) or 0) for info in infos)
            if total_uncompressed and total_uncompressed / max(path.stat().st_size, 1) > MAX_COMPRESSION_RATIO:
                raise ArchiveParseError("7z 压缩包总压缩倍率过高")
            by_name = {_validate_member_name(str(info.filename)): info for info in infos}
            maidata_name, track_name, cover_name = _select_members(list(by_name))
            _validate_target_size(maidata_name, getattr(by_name[maidata_name], "uncompressed", None), MAX_MAIDATA_BYTES)
            _validate_target_size(cover_name, getattr(by_name[cover_name], "uncompressed", None), MAX_COVER_BYTES)
            mv_names = [name for name in by_name if PurePosixPath(name).name.lower() == "mv.mp4"]
            targets = [maidata_name, track_name, cover_name] + ([min(mv_names, key=_member_sort_key)] if mv_names else [])
            extracted = archive.read(targets=targets)
            payload = {str(name): value.read() for name, value in extracted.items()}
            if maidata_name not in payload:
                raise ArchiveParseError("7z 压缩包无法读取 maidata.txt")
    except ArchiveParseError:
        raise
    except Exception as exc:
        raise ArchiveParseError(f"7z 压缩包解析失败: {exc}") from exc
    maidata, track, cover = payload[maidata_name], payload[track_name], payload[cover_name]
    public_files = [
        ("maidata.txt", maidata),
        (_public_file_name("track", track_name), track),
        (_public_file_name("bg", cover_name), cover),
    ]
    if mv_names:
        public_files.append(("mv.mp4", payload[min(mv_names, key=_member_sort_key)]))
    return maidata, cover, Path(cover_name).suffix.lower(), track, track_name, tuple(public_files)


def _read_rar(path: Path) -> tuple[bytes, bytes, str, bytes, str, tuple[tuple[str, bytes], ...]]:
    if rarfile is None:
        raise ArchiveParseError("服务器未安装 rarfile，无法解析 RAR 文件")
    try:
        with rarfile.RarFile(path, mode="r") as archive:
            infos = [info for info in archive.infolist() if not info.isdir()]
            if archive.needs_password():
                raise ArchiveParseError("不支持加密压缩包")
            if any(getattr(info, "is_symlink", lambda: False)() for info in infos):
                raise ArchiveParseError("archive cannot contain symbolic links")
            _validate_archive_sizes([(info.filename, info.file_size, info.compress_size) for info in infos])
            by_name = {_validate_member_name(info.filename): info for info in infos}
            maidata_name, track_name, cover_name = _select_members(list(by_name))
            _validate_target_size(maidata_name, by_name[maidata_name].file_size, MAX_MAIDATA_BYTES)
            _validate_target_size(cover_name, by_name[cover_name].file_size, MAX_COVER_BYTES)
            maidata = archive.read(by_name[maidata_name])
            track = archive.read(by_name[track_name])
            cover = archive.read(by_name[cover_name])
            mv_names = [name for name in by_name if PurePosixPath(name).name.lower() == "mv.mp4"]
            mv = archive.read(by_name[min(mv_names, key=_member_sort_key)]) if mv_names else None
    except ArchiveParseError:
        raise
    except Exception as exc:
        raise ArchiveParseError(f"RAR 压缩包解析失败: {exc}") from exc
    public_files = [
        ("maidata.txt", maidata),
        (_public_file_name("track", track_name), track),
        (_public_file_name("bg", cover_name), cover),
    ]
    if mv is not None:
        public_files.append(("mv.mp4", mv))
    return maidata, cover, Path(cover_name).suffix.lower(), track, track_name, tuple(public_files)


def parse_archive(path: Path) -> ParsedArchive:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_ARCHIVE_SUFFIXES:
        raise ArchiveParseError("仅支持 zip、7z、rar 压缩包")
    if suffix == ".zip":
        maidata_raw, cover_bytes, cover_suffix, track_bytes, track_name, public_files = _read_zip(path)
    elif suffix == ".7z":
        maidata_raw, cover_bytes, cover_suffix, track_bytes, track_name, public_files = _read_7z(path)
    else:
        maidata_raw, cover_bytes, cover_suffix, track_bytes, track_name, public_files = _read_rar(path)

    if len(maidata_raw) > MAX_MAIDATA_BYTES:
        raise ArchiveParseError("maidata.txt 大小超出限制")
    if cover_bytes is not None and len(cover_bytes) > MAX_COVER_BYTES:
        raise ArchiveParseError("封面图片大小超出限制")

    title, author, levels = parse_maidata(decode_maidata(maidata_raw))
    duration = _audio_duration(track_bytes, track_name)
    warnings: tuple[ImportWarning, ...] = ()
    if cover_bytes is None:
        warnings = (ImportWarning("bg_missing", "压缩包缺少 bg 封面图，已使用默认封面"),)
    return ParsedArchive(
        title,
        author,
        levels,
        cover_bytes,
        cover_suffix,
        warnings,
        track_duration_seconds=duration,
        public_files=public_files,
    )


def storage_path_to_absolute(storage_path: str) -> Path:
    settings = get_settings()
    data_dir = settings.data_dir.resolve()
    path = (data_dir / storage_path).resolve()
    try:
        path.relative_to(data_dir)
    except ValueError as exc:
        raise ArchiveParseError("投稿文件路径无效") from exc
    if not path.is_file():
        raise ArchiveParseError("投稿文件不存在")
    return path


def parse_stored_archive(storage_path: str) -> ParsedArchive:
    return parse_archive(storage_path_to_absolute(storage_path))


def _write_cover(event_id: int, source_type: str, source_id: int, parsed: ParsedArchive) -> str:
    if parsed.cover_bytes is None:
        return ""
    # Public URLs must not encode event, account, submission, or original-file IDs.
    file_name = f"{uuid4().hex}{parsed.cover_suffix}"
    directory = get_settings().assets_dir / "guess-covers"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / file_name
    if not target.exists():
        temporary = directory / f".{uuid4().hex}.tmp"
        try:
            temporary.write_bytes(parsed.cover_bytes)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return f"/api/v1/assets/guess-covers/{file_name}"


def _cover_path_to_file(cover_path: str) -> Path | None:
    prefix = "/api/v1/assets/guess-covers/"
    if not cover_path.startswith(prefix):
        return None
    file_name = Path(cover_path.removeprefix(prefix)).name
    return get_settings().assets_dir / "guess-covers" / file_name


def delete_cover_paths(cover_paths: set[str]) -> None:
    for cover_path in cover_paths:
        path = _cover_path_to_file(cover_path)
        if not path:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


def _replace_source_issues(
    db: Session,
    event_id: int,
    source_type: str,
    source_id: int,
    file_name: str,
    issues: tuple[ImportWarning, ...],
    match_source_type: str | None = None,
) -> None:
    issue_source_type = match_source_type or source_type
    db.execute(
        delete(ImportIssue).where(
            ImportIssue.event_id == event_id,
            ImportIssue.source_type == issue_source_type,
            ImportIssue.source_id == source_id,
        )
    )
    for issue in issues:
        db.add(
            ImportIssue(
                event_id=event_id,
                source_type=source_type,
                source_id=source_id,
                file_name=file_name,
                issue_type=issue.issue_type,
                message=issue.message,
            )
        )


def record_source_error(
    db: Session,
    event_id: int,
    source_type: str,
    source_id: int,
    file_name: str,
    message: str,
) -> None:
    _replace_source_issues(
        db,
        event_id,
        source_type,
        source_id,
        file_name,
        (ImportWarning("archive_parse_failed", message[:500]),),
    )


def sync_parsed_source(
    db: Session,
    *,
    event_id: int,
    source_type: str,
    source_id: int,
    file_name: str,
    storage_path: str,
    parsed: ParsedArchive,
    is_self_selected: bool | None = None,
    match_source_type: str | None = None,
) -> SyncResult:
    chart_source_type = match_source_type or source_type
    charts = list(
        db.scalars(
            select(GuessChart)
            .where(
                GuessChart.event_id == event_id,
                GuessChart.source_submission_type == chart_source_type,
                GuessChart.source_submission_id == source_id,
            )
            .order_by(GuessChart.id.asc())
        ).all()
    )
    result = SyncResult(previous_cover_paths={chart.cover_path for chart in charts if chart.cover_path})
    _replace_source_issues(
        db,
        event_id,
        source_type,
        source_id,
        file_name,
        parsed.warnings,
        match_source_type=chart_source_type,
    )
    result.new_cover_path = _write_cover(event_id, source_type, source_id, parsed)
    resolved_self_selected = (
        any(chart.is_self_selected for chart in charts) if is_self_selected is None else is_self_selected
    )
    by_slot: dict[str, GuessChart] = {}
    for chart in charts:
        if chart.source_level_slot in by_slot:
            db.delete(chart)
            result.deleted += 1
        else:
            by_slot[chart.source_level_slot] = chart

    active_slots: set[str] = set()
    group_key = normalize_group_key(parsed.title, parsed.author)
    lane = source_type if source_type in {"normal", "j", "exhibition"} else "normal"
    for level in parsed.levels:
        active_slots.add(level.slot)
        chart = by_slot.get(level.slot)
        values = {
            "title": parsed.title,
            "author": parsed.author,
            "designer": level.designer,
            "level": level.level,
            "lane": lane,
            "guess_group_key": group_key,
            "source_submission_type": source_type,
            "source_submission_id": source_id,
            "source_level_slot": level.slot,
            "cover_path": result.new_cover_path,
            "storage_path": storage_path,
            "is_self_selected": resolved_self_selected,
        }
        if chart is None:
            db.add(GuessChart(event_id=event_id, plays=0, **values))
            result.created += 1
            continue
        changed = False
        for key, value in values.items():
            if getattr(chart, key) != value:
                setattr(chart, key, value)
                changed = True
        if changed:
            result.updated += 1

    for slot, chart in by_slot.items():
        if slot not in active_slots:
            db.delete(chart)
            result.deleted += 1

    return result


def source_cover_paths(db: Session, event_id: int, source_type: str, source_id: int) -> set[str]:
    return {
        value
        for value in db.scalars(
            select(GuessChart.cover_path).where(
                GuessChart.event_id == event_id,
                GuessChart.source_submission_type == source_type,
                GuessChart.source_submission_id == source_id,
            )
        ).all()
        if value
    }


def delete_source_charts(db: Session, event_id: int, source_type: str, source_id: int) -> tuple[int, set[str]]:
    charts = list(
        db.scalars(
            select(GuessChart).where(
                GuessChart.event_id == event_id,
                GuessChart.source_submission_type == source_type,
                GuessChart.source_submission_id == source_id,
            )
        ).all()
    )
    cover_paths = {chart.cover_path for chart in charts if chart.cover_path}
    for chart in charts:
        db.delete(chart)
    db.execute(
        delete(ImportIssue).where(
            ImportIssue.event_id == event_id,
            ImportIssue.source_type == source_type,
            ImportIssue.source_id == source_id,
        )
    )
    return len(charts), cover_paths


def rebuild_event_charts(db: Session, event_id: int) -> RebuildResult:
    normal = list(db.scalars(select(Submission).where(Submission.event_id == event_id).order_by(Submission.id.asc())).all())
    j_track = list(db.scalars(select(JTrackSubmission).where(JTrackSubmission.event_id == event_id).order_by(JTrackSubmission.id.asc())).all())
    admin_archives = list(
        db.scalars(
            select(AdminGuessArchive)
            .where(AdminGuessArchive.event_id == event_id)
            .order_by(AdminGuessArchive.id.asc())
        ).all()
    )
    sources = [(row.track if row.track in {"normal", "j", "exhibition"} else "normal", row) for row in normal] + [
        ("j", row) for row in j_track
    ] + [("admin", row) for row in admin_archives]
    active_keys = {(source_type, row.id) for source_type, row in sources}
    result = RebuildResult(scanned=len(sources))
    stale_covers: set[str] = set()
    active_covers: set[str] = set()
    created_covers: set[str] = set()
    created_public_packages: set[str] = set()

    try:
        for source_type, row in sources:
            try:
                parsed = parse_stored_archive(row.storage_path)
            except ArchiveParseError as exc:
                record_source_error(db, event_id, source_type, row.id, row.file_name, str(exc))
                continue
            if isinstance(row, Submission):
                row.track_duration_seconds = parsed.track_duration_seconds
                if not row.public_storage_path:
                    row.public_storage_path = write_public_package(event_id, row.id, parsed)
                    created_public_packages.add(row.public_storage_path)
            sync = sync_parsed_source(
                db,
                event_id=event_id,
                source_type=source_type,
                source_id=row.id,
                file_name=row.file_name,
                storage_path=row.storage_path,
                parsed=parsed,
                is_self_selected=source_type != "admin" and getattr(row, "source_kind", "") == "self",
            )
            result.created += sync.created
            result.updated += sync.updated
            result.deleted += sync.deleted
            stale_covers.update(sync.stale_cover_paths)
            if sync.new_cover_path:
                active_covers.add(sync.new_cover_path)
                if sync.new_cover_path not in sync.previous_cover_paths:
                    created_covers.add(sync.new_cover_path)

        sourced_charts = list(
            db.scalars(
                select(GuessChart).where(
                    GuessChart.event_id == event_id,
                    GuessChart.source_submission_id.is_not(None),
                    GuessChart.source_submission_type.in_(("normal", "j", "exhibition", "admin")),
                )
            ).all()
        )
        orphan_keys = {
            (chart.source_submission_type, chart.source_submission_id)
            for chart in sourced_charts
            if (chart.source_submission_type, chart.source_submission_id) not in active_keys
        }
        for source_type, source_id in orphan_keys:
            deleted_count, cover_paths = delete_source_charts(db, event_id, source_type, int(source_id))
            result.deleted += deleted_count
            stale_covers.update(cover_paths)

        issue_rows = list(db.scalars(select(ImportIssue).where(ImportIssue.event_id == event_id)).all())
        for issue in issue_rows:
            if issue.source_id is not None and (issue.source_type, issue.source_id) not in active_keys:
                db.delete(issue)

        db.commit()
    except Exception:
        db.rollback()
        delete_cover_paths(created_covers)
        for storage_path in created_public_packages:
            try:
                storage_path_to_absolute(storage_path).unlink(missing_ok=True)
            except ArchiveParseError:
                pass
        raise

    delete_cover_paths(stale_covers - active_covers)
    result.issues = db.scalar(select(func.count()).select_from(ImportIssue).where(ImportIssue.event_id == event_id)) or 0
    return result
