from functools import lru_cache
from pathlib import Path
import os


ARCHIVE_UPLOAD_EXTENSIONS = {"zip", "7z", "rar"}


def parse_allowed_extensions(value: str | None) -> set[str]:
    if not value:
        return set()
    normalized = value.replace(";", ",").replace("，", ",").replace("、", ",")
    return {item.strip().lower().lstrip(".") for item in normalized.split(",") if item.strip()}


class Settings:
    app_name = "ZPPZ Arena"
    api_prefix = "/api/v1"
    database_url = os.getenv("DATABASE_URL", "sqlite:///./zppz_v2.db")
    db_pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
    db_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "5"))
    db_pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    db_pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "1800"))
    slow_request_ms = int(os.getenv("SLOW_REQUEST_MS", "500"))
    public_base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").strip().rstrip("/")
    webhook_scan_interval_seconds = float(os.getenv("WEBHOOK_SCAN_INTERVAL_SECONDS", "2"))
    webhook_asset_url_ttl_seconds = int(os.getenv("WEBHOOK_ASSET_URL_TTL_SECONDS", "604800"))
    webhook_asset_retention_days = int(os.getenv("WEBHOOK_ASSET_RETENTION_DAYS", "30"))
    secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
    webhook_signing_master_key = os.getenv("WEBHOOK_SIGNING_MASTER_KEY", secret_key).strip()
    session_cookie_name = os.getenv("SESSION_COOKIE_NAME", "zppz_session")
    session_expire_hours = int(os.getenv("SESSION_EXPIRE_HOURS", "168"))
    cors_origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:4173,http://127.0.0.1:4173").split(",") if item.strip()]
    data_dir = Path(os.getenv("DATA_DIR", "/data")).resolve()
    uploads_dir = data_dir / "uploads"
    assets_dir = data_dir / "assets"
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "100"))
    object_storage_backend = os.getenv("OBJECT_STORAGE_BACKEND", "local").strip().lower()
    r2_account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    r2_bucket_name = os.getenv("R2_BUCKET_NAME", "").strip()
    r2_access_key_id = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    r2_secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    r2_upload_url_ttl_seconds = int(os.getenv("R2_UPLOAD_URL_TTL_SECONDS", "600"))
    r2_download_url_ttl_seconds = int(os.getenv("R2_DOWNLOAD_URL_TTL_SECONDS", "300"))
    upload_intent_ttl_seconds = int(os.getenv("UPLOAD_INTENT_TTL_SECONDS", "900"))
    preview_enabled = os.getenv("PREVIEW_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    preview_player_url = os.getenv("PREVIEW_PLAYER_URL", "").strip()
    preview_player_origin = os.getenv("PREVIEW_PLAYER_ORIGIN", "http://localhost:4173").strip().rstrip("/")
    preview_url_ttl_seconds = int(os.getenv("PREVIEW_URL_TTL_SECONDS", "21600"))
    preview_backfill_poll_seconds = int(os.getenv("PREVIEW_BACKFILL_POLL_SECONDS", "2"))
    configured_extensions = parse_allowed_extensions(os.getenv("ALLOWED_EXTENSIONS"))
    allowed_extensions = (configured_extensions & ARCHIVE_UPLOAD_EXTENSIONS) or ARCHIVE_UPLOAD_EXTENSIONS
    admin_seed_code = os.getenv("ADMIN_SEED_CODE", "admin")
    admin_seed_password = os.getenv("ADMIN_SEED_PASSWORD", "change-me")
    secure_cookies = os.getenv("SECURE_COOKIES", "false").lower() in {"1", "true", "yes", "on"}
    ban_external_provider = os.getenv("BAN_EXTERNAL_PROVIDER", "disabled")
    ban_external_api_url = os.getenv("BAN_EXTERNAL_API_URL", "")
    ban_external_api_key = os.getenv("BAN_EXTERNAL_API_KEY", "")
    ban_external_timeout_ms = int(os.getenv("BAN_EXTERNAL_TIMEOUT_MS", "2000"))
    ban_external_cache_ttl_seconds = int(os.getenv("BAN_EXTERNAL_CACHE_TTL_SECONDS", "604800"))

    @property
    def r2_endpoint(self) -> str:
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    def validate_object_storage(self) -> None:
        if self.object_storage_backend not in {"local", "r2"}:
            raise RuntimeError("OBJECT_STORAGE_BACKEND must be local or r2")
        if self.object_storage_backend == "r2":
            missing = [
                name
                for name, value in (
                    ("R2_ACCOUNT_ID", self.r2_account_id),
                    ("R2_BUCKET_NAME", self.r2_bucket_name),
                    ("R2_ACCESS_KEY_ID", self.r2_access_key_id),
                    ("R2_SECRET_ACCESS_KEY", self.r2_secret_access_key),
                )
                if not value
            ]
            if missing:
                raise RuntimeError(f"missing R2 configuration: {', '.join(missing)}")

    def validate_preview(self) -> None:
        if not self.preview_enabled:
            return
        if not self.preview_player_url or not self.preview_player_origin:
            raise RuntimeError("PREVIEW_PLAYER_URL and PREVIEW_PLAYER_ORIGIN are required when PREVIEW_ENABLED=true")
        if not self.preview_player_url.startswith(f"{self.preview_player_origin}/"):
            raise RuntimeError("PREVIEW_PLAYER_URL must be hosted on PREVIEW_PLAYER_ORIGIN")
        if self.preview_url_ttl_seconds < 60:
            raise RuntimeError("PREVIEW_URL_TTL_SECONDS must be at least 60")

    def validate_webhooks(self) -> None:
        if not self.public_base_url.startswith(("http://", "https://")):
            raise RuntimeError("PUBLIC_BASE_URL must be an absolute HTTP(S) URL")
        if len(self.webhook_signing_master_key) < 16:
            raise RuntimeError("WEBHOOK_SIGNING_MASTER_KEY must be at least 16 characters")
        if self.webhook_scan_interval_seconds <= 0:
            raise RuntimeError("WEBHOOK_SCAN_INTERVAL_SECONDS must be positive")
        if self.webhook_asset_url_ttl_seconds < 60:
            raise RuntimeError("WEBHOOK_ASSET_URL_TTL_SECONDS must be at least 60")
        if self.webhook_asset_retention_days < 8:
            raise RuntimeError("WEBHOOK_ASSET_RETENTION_DAYS must be at least 8")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "rules").mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "banlists").mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "backgrounds").mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "guess-covers").mkdir(parents=True, exist_ok=True)
    return settings
