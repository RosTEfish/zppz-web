#!/usr/bin/env python3
"""Stage the pinned WebGL player and serve a local record-mode test page.

Parent page is bound to http://127.0.0.1:3000 so player-bridge trusts it.
Open http://127.0.0.1:3000/ and click「加载样例谱面」.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "preview-player"
BUILD = PLAYER / "Build"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".wasm": "application/wasm",
    ".data": "application/octet-stream",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".mp3": "audio/mpeg",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".zip": "application/zip",
}


HARNESS_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>ZPPZ 录制模式预览 · 本地测试</title>
  <style>
    :root { color-scheme: dark; font-family: "Segoe UI", "Noto Sans SC", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: #0b1210; color: #dff7e9; }
    header {
      display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
      padding: 12px 16px; border-bottom: 1px solid #1f332a;
      background: #0f1a16;
    }
    h1 { margin: 0; font-size: 15px; font-weight: 650; flex: 1 1 auto; }
    button, select {
      appearance: none; border: 1px solid #2f5a45; background: #143226; color: #dff7e9;
      border-radius: 8px; padding: 8px 12px; font: inherit; cursor: pointer;
    }
    button.primary { background: #176b52; border-color: #1f8a68; }
    button:disabled { opacity: .45; cursor: not-allowed; }
    #log {
      margin: 0; padding: 8px 16px; max-height: 96px; overflow: auto;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color: #9fbfb0; border-bottom: 1px solid #1f332a; white-space: pre-wrap;
    }
    #frame-wrap { height: calc(100vh - 120px); min-height: 420px; background: #000; }
    iframe { width: 100%; height: 100%; border: 0; display: block; background: #000; }
  </style>
</head>
<body>
  <header>
    <h1>MajdataView record-mode · local harness</h1>
    <label>难度
      <select id="difficulty">
        <option value="4" selected>Basic/Expert slot 4</option>
        <option value="5">Master slot 5</option>
      </select>
    </label>
    <button id="load" class="primary" type="button" disabled>等待播放器就绪</button>
    <button id="reload" type="button">重载 iframe</button>
  </header>
  <pre id="log"></pre>
  <div id="frame-wrap">
    <iframe id="player" title="Majdata preview" allow="autoplay; fullscreen; gamepad"></iframe>
  </div>
  <script>
    const VERSION = 2;
    const PLAYER_ORIGIN = location.origin;
    const sessionId = crypto.randomUUID();
    const logEl = document.getElementById("log");
    const loadBtn = document.getElementById("load");
    const iframe = document.getElementById("player");
    let ready = false;
    let requestSeq = 0;

    function log(line) {
      const stamp = new Date().toISOString().slice(11, 23);
      logEl.textContent = `[${stamp}] ${line}\\n` + logEl.textContent;
    }

    function mountPlayer() {
      ready = false;
      loadBtn.disabled = true;
      loadBtn.textContent = "等待播放器就绪";
      iframe.src = `${PLAYER_ORIGIN}/player/player.html?zppz_session=${encodeURIComponent(sessionId)}`;
      log(`iframe → ${iframe.src}`);
    }

    window.addEventListener("message", (event) => {
      if (event.origin !== PLAYER_ORIGIN || event.source !== iframe.contentWindow) return;
      const data = event.data || {};
      if (data.version !== VERSION || data.session_id !== sessionId) return;
      log(`${data.type}${data.phase ? ` (${data.phase})` : ""}${data.code ? ` [${data.code}]` : ""}${typeof data.progress === "number" ? ` ${Math.round(data.progress * 100)}%` : ""}`);
      if (data.type === "zppz.preview.ready") {
        ready = true;
        loadBtn.disabled = false;
        loadBtn.textContent = "加载样例谱面";
      }
      if (data.type === "zppz.preview.error") {
        loadBtn.disabled = false;
        loadBtn.textContent = "重试加载样例谱面";
      }
    });

    loadBtn.addEventListener("click", () => {
      if (!ready || !iframe.contentWindow) return;
      requestSeq += 1;
      const requestId = `${sessionId}:${requestSeq}`;
      const difficulty = Number(document.getElementById("difficulty").value);
      const payload = {
        maidata_url: `${PLAYER_ORIGIN}/assets/maidata.txt`,
        track_url: `${PLAYER_ORIGIN}/assets/track.mp3`,
        background_url: `${PLAYER_ORIGIN}/assets/bg.jpg`,
        video_url: "",
        difficulty_index: difficulty,
      };
      iframe.contentWindow.postMessage({
        type: "zppz.preview.load",
        version: VERSION,
        session_id: sessionId,
        request_id: requestId,
        payload,
      }, PLAYER_ORIGIN);
      log(`sent load request ${requestId} difficulty=${difficulty}`);
    });

    document.getElementById("reload").addEventListener("click", mountPlayer);
    mountPlayer();
  </script>
</body>
</html>
"""


