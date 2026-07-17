from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from threading import Lock
from typing import Protocol

from fastapi import HTTPException, status
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from rapidfuzz import fuzz
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.models import BanAlias, BanEntry, BanImport


MAX_BAN_FILE_BYTES = 10 * 1024 * 1024
# Keep the automatic check tolerant of small title typos and stylized
# characters while still requiring a strong artist match.
MATCH_TITLE_THRESHOLD = 85.0
MATCH_ARTIST_THRESHOLD = 70.0
MATCH_TITLE_EXACT_ARTIST_THRESHOLD = 80.0
SEARCH_LIMIT = 50
BAN_PARSER_VERSION = 2
TITLE_HEADERS = {"曲名", "songname", "title"}
ARTIST_HEADERS = {"作者", "artist", "author"}
REMARK_HEADERS = {"备注", "remark", "note"}


class ExternalMetadataProvider(Protocol):
    """Future provider contract; provider calls are disabled by default."""

    def lookup(self, title: str, artist: str) -> list[dict[str, str]]: ...


class DisabledExternalMetadataProvider:
    def lookup(self, title: str, artist: str) -> list[dict[str, str]]:
        return []


@dataclass(frozen=True)
class ParsedBanEntry:
    round_label: str
    song_name: str
    artist: str
    remark: str
    row_number: int


_rate_lock = Lock()
_recent_queries: dict[int, deque[float]] = {}


def enforce_query_rate_limit(user_id: int, now: float) -> None:
    with _rate_lock:
        queries = _recent_queries.setdefault(user_id, deque())
        while queries and now - queries[0] > 30:
            queries.popleft()
        if len(queries) >= 60:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="查重请求过于频繁，请稍后再试")
        queries.append(now)


def normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _cell_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _discover_ban_blocks(rows: list[tuple[object, ...]]) -> list[tuple[int, str]]:
    if len(rows) < 2:
        return []
    round_row = rows[0]
    header_row = rows[1]
    column_count = max(len(round_row), len(header_row))
    blocks: list[tuple[int, str]] = []
    for start in range(max(0, column_count - 2)):
        round_label = _cell_text(round_row[start]) if start < len(round_row) else ""
        headers = [
            normalize_text(header_row[index]) if index < len(header_row) else ""
            for index in range(start, start + 3)
        ]
        if (
            round_label.startswith("#")
            and headers[0] in TITLE_HEADERS
            and headers[1] in ARTIST_HEADERS
            and headers[2] in REMARK_HEADERS
        ):
            blocks.append((start, round_label))
    return blocks


def parse_ban_workbook(raw: bytes) -> tuple[list[ParsedBanEntry], list[str]]:
    if not raw:
        raise ValueError("Ban 曲 Excel 文件为空")
    try:
        workbook = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    except (InvalidFileException, OSError, ValueError) as exc:
        raise ValueError("无法读取 Ban 曲 Excel 文件，请上传有效的 .xlsx 文件") from exc
    try:
        worksheet = workbook.active
        rows = list(worksheet.iter_rows(values_only=True))
        blocks = _discover_ban_blocks(rows)
        if not blocks:
            raise ValueError("Excel 中未找到有效的 Ban 曲区块，请确认第 1 行为赛事名称，第 2 行为曲名、作者、备注")

        entries: list[ParsedBanEntry] = []
        issues: list[str] = []
        for start, round_label in blocks:
            seen_in_round: set[tuple[str, str]] = set()
            for row_number, row in enumerate(rows[2:], start=3):
                cells = list(row) + [None] * max(0, start + 3 - len(row))
                title = _cell_text(cells[start])
                artist = _cell_text(cells[start + 1])
                remark = _cell_text(cells[start + 2])
                if not title and not artist and not remark:
                    continue
                if not title or not artist:
                    issues.append(f"第 {row_number} 行（{round_label}）缺少曲名或作者")
                    continue
                key = (normalize_text(title), normalize_text(artist))
                if key in seen_in_round:
                    issues.append(f"第 {row_number} 行（{round_label}）与同届已有曲目重复：{title} / {artist}")
                seen_in_round.add(key)
                entries.append(ParsedBanEntry(round_label, title, artist, remark, row_number))
    finally:
        workbook.close()
    if not entries:
        raise ValueError("Excel 中没有解析到有效的 Ban 曲目")
    return entries, issues


def _preview_json(issues: list[str]) -> str:
    return json.dumps({"issues": issues}, ensure_ascii=False)


