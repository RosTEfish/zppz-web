from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import json
import logging
import mimetypes
from pathlib import Path
import secrets
import socket
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import HTTPException, Request, status
from PIL import Image
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_token
from app.db.session import SessionLocal
from app.models import (
    AdminGuessArchive,
    ChartPublicationState,
    Event,
    GuessChart,
    Submission,
    SubmissionProcessingJob,
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEvent,
    WebhookEventAsset,
    WebhookIntegration,
    WebhookSystemState,
)
from app.modules.events.phase_policy import apply_chart_visibility_filter, chart_visibility_key, get_phase_status
from app.modules.events.service import get_current_event
from app.modules.object_storage import get_object_store


logger = logging.getLogger(__name__)
SUPPORTED_EVENTS = ("chart.published", "chart.updated")
DELIVERY_STATUSES = ("pending", "retrying", "delivering")
LEASE_SECONDS = 60
RETRY_WINDOW = timedelta(days=7)
RETRY_DELAYS = (10, 30, 120, 600, 1800, 7200, 21600, 43200, 86400)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc_iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def issue_integration_token() -> str:
    return f"zppz_whk_{secrets.token_urlsafe(32)}"


def derive_webhook_secret(integration: WebhookIntegration) -> str:
    message = f"webhook-signing-v1:{integration.id}:{integration.secret_generation}".encode()
    return hmac.new(
        get_settings().webhook_signing_master_key.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()


def sign_payload(secret: str, timestamp: int, body: bytes) -> str:
    value = str(timestamp).encode() + b"." + body
    return hmac.new(secret.encode(), value, hashlib.sha256).hexdigest()


def integration_from_request(request: Request, db: Session) -> WebhookIntegration:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing integration token")
    token = auth[7:].strip()
    integration = db.scalar(
        select(WebhookIntegration).where(
            WebhookIntegration.token_hash == hash_token(token),
            WebhookIntegration.is_active.is_(True),
        )
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid integration token")
    return integration


def subscribed_events(endpoint: WebhookEndpoint) -> list[str]:
    try:
        values = json.loads(endpoint.subscribed_events_json)
    except json.JSONDecodeError:
        return []
    return [value for value in values if value in SUPPORTED_EVENTS]


def endpoint_payload(endpoint: WebhookEndpoint) -> dict:
    return {
        "id": endpoint.id,
        "callback_url": endpoint.callback_url,
        "events": subscribed_events(endpoint),
        "schema_version": endpoint.schema_version,
        "status": endpoint.status,
        "activated_at": endpoint.activated_at,
        "verified_at": endpoint.verified_at,
        "consecutive_failures": endpoint.consecutive_failures,
        "last_success_at": endpoint.last_success_at,
        "last_failure_at": endpoint.last_failure_at,
        "last_error": endpoint.last_error,
    }


def integration_payload(db: Session, integration: WebhookIntegration) -> dict:
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.integration_id == integration.id))
    counts = {"pending": 0, "failed": 0}
    if endpoint:
        rows = db.execute(
            select(WebhookDelivery.status, func.count(WebhookDelivery.id))
            .where(WebhookDelivery.endpoint_id == endpoint.id)
            .group_by(WebhookDelivery.status)
        ).all()
        for state, count in rows:
            if state in DELIVERY_STATUSES:
                counts["pending"] += int(count)
            elif state == "failed":
                counts["failed"] += int(count)
    return {
        "id": integration.id,
        "name": integration.name,
        "token_prefix": integration.token_prefix,
        "is_active": integration.is_active,
        "created_at": integration.created_at,
        "revoked_at": integration.revoked_at,
        "endpoint": endpoint_payload(endpoint) if endpoint else None,
        "pending_deliveries": counts["pending"],
        "failed_deliveries": counts["failed"],
    }


def create_integration(db: Session, name: str, owner_id: int) -> tuple[WebhookIntegration, str, str]:
    token = issue_integration_token()
    integration = WebhookIntegration(
        id=uuid4().hex,
        name=name.strip(),
        token_hash=hash_token(token),
        token_prefix=f"{token[:18]}…",
        created_by_id=owner_id,
    )
    db.add(integration)
    db.commit()
    return integration, token, derive_webhook_secret(integration)


