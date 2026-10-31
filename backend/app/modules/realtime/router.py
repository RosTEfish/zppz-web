from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.modules.realtime.stream import iter_event_stream, resolve_cursor, snapshot_viewer

router = APIRouter(tags=["realtime"])

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Content-Encoding": "identity",
}


@router.get(
    "/events",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-Sent Events stream",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def domain_events(
    request: Request,
    after: int | None = Query(default=None, ge=0),
) -> StreamingResponse:
    """Tail contest, draw, guess, swap, and submission-job changes.

    Anonymous clients receive public events (phase changes, guess state).
    A presented session that is missing or expired is rejected. Logged-in
    clients also receive authenticated events, and their own job events.
    Admins receive every participant's job events.
    """
    presented, user_id, is_admin = snapshot_viewer(request)
    if presented and user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已过期")
    cursor = resolve_cursor(after, request.headers.get("last-event-id"))
    return StreamingResponse(
        iter_event_stream(
            request,
            cursor,
            user_id=user_id,
            is_admin=is_admin,
            credentials_presented=presented,
        ),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
