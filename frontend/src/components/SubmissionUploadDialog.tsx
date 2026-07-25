import { useCallback, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { CheckCircle2, RotateCcw, UploadCloud, X } from "lucide-react";
import {
  formatMB,
  type SubmissionProcessingJob,
  type SubmissionUploadOptions,
  type SubmissionUploadProgress,
} from "../api/v1";

type UploadStarter = (options: SubmissionUploadOptions) => Promise<SubmissionProcessingJob>;
type DialogPhase = SubmissionUploadProgress["phase"] | "success" | "error" | "cancelled";

interface UploadDialogState {
  open: boolean;
  phase: DialogPhase;
  fileName: string;
  fileSize: number;
  progress: SubmissionUploadProgress;
  error: string;
}

const EMPTY_PROGRESS: SubmissionUploadProgress = {
  phase: "preparing",
  loaded: 0,
  total: 0,
  percent: 0,
  bytesPerSecond: 0,
  etaSeconds: null,
};

function formatRate(value: number): string {
  if (value <= 0) return "正在测速";
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB/s`;
  return `${Math.max(value / 1024, 0.1).toFixed(1)} KB/s`;
}

function formatEta(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "计算中";
  const seconds = Math.max(Math.ceil(value), 0);
  if (seconds < 60) return `约 ${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `约 ${minutes} 分 ${remainder} 秒`;
}

export function useSubmissionUploadDialog(onQueued: (job: SubmissionProcessingJob) => void) {
  const [state, setState] = useState<UploadDialogState>({
    open: false,
    phase: "preparing",
    fileName: "",
    fileSize: 0,
    progress: EMPTY_PROGRESS,
    error: "",
  });
  const controllerRef = useRef<AbortController | null>(null);
  const retryRef = useRef<{ file: File; starter: UploadStarter } | null>(null);

  const start = useCallback(async (file: File, starter: UploadStarter) => {
    const controller = new AbortController();
    controllerRef.current = controller;
    retryRef.current = { file, starter };
    setState({
      open: true,
      phase: "preparing",
      fileName: file.name,
      fileSize: file.size,
      progress: { ...EMPTY_PROGRESS, total: file.size },
      error: "",
    });
    try {
      const job = await starter({
        signal: controller.signal,
        onProgress: (progress) => {
          setState((current) => ({
            ...current,
            phase: progress.phase,
            progress,
          }));
        },
      });
      controllerRef.current = null;
      onQueued(job);
      setState((current) => ({
        ...current,
        phase: "success",
        progress: { ...current.progress, phase: "confirming", loaded: file.size, percent: 100 },
      }));
    } catch (error) {
      controllerRef.current = null;
      const cancelled = error instanceof DOMException && error.name === "AbortError";
      setState((current) => ({
        ...current,
        phase: cancelled ? "cancelled" : "error",
        error: cancelled ? "上传已取消，当前投稿未发生变化。" : error instanceof Error ? error.message : "上传失败",
      }));
    }
  }, [onQueued]);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
  }, []);

  const retry = useCallback(() => {
    const current = retryRef.current;
    if (current) void start(current.file, current.starter);
  }, [start]);

  const close = useCallback(() => {
    if (state.phase === "preparing" || state.phase === "uploading" || state.phase === "confirming") return;
    setState((current) => ({ ...current, open: false }));
  }, [state.phase]);

  return {
    start,
    dialog: (
      <SubmissionUploadDialog
        state={state}
        onCancel={cancel}
        onRetry={retry}
        onClose={close}
      />
    ),
  };
}

