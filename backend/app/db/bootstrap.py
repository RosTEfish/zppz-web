import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import ensure_roles, hash_password
from app.db.session import Base, engine
from app.models import Event, EventSetting, User


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

        if "identity" in row and row["identity"] in {"participant", "audience"}:
            user.identity = row["identity"]
            changed = True
        if "display_name" in row:
            user.display_name = str(row.get("display_name") or "")
            changed = True
        if "is_active" in row:
            user.is_active = bool(row["is_active"])
            changed = True
        if "roles" in row:
            next_roles = [roles[name] for name in row.get("roles", []) if name in roles]
            user.roles = next_roles
            changed = True

    if changed:
        db.commit()


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


def seed_defaults(db: Session) -> None:
    settings = get_settings()
    roles = ensure_roles(db)
    current_event = db.scalar(select(Event).where(Event.is_current.is_(True)))
    if not current_event:
        current_event = Event(name="这谱谱这正赛", slug="zppz-current", is_current=True)
        current_event.settings = EventSetting()
        db.add(current_event)
        db.commit()

    admin = db.scalar(select(User).where(User.user_code == settings.admin_seed_code))
    if not admin:
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
