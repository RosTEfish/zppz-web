import { useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Snackbar, Stack, TextField, Typography } from "@mui/material";
import { Save, Trash2 } from "lucide-react";
import { api, type AdminResetResponse, type EventUpdatePayload } from "../../api/v1";
import { LoadingBlock } from "../../components/PagePrimitives";
import { useAuth } from "../../contexts/AuthContext";
import { useConfig } from "../../contexts/ConfigContext";
import { useNavigate } from "react-router-dom";

export default function AdminSettings() {
  const { event, refreshConfig } = useConfig();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState<EventUpdatePayload | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [resetOpen, setResetOpen] = useState(false);
  const [resetConfirmation, setResetConfirmation] = useState("");
  const [resetBusy, setResetBusy] = useState(false);
  const [resetError, setResetError] = useState("");
  const [resetResult, setResetResult] = useState<AdminResetResponse | null>(null);
  useEffect(() => {
    if (!event) return;
    const { settings } = event;
    setForm({
      name: event.name,
      participant_song_limit: settings.participant_song_limit,
      audience_song_limit: settings.audience_song_limit,
      draw_songs_per_participant: settings.draw_songs_per_participant,
      true_love_vote_limit_below_14: settings.true_love_vote_limit_below_14,
      true_love_vote_limit_at_least_14: settings.true_love_vote_limit_at_least_14,
      funny_vote_limit: settings.funny_vote_limit,
      announcement_text: settings.announcement_text,
    });
  }, [event]);
  if (!form) return <LoadingBlock />;
  const numberField = (key: keyof EventUpdatePayload, label: string) => <TextField type="number" label={label} value={String(form[key] ?? "")} onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })} />;
  const voteLimitField = (key: "true_love_vote_limit_below_14" | "true_love_vote_limit_at_least_14", label: string) => <TextField type="number" label={label} value={String(form[key] ?? "")} slotProps={{ htmlInput: { min: 0, max: 50 } }} onChange={(event) => setForm({ ...form, [key]: Math.min(50, Math.max(0, Number(event.target.value))) })} />;
  async function save() { try { await api.updateEvent(form); await refreshConfig(); setMessage("赛事设置已保存"); } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); } }
  async function resetAll() { setResetBusy(true); setResetError(""); try { const result = await api.resetAllData(resetConfirmation); setResetResult(result); setResetConfirmation(""); } catch (err) { setResetError(err instanceof Error ? err.message : "清除失败"); } finally { setResetBusy(false); } }
  async function finishReset() { flushSync(() => { void logout(); }); navigate("/login", { replace: true }); }
  const resetReady = resetConfirmation === "清除全部数据";
  return <><Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}><Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}><TextField label="赛事名称" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />{numberField("participant_song_limit", "参赛者曲目上限")}{numberField("audience_song_limit", "观众曲目上限")}{numberField("draw_songs_per_participant", "每人抽取曲目数")}{voteLimitField("true_love_vote_limit_below_14", "14 以下真爱票上限")}{voteLimitField("true_love_vote_limit_at_least_14", "14 及以上真爱票上限")}{numberField("funny_vote_limit", "欢乐票上限")}<TextField label="公告（Markdown）" multiline minRows={5} value={form.announcement_text} onChange={(event) => setForm({ ...form, announcement_text: event.target.value })} sx={{ gridColumn: { md: "1 / -1" } }} /></Box>{error ? <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert> : null}<Button variant="contained" startIcon={<Save size={17} />} onClick={() => void save()} sx={{ mt: 2 }}>保存设置</Button><Snackbar open={Boolean(message)} autoHideDuration={2500} onClose={() => setMessage("")} message={message} /></Paper><Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, mt: 2, borderColor: "error.main", borderTopWidth: 3 }}><Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}><Box><Typography variant="h3" color="error.main">危险操作</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>清除全部赛事和普通用户数据，保留管理员与公共资源。操作不可撤销，完成后所有账号都需要重新登录。</Typography></Box><Button color="error" variant="contained" startIcon={<Trash2 size={17} />} onClick={() => { setResetError(""); setResetResult(null); setResetOpen(true); }}>清除全部数据</Button></Stack></Paper><Dialog open={resetOpen} onClose={resetBusy || resetResult ? undefined : () => setResetOpen(false)} fullWidth maxWidth="sm"><DialogTitle>{resetResult ? "清除完成" : "确认清除全部数据"}</DialogTitle><DialogContent>{resetResult ? <Stack spacing={2}><Alert severity="success">{resetResult.message}</Alert><Typography variant="body2">当前赛事“{resetResult.event_name}”已保留，赛事 ID 为 {resetResult.event_id}。</Typography>{resetResult.file_cleanup_warnings.length ? <Alert severity="warning">{resetResult.file_cleanup_warnings.join("；")}</Alert> : <Alert severity="info">赛事上传文件和猜谱文件已清理，公共资源已保留。</Alert>}</Stack> : <Stack spacing={2}><Alert severity="error">这会删除所有赛事数据、投稿、抽签、换曲、猜谱、投票、评论和普通用户账号，并注销所有登录会话。此操作无法撤销。</Alert><TextField autoFocus fullWidth label="输入确认词" helperText="请输入：清除全部数据" value={resetConfirmation} onChange={(event) => setResetConfirmation(event.target.value)} disabled={resetBusy} error={Boolean(resetError)} />{resetError ? <Alert severity="error">{resetError}</Alert> : null}</Stack>}</DialogContent><DialogActions>{resetResult ? <Button variant="contained" onClick={() => void finishReset()}>重新登录</Button> : <><Button disabled={resetBusy} onClick={() => setResetOpen(false)}>取消</Button><Button color="error" variant="contained" disabled={!resetReady || resetBusy} onClick={() => void resetAll()}>{resetBusy ? "清除中…" : "确认清除"}</Button></>}</DialogActions></Dialog></>;
}
