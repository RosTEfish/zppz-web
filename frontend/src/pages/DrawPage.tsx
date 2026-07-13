import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, Paper, Stack, Typography } from "@mui/material";
import { ArrowLeftRight, Save, Sparkles } from "lucide-react";
import { api, type SwapMeRead } from "../api/v1";
import { DrawList } from "../components/DrawList";
import { PageHeader, type Resource, ResourceState, useResource } from "../components/PagePrimitives";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";

export default function DrawPage() {
  const draws = useResource(api.myDraw, []);
  const swap = useResource(api.mySwap, []);
  const { user } = useAuth();
  const { event, phases } = useConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run() {
    setBusy(true); setError("");
    try { draws.setData(await api.drawMine()); } catch (err) { setError(err instanceof Error ? err.message : "抽签失败"); } finally { setBusy(false); }
  }
  return <Stack spacing={3}><PageHeader icon={Sparkles} title="我的抽签" meta={user?.identity === "participant" ? `应抽 ${event?.settings.draw_songs_per_participant ?? "-"} 首` : "当前账号不参与抽签"} actions={user?.identity === "participant" ? <Button variant="contained" startIcon={<Sparkles size={17} />} disabled={busy || !(phases?.capabilities.draw ?? !event?.settings.submissions_open)} onClick={() => void run()}>{draws.data?.length ? "重新抽签" : "开始抽签"}</Button> : undefined} />{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={draws.loading} error={draws.error} empty={!draws.data?.length ? "暂无抽签结果" : undefined} />{draws.data?.length ? <DrawList rows={draws.data} showAssignee={false} /> : null}{user?.identity === "participant" ? <SwapPanel resource={swap} /> : null}</Stack>;
}

function SwapPanel({ resource }: { resource: Resource<SwapMeRead> }) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestIds = resource.data?.request?.assignment_ids;
  useEffect(() => { if (requestIds) setSelected(new Set(requestIds)); }, [requestIds]);
  const toggle = (id: number) => setSelected((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else if (next.size < 3) next.add(id); return next; });
  async function save() { setBusy(true); setError(""); try { resource.setData(await api.updateMySwap([...selected])); setConfirmOpen(false); } catch (err) { setError(err instanceof Error ? err.message : "换曲申请保存失败"); } finally { setBusy(false); } }
  const status = resource.data?.request?.status;
  return <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 } }}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}><Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><ArrowLeftRight size={20} /><Typography variant="h3">换曲申请</Typography>{status ? <Chip size="small" label={{ pending: "等待处理", processing: "处理中", completed: "已完成", failed: "处理失败" }[status] || status} color={status === "completed" ? "success" : status === "failed" ? "error" : "default"} /> : null}</Stack>{resource.data?.round?.ends_at ? <Typography variant="caption" color="text.secondary">截止：{new Date(resource.data.round.ends_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}</Typography> : null}</Stack><Divider sx={{ my: 1.5 }} /><ResourceState loading={resource.loading} error={resource.error} />{error ? <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert> : null}{resource.data ? <><Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>选择 1～3 首当前有效抽中曲；截止前可反复修改。已有投稿的曲目需先删除投稿。</Typography><Stack>{resource.data.assignments.map((row) => <FormControlLabel key={row.id} control={<Checkbox checked={selected.has(row.id)} disabled={!resource.data?.is_open || status === "processing" || status === "completed" || (!selected.has(row.id) && selected.size >= resource.data.max_selections)} onChange={() => toggle(row.id)} />} label={<><Typography variant="body2" sx={{ fontWeight: 700 }}>{row.song.song_name}</Typography><Typography variant="caption" color="text.secondary">{row.song.artist}</Typography></>} />)}</Stack><Button variant="contained" startIcon={<Save size={16} />} disabled={!resource.data.is_open || selected.size < 1 || selected.size > resource.data.max_selections || status === "processing" || status === "completed"} onClick={() => setConfirmOpen(true)} sx={{ mt: 1 }}>保存申请（{selected.size}/{resource.data.max_selections}）</Button>{resource.data.results.length ? <Stack spacing={1} sx={{ mt: 2 }}>{resource.data.results.map((item) => <Alert severity="success" key={item.original.id}>{item.original.song.song_name} → {item.replacement?.song.song_name || "新曲目"}</Alert>)}</Stack> : null}</> : null}<Dialog open={confirmOpen} onClose={busy ? undefined : () => setConfirmOpen(false)} fullWidth maxWidth="xs"><DialogTitle>确认换曲申请</DialogTitle><DialogContent><Alert severity="warning">将退回所选 {selected.size} 首曲目。管理员完成 Finalize 后才会生成新抽签结果。</Alert></DialogContent><DialogActions><Button disabled={busy} onClick={() => setConfirmOpen(false)}>取消</Button><Button variant="contained" disabled={busy} onClick={() => void save()}>{busy ? "保存中…" : "确认保存"}</Button></DialogActions></Dialog></Paper>;
}
