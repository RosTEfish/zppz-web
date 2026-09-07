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

Unity Editor version: **6000.3.17f1** (see upstream
`ProjectSettings/ProjectVersion.txt`).

## WebGL build

1. Open the patched project in Unity 6000.3.17f1.
2. Switch platform to WebGL; build into `Build/`
   (`Build.loader.js`, `Build.framework.js`, `Build.data`, `Build.wasm`).
3. Copy those four files to
   `zppz-web/preview-player/Build/`.
4. From `zppz-web` run:

```bash
python scripts/package_majdata_record_source.py
python scripts/update_majdata_build_manifest.py
```

5. Commit the updated `majdata-build.json`,
   `corresponding-source.zip` metadata URLs / notices, then deploy as usual.
   `scripts/publish_preview_player.py` prefers local `preview-player/Build/`
   when present.

## Changed files

- `Assets/Scripts/BGManager.cs` — `PlaySongDetail`
- `Assets/Scripts/GameMainManager.cs` — Play = record path
- `Assets/Scripts/Core/AudioTimeProvider.cs` — intro delay + deferred BGM
- `Assets/Scripts/Core/SoundEffect.cs` — `clock_count` + AP when `isOpIncluded`