def create_ban_import(db: Session, file_name: str, raw: bytes, uploaded_by_id: int | None, *, auto_publish: bool = False) -> BanImport:
    if len(raw) > MAX_BAN_FILE_BYTES:
        raise ValueError("Ban 曲 Excel 文件不能超过 10 MB")
    digest = hashlib.sha256(raw).hexdigest()
    existing = db.scalar(
        select(BanImport)
        .where(
            BanImport.file_sha256 == digest,
            BanImport.parser_version == BAN_PARSER_VERSION,
        )
        .order_by(BanImport.id.desc())
    )
    if existing:
        return existing
    entries, issues = parse_ban_workbook(raw)
    previous = db.scalar(
        select(BanImport)
        .options(selectinload(BanImport.entries).selectinload(BanEntry.aliases))
        .where(BanImport.file_sha256 == digest)
        .order_by(BanImport.parser_version.desc(), BanImport.id.desc())
    )
    previous_aliases: dict[tuple[str, str, str], list[BanAlias]] = {}
    if previous:
        for entry in previous.entries:
            key = (entry.round_label, entry.normalized_song_name, entry.normalized_artist)
            previous_aliases[key] = list(entry.aliases)
    record = BanImport(
        file_name=file_name[:255] or "banlist.xlsx",
        file_sha256=digest,
        parser_version=BAN_PARSER_VERSION,
        status="draft",
        entry_count=len(entries),
        issue_count=len(issues),
        preview_json=_preview_json(issues),
        uploaded_by_id=uploaded_by_id,
    )
    db.add(record)
    db.flush()
    for item in entries:
        normalized_song_name = normalize_text(item.song_name)
        normalized_artist = normalize_text(item.artist)
        entry = BanEntry(
            import_id=record.id,
            round_label=item.round_label,
            song_name=item.song_name,
            artist=item.artist,
            remark=item.remark,
            normalized_song_name=normalized_song_name,
            normalized_artist=normalized_artist,
        )
        db.add(entry)
        db.flush()
        key = (item.round_label, normalized_song_name, normalized_artist)
        db.add_all(
            [
                BanAlias(
                    entry_id=entry.id,
                    song_name=alias.song_name,
                    artist=alias.artist,
                    normalized_song_name=alias.normalized_song_name,
                    normalized_artist=alias.normalized_artist,
                    source=alias.source,
                    confirmed_by_id=alias.confirmed_by_id,
                    confirmed_at=alias.confirmed_at,
                )
                for alias in previous_aliases.get(key, [])
            ]
        )
    db.commit()
    db.refresh(record)
    if auto_publish:
        publish_ban_import(db, record.id)
    return record


def publish_ban_import(db: Session, import_id: int) -> BanImport:
    record = db.get(BanImport, import_id)
    if not record:
        raise HTTPException(status_code=404, detail="Ban 曲导入版本不存在")
    if record.entry_count <= 0:
        raise HTTPException(status_code=409, detail="没有可发布的 Ban 曲目")
    db.execute(update(BanImport).where(BanImport.status == "published").values(status="superseded"))
    record.status = "published"
    record.published_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return record


def get_active_import(db: Session) -> BanImport | None:
    return db.scalar(
        select(BanImport)
        .where(BanImport.status == "published")
        .order_by(BanImport.published_at.desc(), BanImport.id.desc())
    )


def get_import_entries(db: Session, import_id: int) -> list[BanEntry]:
    return list(
        db.scalars(
            select(BanEntry)
            .options(selectinload(BanEntry.aliases))
            .where(BanEntry.import_id == import_id)
            .order_by(BanEntry.id.asc())
        ).all()
    )


def import_issues(record: BanImport) -> list[str]:
    try:
        payload = json.loads(record.preview_json or "{}")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in payload.get("issues", [])]


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return round(float(fuzz.WRatio(left, right)), 1)


def _match(entry: BanEntry, match_type: str, score: float | None, reason: str) -> dict:
    return {
        "entry_id": entry.id,
        "title": entry.song_name,
        "artist": entry.artist,
        "round": entry.round_label,
        "note": entry.remark,
        "match_type": match_type,
        "score": score,
        "reason": reason,
    }


def _entry_variants(entry: BanEntry) -> list[tuple[str, str, str]]:
    variants = [(entry.normalized_song_name, entry.normalized_artist, "fuzzy")]
    variants.extend((alias.normalized_song_name, alias.normalized_artist, "alias") for alias in entry.aliases if alias.confirmed_at)
    return variants


