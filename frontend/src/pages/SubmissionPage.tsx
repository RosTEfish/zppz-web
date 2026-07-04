import { useState } from "react";
import { Alert, Box, Button, Card, CardContent, Chip, FormControlLabel, IconButton, Paper, Snackbar, Stack, Switch, Tooltip, Typography } from "@mui/material";
import { Check, RefreshCw, Trash2, Upload } from "lucide-react";
import { api, formatMB, formatTime, type SubmissionTargetRead, type Track } from "../api/v1";
import { PageHeader, ResourceState, useResource } from "../components/PagePrimitives";
import { useAuth } from "../contexts/AuthContext";


export default function SubmissionPage() {
  const targets = useResource(api.submissionTargets, []);
  const [trackChoices, setTrackChoices] = useState<Record<number, Track>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const { user } = useAuth();
  if (user?.identity !== "participant") return <Stack spacing={3}><PageHeader icon={Upload} title="投稿" /><Alert severity="info">仅参赛者账号开放谱面投稿。</Alert></Stack>;

  function choice(target: SubmissionTargetRead): Track { return trackChoices[target.song.id] || target.submission?.track || "normal"; }
  function chooseTrack(songId: number, nextTrack: Track) {
    setTrackChoices((current) => {
      if (nextTrack === "normal") return { ...current, [songId]: "normal" };
      return Object.fromEntries(
        (targets.data?.targets || []).map((target) => [target.song.id, target.song.id === songId ? "j" : "normal"]),
      );
    });
  }
  async function changeTrack(target: SubmissionTargetRead, nextTrack: Track) {
    if (!target.submission || target.submission.track === nextTrack) return;
    setBusyId(target.song.id); setError("");
    try {
      await api.updateSubmissionTrack(target.submission.id, nextTrack);
      setMessage(nextTrack === "j" ? "已切换为 J 赛道" : "已切换为普通赛道");
      await targets.reload();
      setTrackChoices({});
    } catch (err) {
      setTrackChoices({});
      await targets.reload();
      setError(err instanceof Error ? err.message : "赛道切换失败");
    } finally { setBusyId(null); }
  }
  async function upload(target: SubmissionTargetRead, file?: File) {
    if (!file) return;
    setBusyId(target.song.id); setError("");
    try {
      if (target.submission) await api.replaceSubmission(target.submission.id, choice(target), file);
      else await api.uploadSubmission(target.song.id, choice(target), file);
      setMessage(target.submission ? "投稿已替换" : "投稿已上传");
      await targets.reload();
      setTrackChoices({});
    } catch (err) { setError(err instanceof Error ? err.message : "上传失败"); } finally { setBusyId(null); }
  }
  async function remove(target: SubmissionTargetRead) {
    if (!target.submission || !window.confirm(`确认删除《${target.song.song_name}》的投稿？`)) return;
    setBusyId(target.song.id);
    try { await api.deleteSubmission(target.submission.id); await targets.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } finally { setBusyId(null); }
  }

  return (
    <Stack spacing={3}>
      <PageHeader icon={Upload} title="候选投稿" meta={`${targets.data?.targets.filter((item) => item.submission).length ?? 0} / ${targets.data?.targets.length ?? 0} 已完成`} />
      {targets.data && !targets.data.is_open ? <Alert severity="warning">抽签阶段尚未结束，投稿入口暂未开放。</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      <ResourceState loading={targets.loading} error={targets.error} empty={targets.data && !targets.data.targets.length ? "没有可投稿的候选曲目" : undefined} />
      {targets.data?.targets.length ? (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
          {targets.data.targets.map((target) => {
            const submitted = target.submission;
            const selectedTrack = choice(target);
            return (
              <Card variant="outlined" key={target.song.id}>
                <CardContent>
                  <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
                    <Box sx={{ minWidth: 0 }}>
                      <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}>
                        <Typography variant="h3" sx={{ overflowWrap: "anywhere" }}>{target.song.song_name}</Typography>
                        <Chip size="small" color={target.source_kind === "self" ? "primary" : "secondary"} label={target.source_kind === "self" ? "自选" : "抽中"} />
                      </Stack>
                      <Typography color="text.secondary" sx={{ mt: 0.5 }}>{target.song.artist}</Typography>
                    </Box>
                    {submitted ? <Chip size="small" color="success" icon={<Check size={14} />} label="已投稿" /> : <Chip size="small" variant="outlined" label="待投稿" />}
                  </Stack>
                  {submitted ? <Paper variant="outlined" sx={{ p: 1.5, mt: 2, bgcolor: "background.default" }}><Typography variant="body2" noWrap title={submitted.file_name} sx={{ fontWeight: 650 }}>{submitted.file_name}</Typography><Typography variant="caption" color="text.secondary">{formatMB(submitted.file_size)} · {formatTime(submitted.created_at)}</Typography></Paper> : null}
                  <Stack direction={{ xs: "column", sm: "row" }} sx={{ mt: 2, alignItems: { xs: "stretch", sm: "center" }, justifyContent: "space-between", gap: 1.5 }}>
                    <FormControlLabel control={<Switch checked={selectedTrack === "j"} onChange={(e) => { const nextTrack = e.target.checked ? "j" : "normal"; chooseTrack(target.song.id, nextTrack); if (submitted) void changeTrack(target, nextTrack); }} disabled={!targets.data?.is_open || busyId !== null} />} label="J 赛道" />
                    <Stack direction="row" spacing={1}>
                      <Button component="label" variant={submitted ? "outlined" : "contained"} startIcon={submitted ? <RefreshCw size={16} /> : <Upload size={16} />} disabled={!targets.data?.is_open || busyId === target.song.id}>{submitted ? "替换" : "上传"}<input hidden type="file" accept=".zip,.7z,.rar" onChange={(event) => { void upload(target, event.target.files?.[0]); event.currentTarget.value = ""; }} /></Button>
                      {submitted ? <Tooltip title="删除"><IconButton color="error" disabled={!targets.data?.is_open || busyId === target.song.id} onClick={() => void remove(target)}><Trash2 size={18} /></IconButton></Tooltip> : null}
                    </Stack>
                  </Stack>
                </CardContent>
              </Card>
            );
          })}
        </Box>
      ) : null}
      <Snackbar open={Boolean(message)} autoHideDuration={2500} onClose={() => setMessage("")} message={message} />
    </Stack>
  );
}
