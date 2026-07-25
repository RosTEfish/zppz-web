(() => {
  "use strict";

  const VERSION = 1;
  const PRODUCTION_PARENT = "https://przppz.club";
  const LOCAL_PARENTS = new Set(["http://localhost:3000", "http://127.0.0.1:3000"]);
  const canvas = document.getElementById("unity-canvas");
  const status = document.getElementById("status");
  const message = document.getElementById("message");
  const progress = document.getElementById("progress");
  let unity = null;
  let pendingLoad = null;
  let activeParent = null;

  function parentAllowed(origin) {
    return origin === PRODUCTION_PARENT || LOCAL_PARENTS.has(origin);
  }

  function post(type, payload = {}) {
    if (!activeParent || window.parent === window) return;
    window.parent.postMessage({ type, version: VERSION, ...payload }, activeParent);
  }

  function setStatus(text, value) {
    message.textContent = text;
    if (typeof value === "number") progress.value = Math.max(0, Math.min(1, value));
  }

  function validateAssetUrl(value, optional = false) {
    if (optional && !value) return "";
    const url = new URL(value);
    if (url.protocol === "https:") return url.href;
    if (
      url.protocol === "http:"
      && (url.hostname === "localhost" || url.hostname === "127.0.0.1")
    ) return url.href;
    throw new Error("invalid_asset_url");
  }

  function normalizePayload(payload) {
    const difficulty = Number(payload?.difficulty_index);
    if (!Number.isInteger(difficulty) || difficulty < 0 || difficulty > 6) {
      throw new Error("invalid_difficulty");
    }
    return {
      maidata: validateAssetUrl(payload.maidata_url),
      track: validateAssetUrl(payload.track_url),
      background: validateAssetUrl(payload.background_url),
      video: validateAssetUrl(payload.video_url, true),
      difficulty,
    };
  }

  async function preflight(url) {
    const response = await fetch(url, { headers: { Range: "bytes=0-0" } });
    if (response.status === 401 || response.status === 403 || response.status === 410) {
      throw new Error("signed_url_expired");
    }
    if (!response.ok && response.status !== 206) throw new Error("asset_network_failed");
  }

  async function sendChart(payload, requestId) {
    pendingLoad = { payload, requestId };
    if (!unity) return;
    setStatus("加载谱面和音乐", 1);
    try {
      await Promise.all([
        preflight(payload.maidata),
        preflight(payload.track),
        preflight(payload.background),
      ]);
    } catch (error) {
      const code = error instanceof Error ? error.message : "asset_network_failed";
      const text = code === "signed_url_expired" ? "签名地址已过期" : "网络加载失败";
      setStatus(text);
      post("zppz.preview.error", { request_id: requestId, code, message: text });
      return;
    }
    let video = payload.video;
    if (video) {
      const videoElement = document.createElement("video");
      if (!videoElement.canPlayType("video/mp4")) {
        video = "";
        post("zppz.preview.warning", {
          request_id: requestId,
          code: "video_format_unsupported",
          message: "背景视频格式不支持，已回退到静态背景",
        });
      } else {
        try {
          await preflight(video);
        } catch {
          video = "";
          post("zppz.preview.warning", {
            request_id: requestId,
            code: "video_network_failed",
            message: "背景视频加载失败，已回退到静态背景",
          });
        }
      }
    }
    unity.SendMessage(
      "HandleJSMessages",
      "ReceiveMessage",
      `${payload.maidata}\n${payload.track}\n${payload.background}\n${video}\nlv${payload.difficulty}`,
    );
    window.setTimeout(() => {
      status.hidden = true;
      post("zppz.preview.loaded", { request_id: requestId });
    }, 650);
  }

  window.addEventListener("message", (event) => {
    if (!parentAllowed(event.origin) || event.source !== window.parent) return;
    const data = event.data;
    if (data?.type !== "zppz.preview.load" || data.version !== VERSION) return;
    activeParent = event.origin;
    try {
      void sendChart(normalizePayload(data.payload), data.request_id);
    } catch (error) {
      setStatus("预览参数无效");
      post("zppz.preview.error", {
        request_id: data.request_id,
        code: error instanceof Error ? error.message : "invalid_payload",
        message: "预览参数无效",
      });
    }
  });

  const gl = document.createElement("canvas").getContext("webgl2");
  if (!gl || typeof WebAssembly !== "object") {
    setStatus("浏览器不支持 WebGL2");
    post("zppz.preview.error", {
      code: "webgl2_unsupported",
      message: "浏览器不支持 WebGL2",
    });
    return;
  }

  setStatus("加载播放器 0%", 0);
  createUnityInstance(
    canvas,
    {
      dataUrl: "./Build.data",
      frameworkUrl: "./Build.framework.js",
      codeUrl: "./Build.wasm",
      streamingAssetsUrl: "StreamingAssets",
      companyName: "Majdata",
      productName: "MajdataView",
      productVersion: "zppz-pinned",
      showBanner(text, type) {
        if (type === "error") {
          setStatus("播放器加载失败");
          post("zppz.preview.error", { code: "unity_error", message: String(text) });
        }
      },
    },
    (value) => {
      setStatus(`加载播放器 ${Math.round(value * 100)}%`, value);
      post("zppz.preview.progress", { progress: value });
    },
  ).then((instance) => {
    unity = instance;
    setStatus("播放器已就绪，等待谱面", 1);
    post("zppz.preview.ready");
    if (pendingLoad) void sendChart(pendingLoad.payload, pendingLoad.requestId);
  }).catch((error) => {
    setStatus("网络加载失败");
    post("zppz.preview.error", {
      code: "unity_load_failed",
      message: error instanceof Error ? error.message : "播放器加载失败",
    });
  });

  window.addEventListener("pagehide", () => {
    if (unity?.Quit) void unity.Quit().catch(() => {});
  });
})();
