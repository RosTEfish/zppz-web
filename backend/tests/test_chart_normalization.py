"""Regression tests for MiaCode-compatible chart normalization."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from app.modules.guess_game.importer import build_public_package_from_files
from app.modules.simai.chart_normalization import (
    ChartNormalizationOptions,
    normalize_chart_text,
    snap_x_over_y,
)
from app.modules.simai.maidata_format import format_maidata_text


def test_snap_x_over_y_matches_miacode_table():
    r5 = snap_x_over_y(1, 5)
    assert r5.ok and r5.q == 16 and r5.p == 3
    r7 = snap_x_over_y(1, 7)
    assert r7.ok and r7.q == 24 and r7.p == 3
    r28 = snap_x_over_y(1, 28)
    assert r28.ok and r28.q == 96 and r28.p == 3
    r_div = snap_x_over_y(3, 16)
    assert r_div.ok and r_div.q == 16 and r_div.p == 3
    r_big = snap_x_over_y(1, 2000)
    assert r_big.ok and r_big.q == 384 and r_big.p == 0


def test_normalize_touch_hold_canonicalizes_modifier_order():
    result = normalize_chart_text("A1fh[4:1],,,,\nE")
    assert result.ok
    assert result.text == "{16}A1hf[4:1],,,, ,,,, ,,,, ,,,,\nE"


def test_normalize_leaves_384_divisor_and_hash_durations():
    result = normalize_chart_text("A1fh[24:6]/1h[8:0]/1-5[24:3]/1-5[120#24:3],,,,\nE")
    assert result.ok
    assert result.text == "{16}A1hf[24:6]/1h[8:0]/1-5[24:3]/1-5[120#24:3],,,, ,,,, ,,,, ,,,,\nE"


def test_normalize_collapses_zero_length_note_holds():
    result = normalize_chart_text(
        "{16}2h[2000:1],7h[2000:1],3h[2000:1],6h[2000:1], "
        "1h[2000:1],5h[2000:1],8h[2000:1],4h[2000:1], "
        "7h[2000:1]/3h[2000:1],8h[2000:1]/4h[2000:1],5h[2000:1]/1h[2000:1],2h[2000:1]/6h[2000:1], "
        "3h[2000:1]/7-3[1:3],8h[2000:1]/4h[2000:1],5h[2000:1]/1h[2000:1],6h[2000:1]/2h[2000:1],\nE"
    )
    assert result.ok
    assert result.text == (
        "{16}2h,7h,3h,6h, 1h,5h,8h,4h, 7h/3h,8h/4h,5h/1h,2h/6h, 3h/7-3[1:3],8h/4h,5h/1h,6h/2h,\nE"
    )


def test_normalize_snaps_non_384_hold_and_slide_durations():
    hold = normalize_chart_text("1h[7:1],,,,\nE")
    assert hold.ok
    assert hold.text == "{16}1h[24:3],,,, ,,,, ,,,, ,,,,\nE"

    slide = normalize_chart_text("1-5[5:1],,,,\nE")
    assert slide.ok
    assert slide.text == "{16}1-5[16:3],,,, ,,,, ,,,, ,,,,\nE"

    mixed = normalize_chart_text("1h[500:1]/1-5[500:1]/1-5[2000:1],,,,\nE")
    assert mixed.ok
    assert mixed.text == "{16}1h[384:1]/1-5[384:1]/1-5[384:1],,,, ,,,, ,,,, ,,,,\nE"


def test_normalize_routes_non_384_subdivisions():
    assert normalize_chart_text("{7}1,2,3,4,5,6,7,\nE").text.startswith("{24}")
    assert normalize_chart_text(
        "{28}1,2,3,4,5,6,7,8,1,2,3,4,5,6,7,8,1,2,3,4,5,6,7,8,1,2,3,4,\nE"
    ).text.startswith("{96}")


def test_normalize_merges_bpm_and_time_signature():
    result = normalize_chart_text(",,(180)|| 3 / 4\n,,,\nE")
    assert result.ok
    assert result.text == "{16},,,, ,,,,\n(180) || 3/4\n{16},,,, ,,,, ,,,,\nE"


def test_normalize_keeps_ordinary_comments():
    result = normalize_chart_text("1,2, || hello\n3,4,\nE")
    assert result.ok
    assert result.text == "{16}1,,,, 2,,,,\n|| hello\n{16}3,,,, 4,,,,\nE"


def test_normalize_minimizes_subdivisions_per_beat():
    result = normalize_chart_text("{24},1,,,,,{16},,,,,,,,,,,,\nE")
    assert result.ok
    assert result.text == "{24},1,,,,, {16},,,, ,,,, ,,,,\nE"


def test_normalize_preserves_per_branch_slide_break():
    options = ChartNormalizationOptions(start_at_new_measure=True, reduce_to_384_grid=False)
    second = normalize_chart_text("1-5[8:1]*-4b[8:1],,,,\nE", options=options)
    assert second.ok
    assert second.text == "{16}1-5[8:1]*-4b[8:1],,,, ,,,, ,,,, ,,,,\nE"

    first = normalize_chart_text("1-5b[8:1]*-4[8:1],,,,\nE", options=options)
    assert first.ok
    assert first.text == "{16}1-5b[8:1]*-4[8:1],,,, ,,,, ,,,, ,,,,\nE"


def test_normalize_is_idempotent_across_time_signature_change():
    chart = (
        "(126)\n"
        "{1},|| 3/4\n"
        "{16}2h[16:3],,,4h[16:3],,,5h[8:1],,6,,47,,\n"
        "{16}7h[16:3],,,5h[16:3],,,4h[8:1],,3,,52,,"
    )
    first = normalize_chart_text(chart)
    assert first.ok
    assert "|| 3/4" in first.text
    second = normalize_chart_text(first.text)
    assert second.ok
    assert second.text == first.text


def test_format_maidata_rewrites_inote_bodies_and_keeps_metadata():
    maidata = (
        "&title=Demo\n"
        "&artist=Artist\n"
        "&des=Designer\n"
        "&lv_4=13\n"
        "&inote_4=A1fh[4:1],,,,\n"
        "&lv_5=14\n"
        "&inote_5=1-5[5:1],,,,\n"
    )
    formatted = format_maidata_text(maidata)
    assert "&title=Demo" in formatted
    assert "&des=Designer" in formatted
    assert "&inote_4=" in formatted
    assert "{16}A1hf[4:1],,,, ,,,, ,,,, ,,,," in formatted
    assert "{16}1-5[16:3],,,, ,,,, ,,,, ,,,," in formatted
    assert formatted.strip().endswith("E") or "E\n" in formatted


def test_build_public_package_formats_maidata(tmp_path: Path):
    from PIL import Image

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "maidata.txt").write_text(
        "&title=Pkg\n&artist=A\n&des=KeepMe\n&lv_4=12\n&inote_4=1h[7:1],,,,\n",
        encoding="utf-8",
    )
    (assets / "track.mp3").write_bytes(b"ID3fake")
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "#112233").save(buffer, format="PNG")
    (assets / "bg.png").write_bytes(buffer.getvalue())

    target = tmp_path / "public.zip"
    build_public_package_from_files(
        target,
        {
            "maidata.txt": assets / "maidata.txt",
            "track.mp3": assets / "track.mp3",
            "bg.png": assets / "bg.png",
        },
    )

    with ZipFile(target, "r") as archive:
        maidata = archive.read("maidata.txt").decode("utf-8")
    assert "&des=KeepMe" in maidata
    assert "{16}1h[24:3],,,, ,,,, ,,,, ,,,," in maidata
