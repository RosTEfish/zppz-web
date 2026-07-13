from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import random
from secrets import token_hex

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    DrawAssignment,
    EventPhase,
    Song,
    Submission,
    SwapRequest,
    SwapRequestItem,
    SwapRound,
    User,
)
from app.modules.events.phase_policy import get_phase_status
from app.modules.events.service import get_current_event


MAX_SWAP_SELECTIONS = 3


@dataclass(frozen=True)
class SwapPlan:
    slot_items: list[SwapRequestItem]
    song_by_slot: dict[int, int]
    pool_size: int


def _begin_write_transaction(db: Session) -> None:
    if db.get_bind().dialect.name != "sqlite":
        return
    db.rollback()
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _swap_phase(db: Session, event_id: int) -> EventPhase:
    phase = db.scalar(
        select(EventPhase).where(EventPhase.event_id == event_id, EventPhase.phase == "swap")
    )
    if not phase:
        raise HTTPException(status_code=409, detail="尚未配置换曲阶段时间")
    return phase


def get_swap_round(db: Session, event_id: int) -> SwapRound | None:
    return db.scalar(
        select(SwapRound)
        .options(
            selectinload(SwapRound.requests)
            .selectinload(SwapRequest.items)
            .selectinload(SwapRequestItem.original_assignment)
            .selectinload(DrawAssignment.song),
            selectinload(SwapRound.requests)
            .selectinload(SwapRequest.items)
            .selectinload(SwapRequestItem.replacement_assignment)
            .selectinload(DrawAssignment.song),
            selectinload(SwapRound.requests).selectinload(SwapRequest.user),
        )
        .where(SwapRound.event_id == event_id, SwapRound.round_number == 1)
    )


def ensure_swap_round(db: Session, event_id: int) -> SwapRound:
    row = get_swap_round(db, event_id)
    if row:
        return row
    phase = _swap_phase(db, event_id)
    row = SwapRound(
        event_id=event_id,
        round_number=1,
        starts_at=phase.starts_at,
        ends_at=phase.ends_at,
        status="open",
        random_seed=token_hex(24),
    )
    db.add(row)
    db.flush()
    return row


def active_assignments_for_user(db: Session, event_id: int, user_id: int) -> list[DrawAssignment]:
    return list(
        db.scalars(
            select(DrawAssignment)
            .options(selectinload(DrawAssignment.song).selectinload(Song.submitter))
            .where(
                DrawAssignment.event_id == event_id,
                DrawAssignment.assigned_to_id == user_id,
                DrawAssignment.status == "active",
            )
            .order_by(DrawAssignment.created_at.asc(), DrawAssignment.id.asc())
        ).all()
    )


def save_swap_request(db: Session, user: User, assignment_ids: list[int]) -> SwapRound:
    if user.identity != "participant":
        raise HTTPException(status_code=403, detail="只有参赛者可以申请换曲")
    if not 1 <= len(assignment_ids) <= MAX_SWAP_SELECTIONS or len(set(assignment_ids)) != len(assignment_ids):
        raise HTTPException(status_code=400, detail="请选择 1 至 3 首不重复的抽中曲目")

    event = get_current_event(db)
    phase = get_phase_status(db, event)
    if not phase.can("swap"):
        raise HTTPException(status_code=409, detail="当前不在换曲阶段")

    _begin_write_transaction(db)
    event = get_current_event(db)
    round_row = ensure_swap_round(db, event.id)
    if round_row.status != "open":
        raise HTTPException(status_code=409, detail="换曲结果已经生成，不能再修改申请")

    assignments = list(
        db.scalars(
            select(DrawAssignment)
            .where(
                DrawAssignment.id.in_(assignment_ids),
                DrawAssignment.event_id == event.id,
                DrawAssignment.assigned_to_id == user.id,
                DrawAssignment.status == "active",
            )
            .with_for_update()
        ).all()
    )
    by_id = {row.id: row for row in assignments}
    missing = [item for item in assignment_ids if item not in by_id]
    if missing:
        raise HTTPException(status_code=400, detail="所选曲目已失效，请刷新后重试")

    submitted_song_ids = set(
        db.scalars(
            select(Submission.source_song_id).where(
                Submission.event_id == event.id,
                Submission.user_id == user.id,
                Submission.source_song_id.in_([row.song_id for row in assignments]),
            )
        ).all()
    )
    if submitted_song_ids:
        raise HTTPException(status_code=409, detail="已有投稿的曲目不能换曲，请先删除对应投稿")

    request = db.scalar(
        select(SwapRequest).where(SwapRequest.round_id == round_row.id, SwapRequest.user_id == user.id)
    )
    if not request:
        request = SwapRequest(round_id=round_row.id, user_id=user.id, status="pending", error_message="")
        db.add(request)
        db.flush()
    else:
        for item in list(request.items):
            db.delete(item)
        db.flush()
        request.status = "pending"
        request.error_message = ""

    for position, assignment_id in enumerate(assignment_ids):
        db.add(
            SwapRequestItem(
                request_id=request.id,
                original_assignment_id=assignment_id,
                position=position,
            )
        )
    db.commit()
    return get_swap_round(db, event.id)  # type: ignore[return-value]