def rotate_integration(db: Session, integration: WebhookIntegration) -> tuple[str, str]:
    token = issue_integration_token()
    integration.token_hash = hash_token(token)
    integration.token_prefix = f"{token[:18]}…"
    integration.secret_generation += 1
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.integration_id == integration.id))
    if endpoint:
        endpoint.status = "pending"
        endpoint.verified_at = None
        endpoint.last_error = "Credentials rotated; registration verification required"
    db.commit()
    return token, derive_webhook_secret(integration)


def _is_public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_callback_url(url: str) -> str:
    normalized = url.strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443):
        raise HTTPException(status_code=422, detail="callback_url must use public HTTPS on port 443")
    if parsed.username or parsed.password or parsed.fragment:
        raise HTTPException(status_code=422, detail="callback_url contains unsupported URL components")
    try:
        addresses = {row[4][0] for row in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise HTTPException(status_code=422, detail="callback_url hostname could not be resolved") from exc
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise HTTPException(status_code=422, detail="callback_url must resolve only to public IP addresses")
    return normalized


def _signed_headers(integration: WebhookIntegration, event_id: str, body: bytes) -> dict[str, str]:
    timestamp = int(datetime.now(timezone.utc).timestamp())
    signature = sign_payload(derive_webhook_secret(integration), timestamp, body)
    return {
        "Content-Type": "application/json",
        "User-Agent": "ZPPZ-Webhook/1.0",
        "X-ZPPZ-Event-ID": event_id,
        "X-ZPPZ-Timestamp": str(timestamp),
        "X-ZPPZ-Signature": f"sha256={signature}",
    }


def verify_endpoint(integration: WebhookIntegration, callback_url: str) -> None:
    challenge = secrets.token_urlsafe(32)
    event_id = uuid4().hex
    payload = {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": "webhook.verification",
        "occurred_at": _utc_iso(datetime.utcnow()),
        "challenge": challenge,
    }
    body = _json(payload).encode()
    try:
        with httpx.Client(follow_redirects=False, timeout=httpx.Timeout(10, connect=3)) as client:
            response = client.post(callback_url, content=body, headers=_signed_headers(integration, event_id, body))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=422, detail=f"Webhook verification failed: {exc}") from exc
    if not 200 <= response.status_code < 300:
        raise HTTPException(status_code=422, detail=f"Webhook verification returned HTTP {response.status_code}")
    try:
        echoed = response.json().get("challenge")
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="Webhook verification response must be JSON") from exc
    if not isinstance(echoed, str) or not hmac.compare_digest(echoed, challenge):
        raise HTTPException(status_code=422, detail="Webhook verification challenge did not match")


def upsert_endpoint(
    db: Session,
    integration: WebhookIntegration,
    *,
    callback_url: str,
    events: list[str],
    schema_version: int,
) -> WebhookEndpoint:
    url = validate_callback_url(callback_url)
    event_names = sorted(set(events))
    if any(value not in SUPPORTED_EVENTS for value in event_names):
        raise HTTPException(status_code=422, detail="Unsupported webhook event")
    duplicate = db.scalar(
        select(WebhookEndpoint).where(
            WebhookEndpoint.callback_url == url,
            WebhookEndpoint.integration_id != integration.id,
            WebhookEndpoint.status != "revoked",
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="This callback URL is already registered")
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.integration_id == integration.id))
    event_json = _json(event_names)
    if (
        endpoint
        and endpoint.status in {"active", "failing"}
        and endpoint.callback_url == url
        and endpoint.subscribed_events_json == event_json
        and endpoint.schema_version == schema_version
    ):
        return endpoint
    if endpoint is None:
        endpoint = WebhookEndpoint(id=uuid4().hex, integration_id=integration.id)
        db.add(endpoint)
    endpoint.callback_url = url
    endpoint.subscribed_events_json = event_json
    endpoint.schema_version = schema_version
    endpoint.status = "pending"
    endpoint.verified_at = None
    endpoint.last_error = "Verification pending"
    db.commit()
    try:
        verify_endpoint(integration, url)
    except HTTPException as exc:
        endpoint.last_failure_at = datetime.utcnow()
        endpoint.last_error = str(exc.detail)[:500]
        db.commit()
        raise
    now = datetime.utcnow()
    endpoint.status = "active"
    endpoint.verified_at = now
    endpoint.activated_at = endpoint.activated_at or now
    endpoint.consecutive_failures = 0
    endpoint.last_error = ""
    db.commit()
    return endpoint


