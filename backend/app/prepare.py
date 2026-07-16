from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.bootstrap import backfill_guess_chart_metadata, seed_defaults, upgrade_schema
from app.models import BanImport, User
from app.db.session import SessionLocal
from app.modules.banlist.service import create_ban_import
from app.modules.submissions.service import copy_asset_from_repo, drain_storage_deletions


def sync_bundled_assets() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for source, target in (
        (repo_root / "ruleDetail", "rules"),
        (repo_root / "banlist", "banlists"),
        (repo_root / "bg", "backgrounds"),
    ):
        for file in source.glob("*.*"):
            copy_asset_from_repo(file, target)


def prepare() -> None:
    """Apply all one-time database preparation steps for a deployment."""
    upgrade_schema()
    with SessionLocal() as db:
        seed_defaults(db)
        seed_bundled_banlist(db)
        backfill_guess_chart_metadata(db)
        drain_storage_deletions(db)
    sync_bundled_assets()


def seed_bundled_banlist(db) -> None:
    """Make the repository's current Ban workbook usable on a fresh deployment."""
    if db.scalar(select(BanImport.id).limit(1)):
        return
    repo_root = Path(__file__).resolve().parents[2]
    workbook = next(iter(sorted((repo_root / "banlist").glob("*.xlsx"))), None)
    if workbook is None:
        return
    admin = db.scalar(select(User).where(User.user_code == get_settings().admin_seed_code))
    create_ban_import(db, workbook.name, workbook.read_bytes(), admin.id if admin else None, auto_publish=True)


if __name__ == "__main__":
    prepare()
