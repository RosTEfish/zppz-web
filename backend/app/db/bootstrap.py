import json
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import OWNER_ROLE, USER_IDENTITIES, ensure_roles, hash_password
from app.db.session import Base, engine
from app.models import Event, EventSetting, User


GUESS_CHART_METADATA_VERSION = 1
logger = logging.getLogger(__name__)


def sync_permissions_file(db: Session, roles: dict) -> None:
    settings = get_settings()
    path = settings.data_dir / "permissions.json"
    if not path.exists():
        sample = {
            "users": [
                {
                    "user_code": settings.admin_seed_code,
                    "roles": ["admin", "pool_editor", "participant"],
                    "identity": "participant",
                    "display_name": "赛事管理员",
                    "is_active": True,
                }
            ]
        }
        path.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"permissions.json 格式错误: {exc}") from exc

    changed = False
    for row in payload.get("users", []):
        user_code = str(row.get("user_code") or "").strip()
        if not user_code:
            continue
        user = db.scalar(select(User).where(User.user_code == user_code))
        if not user:
            continue

        if "identity" in row and row["identity"] in USER_IDENTITIES:
            user.identity = row["identity"]
            changed = True
        if "display_name" in row:
            user.display_name = str(row.get("display_name") or "")
            changed = True
        if "is_active" in row:
            user.is_active = bool(row["is_active"])
            changed = True
        if "roles" in row:
            requested_roles = row.get("roles", [])
            if not isinstance(requested_roles, list):
                requested_roles = []
            requested_names = {
                str(name)
                for name in requested_roles
                if str(name) in roles and str(name) != OWNER_ROLE
            }
            if user.has_role(OWNER_ROLE):
                requested_names.add(OWNER_ROLE)
            next_roles = [role for name, role in roles.items() if name in requested_names]
            user.roles = next_roles
            changed = True

    if changed:
        db.commit()


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


def upgrade_schema() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("prepend_sys_path", str(backend_root))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def check_schema_current() -> None:
    """Fail fast when a deployed database was not prepared for this release."""
    if get_settings().database_url.endswith(":memory:"):
        return
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    expected = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != expected:
        raise RuntimeError(
            f"database schema is not prepared (current={current or 'none'}, expected={expected}); "
            "run `python -m app.prepare` before starting the service"
        )


def seed_defaults(db: Session) -> None:
    settings = get_settings()
    roles = ensure_roles(db)
    current_event = db.scalar(select(Event).where(Event.is_current.is_(True)))
    if not current_event:
        current_event = Event(name="这谱谱这 #5", slug="zppz-current", is_current=True)
        current_event.settings = EventSetting()
        db.add(current_event)
        db.commit()

    admin = db.scalar(select(User).where(User.user_code == settings.admin_seed_code))
    if not admin:
        if not settings.admin_seed_password:
            logger.warning(
                "ADMIN_SEED_PASSWORD is not set; skipping default admin seeding. "
                "Set ADMIN_SEED_PASSWORD and re-run `python -m app.prepare` to create the default admin."
            )
        else:
            admin = User(
                user_code=settings.admin_seed_code,
                qq_id="0",
                password_hash=hash_password(settings.admin_seed_password),
                identity="participant",
                display_name="赛事管理员",
                roles=[roles["admin"], roles["pool_editor"], roles["participant"]],
            )
            db.add(admin)
            db.commit()

    sync_permissions_file(db, roles)


def backfill_guess_chart_metadata(db: Session) -> None:
    from app.modules.guess_game.importer import rebuild_event_charts

    setting_ids = list(
        db.scalars(
            select(EventSetting.id).where(
                EventSetting.guess_chart_metadata_version < GUESS_CHART_METADATA_VERSION
            )
        ).all()
    )
    for setting_id in setting_ids:
        setting = db.get(EventSetting, setting_id)
        if not setting or setting.guess_chart_metadata_version >= GUESS_CHART_METADATA_VERSION:
            continue
        event_id = setting.event_id
        try:
            rebuild_event_charts(db, event_id)
            setting = db.get(EventSetting, setting_id)
            if setting:
                setting.guess_chart_metadata_version = GUESS_CHART_METADATA_VERSION
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("赛事 %s 的猜谱元数据自动回填失败，将在下次启动时重试", event_id)
