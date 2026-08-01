import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  FormControlLabel,
  IconButton,
  Paper,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import { useConfirm } from "material-ui-confirm";
import { useSnackbar } from "notistack";
import {
  Check,
  Clock3,
  Eye,
  FileCheck2,
  Film,
  LoaderCircle,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import {
  api,
  formatDuration,
  formatMB,
  formatTime,
  type StoredFileRead,
  type SubmissionProcessingJob,
  type SubmissionTargetRead,
  type Track,
} from "../api/v1";
import { ChartPreviewDialog } from "../components/ChartPreviewDialog";
import { PageHeader, ResourceState, useApiResource } from "../components/PagePrimitives";
import { queryKeys } from "../api/queryKeys";
import { useSubmissionUploadDialog } from "../components/SubmissionUploadDialog";
import Stage2SwapPanel from "../components/Stage2SwapPanel";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";

const STAGE_LABELS: Record<SubmissionProcessingJob["stage"], string> = {
  uploaded: "等待校验",
  validating: "校验谱面",
  accepted: "投稿已接收",
  preview_core: "准备静态预览",
  public_package: "生成公开包",
  video: "准备视频",
  cleanup: "清理旧资源",
  complete: "处理完成",
};

export default function SubmissionPage() {
  return (
    <Stack spacing={3}>
      <SubmissionPageContent />
      <Stage2SwapPanel />
    </Stack>
  );
}

function SubmissionPageContent() {
  const confirm = useConfirm();
  const { enqueueSnackbar } = useSnackbar();
  const targets = useApiResource(queryKeys.submissions.targets, api.submissionTargets);
  const submissions = useApiResource(queryKeys.submissions.mine, api.mySubmissions);
  const processingJobs = useApiResource(queryKeys.submissions.jobs, api.submissionProcessingJobs);
  const [trackChoices, setTrackChoices] = useState<Record<number, Track>>({});
  const [banAcknowledgements, setBanAcknowledgements] = useState<Record<number, boolean>>({});
  const [busyId, setBusyId] = useState<number | "exhibition" | null>(null);
  const [error, setError] = useState("");
  const [previewFile, setPreviewFile] = useState<StoredFileRead | null>(null);
  const { user } = useAuth();
  const { refreshGuessAvailability } = useConfig();

  const handleQueued = useCallback(
    (job: SubmissionProcessingJob) => {
      processingJobs.setData((current) => [
        job,
        ...(current ?? []).filter(
          (item) =>
            item.id !== job.id &&
            !(
              (job.replace_submission_id !== null &&
                item.replace_submission_id === job.replace_submission_id) ||
              (job.replace_submission_id === null &&
                job.source_song_id !== null &&
                item.replace_submission_id === null &&
                item.source_song_id === job.source_song_id) ||
              (job.replace_submission_id === null &&
                job.source_song_id === null &&
                item.replace_submission_id === null &&
                item.source_song_id === null &&
                item.status === "failed")
            ),
        ),
      ]);
    },
    [processingJobs.setData],
  );
  const uploadDialog = useSubmissionUploadDialog(handleQueued);
  const hasActiveJobs =
    processingJobs.data?.some((job) => job.status === "queued" || job.status === "processing") ?? false;

  useEffect(() => {
    if (!hasActiveJobs) return;
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      void Promise.all([
        processingJobs.reload(),
        targets.reload(),
        submissions.reload(),
        refreshGuessAvailability().catch(() => undefined),
      ]);
    };
    const timer = window.setInterval(refresh, 3000);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [
    hasActiveJobs,
    processingJobs.reload,
    refreshGuessAvailability,
    submissions.reload,
    targets.reload,
  ]);

  if (user?.identity !== "participant") {
    return (
      <Stack spacing={3}>
        <PageHeader icon={Upload} title="投稿" />
        <Alert severity="info">仅参赛者账号开放谱面投稿。</Alert>
      </Stack>
    );
  }

  const exhibitions = submissions.data?.filter((item) => item.track === "exhibition") ?? [];
  const jobs = processingJobs.data ?? [];
  const exhibitionJobs = jobs.filter(
    (job) => job.source_song_id === null && job.replace_submission_id === null,
  );

  function choice(target: SubmissionTargetRead): Track {
    return trackChoices[target.song.id] || target.submission?.track || "normal";
  }

  function chooseTrack(songId: number, nextTrack: Track) {
    setTrackChoices((current) =>
      nextTrack === "j"
        ? Object.fromEntries(
            (targets.data?.targets || []).map((target) => [
              target.song.id,
              target.song.id === songId ? "j" : "normal",
            ]),
          )
        : { ...current, [songId]: "normal" },
    );
  }

  function storeSubmission(next: StoredFileRead, songId?: number) {
    submissions.updateData((items) => {
      const exists = items.some((item) => item.id === next.id);
      return exists ? items.map((item) => (item.id === next.id ? next : item)) : [next, ...items];
    });
    if (songId !== undefined) {
      targets.updateData((current) => ({
        ...current,
        targets: current.targets.map((target) =>
          target.song.id === songId ? { ...target, submission: next } : target,
        ),
      }));
    }
  }

  async function changeTrack(target: SubmissionTargetRead, nextTrack: Track) {
    if (!target.submission || target.submission.track === nextTrack) return;
    setBusyId(target.song.id);
    setError("");
    try {
      const updated = await api.updateSubmissionTrack(target.submission.id, nextTrack);
      storeSubmission(updated, target.song.id);
      enqueueSnackbar(nextTrack === "j" ? "已切换为 J 投稿" : "已切换为普通投稿", { variant: "success" });
      await refreshGuessAvailability();
      setTrackChoices({});
    } catch (err) {
      setTrackChoices({});
      setError(err instanceof Error ? err.message : "类型切换失败");
    } finally {
      setBusyId(null);
    }
  }

  async function upload(target: SubmissionTargetRead, file?: File) {
    if (!file) return;
    setBusyId(target.song.id);
    setError("");
    const acknowledged = banAcknowledgements[target.song.id] ?? false;
    try {
      await uploadDialog.start(file, (options) =>
        target.submission
          ? api.replaceSubmission(target.submission.id, choice(target), file, acknowledged, options)
          : api.uploadSubmission(target.song.id, choice(target), file, acknowledged, options),
      );
      setTrackChoices({});
    } finally {
      setBusyId(null);
    }
  }

  async function uploadExhibition(file?: File) {
    if (!file) return;
    setBusyId("exhibition");
    setError("");
    try {
      await uploadDialog.start(file, (options) => api.uploadExhibition(file, false, options));
    } finally {
      setBusyId(null);
    }
  }

  async function remove(file: StoredFileRead, songId?: number) {
    const result = await confirm({ title: "删除投稿", description: `确认删除“${file.file_name}”？此操作不可撤销。`, confirmationButtonProps: { color: "error" } });
    if (!result.confirmed) return;
    setBusyId(songId ?? "exhibition");
    try {
      await api.deleteSubmission(file.id);
      submissions.updateData((items) => items.filter((item) => item.id !== file.id));
      if (songId !== undefined) {
        targets.updateData((current) => ({
          ...current,
          targets: current.targets.map((target) =>
            target.song.id === songId ? { ...target, submission: null } : target,
          ),
        }));
      }
      await refreshGuessAvailability();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Stack spacing={3}>
      <PageHeader
        icon={Upload}
        title="投稿"
        meta={`${targets.data?.targets.filter((item) => item.submission).length ?? 0} 个正赛 / J 投稿，${exhibitions.length} 个场外投稿`}
      />
      {targets.data && !targets.data.is_open ? (
        <Alert severity="warning">当前阶段未开放普通与 J 投稿。</Alert>
      ) : null}
      {error ? <Alert severity="error" aria-live="polite">{error}</Alert> : null}
      <ResourceState
        loading={
          (targets.loading && targets.data === null) ||
          (processingJobs.loading && processingJobs.data === null)
        }
        error={targets.error || processingJobs.error}
      />
      {targets.data?.targets.length ? (
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" },
            gap: 2,
          }}
        >
          {targets.data.targets.map((target) => {
            const job = jobs.find(
              (candidate) =>
                candidate.replace_submission_id === target.submission?.id ||
                (candidate.replace_submission_id === null &&
                  candidate.source_song_id === target.song.id),
            );
            return (
              <SubmissionCard
                key={target.song.id}
                target={target}
                job={job}
                selectedTrack={choice(target)}
                banAcknowledged={banAcknowledgements[target.song.id] ?? false}
                onBanAcknowledged={(checked) =>
                  setBanAcknowledgements((current) => ({
                    ...current,
                    [target.song.id]: checked,
                  }))
                }
                disabled={!targets.data?.is_open || busyId !== null || Boolean(job && job.status !== "failed")}
                busy={busyId === target.song.id}
                onTrack={(track) => {
                  chooseTrack(target.song.id, track);
                  if (target.submission) void changeTrack(target, track);
                }}
                onUpload={(file) => void upload(target, file)}
                onPreview={() => target.submission && setPreviewFile(target.submission)}
                onRemove={() =>
                  target.submission && void remove(target.submission, target.song.id)
                }
              />
            );
          })}
        </Box>
      ) : null}

      <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, borderStyle: "dashed" }}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
        >
          <Box>
            <Typography variant="h3">场外投稿</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              校验通过后公开，预览与下载资源将在后台准备；数量不限，不参与作者竞猜。
            </Typography>
          </Box>
          <Button
            component="label"
            variant="contained"
            startIcon={<Upload size={16} />}
            disabled={!targets.data?.is_open || busyId !== null}
          >
            {busyId === "exhibition" ? "正在上传…" : "上传场外包"}
            <input
              hidden
              type="file"
              accept=".zip,.7z,.rar"
              onChange={(event) => {
                void uploadExhibition(event.target.files?.[0]);
                event.currentTarget.value = "";
              }}
            />
          </Button>
        </Stack>
        {exhibitionJobs.map((job) => <ProcessingJobNotice key={job.id} job={job} />)}
        {exhibitions.length ? (
          <Stack spacing={1} sx={{ mt: 2 }}>
            {exhibitions.map((file) => (
              <FileSummary
                key={file.id}
                file={file}
                actions={
                  <Stack direction="row">
                    <Tooltip title="在线预览">
                      <span>
                        <IconButton
                          aria-label={`预览 ${file.file_name}`}
                          disabled={file.preview_status !== "ready"}
                          onClick={() => setPreviewFile(file)}
                        >
                          <Eye size={17} />
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title="删除场外投稿">
                      <IconButton
                        aria-label={`删除 ${file.file_name}`}
                        color="error"
                        disabled={busyId !== null}
                        onClick={() => void remove(file)}
                      >
                        <Trash2 size={17} />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                }
              />
            ))}
          </Stack>
        ) : null}
      </Paper>

      <ChartPreviewDialog
        open={Boolean(previewFile)}
        source="submission"
        sourceId={previewFile?.id ?? null}
        title={previewFile?.file_name ?? "投稿"}
        onClose={() => setPreviewFile(null)}
        onDownload={() =>
          previewFile ? api.downloadSubmission(previewFile.id) : Promise.resolve()
        }
      />
      {uploadDialog.dialog}
    </Stack>
  );
}

