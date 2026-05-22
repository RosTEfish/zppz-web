from functools import lru_cache
from pathlib import Path
import os


class Settings:
    app_name = "ZPPZ Arena"
    api_prefix = "/api/v1"
    database_url = os.getenv("DATABASE_URL", "sqlite:///./zppz_v2.db")
    secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
    session_cookie_name = os.getenv("SESSION_COOKIE_NAME", "zppz_session")
    session_expire_hours = int(os.getenv("SESSION_EXPIRE_HOURS", "168"))
    cors_origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if item.strip()]
    data_dir = Path(os.getenv("DATA_DIR", "/data")).resolve()
    uploads_dir = data_dir / "uploads"
    assets_dir = data_dir / "assets"
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "100"))
    allowed_extensions = {item.strip().lower() for item in os.getenv("ALLOWED_EXTENSIONS", "mp3,wav,flac,aac,m4a,ogg,zip,7z,rar").split(",") if item.strip()}
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
    return settings

