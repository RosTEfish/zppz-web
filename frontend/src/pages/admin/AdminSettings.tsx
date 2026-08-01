import { useEffect, useState } from "react";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Stack, TextField, Typography } from "@mui/material";
import { Save, Trash2 } from "lucide-react";
import { useSnackbar } from "notistack";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import { api, type AdminResetResponse, type EventUpdatePayload } from "../../api/v1";
import { LoadingBlock } from "../../components/PagePrimitives";
import { useAuth } from "../../contexts/AuthContext";
import { useConfig } from "../../contexts/ConfigContext";
import { eventSettingsSchema, resetConfirmationSchema } from "../../forms/schemas";

type ResetForm = { confirmation: string };

export default function AdminSettings() {
  const { enqueueSnackbar } = useSnackbar();
  const { event, refreshConfig } = useConfig();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [resetOpen, setResetOpen] = useState(false);
  const [resetError, setResetError] = useState("");
  const [resetResult, setResetResult] = useState<AdminResetResponse | null>(null);
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<EventUpdatePayload>({ resolver: zodResolver(eventSettingsSchema) });
  const resetForm = useForm<ResetForm>({ resolver: zodResolver(resetConfirmationSchema), mode: "onChange", defaultValues: { confirmation: "" } });
  const resetReady = resetForm.watch("confirmation") === "清除全部数据";

  useEffect(() => {
    if (!event) return;
    reset({
      name: event.name,
      participant_song_limit: event.settings.participant_song_limit,
      audience_song_limit: event.settings.audience_song_limit,
      draw_songs_per_participant: event.settings.draw_songs_per_participant,
      true_love_vote_limit_below_14: event.settings.true_love_vote_limit_below_14,
      true_love_vote_limit_at_least_14: event.settings.true_love_vote_limit_at_least_14,
      funny_vote_limit: event.settings.funny_vote_limit,
      announcement_text: event.settings.announcement_text,
    });
  }, [event, reset]);

  if (!event) return <LoadingBlock />;

  const save = handleSubmit(async (form) => {
    setError("");
    try {
      await api.updateEvent(form);
      await refreshConfig();
      reset(form);
      enqueueSnackbar("赛事设置已保存", { variant: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  });

  const resetAll = resetForm.handleSubmit(async ({ confirmation }) => {
    setResetError("");
    try {
      setResetResult(await api.resetAllData(confirmation));
      resetForm.reset();
    } catch (err) {
      setResetError(err instanceof Error ? err.message : "清除失败");
    }
  });

  async function finishReset() {
    await logout();
    navigate("/login", { replace: true });
  }

  const numberField = (name: keyof EventUpdatePayload, label: string, min: number, max: number) => (
    <TextField type="number" label={label} {...register(name, { valueAsNumber: true })} error={Boolean(errors[name])} helperText={errors[name]?.message} slotProps={{ htmlInput: { min, max } }} />
  );

  return <>
    <Paper component="form" onSubmit={save} noValidate variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}>
        <TextField label="赛事名称" {...register("name")} error={Boolean(errors.name)} helperText={errors.name?.message} />
        {numberField("participant_song_limit", "参赛者曲目上限", 0, 50)}
        {numberField("audience_song_limit", "观众曲目上限", 0, 50)}
        {numberField("draw_songs_per_participant", "每人抽取曲目数", 1, 10)}
        {numberField("true_love_vote_limit_below_14", "14 以下真爱票上限", 0, 50)}
        {numberField("true_love_vote_limit_at_least_14", "14 及以上真爱票上限", 0, 50)}
        {numberField("funny_vote_limit", "欢乐票上限", 0, 50)}
        <TextField label="公告（Markdown）" multiline minRows={5} {...register("announcement_text")} error={Boolean(errors.announcement_text)} helperText={errors.announcement_text?.message} sx={{ gridColumn: { md: "1 / -1" } }} />
      </Box>
      {error ? <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert> : null}
      <Button type="submit" variant="contained" disabled={isSubmitting} startIcon={<Save size={17} />} sx={{ mt: 2 }}>{isSubmitting ? "保存中…" : "保存设置"}</Button>
    </Paper>
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, mt: 2, borderColor: "error.main", borderTopWidth: 3 }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
        <Box><Typography variant="h3" color="error.main">危险操作</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>清除全部赛事和普通用户数据，保留管理员与公共资源。操作不可撤销，完成后所有账号都需要重新登录。</Typography></Box>
        <Button color="error" variant="contained" startIcon={<Trash2 size={17} />} onClick={() => { setResetError(""); setResetResult(null); resetForm.reset(); setResetOpen(true); }}>清除全部数据</Button>
      </Stack>
    </Paper>
    <Dialog open={resetOpen} onClose={resetForm.formState.isSubmitting || resetResult ? undefined : () => setResetOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>{resetResult ? "清除完成" : "确认清除全部数据"}</DialogTitle>
      <DialogContent>{resetResult ? <Stack spacing={2}><Alert severity="success">{resetResult.message}</Alert><Typography variant="body2">当前赛事“{resetResult.event_name}”已保留，赛事 ID 为 {resetResult.event_id}。</Typography>{resetResult.file_cleanup_warnings.length ? <Alert severity="warning">{resetResult.file_cleanup_warnings.join("；")}</Alert> : <Alert severity="info">赛事上传文件和猜谱文件已清理，公共资源已保留。</Alert>}</Stack> : <Stack spacing={2}><Alert severity="error">这会删除所有赛事数据、投稿、抽签、换曲、猜谱、投票、评论和普通用户账号，并注销所有登录会话。此操作无法撤销。</Alert><TextField autoFocus fullWidth label="输入确认词" helperText={resetForm.formState.errors.confirmation?.message ?? "请输入：清除全部数据"} {...resetForm.register("confirmation")} disabled={resetForm.formState.isSubmitting} error={Boolean(resetForm.formState.errors.confirmation || resetError)} />{resetError ? <Alert severity="error">{resetError}</Alert> : null}</Stack>}</DialogContent>
      <DialogActions>{resetResult ? <Button variant="contained" onClick={() => void finishReset()}>重新登录</Button> : <><Button disabled={resetForm.formState.isSubmitting} onClick={() => setResetOpen(false)}>取消</Button><Button color="error" variant="contained" disabled={!resetReady || resetForm.formState.isSubmitting} onClick={() => void resetAll()}>{resetForm.formState.isSubmitting ? "清除中…" : "确认清除"}</Button></>}</DialogActions>
    </Dialog>
  </>;
}