function SubmissionCard({
  target,
  job,
  selectedTrack,
  banAcknowledged,
  onBanAcknowledged,
  disabled,
  busy,
  onTrack,
  onUpload,
  onPreview,
  onRemove,
}: {
  target: SubmissionTargetRead;
  job?: SubmissionProcessingJob;
  selectedTrack: Track;
  banAcknowledged: boolean;
  onBanAcknowledged: (checked: boolean) => void;
  disabled: boolean;
  busy: boolean;
  onTrack: (track: "normal" | "j") => void;
  onUpload: (file?: File) => void;
  onPreview: () => void;
  onRemove: () => void;
}) {
  const submitted = target.submission;
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack
          direction="row"
          sx={{ justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}
        >
          <Box sx={{ minWidth: 0 }}>
            <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}>
              <Typography variant="h3" sx={{ overflowWrap: "anywhere" }}>
                {target.song.song_name}
              </Typography>
              <Chip
                size="small"
                color={target.source_kind === "self" ? "primary" : "secondary"}
                label={target.source_kind === "self" ? "自选" : "抽中"}
              />
            </Stack>
            <Typography color="text.secondary" sx={{ mt: 0.5 }}>{target.song.artist}</Typography>
          </Box>
          {submitted ? (
            <Chip size="small" color="success" icon={<Check size={14} />} label="已投稿" />
          ) : (
            <Chip size="small" variant="outlined" label={job ? "后台处理中" : "待投稿"} />
          )}
        </Stack>
        <FormControlLabel
          control={
            <Checkbox
              size="small"
              checked={banAcknowledged}
              onChange={(event) => onBanAcknowledged(event.target.checked)}
            />
          }
          label="若查重提示疑似 Ban，确认这不是同一首曲目"
          sx={{ mt: 1, alignItems: "flex-start" }}
        />
        {job ? <ProcessingJobNotice job={job} replacing={Boolean(submitted)} /> : null}
        {submitted ? <FileSummary file={submitted} /> : null}
        <Stack
          direction={{ xs: "column", sm: "row" }}
          sx={{
            mt: 2,
            alignItems: { xs: "stretch", sm: "center" },
            justifyContent: "space-between",
            gap: 1.5,
          }}
        >
          <ToggleButtonGroup
            size="small"
            exclusive
            value={selectedTrack}
            aria-label="投稿赛道"
            sx={{
              width: { xs: "100%", sm: 224 },
              "& .MuiToggleButton-root": { flex: 1, minWidth: 0 },
            }}
            onChange={(_, value: "normal" | "j" | null) => {
              if (value) onTrack(value);
            }}
          >
            <ToggleButton value="normal">普通赛道</ToggleButton>
            <ToggleButton value="j">J赛道</ToggleButton>
          </ToggleButtonGroup>
          <Stack direction="row" spacing={1}>
            {submitted ? (
              <Button
                variant="outlined"
                startIcon={<Eye size={16} />}
                disabled={submitted.preview_status !== "ready"}
                onClick={onPreview}
              >
                预览
              </Button>
            ) : null}
            <Button
              component="label"
              variant={submitted ? "outlined" : "contained"}
              startIcon={submitted ? <RefreshCw size={16} /> : <Upload size={16} />}
              disabled={disabled}
            >
              {busy ? "正在上传…" : job?.status === "failed" ? "重新选择文件" : submitted ? "替换" : "上传"}
              <input
                hidden
                type="file"
                accept=".zip,.7z,.rar"
                onChange={(event) => {
                  onUpload(event.target.files?.[0]);
                  event.currentTarget.value = "";
                }}
              />
            </Button>
            {submitted ? (
              <Tooltip title="删除">
                <IconButton
                  aria-label={`删除 ${target.song.song_name} 投稿`}
                  color="error"
                  disabled={disabled}
                  onClick={onRemove}
                >
                  <Trash2 size={18} />
                </IconButton>
              </Tooltip>
            ) : null}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

function ProcessingJobNotice({
  job,
  replacing = false,
}: {
  job: SubmissionProcessingJob;
  replacing?: boolean;
}) {
  const failed = job.status === "failed";
  const stages: SubmissionProcessingJob["stage"][] = [
    "uploaded",
    "validating",
    "accepted",
    "preview_core",
    "public_package",
    "video",
    "cleanup",
    "complete",
  ];
  const currentStage = stages.indexOf(job.stage);
  const visibleStages: Array<[SubmissionProcessingJob["stage"], string]> = [
    ["validating", "校验"],
    ["preview_core", "静态预览"],
    ["public_package", "公开包"],
    ["video", "视频"],
  ];
  return (
    <Alert
      severity={failed ? "error" : "info"}
      icon={failed ? undefined : (
        <Box
          sx={{
            display: "grid",
            "@keyframes submission-job-spin": { to: { transform: "rotate(360deg)" } },
            animation: "submission-job-spin 1.2s linear infinite",
          }}
        >
          <LoaderCircle size={19} />
        </Box>
      )}
      sx={{ mt: 2 }}
    >
      <Typography variant="body2" sx={{ fontWeight: 750 }}>
        {failed ? "后台校验失败" : replacing ? "新版本正在处理" : "后台处理中"}
        {!failed ? ` · ${STAGE_LABELS[job.stage]}` : ""}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {job.file_name} · {formatMB(job.file_size)} · {job.message}
      </Typography>
      {!failed ? (
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ mt: 1, flexWrap: "wrap" }}>
          {visibleStages.map(([stage, label]) => {
            const targetStage = stages.indexOf(stage);
            const completed = currentStage > targetStage;
            const active = currentStage === targetStage;
            return (
              <Chip
                key={stage}
                size="small"
                color={completed ? "success" : active ? "info" : "default"}
                variant={completed || active ? "filled" : "outlined"}
                label={`${completed ? "✓ " : active ? "• " : ""}${label}`}
              />
            );
          })}
        </Stack>
      ) : null}
    </Alert>
  );
}

