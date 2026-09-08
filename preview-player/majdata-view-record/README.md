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
scripts / Resources are kept here.

## Apply on a clean upstream tree

```bash
git clone https://github.com/TeamMajdata/MajdataView.git MajdataView-zppz-preview
cd MajdataView-zppz-preview
git checkout ad734f1272159a52cbd948c27c68cfa7cf1dc536
git checkout -b zppz-record-mode
git apply /path/to/zppz-web/preview-player/majdata-view-record/patches/0001-web-record-mode.patch
# copy scripts + Resources (SongCover must live under Resources for WebGL):
cp -r /path/to/zppz-web/preview-player/majdata-view-record/Assets/Scripts ./Assets/
cp -r /path/to/zppz-web/preview-player/majdata-view-record/Assets/Resources ./Assets/
rm -rf Assets/Prefabs/SongCover Assets/Animation/SongDetail
```

Upstream project version: **6000.3.17f1**. The pinned WebGL player was built
with **Unity 6000.6.0f1** (upgrade on open) plus the `JSLibFileCreator`
API fix below.

### SongDetail note

`Main.unity` 里名为 `Covers` 的对象是四边 letterbox，**不是**封面 UI。
真正的 `SongDetail` 在 `Assets/Resources/SongCover/Covers.prefab`，由
`BGManager` 在运行时 `Resources.Load` 成独立 `ScreenSpaceOverlay` Canvas
（实例名 `SongCoverUI`，并放大显示）。不要再 `Find("Covers")` 或挂到场景
主 `Canvas` 下，否则开场封面不可见或极小。

## WebGL rebuild (required after SongCover fix)

1. Sync the Windows fork `MajdataView-zppz-preview` with the scripts +
   `Assets/Resources/SongCover/**` from this directory; remove
   `Assets/Prefabs/SongCover` and `Assets/Animation/SongDetail` to avoid
   duplicate GUIDs.
2. Open in Unity **6000.6.0f1**, switch to WebGL, build.
3. Copy/rename `build/Build/build.*` → `zppz-web/preview-player/Build/Build.*`.
4. From `zppz-web`:

```bash
python scripts/package_majdata_record_source.py
python scripts/update_majdata_build_manifest.py \
  --version majdataview-zppz-record2-webgl-6000.6 \
  --source-commit "$(cat preview-player/majdata-view-record/FORK_COMMIT.txt)" \
  --build-base-url local://preview-player/Build \
  --source-archive-url local://preview-player/corresponding-source.zip
```

5. Commit Build + zip + manifest; merge/deploy with `PREVIEW_ENABLED=true`
   so CI runs `publish_preview_player.py`.

Local smoke (no R2): `python3 scripts/serve_preview_local.py --port 3000`

## Changed files

- `Assets/Scripts/BGManager.cs` — `PlaySongDetail` via Resources SongCover
- `Assets/Scripts/GameMainManager.cs` — Play = record path; hide `SongCoverUI`
- `Assets/Scripts/Core/AudioTimeProvider.cs` — intro delay + deferred BGM
- `Assets/Scripts/Core/SoundEffect.cs` — `clock_count` + AP when `isOpIncluded`
- `Assets/Scripts/Misc/JSLibFileCreator.cs` — Unity 6000.6 editor API
- `Assets/Resources/SongCover/**` — SongDetail prefab + Entry animator
