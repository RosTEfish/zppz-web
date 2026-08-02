import hashlib
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.bootstrap import backfill_guess_chart_metadata, seed_defaults, upgrade_schema
from app.models import BanImport, User
from app.db.session import SessionLocal
from app.modules.banlist.service import BAN_PARSER_VERSION, create_ban_import
from app.modules.submissions.service import copy_asset_from_repo, drain_storage_deletions
from app.modules.webhooks.service import seed_publication_baseline


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
        seed_publication_baseline(db)
        drain_storage_deletions(db)
    sync_bundled_assets()


def seed_bundled_banlist(db) -> None:
    """Seed Ban data and repair a published bundled workbook parsed by older code."""
    repo_root = Path(__file__).resolve().parents[2]
    workbook = next(iter(sorted((repo_root / "banlist").glob("*.xlsx"))), None)
    if workbook is None:
        return
    raw = workbook.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    matching = list(
        db.scalars(
            select(BanImport)
            .where(BanImport.file_sha256 == digest)
            .order_by(BanImport.id.desc())
        ).all()
    )
    if any(record.parser_version == BAN_PARSER_VERSION for record in matching):
        return
    any_import = db.scalar(select(BanImport.id).limit(1)) is not None
    should_publish = not any_import or any(record.status == "published" for record in matching)
    if not should_publish:
        return
    admin = db.scalar(select(User).where(User.user_code == get_settings().admin_seed_code))
    create_ban_import(db, workbook.name, raw, admin.id if admin else None, auto_publish=True)


if __name__ == "__main__":
    prepare()
