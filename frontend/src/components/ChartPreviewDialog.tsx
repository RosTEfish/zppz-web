import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { Download, Music2, Play, RefreshCw, Square, Wifi } from "lucide-react";
import { api, type PreviewManifest } from "../api/v1";

export type PreviewSource = "submission" | "guess";

type PreviewPhase =
  | "idle"
  | "confirm"
  | "preparing"
  | "loading-player"
  | "waiting-receiver"
  | "checking-assets"
  | "loading-chart"
  | "error";

const PROTOCOL_VERSION = 2;
const PLAYER_READY_TIMEOUT_MS = 90_000;
const MOBILE_CONFIRMATION_KEY = "zppz-preview-mobile-confirmed";

function createId(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function playerUrlWithSession(url: string, sessionId: string): string {
  const next = new URL(url, window.location.href);
  next.searchParams.set("zppz_session", sessionId);
  return next.href;
}

const PHASE_LABELS: Partial<Record<PreviewPhase, string>> = {
  preparing: "准备预览素材",
  "loading-player": "加载播放器",
  "waiting-receiver": "初始化谱面接收器",
  "checking-assets": "检查谱面和媒体素材",
  "loading-chart": "加载谱面和音乐",
};

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
  const [sessionId, setSessionId] = useState(createId);
  const [manifest, setManifest] = useState<PreviewManifest | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
  const [phase, setPhase] = useState<PreviewPhase>("idle");
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [playerProgress, setPlayerProgress] = useState(0);
  const [playerReady, setPlayerReady] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const sentRequestsRef = useRef<Set<string>>(new Set());
  const activeIdentityRef = useRef("");

  const resetSession = useCallback(() => {
    setSessionId(createId());
    setManifest(null);
    setSelectedSlot(null);
    setError("");
    setWarning("");
    setPlayerProgress(0);
    setPlayerReady(false);
    sentRequestsRef.current.clear();
    setAttempt((current) => current + 1);
  }, []);

  useEffect(() => {
    if (!active) {
      activeIdentityRef.current = "";
      setLoadApproved(false);
      setManifest(null);
      setSelectedSlot(null);
      setError("");
      setWarning("");
      setPlayerProgress(0);
      setPlayerReady(false);
      setPhase("idle");
      sentRequestsRef.current.clear();
      return;
    }
    const identity = `${source}:${sourceId ?? "none"}`;
    if (activeIdentityRef.current !== identity) {
      activeIdentityRef.current = identity;
      setSessionId(createId());
      setManifest(null);
      setSelectedSlot(null);
      setError("");
      setWarning("");
      setPlayerProgress(0);
      setPlayerReady(false);
      sentRequestsRef.current.clear();
    }
    const approved = !mobile || localStorage.getItem(MOBILE_CONFIRMATION_KEY) === "1";
    setLoadApproved(approved);
    setPhase(approved ? "preparing" : "confirm");
  }, [active, attempt, mobile, source, sourceId]);

  useEffect(() => {
    if (!active || !loadApproved || sourceId === null) return;
    const controller = new AbortController();
    let timer = 0;
    let attempts = 0;
    const load = async () => {
      try {
        const next = source === "submission"
          ? await api.submissionPreviewManifest(sourceId, controller.signal)
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
        if (next.status !== "ready" || !next.assets || !next.player_url) {
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

  const selectedLevel = manifest?.levels.find((item) => item.slot === selectedSlot);
  const requestId = useMemo(
    () => selectedLevel && manifest
      ? `${sessionId}:${manifest.source_version}:${selectedLevel.slot}`
      : "",
    [manifest, selectedLevel, sessionId],
  );
  const ready = manifest?.status === "ready" && Boolean(manifest.assets && manifest.player_url);
  const iframeUrl = ready && manifest
    ? playerUrlWithSession(manifest.player_url, sessionId)
    : "";

  useEffect(() => {
    if (!active || !ready || playerReady) return;
    const timer = window.setTimeout(() => {
      setPhase("error");
      setError("播放器初始化超时，请重新加载预览");
    }, PLAYER_READY_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [active, playerReady, ready, sessionId]);

  useEffect(() => {
    if (!active || !manifest?.player_origin) return;
    const receive = (event: MessageEvent) => {
      if (
        event.origin !== manifest.player_origin
        || event.source !== iframeRef.current?.contentWindow
        || event.data?.version !== PROTOCOL_VERSION
        || event.data?.session_id !== sessionId
      ) return;
      if (event.data.type === "zppz.preview.progress") {
        const progress = Math.max(0, Math.min(1, Number(event.data.progress) || 0));
        setPlayerProgress(progress);
        setPhase(progress >= 1 ? "waiting-receiver" : "loading-player");
      } else if (event.data.type === "zppz.preview.ready") {
        setPlayerReady(true);
        setPhase("checking-assets");
      } else if (event.data.type === "zppz.preview.state") {
        if (event.data.request_id !== requestId) return;
        if (event.data.phase === "checking-assets") setPhase("checking-assets");
        if (event.data.phase === "chart-dispatched") setPhase("loading-chart");
      } else if (event.data.type === "zppz.preview.error") {
        setPhase("error");
        setError(event.data.message || "播放器加载失败");
      } else if (event.data.type === "zppz.preview.warning") {
        setWarning(event.data.message || "部分媒体已回退");
      }
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [active, manifest?.player_origin, requestId, sessionId]);

  useEffect(() => {
    if (
      !playerReady
      || !manifest?.assets
      || !selectedLevel
      || !requestId
      || !iframeRef.current?.contentWindow
      || sentRequestsRef.current.has(requestId)
    ) return;
    sentRequestsRef.current.add(requestId);
    setPhase("checking-assets");
    iframeRef.current.contentWindow.postMessage(
      {
        type: "zppz.preview.load",
        version: PROTOCOL_VERSION,
        session_id: sessionId,
        request_id: requestId,
        payload: {
          ...manifest.assets,
          difficulty_index: selectedLevel.difficulty_index,
        },
      },
      manifest.player_origin,
    );
  }, [manifest, playerReady, requestId, selectedLevel, sessionId]);

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
            <Typography variant="body2" sx={{ color: "rgba(255,255,255,.76)" }}>Majdata 实时渲染</Typography>
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
  return (
    <Stack spacing={1.25}>
      {warning ? <Alert severity="warning">{warning}</Alert> : null}
      <Box
        sx={{
          width: "100%",
          aspectRatio: "1",
          position: "relative",
          overflow: "hidden",
          bgcolor: "#050807",
          borderRadius: { xs: 0, sm: 1.5 },
          color: "common.white",
          boxShadow: "0 18px 48px rgba(3, 18, 12, .18)",
        }}
      >
        {!loadApproved ? (
          <StageMessage
            icon={<Wifi size={42} />}
            title="播放器首次加载约几十 MB"
            body="建议使用 Wi-Fi；播放器文件后续将使用浏览器缓存。"
            actions={<Button variant="contained" startIcon={<Play size={17} />} onClick={approveMobileLoad}>继续加载预览</Button>}
          />
        ) : recoverableError || manifest?.status === "unsupported" ? (
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
        ) : ready && manifest ? (
          <>
            <Box
              component="iframe"
              key={sessionId}
              ref={iframeRef}
              src={iframeUrl}
              title={`${title} Majdata 在线预览`}
              allow="autoplay; fullscreen"
              allowFullScreen
              sandbox="allow-scripts allow-same-origin allow-pointer-lock"
              sx={{ border: 0, width: "100%", height: "100%", display: "block" }}
            />
            {phase !== "loading-chart" ? (
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
                  {PHASE_LABELS[phase] ?? "加载预览"}
                </Typography>
              </Box>
            ) : null}
            {phase === "loading-player" && playerProgress < 1 ? (
              <LinearProgress
                variant="determinate"
                value={playerProgress * 100}
                sx={{ position: "absolute", left: 0, right: 0, bottom: 0 }}
              />
            ) : null}
          </>
        ) : (
          <StageMessage
            icon={<CircularProgress color="inherit" />}
            title={manifestMessage}
            body="首次生成历史投稿预览时可能需要等待片刻。"
          />
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
