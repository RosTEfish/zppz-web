from app.core.config import get_settings
from app.modules.submissions.service import copy_asset_from_repo


def test_bundled_asset_sync_replaces_changed_same_name(tmp_path):
    source = tmp_path / "same-name.bin"
    source.write_bytes(b"old contents")

    copy_asset_from_repo(source, "bundled-sync-regression")
    target = get_settings().assets_dir / "bundled-sync-regression" / source.name
    assert target.read_bytes() == b"old contents"

    source.write_bytes(b"new contents")
    copy_asset_from_repo(source, "bundled-sync-regression")

    assert target.read_bytes() == b"new contents"