function FileSummary({ file, actions }: { file: StoredFileRead; actions?: React.ReactNode }) {
  const checks = file.validation;
  const packageStatus = file.public_package_status ?? (file.public_package_ready ? "ready" : "processing");
  return (
    <Paper variant="outlined" sx={{ p: 1.5, mt: 2, bgcolor: "background.default" }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" noWrap title={file.file_name} sx={{ fontWeight: 700 }}>
            {file.file_name}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {formatMB(file.file_size)} · {formatTime(file.created_at)}
          </Typography>
        </Box>
        {actions}
      </Stack>
      <Stack direction="row" spacing={1} useFlexGap sx={{ mt: 1, flexWrap: "wrap", alignItems: "center" }}>
        <Chip size="small" icon={<Clock3 size={13} />} label={formatDuration(file.track_duration_seconds)} />
        <Chip
          size="small"
          color={packageStatus === "ready" ? "success" : packageStatus === "failed" ? "error" : "default"}
          icon={<FileCheck2 size={13} />}
          label={
            packageStatus === "ready"
              ? "公开包就绪"
              : packageStatus === "failed"
                ? "公开包失败"
                : "公开包处理中"
          }
        />
        <Chip
          size="small"
          color={
            file.preview_status === "ready"
              ? "success"
              : file.preview_status === "failed"
                ? "error"
                : file.preview_status === "unsupported"
                  ? "warning"
                  : "default"
          }
          icon={<Eye size={13} />}
          label={
            file.preview_status === "ready"
              ? "预览就绪"
              : file.preview_status === "failed"
                ? "预览失败"
                : file.preview_status === "unsupported"
                  ? "格式暂不支持预览"
                  : "预览处理中"
          }
        />
        <Chip
          size="small"
          color={file.video_status === "ready" ? "success" : file.video_status === "failed" ? "warning" : "default"}
          icon={<Film size={13} />}
          label={
            file.video_status === "ready"
              ? "视频就绪"
              : file.video_status === "processing"
                ? "视频处理中"
                : file.video_status === "failed"
                  ? "视频失败，使用静态背景"
                  : "无视频"
          }
        />
        {checks
          ? Object.entries({
              maidata: "maidata",
              track: "track",
              background: "背景",
              duration: "时长",
            }).map(([key, label]) => (
              <Chip
                key={key}
                size="small"
                variant="outlined"
                color={checks[key as keyof typeof checks] ? "success" : "error"}
                label={`${label} ${checks[key as keyof typeof checks] ? "✓" : "×"}`}
              />
            ))
          : null}
      </Stack>
      {file.public_package_message ? (
        <Typography variant="caption" color="error.main" sx={{ display: "block", mt: 1 }}>
          {file.public_package_message}
        </Typography>
      ) : null}
      {file.preview_message && file.preview_status !== "ready" ? (
        <Typography variant="caption" color="warning.main" sx={{ display: "block", mt: 0.5 }}>
          {file.preview_message}
        </Typography>
      ) : null}
      {file.video_message ? (
        <Typography variant="caption" color="warning.main" sx={{ display: "block", mt: 0.5 }}>
          {file.video_message}
        </Typography>
      ) : null}
    </Paper>
  );
}
