const VERSION = 2;
const PRODUCTION_PARENT = "https://przppz.club";
const LOCAL_PARENTS = new Set(["http://localhost:3000", "http://127.0.0.1:3000"]);

export function createReadinessGate(onReady) {
  let instance = null;
  let receiverReady = false;
  let announced = false;

  function announceIfReady() {
    if (!announced && instance && receiverReady) {
      announced = true;
      onReady(instance);
    }
  }

  return {
    setInstance(next) {
      instance = next;
      announceIfReady();
    },
    markReceiverReady() {
      receiverReady = true;
      announceIfReady();
    },
    get isReady() {
      return announced;
    },
  };
}

export function createRequestGate() {
  const processed = new Set();
  let generation = 0;
  return {
    claim(requestId) {
      if (!requestId || processed.has(requestId)) return null;
      processed.add(requestId);
      generation += 1;
      return generation;
    },
    isCurrent(token) {
      return token === generation;
    },
    cancel() {
      generation += 1;
    },
  };
}

export function isTrustedLoadMessage(event, parentWindow, parentOrigin, sessionId) {
  return (
    event.origin === parentOrigin
    && event.source === parentWindow
    && event.data?.type === "zppz.preview.load"
    && event.data?.version === VERSION
    && event.data?.session_id === sessionId
  );
}

function parentAllowed(origin) {
  return origin === PRODUCTION_PARENT || LOCAL_PARENTS.has(origin);
}

function resolveParentOrigin() {
  try {
    const referrerOrigin = new URL(document.referrer).origin;
    if (parentAllowed(referrerOrigin)) return referrerOrigin;
  } catch {
    // Production remains the only fallback when referrer is absent.
  }
  return PRODUCTION_PARENT;
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

function bootstrap() {
  const canvas = document.getElementById("unity-canvas");
  const status = document.getElementById("status");
  const message = document.getElementById("message");
  const progress = document.getElementById("progress");
  if (!canvas || !status || !message || !progress) return;

  const sessionId = new URL(window.location.href).searchParams.get("zppz_session") || "";
  const parentOrigin = resolveParentOrigin();
  const requests = createRequestGate();
  let unity = null;
  let activeAbortController = null;
  let receiverTimer = 0;

  function post(type, payload = {}) {
    if (window.parent === window) return;
    window.parent.postMessage(
      { type, version: VERSION, session_id: sessionId, ...payload },
      parentOrigin,
    );
  }

  function setStatus(text, value) {
    message.textContent = text;
    status.hidden = false;
    if (typeof value === "number") progress.value = Math.max(0, Math.min(1, value));
  }

  async function preflight(url, signal) {
    const response = await fetch(url, {
      cache: "no-store",
      headers: { Range: "bytes=0-0" },
      signal,
    });
    if (response.status === 401 || response.status === 403 || response.status === 410) {
      await response.body?.cancel();
      throw new Error("signed_url_expired");
    }
    if (!response.ok && response.status !== 206) {
      await response.body?.cancel();
      throw new Error("asset_network_failed");
    }
    await response.body?.cancel();
  }

  async function sendChart(payload, requestId, token, controller) {
    setStatus("检查谱面和媒体素材", 1);
    post("zppz.preview.state", { request_id: requestId, phase: "checking-assets" });
    try {
      await Promise.all([
        preflight(payload.maidata, controller.signal),
        preflight(payload.track, controller.signal),
        preflight(payload.background, controller.signal),
      ]);
    } catch (error) {
      if (controller.signal.aborted || !requests.isCurrent(token)) return;
      const code = error instanceof Error ? error.message : "asset_network_failed";
      const text = code === "signed_url_expired" ? "签名地址已过期" : "谱面或媒体网络加载失败";
      setStatus(text);
      post("zppz.preview.error", { request_id: requestId, code, message: text });
      return;
    }
    if (!requests.isCurrent(token)) return;

    let video = payload.video;
    if (video) {
      const videoElement = document.createElement("video");
      if (!videoElement.canPlayType("video/mp4")) {
        video = "";
        post("zppz.preview.warning", {
          request_id: requestId,
          code: "video_format_unsupported",
          message: "背景视频格式不受支持，已回退到静态背景",
        });
      } else {
        try {
          await preflight(video, controller.signal);
        } catch {
          if (controller.signal.aborted || !requests.isCurrent(token)) return;
          video = "";
          post("zppz.preview.warning", {
            request_id: requestId,
            code: "video_network_failed",
            message: "背景视频加载失败，已回退到静态背景",
          });
        }
      }
    }
    if (!requests.isCurrent(token) || !unity) return;

    setStatus("加载谱面和音乐", 1);
    unity.SendMessage(
      "HandleJSMessages",
      "ReceiveMessage",
      `${payload.maidata}\n${payload.track}\n${payload.background}\n${video}\nlv${payload.difficulty}`,
    );
    post("zppz.preview.state", { request_id: requestId, phase: "chart-dispatched" });
    status.hidden = true;
  }

  window.addEventListener("message", (event) => {
    if (!isTrustedLoadMessage(event, window.parent, parentOrigin, sessionId)) return;
    const requestId = String(event.data.request_id || "");
    const token = requests.claim(requestId);
    if (token === null) return;
    try {
      const payload = normalizePayload(event.data.payload);
      activeAbortController?.abort();
      activeAbortController = new AbortController();
      void sendChart(payload, requestId, token, activeAbortController);
    } catch (error) {
      setStatus("预览参数无效");
      post("zppz.preview.error", {
        request_id: requestId,
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

  const readiness = createReadinessGate((instance) => {
    window.clearTimeout(receiverTimer);
    unity = instance;
    setStatus("谱面接收器已就绪", 1);
    post("zppz.preview.ready");
  });

  // MajdataView invokes this explicit hook from HandleJSMessages.Awake().
  // createUnityInstance resolving alone does not guarantee that ReceiveMessage exists.
  window.onUnityLoaded = () => readiness.markReceiverReady();

  setStatus("加载播放器 0%", 0);
  window.createUnityInstance(
    canvas,
    {
      dataUrl: "./Build.data",
      frameworkUrl: "./Build.framework.js",
      codeUrl: "./Build.wasm",
      streamingAssetsUrl: "StreamingAssets",
      companyName: "Majdata",
      productName: "MajdataView",
      productVersion: "zppz-record5-6000.6",
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
    readiness.setInstance(instance);
    if (!readiness.isReady) {
      setStatus("初始化谱面接收器", 1);
      receiverTimer = window.setTimeout(() => {
        if (readiness.isReady) return;
        setStatus("谱面接收器初始化失败");
        post("zppz.preview.error", {
          code: "unity_receiver_timeout",
          message: "谱面接收器初始化失败，请重新加载预览",
        });
      }, 10_000);
    }
  }).catch((error) => {
    setStatus("播放器网络加载失败");
    post("zppz.preview.error", {
      code: "unity_load_failed",
      message: error instanceof Error ? error.message : "播放器加载失败",
    });
  });

  window.addEventListener("pagehide", () => {
    window.clearTimeout(receiverTimer);
    requests.cancel();
    activeAbortController?.abort();
    if (unity?.Quit) void unity.Quit().catch(() => {});
  });
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  bootstrap();
}