def cancel_subscription(db: Session, integration: WebhookIntegration) -> None:
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.integration_id == integration.id))
    if not endpoint:
        return
    endpoint.status = "revoked"
    endpoint.activated_at = None
    endpoint.verified_at = None
    db.execute(
        update(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == endpoint.id, WebhookDelivery.status.in_(DELIVERY_STATUSES))
        .values(status="cancelled", lease_until=None, next_attempt_at=None)
    )
    db.commit()


def _cover_file(cover_path: str) -> Path | None:
    if not cover_path:
        return None
    safe = Path(cover_path).name
    path = get_settings().assets_dir / "guess-covers" / safe
    return path if path.is_file() else None


def _chart_source_key(chart: GuessChart) -> tuple[str, int]:
    return chart.source_submission_type, int(chart.source_submission_id or chart.id)


def _changed_source_keys(db: Session, event: Event, since: datetime) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for chart in db.scalars(
        select(GuessChart).where(GuessChart.event_id == event.id, GuessChart.updated_at >= since)
    ).all():
        keys.add(_chart_source_key(chart))

    changed_submission_ids = set(
        db.scalars(
            select(Submission.id).where(Submission.event_id == event.id, Submission.updated_at >= since)
        ).all()
    )
    if changed_submission_ids:
        for chart in db.scalars(
            select(GuessChart).where(
                GuessChart.event_id == event.id,
                GuessChart.source_submission_type.in_(("normal", "j", "exhibition")),
                GuessChart.source_submission_id.in_(changed_submission_ids),
            )
        ).all():
            keys.add(_chart_source_key(chart))

    changed_archive_ids = set(
        db.scalars(
            select(AdminGuessArchive.id).where(
                AdminGuessArchive.event_id == event.id,
                AdminGuessArchive.updated_at >= since,
            )
        ).all()
    )
    if changed_archive_ids:
        for chart in db.scalars(
            select(GuessChart).where(
                GuessChart.event_id == event.id,
                GuessChart.source_submission_type == "admin",
                GuessChart.source_submission_id.in_(changed_archive_ids),
            )
        ).all():
            keys.add(_chart_source_key(chart))
    return keys


def _source_groups(
    db: Session,
    event: Event,
    *,
    source_keys: set[tuple[str, int]] | None = None,
) -> list[dict]:
    phase = get_phase_status(db, event)
    stmt = apply_chart_visibility_filter(
        select(GuessChart).where(GuessChart.event_id == event.id).order_by(GuessChart.id.asc()),
        phase,
    )
    charts = list(db.scalars(stmt).all())
    if source_keys is not None:
        charts = [chart for chart in charts if _chart_source_key(chart) in source_keys]
    grouped: dict[tuple[str, int], list[GuessChart]] = defaultdict(list)
    for chart in charts:
        grouped[(chart.source_submission_type, int(chart.source_submission_id or chart.id))].append(chart)

    submission_ids = {
        source_id for (source_type, source_id) in grouped if source_type in {"normal", "j", "exhibition"}
    }
    submissions = {
        row.id: row for row in db.scalars(select(Submission).where(Submission.id.in_(submission_ids))).all()
    } if submission_ids else {}
    active_submission_ids = set(
        db.scalars(
            select(SubmissionProcessingJob.result_submission_id).where(
                SubmissionProcessingJob.result_submission_id.in_(submission_ids),
                SubmissionProcessingJob.status.in_(("queued", "processing")),
            )
        ).all()
    ) if submission_ids else set()
    admin_ids = {source_id for (source_type, source_id) in grouped if source_type == "admin"}
    archives = {
        row.id: row for row in db.scalars(select(AdminGuessArchive).where(AdminGuessArchive.id.in_(admin_ids))).all()
    } if admin_ids else {}

    result: list[dict] = []
    for (source_type, source_id), rows in grouped.items():
        source_version = ""
        if source_type in {"normal", "j", "exhibition"}:
            submission = submissions.get(source_id)
            if (
                not submission
                or submission.public_package_status != "ready"
                or submission.id in active_submission_ids
            ):
                continue
            source_version = submission.storage_path
        elif source_type == "admin":
            archive = archives.get(source_id)
            source_version = archive.storage_path if archive else ""
        first = rows[0]
        levels = [
            {
                "chart_id": row.id,
                "slot": row.source_level_slot,
                "level": row.level,
                "designer": row.designer,
            }
            for row in sorted(rows, key=lambda item: (item.source_level_slot, item.id))
        ]
        chart_set = {
            "title": first.title,
            "artist": first.author,
            "track": first.lane,
            "is_self_selected": first.is_self_selected,
            "levels": levels,
            "page_url": f"{get_settings().public_base_url}/guess",
        }
        semantic = {
            "title": first.title,
            "artist": first.author,
            "track": first.lane,
            "is_self_selected": first.is_self_selected,
            "levels": [
                {"slot": item["slot"], "level": item["level"], "designer": item["designer"]}
                for item in levels
            ],
            "source_version": source_version,
        }
        result.append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "source_version": source_version,
                "fingerprint": hashlib.sha256(_json(semantic).encode()).hexdigest(),
                "chart_set": chart_set,
                "cover_path": next((row.cover_path for row in rows if row.cover_path), ""),
            }
        )
    return result


