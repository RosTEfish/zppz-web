#!/usr/bin/env python3
"""Build corresponding-source.zip for the ZPPZ MajdataView record-mode fork."""

from __future__ import annotations

import argparse
import io
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen


UPSTREAM_COMMIT = "ad734f1272159a52cbd948c27c68cfa7cf1dc536"
UPSTREAM_ZIP = (
    f"https://github.com/TeamMajdata/MajdataView/archive/{UPSTREAM_COMMIT}.zip"
)
CHANGED = (
    "Assets/Scripts/BGManager.cs",
    "Assets/Scripts/GameMainManager.cs",
    "Assets/Scripts/Core/AudioTimeProvider.cs",
    "Assets/Scripts/Core/SoundEffect.cs",
)


def download(url: str, target: Path) -> None:
    request = Request(url, headers={"User-Agent": "zppz-majdata-packager/1"})
    with urlopen(request, timeout=180) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fork-dir",
        default="preview-player/majdata-view-record",
        help="Directory with patched Assets/Scripts copies",
    )
    parser.add_argument(
        "--output",
        default="preview-player/corresponding-source.zip",
        help="Output zip path published beside the WebGL player",
    )
    args = parser.parse_args()

    root = Path.cwd()
    fork_dir = root / args.fork_dir
    output = root / args.output
    for relative in CHANGED:
        if not (fork_dir / relative).is_file():
            raise SystemExit(f"missing patched file: {fork_dir / relative}")

    with tempfile.TemporaryDirectory(prefix="zppz-majdata-src-") as temp:
        temp_path = Path(temp)
        upstream_zip = temp_path / "upstream.zip"
        print(f"downloading {UPSTREAM_ZIP}")
        download(UPSTREAM_ZIP, upstream_zip)
        extract_root = temp_path / "src"
        extract_root.mkdir()
        with zipfile.ZipFile(upstream_zip) as archive:
            archive.extractall(extract_root)
        children = [path for path in extract_root.iterdir() if path.is_dir()]
        if len(children) != 1:
            raise SystemExit("unexpected upstream zip layout")
        project = children[0]
        for relative in CHANGED:
            source = fork_dir / relative
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            print(f"patched {relative}")

        readme = project / "ZPPZ_RECORD_MODE.md"
        readme.write_text(
            (fork_dir / "README.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(project.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(project).as_posix())
        output.write_bytes(buffer.getvalue())
        print(f"wrote {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
