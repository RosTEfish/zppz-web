from pathlib import Path
import struct
import zipfile

import pytest

from app.modules.guess_game.chart_validate import (
    ensure_built_for_tests,
    prepare_archive_with_rust,
    resolve_chart_validate_bin,
    rust_prepare_available,
)
from app.modules.guess_game.importer import ArchiveParseError, prepare_archive
from tests.test_guess_import import PNG_COVER, archive_bytes


@pytest.fixture(scope="module")
def chart_validate_bin():
    binary = ensure_built_for_tests()
    if binary is None:
        pytest.skip("zppz-chart-validate binary is unavailable")
    return binary


def test_resolve_finds_binary(chart_validate_bin: Path):
    found = resolve_chart_validate_bin()
    assert found is not None
    assert found.is_file()
    assert rust_prepare_available(Path("chart.zip"))


def test_rust_prepare_archive_matches_python_contract(
    tmp_path: Path,
    chart_validate_bin: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ZPPZ_CHART_VALIDATE_BIN", str(chart_validate_bin))
    path = tmp_path / "chart.zip"
    path.write_bytes(archive_bytes("&title=RustSong\n&artist=Artist\n&lv_4=13"))
    prepared = prepare_archive(path, tmp_path / "out")
    assert prepared.parsed.title == "RustSong"
    assert prepared.parsed.author == "Artist"
    assert "maidata.txt" in prepared.files
    assert any(name.startswith("track.") for name in prepared.files)
    assert any(name.startswith("bg.") for name in prepared.files)


def test_rust_rejects_absolute_member_paths(
    tmp_path: Path,
    chart_validate_bin: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ZPPZ_CHART_VALIDATE_BIN", str(chart_validate_bin))
    bad = tmp_path / "absolute.zip"
    _write_zip_with_name(bad, "/tmp/maidata.txt", b"&title=X\n&artist=Y\n&lv_4=13\n&inote_4=a")
    with pytest.raises(ArchiveParseError, match="绝对路径|不安全路径|maidata"):
        prepare_archive_with_rust(bad, tmp_path / "out-abs")


def test_rust_enforces_member_byte_cap(
    tmp_path: Path,
    chart_validate_bin: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ZPPZ_CHART_VALIDATE_BIN", str(chart_validate_bin))
    path = tmp_path / "huge-maidata.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("maidata.txt", b"a" * (1024 * 1024 + 8))
        archive.writestr("track.mp3", (bytes.fromhex("FFFB9064") + bytes(413)) * 2)
        archive.writestr("bg.png", PNG_COVER)
    with pytest.raises(ArchiveParseError, match="大小超出限制"):
        prepare_archive_with_rust(path, tmp_path / "out")


def test_rust_cli_timeout_is_killable(
    tmp_path: Path,
    chart_validate_bin: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ZPPZ_CHART_VALIDATE_BIN", str(chart_validate_bin))
    path = tmp_path / "chart.zip"
    path.write_bytes(archive_bytes("&title=Slow\n&artist=Artist\n&lv_4=13"))
    with pytest.raises(ArchiveParseError, match="超时"):
        prepare_archive_with_rust(path, tmp_path / "out", timeout_seconds=0)


def _write_zip_with_name(path: Path, member_name: str, payload: bytes) -> None:
    """Write a single-entry stored zip using an unsanitized member name."""
    name_bytes = member_name.encode("utf-8")
    header = bytearray()
    header.extend(b"PK\x03\x04")
    header.extend(struct.pack("<HHHHHIIIHH", 20, 0, 0, 0, 0, 0, len(payload), len(payload), len(name_bytes), 0))
    header.extend(name_bytes)
    header.extend(payload)
    central = bytearray()
    central.extend(b"PK\x01\x02")
    central.extend(
        struct.pack(
            "<HHHHHHIIIHHHHHII",
            20,
            20,
            0,
            0,
            0,
            0,
            0,
            len(payload),
            len(payload),
            len(name_bytes),
            0,
            0,
            0,
            0,
            0,
            0,
        )
    )
    central.extend(name_bytes)
    end = bytearray()
    end.extend(b"PK\x05\x06")
    end.extend(struct.pack("<HHHHIIH", 0, 0, 1, 1, len(central), len(header), 0))
    path.write_bytes(bytes(header) + bytes(central) + bytes(end))
