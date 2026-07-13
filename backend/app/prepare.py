from pathlib import Path

from app.db.bootstrap import backfill_guess_chart_metadata, seed_defaults, upgrade_schema
from app.db.session import SessionLocal
from app.modules.submissions.service import copy_asset_from_repo


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
        backfill_guess_chart_metadata(db)
    sync_bundled_assets()


if __name__ == "__main__":
    prepare()