def check_song(db: Session, title: str, artist: str) -> dict:
    active = get_active_import(db)
    if not active:
        return {"status": "unavailable", "matches": [], "import_id": None}
    title_key = normalize_text(title)
    artist_key = normalize_text(artist)
    entries = get_import_entries(db, active.id)
    exact: list[dict] = []
    fuzzy: dict[int, dict] = {}
    for entry in entries:
        for entry_title, entry_artist, variant_type in _entry_variants(entry):
            if entry_title == title_key and entry_artist == artist_key:
                exact.append(_match(entry, "alias" if variant_type == "alias" else "exact", 100.0, "曲名和作者均完全匹配" if variant_type == "fuzzy" else "命中管理员确认的曲目别名"))
                break
            title_score = similarity(title_key, entry_title)
            artist_score = similarity(artist_key, entry_artist)
            title_exact = title_key == entry_title
            if (title_score >= MATCH_TITLE_THRESHOLD and artist_score >= MATCH_ARTIST_THRESHOLD) or (
                title_exact and artist_score >= MATCH_TITLE_EXACT_ARTIST_THRESHOLD
            ):
                score = round(title_score * 0.6 + artist_score * 0.4, 1)
                reason = f"曲名相似度 {title_score:.1f}%，作者相似度 {artist_score:.1f}%"
                if variant_type == "alias":
                    reason = f"与管理员确认的别名相似，{reason}"
                previous = fuzzy.get(entry.id)
                if previous is None or score > float(previous["score"] or 0):
                    fuzzy[entry.id] = _match(entry, "fuzzy", score, reason)

    if exact:
        return {"status": "exact", "matches": exact, "import_id": active.id}
    matches = sorted(fuzzy.values(), key=lambda item: float(item["score"] or 0), reverse=True)[:5]
    return {"status": "review" if matches else "clear", "matches": matches, "import_id": active.id}


def enforce_song_allowed(db: Session, title: str, artist: str, acknowledge_ban_warning: bool = False) -> dict:
    result = check_song(db, title, artist)
    matches = result["matches"]
    if result["status"] == "exact":
        first = matches[0] if matches else {}
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"该曲目命中往届 Ban 曲：{first.get('title', title)} / {first.get('artist', artist)}（{first.get('round', '历史赛事')}）",
        )
    if result["status"] == "review" and not acknowledge_ban_warning:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该曲目疑似命中往届 Ban 曲，请确认不是同一首曲目后再继续")
    return result


def _search_score(query: str, value: str) -> tuple[float, bool]:
    if not query:
        return 0.0, False
    if query == value:
        return 100.0, True
    if query in value or value in query:
        return 92.0, True
    return similarity(query, value), False


def search_ban_entries(db: Session, title: str = "", artist: str = "", limit: int = SEARCH_LIMIT) -> dict:
    active = get_active_import(db)
    if not active:
        return {"items": [], "import_id": None}
    title_key = normalize_text(title)
    artist_key = normalize_text(artist)
    entries = get_import_entries(db, active.id)
    scored: list[tuple[float, dict]] = []
    for entry in entries:
        title_score, title_hit = _search_score(title_key, entry.normalized_song_name)
        artist_score, artist_hit = _search_score(artist_key, entry.normalized_artist)
        if title_key and artist_key:
            if not ((title_hit and artist_score >= 45) or (artist_hit and title_score >= 45) or (title_score >= 65 and artist_score >= 65)):
                continue
            score = round(title_score * 0.6 + artist_score * 0.4, 1)
            reason = "曲名和作者均命中搜索条件" if title_hit and artist_hit else "曲名或作者命中搜索条件"
        elif title_key:
            if title_score < 55:
                continue
            score = title_score
            reason = "曲名命中搜索条件"
        elif artist_key:
            if artist_score < 55:
                continue
            score = artist_score
            reason = "作者命中搜索条件"
        else:
            continue
        match_type = "exact" if score >= 100 else "fuzzy"
        scored.append((score, _match(entry, match_type, score, reason)))
    scored.sort(key=lambda item: item[0], reverse=True)
    return {"items": [item for _, item in scored[: max(1, min(limit, SEARCH_LIMIT))]], "import_id": active.id}


def serialize_import(record: BanImport) -> dict:
    return {
        "id": record.id,
        "file_name": record.file_name,
        "file_sha256": record.file_sha256,
        "status": record.status,
        "entry_count": record.entry_count,
        "issue_count": record.issue_count,
        "uploaded_by_id": record.uploaded_by_id,
        "published_at": record.published_at,
        "created_at": record.created_at,
    }


def serialize_preview(record: BanImport, entries: list[BanEntry]) -> dict:
    return {
        **serialize_import(record),
        "entries": [
            {"id": entry.id, "round": entry.round_label, "title": entry.song_name, "artist": entry.artist, "note": entry.remark}
            for entry in entries
        ],
        "issues": import_issues(record),
    }