function SubmissionUploadDialog({
  state,
  onCancel,
  onRetry,
  onClose,
}: {
  state: UploadDialogState;
  onCancel: () => void;
  onRetry: () => void;
  onClose: () => void;
}) {
  const active = state.phase === "preparing" || state.phase === "uploading" || state.phase === "confirming";
  const cancellable = state.phase === "preparing" || state.phase === "uploading";
  const success = state.phase === "success";
  const percent = Math.round(state.progress.percent);
  return (
    <Dialog
      open={state.open}
      onClose={active ? undefined : onClose}
      fullWidth
      maxWidth="sm"
      aria-labelledby="submission-upload-title"
    >
      <DialogTitle
        id="submission-upload-title"
        sx={{
          pb: 1.5,
          background: success
            ? "linear-gradient(135deg, rgba(22,101,52,.16), rgba(34,197,94,.05))"
            : "linear-gradient(135deg, rgba(20,83,45,.12), transparent)",
        }}
      >
        <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
          {success ? <CheckCircle2 size={24} /> : <UploadCloud size={24} />}
          <Box>
            <Typography component="div" variant="h3">
              {success ? "压缩包上传成功" : state.phase === "confirming" ? "正在确认 R2 文件" : "上传投稿压缩包"}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>
              {state.fileName}
            </Typography>
          </Box>
        </Stack>
      </DialogTitle>
      <DialogContent dividers sx={{ py: 2.5 }}>
        {success ? (
          <Alert severity="success" icon={<CheckCircle2 size={20} />}>
            压缩包已保存至 R2。服务器会在后台继续校验谱面，并准备在线预览和谱面下载公开包。你现在可以关闭此页面，处理结果会保留在投稿卡片中。
          </Alert>
        ) : state.phase === "error" || state.phase === "cancelled" ? (
          <Alert severity={state.phase === "cancelled" ? "info" : "error"}>{state.error}</Alert>
        ) : (
          <Stack spacing={2.25}>
            <Box
              sx={{
                p: 2,
                borderRadius: 2,
                border: 1,
                borderColor: "divider",
                bgcolor: "background.default",
                position: "relative",
                overflow: "hidden",
                "&::after": {
                  content: '""',
                  position: "absolute",
                  inset: 0,
                  pointerEvents: "none",
                  background: "linear-gradient(90deg, transparent, rgba(34,197,94,.07), transparent)",
                  transform: `translateX(${Math.min(percent, 100) - 100}%)`,
                },
              }}
            >
              <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "baseline" }}>
                <Typography variant="caption" color="text.secondary">
                  {state.phase === "preparing" ? "申请安全上传通道" : state.phase === "confirming" ? "校验对象完整性" : "浏览器 → 私有 R2"}
                </Typography>
                <Typography sx={{ fontSize: "2rem", lineHeight: 1, fontWeight: 850, fontVariantNumeric: "tabular-nums" }}>
                  {state.phase === "preparing" ? "—" : `${percent}%`}
                </Typography>
              </Stack>
              <LinearProgress
                variant={state.phase === "preparing" || state.phase === "confirming" ? "indeterminate" : "determinate"}
                value={state.progress.percent}
                aria-label="投稿上传进度"
                sx={{ mt: 1.75, height: 8, borderRadius: 99 }}
              />
            </Box>
            <Box sx={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 1 }}>
              {[
                ["已上传", `${formatMB(state.progress.loaded)} / ${formatMB(state.fileSize)}`],
                ["当前速度", formatRate(state.progress.bytesPerSecond)],
                ["预计剩余", formatEta(state.progress.etaSeconds)],
              ].map(([label, value]) => (
                <Box key={label} sx={{ minWidth: 0 }}>
                  <Typography variant="caption" color="text.secondary">{label}</Typography>
                  <Typography variant="body2" sx={{ fontWeight: 750, fontVariantNumeric: "tabular-nums", overflowWrap: "anywhere" }}>
                    {value}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {cancellable ? (
          <Button color="inherit" startIcon={<X size={16} />} onClick={onCancel}>取消上传</Button>
        ) : state.phase === "error" || state.phase === "cancelled" ? (
          <>
            <Button color="inherit" onClick={onClose}>关闭</Button>
            <Button variant="contained" startIcon={<RotateCcw size={16} />} onClick={onRetry}>重新上传</Button>
          </>
        ) : success ? (
          <Button variant="contained" onClick={onClose}>知道了</Button>
        ) : null}
      </DialogActions>
    </Dialog>
  );
}
