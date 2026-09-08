#!/usr/bin/env python3
"""Sync zppz-web majdata-view-record sources into a local MajdataView Unity tree.

Run this on the machine that has MajdataView-zppz-preview (Windows/WSL/macOS).

Example (PowerShell / WSL / bash):

  python scripts/sync_majdata_record_fork.py --unity-root "C:/Users/areal/MajdataView-zppz-preview"

Close the Unity Editor before running.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FORK = REPO_ROOT / "preview-player" / "majdata-view-record"

SCRIPT_FILES = (
    "Assets/Scripts/BGManager.cs",
    "Assets/Scripts/GameMainManager.cs",
    "Assets/Scripts/Core/AudioTimeProvider.cs",
    "Assets/Scripts/Core/SoundEffect.cs",
    "Assets/Scripts/Misc/JSLibFileCreator.cs",
)
RESOURCE_TREE = "Assets/Resources"
REMOVE_TREES = (
    "Assets/Prefabs/SongCover",
    "Assets/Animation/SongDetail",
)


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"copied  {src.relative_to(FORK)} -> {dst}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unity-root",
        required=True,
        type=Path,
        help="Path to MajdataView-zppz-preview (folder that contains Assets/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing",
    )
    args = parser.parse_args()
    unity = args.unity_root.expanduser().resolve()

    if not (unity / "Assets").is_dir():
        print(f"error: {unity} does not look like a Unity project (no Assets/)", file=sys.stderr)
        return 1
    if not (FORK / "Assets/Scripts/BGManager.cs").is_file():
        print(f"error: fork sources missing under {FORK}", file=sys.stderr)
        return 1

    print(f"website fork: {FORK}")
    print(f"unity root:   {unity}")
    if args.dry_run:
        print("dry-run only")

    for relative in SCRIPT_FILES:
        src = FORK / relative
        dst = unity / relative
        if not src.is_file():
            print(f"error: missing {src}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(f"would copy {relative}")
        else:
            copy_file(src, dst)

    src_res = FORK / RESOURCE_TREE
    dst_res = unity / RESOURCE_TREE
    if not src_res.is_dir():
        print(f"error: missing {src_res}", file=sys.stderr)
        return 1
    # Merge SongCover under Resources; do not wipe unrelated assets (e.g. DOTweenSettings).
    songcover_src = src_res / "SongCover"
    songcover_dst = dst_res / "SongCover"
    if args.dry_run:
        print(f"would merge {RESOURCE_TREE}/SongCover")
    else:
        dst_res.mkdir(parents=True, exist_ok=True)
        if songcover_dst.exists():
            shutil.rmtree(songcover_dst)
        shutil.copytree(songcover_src, songcover_dst)
        src_meta = src_res / "SongCover.meta"
        if src_meta.is_file():
            shutil.copy2(src_meta, dst_res / "SongCover.meta")
        # Ensure Resources.meta exists if we created Resources
        res_meta_src = FORK / "Assets" / "Resources.meta"
        res_meta_dst = unity / "Assets" / "Resources.meta"
        if res_meta_src.is_file() and not res_meta_dst.is_file():
            shutil.copy2(res_meta_src, res_meta_dst)
        print(f"merged {RESOURCE_TREE}/SongCover")

    for relative in REMOVE_TREES:
        target = unity / relative
        meta = Path(str(target) + ".meta")
        if args.dry_run:
            print(f"would remove {relative}")
            continue
        if target.exists():
            shutil.rmtree(target)
            print(f"removed {relative}")
        else:
            print(f"skip    {relative} (already absent)")
        if meta.exists():
            meta.unlink()
            print(f"removed {relative}.meta")

    # Quick sanity checks on the Unity tree
    bg = (unity / "Assets/Scripts/BGManager.cs").read_text(encoding="utf-8")
    if "SongCover/Covers" not in bg or 'Find("Covers")' in bg:
        print("error: BGManager.cs does not look like the SongCover fix", file=sys.stderr)
        return 1
    prefab = unity / "Assets/Resources/SongCover/Covers.prefab"
    if not prefab.is_file():
        print(f"error: missing {prefab}", file=sys.stderr)
        return 1
    if (unity / "Assets/Prefabs/SongCover").exists():
        print("error: Prefabs/SongCover still present", file=sys.stderr)
        return 1
    if (unity / "Assets/Animation/SongDetail").exists():
        print("error: Animation/SongDetail still present", file=sys.stderr)
        return 1

    print("OK — close/reopen Unity if needed, then WebGL Build.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