def _changes(previous: dict, current: dict) -> dict:
    changed_fields = [
        key for key in ("title", "artist", "track", "is_self_selected") if previous.get(key) != current.get(key)
    ]
    before = {str(item["slot"]): item for item in previous.get("levels", [])}
    after = {str(item["slot"]): item for item in current.get("levels", [])}
    return {
        "changed_fields": changed_fields,
        "levels_added": [after[key] for key in sorted(after.keys() - before.keys())],
        "levels_removed": [before[key] for key in sorted(before.keys() - after.keys())],
        "levels_changed": [
            {"slot": key, "before": before[key], "after": after[key]}
            for key in sorted(before.keys() & after.keys())
            if before[key].get("level") != after[key].get("level")
            or before[key].get("designer") != after[key].get("designer")
        ],
    }


def _snapshot_cover_file(db: Session, webhook_event: WebhookEvent, source: Path) -> str:
    suffix = source.suffix.lower() or ".bin"
    asset_id = uuid4().hex
    object_key = f"webhook-events/{webhook_event.id}/cover{suffix}"
    with Image.open(source) as image:
        image.verify()
    with Image.open(source) as image:
        width, height = image.size
        content_type = Image.MIME.get(image.format or "") or mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    get_object_store().put_file(object_key, source, content_type=content_type, content_disposition="inline")
    db.add(
        WebhookEventAsset(
            id=asset_id,
            webhook_event_id=webhook_event.id,
            object_key=object_key,
            content_type=content_type,
            width=width,
            height=height,
            size_bytes=source.stat().st_size,
            sha256=digest,
        )
    )
    return object_key


def _snapshot_cover(db: Session, webhook_event: WebhookEvent, cover_path: str) -> str | None:
    source = _cover_file(cover_path)
    return _snapshot_cover_file(db, webhook_event, source) if source else None


def _create_event_for_source(db: Session, event: Event, source: dict, state: ChartPublicationState | None) -> int:
    if state and state.fingerprint == source["fingerprint"]:
        return 0
    now = datetime.utcnow()
    revision = state.revision + 1 if state else 1
    event_type = "chart.updated" if state else "chart.published"
    previous = json.loads(state.snapshot_json) if state else None
    event_uid = uuid4().hex
    payload = {
        "schema_version": 1,
        "event_id": event_uid,
        "event_type": event_type,
        "occurred_at": _utc_iso(now),
        "competition": {"id": event.id, "slug": event.slug, "name": event.name},
        "source": {"type": source["source_type"], "id": source["source_id"], "revision": revision},
        "chart_set": source["chart_set"],
        "changes": _changes(previous, source["chart_set"]) if previous else None,
    }
    webhook_event = WebhookEvent(
        id=event_uid,
        event_id=event.id,
        event_type=event_type,
        source_type=source["source_type"],
        source_id=source["source_id"],
        revision=revision,
        payload_json=_json(payload),
    )
    db.add(webhook_event)
    db.flush()
    object_key = _snapshot_cover(db, webhook_event, source["cover_path"])
    if state:
        state.revision = revision
        state.fingerprint = source["fingerprint"]
        state.source_version = source["source_version"]
        state.snapshot_json = _json(source["chart_set"])
        state.last_published_at = now
    else:
        db.add(
            ChartPublicationState(
                event_id=event.id,
                source_type=source["source_type"],
                source_id=source["source_id"],
                revision=revision,
                fingerprint=source["fingerprint"],
                source_version=source["source_version"],
                snapshot_json=_json(source["chart_set"]),
                first_published_at=now,
                last_published_at=now,
            )
        )
    endpoints = db.scalars(
        select(WebhookEndpoint)
        .join(WebhookIntegration, WebhookIntegration.id == WebhookEndpoint.integration_id)
        .where(
            WebhookIntegration.is_active.is_(True),
            WebhookEndpoint.activated_at.is_not(None),
            WebhookEndpoint.status != "revoked",
        )
    ).all()
    for endpoint in endpoints:
        if event_type in subscribed_events(endpoint):
            db.add(
                WebhookDelivery(
                    webhook_event_id=event_uid,
                    endpoint_id=endpoint.id,
                    status="pending",
                    next_attempt_at=now,
                )
            )
    try:
        db.commit()
    except Exception:
        db.rollback()
        if object_key:
            try:
                get_object_store().delete(object_key)
            except Exception:
                logger.warning("Could not remove orphaned webhook asset %s", object_key)
        raise
    return 1


