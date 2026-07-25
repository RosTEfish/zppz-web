import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
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
import { Download, Play, Wifi } from "lucide-react";
import { api, type PreviewManifest } from "../api/v1";

type PreviewSource = "submission" | "guess";

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
  const [confirmed, setConfirmed] = useState(false);
  const [manifest, setManifest] = useState<PreviewManifest | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [playerProgress, setPlayerProgress] = useState(0);
  const [playerReady, setPlayerReady] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  useEffect(() => {
    if (!open) {
      setManifest(null);
      setSelectedSlot(null);
      setError("");
      setWarning("");
      setPlayerProgress(0);
      setPlayerReady(false);
      setConfirmed(false);
      return;
    }
    setConfirmed(!mobile || localStorage.getItem("zppz-preview-mobile-confirmed") === "1");
  }, [mobile, open, sourceId]);

  useEffect(() => {
    if (!open || !confirmed || sourceId === null) return;
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
          timer = window.setTimeout(() => void load(), 2000);
        } else if (next.status === "processing") {
          setError("预览素材准备超时，请稍后重试");
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "预览信息加载失败");
        }
      }
    };
    void load();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [confirmed, open, source, sourceId]);

  const selectedLevel = manifest?.levels.find((item) => item.slot === selectedSlot);
  const sendLoad = () => {
    if (!manifest?.assets || !selectedLevel || !iframeRef.current?.contentWindow) return;
    iframeRef.current.contentWindow.postMessage(
      {
        type: "zppz.preview.load",
        version: 1,
        request_id: crypto.randomUUID(),
        payload: {
          ...manifest.assets,
          difficulty_index: selectedLevel.difficulty_index,
        },
      },
      manifest.player_origin,
    );
  };

  useEffect(() => {
    if (!open || !manifest?.player_origin) return;
    const receive = (event: MessageEvent) => {
      if (
        event.origin !== manifest.player_origin
        || event.source !== iframeRef.current?.contentWindow
      ) return;
      if (event.data?.type === "zppz.preview.progress") {
        setPlayerProgress(Number(event.data.progress) || 0);
      }
      if (event.data?.type === "zppz.preview.ready") {
        setPlayerReady(true);
        sendLoad();
      }
      if (event.data?.type === "zppz.preview.loaded") {
        setPlayerReady(true);
        setPlayerProgress(1);
      }
      if (event.data?.type === "zppz.preview.error") {
        setError(event.data.message || "播放器加载失败");
      }
      if (event.data?.type === "zppz.preview.warning") {
        setWarning(event.data.message || "部分媒体已回退");
      }
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  });

  useEffect(() => {
    if (playerReady) sendLoad();
  }, [selectedSlot]);

  function confirmMobileLoad() {
    localStorage.setItem("zppz-preview-mobile-confirmed", "1");
    setConfirmed(true);
  }

  const ready = manifest?.status === "ready" && manifest.assets && manifest.player_url;
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
      <DialogContent dividers sx={{ p: { xs: 1.5, sm: 2 }, bgcolor: "#050807" }}>
        {!confirmed ? (
          <Stack spacing={2.5} sx={{ minHeight: 360, justifyContent: "center", alignItems: "center", textAlign: "center", color: "common.white", px: 2 }}>
            <Wifi size={42} />
            <Box>
              <Typography variant="h3">首次加载约几十 MB</Typography>
              <Typography color="grey.400" sx={{ mt: 1 }}>建议使用 Wi-Fi；播放器文件后续将使用浏览器缓存。</Typography>
            </Box>
            <Button variant="contained" startIcon={<Play size={17} />} onClick={confirmMobileLoad}>继续加载预览</Button>
          </Stack>
        ) : ready ? (
          <Stack spacing={1.5}>
            {error ? <Alert severity="error">{error}</Alert> : null}
            {warning ? <Alert severity="warning">{warning}</Alert> : null}
            {manifest.levels.length > 1 && source === "submission" ? (
              <FormControl size="small" sx={{ width: 190, bgcolor: "background.paper", borderRadius: 1 }}>
                <InputLabel>预览难度</InputLabel>
                <Select value={selectedSlot ?? ""} label="预览难度" onChange={(event) => setSelectedSlot(Number(event.target.value))}>
                  {manifest.levels.map((level) => <MenuItem key={level.slot} value={level.slot}>槽位 {level.slot} · {level.level}</MenuItem>)}
                </Select>
              </FormControl>
            ) : null}
            <Box sx={{ width: "100%", aspectRatio: "1", position: "relative", bgcolor: "black", borderRadius: { sm: 1.5 }, overflow: "hidden" }}>
              <Box
                component="iframe"
                ref={iframeRef}
                src={manifest.player_url}
                title={`${title} Majdata 在线预览`}
                allow="autoplay; fullscreen"
                allowFullScreen
                sandbox="allow-scripts allow-same-origin allow-pointer-lock"
                onLoad={sendLoad}
                sx={{ border: 0, width: "100%", height: "100%", display: "block" }}
              />
              {playerProgress < 1 ? <LinearProgress variant="determinate" value={playerProgress * 100} sx={{ position: "absolute", left: 0, right: 0, bottom: 0 }} /> : null}
            </Box>
          </Stack>
        ) : (
          <Stack spacing={2} sx={{ minHeight: 360, justifyContent: "center", alignItems: "center", textAlign: "center", color: "common.white", px: 2 }}>
            {manifest?.status === "processing" && !error ? <CircularProgress /> : null}
            <Typography variant="h3">
              {error || manifest?.message || "正在准备预览素材"}
            </Typography>
            {manifest?.status === "unsupported" ? <Alert severity="warning">{manifest.message}</Alert> : null}
            {manifest?.status === "failed" || error ? <Alert severity="error">在线预览暂不可用，仍可下载投稿。</Alert> : null}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button startIcon={<Download size={16} />} onClick={() => void onDownload().catch(() => {})}>下载投稿</Button>
        <Button onClick={onClose}>关闭</Button>
      </DialogActions>
    </Dialog>
  );
}
