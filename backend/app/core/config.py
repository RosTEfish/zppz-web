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
    secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
    session_cookie_name = os.getenv("SESSION_COOKIE_NAME", "zppz_session")
    session_expire_hours = int(os.getenv("SESSION_EXPIRE_HOURS", "168"))
    cors_origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if item.strip()]
    data_dir = Path(os.getenv("DATA_DIR", "/data")).resolve()
    uploads_dir = data_dir / "uploads"
    assets_dir = data_dir / "assets"
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "100"))
    configured_extensions = parse_allowed_extensions(os.getenv("ALLOWED_EXTENSIONS"))
    allowed_extensions = (configured_extensions & ARCHIVE_UPLOAD_EXTENSIONS) or ARCHIVE_UPLOAD_EXTENSIONS
    admin_seed_code = os.getenv("ADMIN_SEED_CODE", "admin")
    admin_seed_password = os.getenv("ADMIN_SEED_PASSWORD", "change-me")
    secure_cookies = os.getenv("SECURE_COOKIES", "false").lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "rules").mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "banlists").mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "backgrounds").mkdir(parents=True, exist_ok=True)
    (settings.assets_dir / "guess-covers").mkdir(parents=True, exist_ok=True)
    return settings