def materialize_publication_events() -> int:
    created = 0
    with SessionLocal() as db:
        system_state = db.get(WebhookSystemState, 1)
        event = get_current_event(db)
        phase_status = get_phase_status(db, event)
        visibility_key = chart_visibility_key(phase_status)
        now = datetime.utcnow()
        if system_state is None:
            sources = _source_groups(db, event)
        else:
            full_scan = (
                system_state.last_visibility_key != visibility_key
                or system_state.last_publication_scan_at is None
            )
            if full_scan:
                sources = _source_groups(db, event)
            else:
                changed_keys = _changed_source_keys(db, event, system_state.last_publication_scan_at)
                if not changed_keys:
                    system_state.last_publication_scan_at = now
                    system_state.last_visibility_key = visibility_key
                    db.commit()
                    return 0
                sources = _source_groups(db, event, source_keys=changed_keys)

        state_by_key: dict[tuple[str, int], ChartPublicationState] = {}
        if sources:
            conditions = [
                (ChartPublicationState.source_type == source["source_type"])
                & (ChartPublicationState.source_id == source["source_id"])
                for source in sources
            ]
            existing_states = db.scalars(
                select(ChartPublicationState).where(
                    ChartPublicationState.event_id == event.id,
                    or_(*conditions),
                )
            ).all()
            state_by_key = {(state.source_type, state.source_id): state for state in existing_states}

        for source in sources:
            state = state_by_key.get((source["source_type"], source["source_id"]))
            try:
                created += _create_event_for_source(db, event, source, state)
            except IntegrityError:
                db.rollback()
            except Exception:
                db.rollback()
                logger.exception(
                    "Could not materialize webhook event for %s:%s",
                    source["source_type"],
                    source["source_id"],
                )
        if system_state is not None:
            system_state.last_publication_scan_at = now
            system_state.last_visibility_key = visibility_key
            db.commit()
    return created


def seed_publication_baseline(db: Session) -> int:
    if db.get(WebhookSystemState, 1):
        return 0
    event = get_current_event(db)
    now = datetime.utcnow()
    created = 0
    for source in _source_groups(db, event):
        existing = db.scalar(
            select(ChartPublicationState.id).where(
                ChartPublicationState.event_id == event.id,
                ChartPublicationState.source_type == source["source_type"],
                ChartPublicationState.source_id == source["source_id"],
            )
        )
        if existing:
            continue
        db.add(
            ChartPublicationState(
                event_id=event.id,
                source_type=source["source_type"],
                source_id=source["source_id"],
                revision=1,
                fingerprint=source["fingerprint"],
                source_version=source["source_version"],
                snapshot_json=_json(source["chart_set"]),
                first_published_at=now,
                last_published_at=now,
            )
        )
        created += 1
    db.add(WebhookSystemState(
        id=1,
        baseline_completed_at=now,
        last_publication_scan_at=now,
        last_visibility_key=chart_visibility_key(get_phase_status(db, event)),
    ))
    db.commit()
    return created


def _asset_signature(asset_id: str, endpoint_id: str, expires: int) -> str:
    message = f"webhook-asset-v1:{asset_id}:{endpoint_id}:{expires}".encode()
    return hmac.new(get_settings().webhook_signing_master_key.encode(), message, hashlib.sha256).hexdigest()


