from __future__ import annotations

from fastapi import APIRouter

from app.modules.submissions.admin import register_admin_routes
from app.modules.submissions.downloads import register_download_routes
from app.modules.submissions.listing import register_listing_routes
from app.modules.submissions.submit import register_submit_routes
from app.modules.submissions.upload import register_upload_routes

# Registration order matches the previous monolithic router so path matching
# and OpenAPI operation order stay the same.
router = APIRouter(prefix="/submissions", tags=["submissions"])
admin_router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])

register_listing_routes(router)
register_upload_routes(router)
register_submit_routes(router)
register_download_routes(router)
register_admin_routes(admin_router)