MAIDATA = """&title=ZPPZ Record Mode Test
&artist=Local Harness
&des=Record Mode Designer
&first=0
&lv_4=12
&lv_5=14
&clock_count=4
&inote_4=(120){4}1,2,3,4,5,6,7,8,1,2,3,4,5,6,7,8,
&inote_5=(140){4}1,3,5,7,2,4,6,8,1,3,5,7,2,4,6,8,
"""


class PreviewHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **getattr(SimpleHTTPRequestHandler, "extensions_map", {}),
        **MIME,
    }

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        self.send_header("Access-Control-Expose-Headers", "Accept-Ranges, Content-Length, Content-Range")
        # Unity WebGL often expects cross-origin isolation for SharedArrayBuffer.
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        print(f"[preview-local] {self.address_string()} - {format % args}")


def write_assets(assets: Path) -> None:
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "maidata.txt").write_text(MAIDATA, encoding="utf-8")
    track = assets / "track.mp3"
    if not track.is_file():
        # Tiny valid-enough MPEG frame filler; ffmpeg optional.
        if shutil.which("ffmpeg"):
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=12",
                    "-ac",
                    "2",
                    "-ar",
                    "44100",
                    "-b:a",
                    "128k",
                    str(track),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            track.write_bytes((bytes.fromhex("FFFB9064") + bytes(413)) * 80)
    bg = assets / "bg.jpg"
    if not bg.is_file():
        if shutil.which("ffmpeg"):
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=0x176B52:s=512x512",
                    "-frames:v",
                    "1",
                    str(bg),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            try:
                from PIL import Image
                Image.new("RGB", (512, 512), "#176B52").save(bg, format="JPEG")
            except Exception:
                # Minimal 1x1 JPEG
                bg.write_bytes(
                    bytes.fromhex(
                        "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
                        "070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c"
                        "1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d"
                        "0d1832211c2132323232323232323232323232323232323232323232323232323232"
                        "323232323232323232323232323232323232323232ffc00011080001000103011100"
                        "02110311003f00bf80ffd9"
                    )
                )


def stage(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / "index.html").write_text(HARNESS_HTML, encoding="utf-8")
    player_out = dest / "player"
    player_out.mkdir()
    for name in (
        "player.html",
        "player-bridge.js",
        "THIRD_PARTY_NOTICES.txt",
        "corresponding-source.zip",
        "majdata-build.json",
    ):
        src = PLAYER / name
        if src.is_file():
            shutil.copy2(src, player_out / name)
    for name in ("Build.loader.js", "Build.framework.js", "Build.data", "Build.wasm"):
        shutil.copy2(BUILD / name, player_out / name)
    # player.html links ./LICENSE — publish resolves from upstream; local stub is fine for harness.
    license_src = ROOT / "LICENSE"
    shutil.copy2(license_src, player_out / "LICENSE")
    write_assets(dest / "assets")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "zppz-preview-local",
        help="staging directory for flattened player + harness",
    )
    args = parser.parse_args()

    for required in (
        BUILD / "Build.loader.js",
        BUILD / "Build.framework.js",
        BUILD / "Build.data",
        BUILD / "Build.wasm",
        PLAYER / "player.html",
        PLAYER / "player-bridge.js",
    ):
        if not required.is_file():
            raise SystemExit(f"missing required file: {required}")

    stage(args.dir)
    handler = partial(PreviewHandler, directory=str(args.dir))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"staged {args.dir}")
    print(f"open {url}")
    print("Click「加载样例谱面」, then press Play inside Unity for record-mode intro.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