def asset_url(asset: WebhookEventAsset, endpoint_id: str) -> tuple[str, int]:
    expires = int(datetime.now(timezone.utc).timestamp()) + get_settings().webhook_asset_url_ttl_seconds
    signature = _asset_signature(asset.id, endpoint_id, expires)
    url = (
        f"{get_settings().public_base_url}{get_settings().api_prefix}/integrations/webhook-assets/{asset.id}"
        f"?endpoint={endpoint_id}&expires={expires}&signature={signature}"
    )
    return url, expires


def validate_asset_signature(asset_id: str, endpoint_id: str, expires: int, signature: str) -> None:
    now = int(datetime.now(timezone.utc).timestamp())
    if expires < now:
        raise HTTPException(status_code=403, detail="Cover URL has expired")
    expected = _asset_signature(asset_id, endpoint_id, expires)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid cover URL signature")


def _delivery_payload(db: Session, event: WebhookEvent, endpoint: WebhookEndpoint) -> dict:
    payload = json.loads(event.payload_json)
    asset = db.scalar(select(WebhookEventAsset).where(WebhookEventAsset.webhook_event_id == event.id))
    cover = None
    if asset:
        url, expires = asset_url(asset, endpoint.id)
        cover = {
            "url": url,
            "content_type": asset.content_type,
            "width": asset.width,
            "height": asset.height,
            "size_bytes": asset.size_bytes,
            "sha256": asset.sha256,
            "expires_at": _utc_iso(datetime.utcfromtimestamp(expires)),
        }
    payload["chart_set"]["cover"] = cover
    return payload


def claim_next_delivery(db: Session) -> int | None:
    now = datetime.utcnow()
    candidates = db.scalars(
        select(WebhookDelivery)
        .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
        .join(WebhookIntegration, WebhookIntegration.id == WebhookEndpoint.integration_id)
        .where(
            WebhookIntegration.is_active.is_(True),
            WebhookEndpoint.status.in_(("active", "failing")),
            or_(
                (
                    WebhookDelivery.status.in_(("pending", "retrying"))
                    & or_(WebhookDelivery.next_attempt_at.is_(None), WebhookDelivery.next_attempt_at <= now)
                ),
                ((WebhookDelivery.status == "delivering") & (WebhookDelivery.lease_until < now)),
            ),
        )
        .order_by(WebhookDelivery.created_at.asc(), WebhookDelivery.id.asc())
        .limit(50)
    ).all()
    for candidate in candidates:
        earlier = db.scalar(
            select(WebhookDelivery.id).where(
                WebhookDelivery.endpoint_id == candidate.endpoint_id,
                WebhookDelivery.id < candidate.id,
                WebhookDelivery.status.in_(DELIVERY_STATUSES),
            ).limit(1)
        )
        if earlier:
            continue
        result = db.execute(
            update(WebhookDelivery)
            .where(
                WebhookDelivery.id == candidate.id,
                WebhookDelivery.status.in_(DELIVERY_STATUSES),
            )
            .values(status="delivering", attempts=WebhookDelivery.attempts + 1, lease_until=now + timedelta(seconds=LEASE_SECONDS))
        )
        db.commit()
        if result.rowcount == 1:
            return candidate.id
    return None


def process_delivery(delivery_id: int) -> None:
    with SessionLocal() as db:
        delivery = db.get(WebhookDelivery, delivery_id)
        if not delivery or delivery.status != "delivering":
            return
        endpoint = db.get(WebhookEndpoint, delivery.endpoint_id)
        event = db.get(WebhookEvent, delivery.webhook_event_id)
        integration = db.get(WebhookIntegration, endpoint.integration_id) if endpoint else None
        if not endpoint or not event or not integration or not integration.is_active:
            delivery.status = "cancelled"
            delivery.lease_until = None
            db.commit()
            return
        response_status = None
        error = ""
        try:
            validate_callback_url(endpoint.callback_url)
            body = _json(_delivery_payload(db, event, endpoint)).encode()
            with httpx.Client(follow_redirects=False, timeout=httpx.Timeout(10, connect=3)) as client:
                response = client.post(
                    endpoint.callback_url,
                    content=body,
                    headers=_signed_headers(integration, event.id, body),
                )
            response_status = response.status_code
            if not 200 <= response.status_code < 300:
                error = f"Webhook returned HTTP {response.status_code}"
        except (httpx.HTTPError, HTTPException) as exc:
            error = str(exc.detail if isinstance(exc, HTTPException) else exc)
        now = datetime.utcnow()
        if not error:
            delivery.status = "delivered"
            delivery.delivered_at = now
            delivery.next_attempt_at = None
            delivery.lease_until = None
            delivery.response_status = response_status
            delivery.last_error = ""
            endpoint.status = "active"
            endpoint.consecutive_failures = 0
            endpoint.last_success_at = now
            endpoint.last_error = ""
        else:
            delivery.response_status = response_status
            delivery.last_error = error[:500]
            delivery.lease_until = None
            endpoint.consecutive_failures += 1
            endpoint.last_failure_at = now
            endpoint.last_error = error[:500]
            if endpoint.consecutive_failures >= 5:
                endpoint.status = "failing"
            if now - delivery.created_at >= RETRY_WINDOW:
                delivery.status = "failed"
                delivery.next_attempt_at = None
            else:
                delay = RETRY_DELAYS[min(max(delivery.attempts - 1, 0), len(RETRY_DELAYS) - 1)]
                delivery.status = "retrying"
                delivery.next_attempt_at = now + timedelta(seconds=delay)
        db.commit()


