import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { Download, Music2, Play, RefreshCw, Square, Wifi } from "lucide-react";
import { api, type PreviewManifest } from "../api/v1";

export type PreviewSource = "submission" | "guess" | "archive";

type PreviewPhase =
  | "idle"
  | "confirm"
  | "preparing"
  | "loading-player"
  | "loading-chart"
  | "ready"
  | "error";

/** MiaView SDK surface used by the stage; kept local so tests can mock createPreview. */
export interface MiaViewPreview {
  ready: Promise<unknown>;
  load: (input: {
    maidata: { url: string };
    audio?: string;
    cover?: string;
    video?: string | null;
    difficulty?: number;
  }) => Promise<unknown>;
  selectDifficulty: (difficulty: number) => Promise<unknown>;
  destroy: () => void;
  on: (type: string, listener: (payload: { message?: string }) => void) => () => void;
}

export type CreateMiaViewPreview = (
  container: HTMLElement,
  options: {
    rendererUrl: string;
    resolution: { width: number; height: number };
    maxFps: number | "unlimited";
    diagnostics: boolean;
    theme: "dark" | "light";
  },
) => MiaViewPreview;

const PLAYER_READY_TIMEOUT_MS = 90_000;
const MOBILE_CONFIRMATION_KEY = "zppz-preview-mobile-confirmed";
const PREVIEW_RESOLUTION = { width: 1080, height: 1080 } as const;

const PHASE_LABELS: Partial<Record<PreviewPhase, string>> = {
  preparing: "准备预览素材",
  "loading-player": "加载播放器",
  "loading-chart": "加载谱面和音乐",
};

async function importCreatePreview(sdkUrl: string): Promise<CreateMiaViewPreview> {
  const module = await import(/* @vite-ignore */ sdkUrl) as { createPreview?: CreateMiaViewPreview };
  if (typeof module.createPreview !== "function") {
    throw new Error("MiaView SDK 未导出 createPreview");
  }
  return module.createPreview;
}

/** Test seam: swap to inject a fake SDK without dynamic import. */
export let loadMiaViewCreatePreview: (sdkUrl: string) => Promise<CreateMiaViewPreview> = importCreatePreview;

export function setMiaViewCreatePreviewLoader(
  loader: ((sdkUrl: string) => Promise<CreateMiaViewPreview>) | null,
): void {
  loadMiaViewCreatePreview = loader ?? importCreatePreview;
}

const PHASE_LABELS_READY = "预览已就绪";

export interface ChartPreviewStageProps {
  active: boolean;
  source: PreviewSource;
  sourceId: number | null;
  title: string;
  coverUrl?: string | null;
  levelLabel?: string;
  canPreview?: boolean;
  idleAction?: ReactNode;
  onActivate?: () => void;
  onDeactivate?: () => void;
  onDownload: () => Promise<void>;
}

