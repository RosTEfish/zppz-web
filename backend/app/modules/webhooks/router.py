from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import require_role
from app.db.session import get_db
from app.models import User, WebhookDelivery, WebhookEndpoint, WebhookEventAsset, WebhookIntegration
from app.modules.object_storage import get_object_store
from app.modules.webhooks.service import (
    DELIVERY_STATUSES,
    cancel_subscription,
    create_integration,
    create_test_delivery,
    endpoint_payload,
    integration_from_request,
    integration_payload,
    retry_failed_deliveries,
    rotate_integration,
    upsert_endpoint,
    validate_asset_signature,
)
from app.schemas import (
    WebhookCredentialsRead,
    WebhookEndpointRead,
    WebhookEndpointWrite,
    WebhookIntegrationCreate,
    WebhookIntegrationRead,
    WebhookTestRead,
)


router = APIRouter(prefix="/integrations", tags=["integrations"])
admin_router = APIRouter(prefix="/admin/webhook-integrations", tags=["admin-webhook-integrations"])


def _integration_dependency(request: Request, db: Session = Depends(get_db)) -> WebhookIntegration:
    return integration_from_request(request, db)


def _active_integration(db: Session, integration_id: str) -> WebhookIntegration:
    integration = db.get(WebhookIntegration, integration_id)
    if not integration or not integration.is_active:
        raise HTTPException(status_code=404, detail="Webhook integration not found")
    return integration


@admin_router.get("", response_model=list[WebhookIntegrationRead])
def list_integrations(
    _: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(select(WebhookIntegration).order_by(WebhookIntegration.created_at.desc())).all()
    return [integration_payload(db, row) for row in rows]


@admin_router.post("", response_model=WebhookCredentialsRead, status_code=201)
def admin_create_integration(
    payload: WebhookIntegrationCreate,
    owner: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
) -> dict:
    integration, token, secret = create_integration(db, payload.name, owner.id)
    return {"integration_id": integration.id, "integration_token": token, "webhook_secret": secret}


@admin_router.post("/{integration_id}/rotate-credentials", response_model=WebhookCredentialsRead)
def admin_rotate_credentials(
    integration_id: str,
    _: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
) -> dict:
    integration = _active_integration(db, integration_id)
    token, secret = rotate_integration(db, integration)
    return {"integration_id": integration.id, "integration_token": token, "webhook_secret": secret}


@admin_router.post("/{integration_id}/test", response_model=WebhookTestRead, status_code=202)
def admin_test_integration(
    integration_id: str,
    _: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
) -> dict:
    event = create_test_delivery(db, _active_integration(db, integration_id))
    return {"event_id": event.id, "status": "queued"}


@admin_router.post("/{integration_id}/retry-failed")
def admin_retry_failed(
    integration_id: str,
    _: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
) -> dict:
    retried = retry_failed_deliveries(db, _active_integration(db, integration_id))
    return {"message": f"Queued {retried} failed deliveries", "retried": retried}


@admin_router.delete("/{integration_id}", status_code=204)
def admin_revoke_integration(
    integration_id: str,
    _: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
):
    integration = _active_integration(db, integration_id)
    integration.is_active = False
    integration.revoked_at = datetime.utcnow()
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.integration_id == integration.id))
    if endpoint:
        endpoint.status = "revoked"
        db.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.endpoint_id == endpoint.id, WebhookDelivery.status.in_(DELIVERY_STATUSES))
            .values(status="cancelled", lease_until=None, next_attempt_at=None)
        )
    db.commit()


@router.put("/webhook-subscription", response_model=WebhookEndpointRead)
def register_subscription(
    payload: WebhookEndpointWrite,
    integration: WebhookIntegration = Depends(_integration_dependency),
    db: Session = Depends(get_db),
) -> dict:
    endpoint = upsert_endpoint(
        db,
        integration,
        callback_url=payload.callback_url,
        events=list(payload.events),
        schema_version=payload.schema_version,
    )
    return endpoint_payload(endpoint)


@router.get("/webhook-subscription", response_model=WebhookEndpointRead)
def get_subscription(
    integration: WebhookIntegration = Depends(_integration_dependency),
    db: Session = Depends(get_db),
) -> dict:
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.integration_id == integration.id))
    if not endpoint or endpoint.status == "revoked":
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    return endpoint_payload(endpoint)


@router.delete("/webhook-subscription", status_code=204)
def delete_subscription(
    integration: WebhookIntegration = Depends(_integration_dependency),
    db: Session = Depends(get_db),
):
    cancel_subscription(db, integration)


@router.post("/webhook-subscription/test", response_model=WebhookTestRead, status_code=202)
def test_subscription(
    integration: WebhookIntegration = Depends(_integration_dependency),
    db: Session = Depends(get_db),
) -> dict:
    event = create_test_delivery(db, integration)
    return {"event_id": event.id, "status": "queued"}


@router.get("/webhook-assets/{asset_id}")
def webhook_cover_asset(
    asset_id: str,
    endpoint: str = Query(..., min_length=32, max_length=32),
    expires: int = Query(..., gt=0),
    signature: str = Query(..., min_length=64, max_length=64),
    db: Session = Depends(get_db),
):
    validate_asset_signature(asset_id, endpoint, expires, signature)
    asset = db.get(WebhookEventAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Webhook cover asset not found")
    permitted = db.scalar(
        select(WebhookDelivery.id).where(
            WebhookDelivery.webhook_event_id == asset.webhook_event_id,
            WebhookDelivery.endpoint_id == endpoint,
        ).limit(1)
    )
    if not permitted:
        raise HTTPException(status_code=403, detail="Cover URL is not valid for this endpoint")
    store = get_object_store()
    try:
        info = store.head(asset.object_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Webhook cover asset not found") from exc
    headers = {
        "Cache-Control": "private, max-age=3600",
        "Content-Length": str(info.size),
        "ETag": f'"{asset.sha256}"',
        "Content-Encoding": "identity",
    }
    if store.backend == "r2":
        url = store.create_inline_url(asset.object_key, asset.content_type, min(max(expires - int(datetime.utcnow().timestamp()), 60), 3600))
        return RedirectResponse(url, status_code=307, headers={"Cache-Control": "private, no-store"})
    return StreamingResponse(store.chunks(asset.object_key, info.size), media_type=asset.content_type, headers=headers)