def process_next_delivery() -> bool:
    with SessionLocal() as db:
        delivery_id = claim_next_delivery(db)
    if delivery_id is None:
        return False
    process_delivery(delivery_id)
    return True


def create_test_delivery(db: Session, integration: WebhookIntegration) -> WebhookEvent:
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.integration_id == integration.id))
    if not endpoint or endpoint.status not in {"active", "failing"}:
        raise HTTPException(status_code=409, detail="Webhook endpoint is not active")
    now = datetime.utcnow()
    if integration.last_test_at and now - integration.last_test_at < timedelta(minutes=1):
        raise HTTPException(status_code=429, detail="A test event can be sent once per minute")
    current = get_current_event(db)
    event_uid = uuid4().hex
    payload = {
        "schema_version": 1,
        "event_id": event_uid,
        "event_type": "webhook.test",
        "occurred_at": _utc_iso(now),
        "competition": {"id": current.id, "slug": current.slug, "name": current.name},
        "source": {"type": "test", "id": 0, "revision": 1},
        "chart_set": {
            "title": "Webhook Test",
            "artist": "ZPPZ Arena",
            "track": "test",
            "is_self_selected": False,
            "levels": [{"chart_id": 0, "slot": "0", "level": "Test", "designer": "Webhook"}],
            "page_url": f"{get_settings().public_base_url}/guess",
        },
        "changes": None,
    }
    webhook_event = WebhookEvent(
        id=event_uid,
        event_id=current.id,
        event_type="webhook.test",
        source_type="test",
        source_id=-secrets.randbelow(2_000_000_000) - 1,
        revision=1,
        payload_json=_json(payload),
    )
    db.add(webhook_event)
    db.flush()
    repo_root = Path(__file__).resolve().parents[4]
    test_cover = repo_root / "bg" / "zppz4_square.png"
    object_key = None
    if test_cover.is_file():
        object_key = _snapshot_cover_file(db, webhook_event, test_cover)
    db.add(WebhookDelivery(webhook_event_id=event_uid, endpoint_id=endpoint.id, status="pending", next_attempt_at=now))
    integration.last_test_at = now
    try:
        db.commit()
    except Exception:
        db.rollback()
        if object_key:
            get_object_store().delete(object_key)
        raise
    return webhook_event


def retry_failed_deliveries(db: Session, integration: WebhookIntegration) -> int:
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.integration_id == integration.id))
    if not endpoint:
        return 0
    result = db.execute(
        update(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == endpoint.id, WebhookDelivery.status == "failed")
        .values(status="retrying", attempts=0, next_attempt_at=datetime.utcnow(), lease_until=None, last_error="")
    )
    db.commit()
    return int(result.rowcount or 0)


def cleanup_expired_assets() -> int:
    cutoff = datetime.utcnow() - timedelta(days=get_settings().webhook_asset_retention_days)
    with SessionLocal() as db:
        assets = list(
            db.scalars(
                select(WebhookEventAsset).where(WebhookEventAsset.created_at < cutoff).order_by(WebhookEventAsset.created_at).limit(100)
            ).all()
        )
        deleted = 0
        for asset in assets:
            try:
                get_object_store().delete(asset.object_key)
            except Exception:
                logger.exception("Could not delete expired webhook asset %s", asset.object_key)
                continue
            db.delete(asset)
            deleted += 1
        db.commit()
        return deleted