export function ChartPreviewStage({
  active,
  source,
  sourceId,
  title,
  coverUrl,
  levelLabel,
  canPreview = true,
  idleAction,
  onActivate,
  onDeactivate,
  onDownload,
}: ChartPreviewStageProps) {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [loadApproved, setLoadApproved] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [manifest, setManifest] = useState<PreviewManifest | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
  const [phase, setPhase] = useState<PreviewPhase>("idle");
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const previewRef = useRef<MiaViewPreview | null>(null);
  const instanceKeyRef = useRef("");
  const loadedDifficultyRef = useRef<number | null>(null);
  const activeIdentityRef = useRef("");

  const destroyPreview = useCallback(() => {
    previewRef.current?.destroy();
    previewRef.current = null;
    instanceKeyRef.current = "";
    loadedDifficultyRef.current = null;
    if (containerRef.current) containerRef.current.replaceChildren();
  }, []);

  const resetSession = useCallback(() => {
    destroyPreview();
    setManifest(null);
    setSelectedSlot(null);
    setError("");
    setWarning("");
    setAttempt((current) => current + 1);
  }, [destroyPreview]);

  useEffect(() => {
    if (!active) {
      activeIdentityRef.current = "";
      destroyPreview();
      setLoadApproved(false);
      setManifest(null);
      setSelectedSlot(null);
      setError("");
      setWarning("");
      setPhase("idle");
      return;
    }
    const identity = `${source}:${sourceId ?? "none"}`;
    if (activeIdentityRef.current !== identity) {
      activeIdentityRef.current = identity;
      destroyPreview();
      setManifest(null);
      setSelectedSlot(null);
      setError("");
      setWarning("");
    }
    const approved = !mobile || localStorage.getItem(MOBILE_CONFIRMATION_KEY) === "1";
    setLoadApproved(approved);
    setPhase(approved ? "preparing" : "confirm");
  }, [active, attempt, destroyPreview, mobile, source, sourceId]);

  useEffect(() => {
    if (!active || !loadApproved || sourceId === null) return;
    const controller = new AbortController();
    let timer = 0;
    let attempts = 0;
    const load = async () => {
      try {
        const next = source === "submission"
          ? await api.submissionPreviewManifest(sourceId, controller.signal)
          : source === "archive"
            ? await api.archivePreviewManifest(sourceId, controller.signal)
            : await api.guessPreviewManifest(sourceId, controller.signal);
        if (controller.signal.aborted) return;
        setManifest(next);
        setSelectedSlot((current) => current ?? next.selected_level_slot ?? next.levels[0]?.slot ?? null);
        if (next.status === "processing" && attempts < 30) {
          attempts += 1;
          setPhase("preparing");
          timer = window.setTimeout(() => void load(), 2_000);
          return;
        }
        if (next.status === "processing") {
          setPhase("error");
          setError("预览素材准备超时，请稍后重试");
          return;
        }
        if (next.status !== "ready" || !next.assets || !next.player_url || !next.renderer_url) {
          setPhase("error");
          return;
        }
        setPhase("loading-player");
      } catch (reason) {
        if (!controller.signal.aborted) {
          setPhase("error");
          setError(reason instanceof Error ? reason.message : "预览信息加载失败");
        }
      }
    };
    void load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [active, attempt, loadApproved, source, sourceId]);

  const ready = manifest?.status === "ready"
    && Boolean(manifest.assets && manifest.player_url && manifest.renderer_url);
  const slotReady = selectedSlot !== null;
  const selectedSlotRef = useRef(selectedSlot);
  selectedSlotRef.current = selectedSlot;

  useEffect(() => {
    if (!active || !ready || !manifest?.assets || !slotReady) return;

    const instanceKey = `${manifest.player_url}|${manifest.renderer_url}|${manifest.source_version}|${attempt}`;
    // Only skip when this exact instance already finished loading a chart.
    // Skipping earlier left a "player shell ready, chart never loaded" zombie after
    // React Strict Mode / dependency churn cancelled an in-flight load().
    if (
      instanceKeyRef.current === instanceKey
      && previewRef.current
      && loadedDifficultyRef.current !== null
    ) {
      return;
    }

    let cancelled = false;
    let preview: MiaViewPreview | null = null;
    let unsubscribe: (() => void) | null = null;
    const assets = manifest.assets;
    const playerUrl = manifest.player_url;
    const rendererUrl = manifest.renderer_url;
    const timeout = window.setTimeout(() => {
      if (cancelled) return;
      setPhase("error");
      setError("播放器初始化超时，请重新加载预览");
      destroyPreview();
    }, PLAYER_READY_TIMEOUT_MS);

    const run = async () => {
      try {
        // Wait until the player host node is actually mounted. The first ready
        // render can run this effect before the ref is attached.
        let container = containerRef.current;
        for (let spin = 0; !container && spin < 30 && !cancelled; spin += 1) {
          await new Promise<void>((resolve) => {
            window.requestAnimationFrame(() => resolve());
          });
          container = containerRef.current;
        }
        if (cancelled || !container) {
          if (!cancelled) {
            setPhase("error");
            setError("播放器容器未就绪，请重新加载预览");
          }
          return;
        }

        setPhase("loading-player");
        destroyPreview();
        const createPreview = await loadMiaViewCreatePreview(playerUrl);
        if (cancelled) return;
        preview = createPreview(container, {
          rendererUrl,
          resolution: { ...PREVIEW_RESOLUTION },
          maxFps: "unlimited",
          diagnostics: false,
          theme: "dark",
        });
        if (cancelled) {
          preview.destroy();
          preview = null;
          return;
        }
        previewRef.current = preview;
        unsubscribe = preview.on("error", ({ message }) => {
          setPhase("error");
          setError(message || "播放器加载失败");
        });
        await preview.ready;
        if (cancelled) return;
        setPhase("loading-chart");
        const difficulty = selectedSlotRef.current;
        if (difficulty === null) {
          throw new Error("未选择预览难度");
        }
        await preview.load({
          maidata: { url: assets.maidata_url },
          audio: assets.track_url,
          cover: assets.background_url,
          video: assets.video_url ?? undefined,
          difficulty,
        });
        if (cancelled) return;
        instanceKeyRef.current = instanceKey;
        loadedDifficultyRef.current = difficulty;
        setPhase("ready");
      } catch (reason) {
        if (cancelled) return;
        destroyPreview();
        setPhase("error");
        setError(reason instanceof Error ? reason.message : "播放器加载失败");
      } finally {
        window.clearTimeout(timeout);
      }
    };

    void run();
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
      unsubscribe?.();
      // Always tear down incomplete instances. A cancelled run that already
      // created the SDK shell must not leave previewRef pointing at an empty player.
      if (preview && previewRef.current === preview) {
        preview.destroy();
        previewRef.current = null;
        instanceKeyRef.current = "";
        loadedDifficultyRef.current = null;
        if (containerRef.current) containerRef.current.replaceChildren();
      } else if (preview) {
        preview.destroy();
      }
    };
  }, [active, attempt, destroyPreview, manifest, ready, slotReady]);

  useEffect(() => {
    const preview = previewRef.current;
    if (!preview || selectedSlot === null || phase !== "ready") return;
    if (loadedDifficultyRef.current === selectedSlot) return;
    let cancelled = false;
    void preview.selectDifficulty(selectedSlot)
      .then(() => {
        if (cancelled) return;
        loadedDifficultyRef.current = selectedSlot;
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setPhase("error");
        setError(reason instanceof Error ? reason.message : "切换难度失败");
      });
    return () => {
      cancelled = true;
    };
  }, [phase, selectedSlot]);

  function approveMobileLoad() {
    localStorage.setItem(MOBILE_CONFIRMATION_KEY, "1");
    setLoadApproved(true);
    setPhase("preparing");
  }

  function retry() {
    setPhase("preparing");
    resetSession();
  }

  if (!active) {
    return (
      <Box
        sx={{
          width: "100%",
          aspectRatio: "1",
          position: "relative",
          overflow: "hidden",
          bgcolor: "#07100d",
          borderRadius: { xs: 0, sm: 1.5 },
          isolation: "isolate",
        }}
      >
        {coverUrl ? (
          <Box
            component="img"
            src={coverUrl}
            alt={`${title} 封面`}
            sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        ) : (
          <Box sx={{ width: "100%", height: "100%", display: "grid", placeItems: "center", color: "rgba(223,247,233,.72)" }}>
            <Music2 size={64} strokeWidth={1.4} />
          </Box>
        )}
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            justifyContent: "flex-end",
            p: { xs: 2, sm: 3 },
            color: "common.white",
            background: "linear-gradient(180deg, transparent 42%, rgba(2,10,7,.9) 100%)",
          }}
        >
          <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap", mb: 1.5 }}>
            {levelLabel ? <Chip label={levelLabel} sx={{ bgcolor: "rgba(255,255,255,.92)", color: "#17211d" }} /> : null}
            <Typography variant="body2" sx={{ color: "rgba(255,255,255,.76)" }}>MiaView 实时渲染</Typography>
          </Stack>
          {idleAction ?? (
            <Button
              variant="contained"
              color="primary"
              startIcon={<Play size={18} />}
              disabled={!canPreview}
              onClick={onActivate}
              sx={{ alignSelf: "flex-start", px: 2.5 }}
            >
              {canPreview ? "开始在线预览" : "当前不可预览"}
            </Button>
          )}
        </Box>
      </Box>
    );
  }

  const manifestMessage = manifest?.message || "正在准备预览素材";
  const recoverableError = error || (manifest?.status === "failed" ? manifestMessage : "");
  const showPlayer = ready && !recoverableError && manifest?.status !== "unsupported" && loadApproved;

  return (
    <Stack spacing={1.25}>
      {warning ? <Alert severity="warning">{warning}</Alert> : null}
      <Box
        sx={{
          width: "100%",
          position: "relative",
          overflow: "hidden",
          bgcolor: "#050807",
          borderRadius: { xs: 0, sm: 1.5 },
          color: "common.white",
          boxShadow: "0 18px 48px rgba(3, 18, 12, .18)",
          // Square canvas + MiaView transport bar (~80px).
          minHeight: { xs: 320, sm: 420 },
        }}
      >
        {!loadApproved ? (
          <Box sx={{ aspectRatio: "1", position: "relative" }}>
            <StageMessage
              icon={<Wifi size={42} />}
              title="播放器首次加载约几十 MB"
              body="建议使用 Wi-Fi；播放器文件后续将使用浏览器缓存。"
              actions={<Button variant="contained" startIcon={<Play size={17} />} onClick={approveMobileLoad}>继续加载预览</Button>}
            />
          </Box>
        ) : recoverableError || manifest?.status === "unsupported" ? (
          <Box sx={{ aspectRatio: "1", position: "relative" }}>
            <StageMessage
              title={recoverableError || manifestMessage}
              body={manifest?.status === "unsupported" ? "该投稿仍可正常下载，不影响赛事流程。" : "在线预览暂不可用，可以重新创建播放器会话。"}
              severity={manifest?.status === "unsupported" ? "warning" : "error"}
              actions={(
                <Stack direction="row" spacing={1} useFlexGap sx={{ justifyContent: "center", flexWrap: "wrap" }}>
                  {manifest?.status !== "unsupported" ? <Button variant="contained" startIcon={<RefreshCw size={17} />} onClick={retry}>重新加载预览</Button> : null}
                  <Button color="inherit" variant="outlined" startIcon={<Download size={17} />} onClick={() => void onDownload().catch(() => {})}>下载投稿</Button>
                </Stack>
              )}
            />
          </Box>
        ) : showPlayer ? (
          <Box sx={{ position: "relative", width: "100%" }}>
            <Box
              ref={containerRef}
              data-testid="miaview-preview-root"
              title={`${title} MiaView 在线预览`}
              sx={{ width: "100%", "& > *": { width: "100% !important", maxWidth: "100%" } }}
            />
            {phase !== "ready" ? (
              <Box
                role="status"
                sx={{
                  position: "absolute",
                  top: 12,
                  left: 12,
                  right: 12,
                  display: "flex",
                  justifyContent: "center",
                  pointerEvents: "none",
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    px: 1.5,
                    py: 0.75,
                    border: "1px solid rgba(166,221,189,.26)",
                    borderRadius: 10,
                    bgcolor: "rgba(2,10,7,.78)",
                    color: "#dff7e9",
                    backdropFilter: "blur(8px)",
                  }}
                >
                  {PHASE_LABELS[phase] ?? PHASE_LABELS_READY}
                </Typography>
              </Box>
            ) : null}
          </Box>
        ) : (
          <Box sx={{ aspectRatio: "1", position: "relative" }}>
            <StageMessage
              icon={<CircularProgress color="inherit" />}
              title={manifestMessage}
              body="首次生成历史投稿预览时可能需要等待片刻。"
            />
          </Box>
        )}
      </Box>
      {active && onDeactivate ? (
        <Button color="inherit" size="small" startIcon={<Square size={15} />} onClick={onDeactivate} sx={{ alignSelf: "flex-start" }}>
          退出预览并释放播放器
        </Button>
      ) : null}
      {Boolean(manifest?.levels.length) && (manifest?.levels.length ?? 0) > 1 && source === "submission" ? (
        <FormControl size="small" sx={{ width: 210 }}>
          <InputLabel>预览难度</InputLabel>
          <Select value={selectedSlot ?? ""} label="预览难度" onChange={(event) => setSelectedSlot(Number(event.target.value))}>
            {manifest.levels.map((level) => <MenuItem key={level.slot} value={level.slot}>槽位 {level.slot} · {level.level}</MenuItem>)}
          </Select>
        </FormControl>
      ) : null}
    </Stack>
  );
}