def _build_plan(db: Session, round_row: SwapRound) -> SwapPlan:
    requests = [request for request in round_row.requests if request.items]
    slot_items = [item for request in requests for item in request.items]
    if not slot_items:
        raise HTTPException(status_code=400, detail="当前没有换曲申请")

    event_id = round_row.event_id
    requested_assignment_ids = {item.original_assignment_id for item in slot_items}
    active_assignments = list(
        db.scalars(
            select(DrawAssignment).where(
                DrawAssignment.event_id == event_id,
                DrawAssignment.status == "active",
            )
        ).all()
    )
    active_by_id = {row.id: row for row in active_assignments}
    if not requested_assignment_ids.issubset(active_by_id):
        raise HTTPException(status_code=409, detail="部分换曲申请对应的抽签结果已经失效")

    submitted = db.scalar(
        select(Submission.id)
        .join(
            DrawAssignment,
            (DrawAssignment.song_id == Submission.source_song_id)
            & (DrawAssignment.assigned_to_id == Submission.user_id),
        )
        .where(
            DrawAssignment.id.in_(requested_assignment_ids),
            Submission.event_id == event_id,
        )
        .limit(1)
    )
    if submitted:
        raise HTTPException(status_code=409, detail="有换曲目标已经投稿，请先删除投稿后再执行")

    occupied_song_ids = {
        row.song_id for row in active_assignments if row.id not in requested_assignment_ids
    }
    songs = list(db.scalars(select(Song).where(Song.event_id == event_id)).all())
    pool = [song for song in songs if song.id not in occupied_song_ids]
    if len(pool) < len(slot_items):
        raise HTTPException(status_code=409, detail="换曲曲池数量不足，无法满足全部申请")

    user_by_request = {request.id: request.user_id for request in requests}
    returned_song_ids_by_user: dict[int, set[int]] = {}
    for item in slot_items:
        user_id = user_by_request[item.request_id]
        returned_song_ids_by_user.setdefault(user_id, set()).add(
            active_by_id[item.original_assignment_id].song_id
        )
    randomizer = random.Random(round_row.random_seed)
    candidates: dict[int, list[int]] = {}
    for slot_index, item in enumerate(slot_items):
        original = active_by_id[item.original_assignment_id]
        user_id = user_by_request[item.request_id]
        choices = [
            song.id
            for song in pool
            if song.submitted_by_id != user_id
            and song.id not in returned_song_ids_by_user[user_id]
        ]
        randomizer.shuffle(choices)
        candidates[slot_index] = choices

    slot_for_song: dict[int, int] = {}

    def assign(slot_index: int, visited: set[int]) -> bool:
        for song_id in candidates[slot_index]:
            if song_id in visited:
                continue
            visited.add(song_id)
            previous = slot_for_song.get(song_id)
            if previous is None or assign(previous, visited):
                slot_for_song[song_id] = slot_index
                return True
        return False

    slot_order = list(range(len(slot_items)))
    randomizer.shuffle(slot_order)
    for slot_index in slot_order:
        if not assign(slot_index, set()):
            raise HTTPException(status_code=409, detail="排除自投曲和原曲后无法满足全部换曲申请")

    song_by_slot = {slot_index: song_id for song_id, slot_index in slot_for_song.items()}
    return SwapPlan(slot_items=slot_items, song_by_slot=song_by_slot, pool_size=len(pool))


def validate_swap_round(db: Session) -> dict:
    event = get_current_event(db)
    round_row = get_swap_round(db, event.id)
    if not round_row:
        return {"ok": False, "valid": False, "request_count": 0, "item_count": 0, "pool_size": 0, "message": "当前没有换曲申请"}
    try:
        plan = _build_plan(db, round_row)
    except HTTPException as exc:
        return {
            "ok": False,
            "valid": False,
            "request_count": len([row for row in round_row.requests if row.items]),
            "item_count": sum(len(row.items) for row in round_row.requests),
            "pool_size": 0,
            "message": str(exc.detail),
        }
    return {
        "ok": True,
        "valid": True,
        "request_count": len([row for row in round_row.requests if row.items]),
        "item_count": len(plan.slot_items),
        "pool_size": plan.pool_size,
        "message": "全部换曲申请均可完成",
    }


def finalize_swap_round(db: Session) -> SwapRound:
    _begin_write_transaction(db)
    event = get_current_event(db)
    # PostgreSQL needs an explicit row lock so concurrent finalize requests cannot
    # both create replacements. SQLite is covered by BEGIN IMMEDIATE above.
    db.scalar(
        select(SwapRound.id)
        .where(SwapRound.event_id == event.id, SwapRound.round_number == 1)
        .with_for_update()
    )
    round_row = get_swap_round(db, event.id)
    if not round_row:
        raise HTTPException(status_code=400, detail="当前没有换曲申请")
    if round_row.status == "finalized":
        return round_row

    plan = _build_plan(db, round_row)
    for slot_index, item in enumerate(plan.slot_items):
        original = item.original_assignment
        original.status = "returned"
        replacement = DrawAssignment(
            event_id=event.id,
            assigned_to_id=original.assigned_to_id,
            song_id=plan.song_by_slot[slot_index],
            status="active",
            draw_kind="swap",
            replaces_assignment_id=original.id,
        )
        db.add(replacement)
        db.flush()
        item.replacement_assignment_id = replacement.id
        item.request.status = "completed"
        item.request.error_message = ""

    round_row.status = "finalized"
    round_row.finalized_at = datetime.utcnow()
    db.commit()
    return get_swap_round(db, event.id)  # type: ignore[return-value]
