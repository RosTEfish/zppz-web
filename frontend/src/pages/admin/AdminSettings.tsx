import { useEffect, useState } from "react";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Stack, TextField, Typography } from "@mui/material";
import { Archive, Save, Trash2 } from "lucide-react";
import { useSnackbar } from "notistack";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router-dom";
import { api, type AdminResetResponse, type EventRotateResponse, type EventUpdatePayload } from "../../api/v1";
import { LoadingBlock } from "../../components/PagePrimitives";
import { useAuth } from "../../contexts/AuthContext";
import { useConfig } from "../../contexts/ConfigContext";
import { eventRotateSchema, eventSettingsSchema, resetConfirmationSchema, type EventRotateFormValues } from "../../forms/schemas";

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
  const [rotateOpen, setRotateOpen] = useState(false);
  const [rotateError, setRotateError] = useState("");
  const [rotateResult, setRotateResult] = useState<EventRotateResponse | null>(null);
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<EventUpdatePayload>({ resolver: zodResolver(eventSettingsSchema) });
  const resetForm = useForm<ResetForm>({ resolver: zodResolver(resetConfirmationSchema), mode: "onChange", defaultValues: { confirmation: "" } });
  const rotateForm = useForm<EventRotateFormValues>({
    resolver: zodResolver(eventRotateSchema),
    mode: "onChange",
    defaultValues: { name: "", slug: "", confirmation: "" },
  });
  const resetReady = resetForm.watch("confirmation") === "清除全部数据";
  const rotateReady = rotateForm.watch("confirmation") === "归档并开启新届";

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

  const rotateEvent = rotateForm.handleSubmit(async (form) => {
    setRotateError("");
    try {
      const result = await api.rotateEvent(form);
      setRotateResult(result);
      rotateForm.reset();
      await refreshConfig();
      enqueueSnackbar(result.message, { variant: "success" });
    } catch (err) {
      setRotateError(err instanceof Error ? err.message : "归档失败");
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

    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, mt: 2 }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
        <Box>
          <Typography variant="h3">归档本届并开启新届</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            将当前赛事「{event.name}」封存进往届一览，并开启全新空届。本届投稿公开包会被删除以释放存储，往届下载改用原始包。可每届结束重复操作；请勿用下方「清除全部数据」代替开新届。
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Archive size={17} />}
          onClick={() => {
            setRotateError("");
            setRotateResult(null);
            rotateForm.reset({ name: "", slug: "", confirmation: "" });
            setRotateOpen(true);
          }}
        >
          归档并开新届
        </Button>
      </Stack>
    </Paper>

    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, mt: 2, borderColor: "error.main", borderTopWidth: 3 }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
        <Box>
          <Typography variant="h3" color="error.main">危险操作</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            清除全部赛事和普通用户数据，保留管理员与公共资源。这会毁掉所有往届归档，操作不可撤销，完成后所有账号都需要重新登录。
          </Typography>
        </Box>
        <Button color="error" variant="contained" startIcon={<Trash2 size={17} />} onClick={() => { setResetError(""); setResetResult(null); resetForm.reset(); setResetOpen(true); }}>清除全部数据</Button>
      </Stack>
    </Paper>

    <Dialog open={rotateOpen} onClose={rotateForm.formState.isSubmitting || rotateResult ? undefined : () => setRotateOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>{rotateResult ? "归档完成" : "确认归档并开启新届"}</DialogTitle>
      <DialogContent>
        {rotateResult ? (
          <Stack spacing={2}>
            <Alert severity="success">{rotateResult.message}</Alert>
            <Typography variant="body2">
              已归档「{rotateResult.archived_event.name}」，当前届为「{rotateResult.current_event.name}」。清除公开包 {rotateResult.purged_public_packages} 个。可在「往届乐曲」查看归档谱面。
            </Typography>
          </Stack>
        ) : (
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <Alert severity="warning">
              当前届「{event.name}」将被封存；公开下载包会被删除，原始包与试听保留。包内文件名可能仍带投稿痕迹。新届从空白赛程开始，需重新配置阶段。
            </Alert>
            <TextField label="新届名称" autoFocus fullWidth {...rotateForm.register("name")} error={Boolean(rotateForm.formState.errors.name)} helperText={rotateForm.formState.errors.name?.message ?? "例如：这谱谱这 #6"} disabled={rotateForm.formState.isSubmitting} />
            <TextField label="新届 slug" fullWidth {...rotateForm.register("slug")} error={Boolean(rotateForm.formState.errors.slug)} helperText={rotateForm.formState.errors.slug?.message ?? "例如：zppz-6（小写字母、数字、连字符）"} disabled={rotateForm.formState.isSubmitting} />
            <TextField label="输入确认词" fullWidth helperText={rotateForm.formState.errors.confirmation?.message ?? "请输入：归档并开启新届"} {...rotateForm.register("confirmation")} disabled={rotateForm.formState.isSubmitting} error={Boolean(rotateForm.formState.errors.confirmation || rotateError)} />
            {rotateError ? <Alert severity="error">{rotateError}</Alert> : null}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {rotateResult ? (
          <Button variant="contained" onClick={() => { setRotateOpen(false); navigate("/archive"); }}>查看往届乐曲</Button>
        ) : (
          <>
            <Button disabled={rotateForm.formState.isSubmitting} onClick={() => setRotateOpen(false)}>取消</Button>
            <Button variant="contained" disabled={!rotateReady || rotateForm.formState.isSubmitting} onClick={() => void rotateEvent()}>
              {rotateForm.formState.isSubmitting ? "归档中…" : "确认归档"}
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>

    <Dialog open={resetOpen} onClose={resetForm.formState.isSubmitting || resetResult ? undefined : () => setResetOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>{resetResult ? "清除完成" : "确认清除全部数据"}</DialogTitle>
      <DialogContent>{resetResult ? <Stack spacing={2}><Alert severity="success">{resetResult.message}</Alert><Typography variant="body2">当前赛事“{resetResult.event_name}”已保留，赛事 ID 为 {resetResult.event_id}。</Typography>{resetResult.file_cleanup_warnings.length ? <Alert severity="warning">{resetResult.file_cleanup_warnings.join("；")}</Alert> : <Alert severity="info">赛事上传文件和猜谱文件已清理，公共资源已保留。</Alert>}</Stack> : <Stack spacing={2}><Alert severity="error">这会删除所有赛事数据、投稿、抽签、换曲、猜谱、投票、评论、往届归档和普通用户账号，并注销所有登录会话。此操作无法撤销。若只是开新届，请使用上方「归档并开新届」。</Alert><TextField autoFocus fullWidth label="输入确认词" helperText={resetForm.formState.errors.confirmation?.message ?? "请输入：清除全部数据"} {...resetForm.register("confirmation")} disabled={resetForm.formState.isSubmitting} error={Boolean(resetForm.formState.errors.confirmation || resetError)} />{resetError ? <Alert severity="error">{resetError}</Alert> : null}</Stack>}</DialogContent>
      <DialogActions>{resetResult ? <Button variant="contained" onClick={() => void finishReset()}>重新登录</Button> : <><Button disabled={resetForm.formState.isSubmitting} onClick={() => setResetOpen(false)}>取消</Button><Button color="error" variant="contained" disabled={!resetReady || resetForm.formState.isSubmitting} onClick={() => void resetAll()}>{resetForm.formState.isSubmitting ? "清除中…" : "确认清除"}</Button></>}</DialogActions>
    </Dialog>
  </>;
}
