from pathlib import Path

from PIL import Image

from app.core.config import get_settings
from app.modules.assets.sync import sync_background_file


def test_sync_background_converts_png_to_webp(tmp_path: Path):
    source = tmp_path / "banner.png"
    Image.new("RGB", (32, 16), color=(255, 100, 60)).save(source, format="PNG")

    sync_background_file(source)

    directory = get_settings().assets_dir / "backgrounds"
    webp = directory / "banner.webp"
    assert webp.is_file()
    assert webp.read_bytes()[:4] == b"RIFF"
    assert not (directory / "banner.png").exists()


def test_sync_background_keeps_native_webp(tmp_path: Path):
    source = tmp_path / "post.webp"
    Image.new("RGB", (24, 24), color=(40, 180, 120)).save(source, format="WEBP", quality=80)

    sync_background_file(source)

    target = get_settings().assets_dir / "backgrounds" / "post.webp"
    assert target.is_file()
    assert target.read_bytes() == source.read_bytes()