function StageMessage({
  icon,
  title,
  body,
  severity,
  actions,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  severity?: "warning" | "error";
  actions?: ReactNode;
}) {
  return (
    <Stack
      spacing={2}
      sx={{
        position: "absolute",
        inset: 0,
        justifyContent: "center",
        alignItems: "center",
        textAlign: "center",
        px: 3,
        background: "radial-gradient(circle at 50% 32%, rgba(47,145,93,.2), transparent 38%)",
      }}
    >
      {icon}
      {severity ? <Alert severity={severity} sx={{ maxWidth: 520 }}>{title}</Alert> : <Typography variant="h3">{title}</Typography>}
      {body ? <Typography variant="body2" sx={{ color: "grey.400", maxWidth: 520 }}>{body}</Typography> : null}
      {actions}
    </Stack>
  );
}

export function ChartPreviewDialog({
  open,
  source,
  sourceId,
  title,
  onClose,
  onDownload,
}: {
  open: boolean;
  source: PreviewSource;
  sourceId: number | null;
  title: string;
  onClose: () => void;
  onDownload: () => Promise<void>;
}) {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("sm"));
  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullScreen={mobile}
      fullWidth
      maxWidth="md"
      slotProps={{ paper: { sx: { overflow: "hidden" } } }}
    >
      <DialogTitle sx={{ pb: 1 }}>{title} · 在线预览</DialogTitle>
      <DialogContent dividers sx={{ p: { xs: 0, sm: 2 }, bgcolor: "#050807" }}>
        <ChartPreviewStage
          active={open}
          source={source}
          sourceId={sourceId}
          title={title}
          onDeactivate={onClose}
          onDownload={onDownload}
        />
      </DialogContent>
      <DialogActions>
        <Button startIcon={<Download size={16} />} onClick={() => void onDownload().catch(() => {})}>下载投稿</Button>
        <Button onClick={onClose}>关闭</Button>
      </DialogActions>
    </Dialog>
  );
}
