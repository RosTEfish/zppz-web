# MajdataView record-mode fork (ZPPZ)

GPL-3.0 modifications on top of TeamMajdata/MajdataView
`ad734f1272159a52cbd948c27c68cfa7cf1dc536` so web preview **Play** matches
desktop **录制模式**:

- `SongDetail` jacket / title / artist / designer intro
- ~5s timeline delay before notes and BGM
- All Perfect at chart end
- `&clock_count` guide clicks from `other_commands`

This directory is the source of truth for the fork until you publish an
independent GitHub repository (recommended name:
`MajdataView-zppz-preview`). Do **not** merge these Unity sources into the
website `main` history as a full project tree; only the patch + changed
scripts are kept here.

## Apply on a clean upstream tree

```bash
git clone https://github.com/TeamMajdata/MajdataView.git MajdataView-zppz-preview
cd MajdataView-zppz-preview
git checkout ad734f1272159a52cbd948c27c68cfa7cf1dc536
git checkout -b zppz-record-mode
git apply /path/to/zppz-web/preview-player/majdata-view-record/patches/0001-web-record-mode.patch
# or copy Assets/Scripts/** over the same paths
```

Upstream project version: **6000.3.17f1**. The pinned WebGL player was built
with **Unity 6000.6.0f1** (upgrade on open) plus the `JSLibFileCreator`
API fix below.

## WebGL build

1. Open the patched project in Unity (6000.6.0f1 works after the JSLib fix).
2. Switch platform to WebGL; build (Unity may write `build/Build/build.*`).
3. Copy/rename the four files to `zppz-web/preview-player/Build/` as
   `Build.loader.js`, `Build.framework.js`, `Build.data`, `Build.wasm`.
4. From `zppz-web` run:

```bash
python scripts/package_majdata_record_source.py
python scripts/update_majdata_build_manifest.py \
  --version majdataview-zppz-record1-webgl-6000.6 \
  --source-commit "$(cat preview-player/majdata-view-record/FORK_COMMIT.txt)" \
  --build-base-url local://preview-player/Build \
  --source-archive-url local://preview-player/corresponding-source.zip
```

5. Commit `majdata-build.json`, `preview-player/Build/`,
   `corresponding-source.zip`, and notices; deploy as usual.
   `scripts/publish_preview_player.py` reads `local://` paths from the manifest.

## Changed files

- `Assets/Scripts/BGManager.cs` — `PlaySongDetail`
- `Assets/Scripts/GameMainManager.cs` — Play = record path
- `Assets/Scripts/Core/AudioTimeProvider.cs` — intro delay + deferred BGM
- `Assets/Scripts/Core/SoundEffect.cs` — `clock_count` + AP when `isOpIncluded`
- `Assets/Scripts/Misc/JSLibFileCreator.cs` — Unity 6000.6 editor API