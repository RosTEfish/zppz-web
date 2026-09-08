from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FORK_DIR = REPOSITORY_ROOT / "preview-player" / "majdata-view-record"
PATCH = FORK_DIR / "patches" / "0001-web-record-mode.patch"
UPSTREAM_COMMIT = "ad734f1272159a52cbd948c27c68cfa7cf1dc536"
CHANGED = (
    "Assets/Scripts/BGManager.cs",
    "Assets/Scripts/GameMainManager.cs",
    "Assets/Scripts/Core/AudioTimeProvider.cs",
    "Assets/Scripts/Core/SoundEffect.cs",
    "Assets/Scripts/Misc/JSLibFileCreator.cs",
)


def test_record_mode_fork_files_exist() -> None:
    assert PATCH.is_file()
    assert (FORK_DIR / "README.md").is_file()
    for relative in CHANGED:
        path = FORK_DIR / relative
        assert path.is_file(), relative
        text = path.read_text(encoding="utf-8")
        if relative.endswith("BGManager.cs"):
            assert "PlaySongDetail" in text
            assert "SongCover/Covers" in text
            assert "ScreenSpaceOverlay" in text
            assert "SongCoverOverlayScale" in text
            assert 'Find("Covers")' not in text
        if relative.endswith("GameMainManager.cs"):
            assert "recordMode: true" in text
            assert "SongCoverUI" in text
        if relative.endswith("AudioTimeProvider.cs"):
            assert "RecordIntroDelaySeconds" in text
        if relative.endswith("SoundEffect.cs"):
            assert "isOpIncluded" in text
            assert "clock_count" in text


def test_record_mode_songcover_resources_exist() -> None:
    prefab = FORK_DIR / "Assets/Resources/SongCover/Covers.prefab"
    controller = FORK_DIR / "Assets/Resources/SongCover/Animation/Canvas.controller"
    assert prefab.is_file()
    assert controller.is_file()
    assert "SongDetail" in prefab.read_text(encoding="utf-8", errors="replace")


def test_record_mode_patch_targets_upstream_commit() -> None:
    readme = (FORK_DIR / "README.md").read_text(encoding="utf-8")
    assert UPSTREAM_COMMIT in readme
    assert "PlaySongDetail" in PATCH.read_text(encoding="utf-8")
