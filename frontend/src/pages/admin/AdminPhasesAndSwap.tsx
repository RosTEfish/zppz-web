import { useEffect, useState } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, InputLabel, MenuItem, Paper, Select, Stack, TextField, Typography } from "@mui/material";
import { ArrowLeftRight, ArrowRight, Save } from "lucide-react";
import { api, formatTime, type EventPhaseName, type EventPhasesUpdate, type SwapAuditAssignmentRead, type SwapAuditRequestRead } from "../../api/v1";
import { PHASE_LABELS } from "../../components/EventPhaseStatus";
import { LoadingBlock, useResource } from "../../components/PagePrimitives";
import { useAuth } from "../../contexts/AuthContext";
import { useConfig } from "../../contexts/ConfigContext";

const PHASE_ORDER = Object.keys(PHASE_LABELS) as EventPhaseName[];

export default function AdminPhasesAndSwap() {
  const { phases, refreshConfig } = useConfig();
  const { isAdmin } = useAuth();
  const [form, setForm] = useState<EventPhasesUpdate | null>(null);
  const [confirmPhase, setConfirmPhase] = useState<EventPhaseName | null>(null);
  const [finalizeOpen, setFinalizeOpen] = useState(false);
  const [validation, setValidation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<SwapAuditRequestRead | null>(null);
  const audit = useResource(api.swapAudit, []);
  useEffect(() => {
    if (!phases) return;
    setForm({ phase_mode: phases.phase_mode, manual_phase: phases.manual_phase, phases: PHASE_ORDER.map((phase) => phases.phases.find((item) => item.phase === phase) ?? { phase, starts_at: "", ends_at: "" }) });
  }, [phases]);
  if (!form) return <LoadingBlock />;

  const updateWindow = (phase: EventPhaseName, key: "starts_at" | "ends_at", value: string) => setForm((current) => current ? { ...current, phases: current.phases.map((item) => item.phase === phase ? { ...item, [key]: value ? new Date(value).toISOString() : "" } : item) } : current);
  async function save(nextForm = form) {
    const partial = nextForm.phases.find((item) => Boolean(item.starts_at) !== Boolean(item.ends_at));
    if (partial) { setError(`${PHASE_LABELS[partial.phase]}需要同时填写开始和结束时间`); return; }
    setBusy(true); setError("");
    try { await api.updateEventPhases({ ...nextForm, phases: nextForm.phases.filter((item) => item.starts_at && item.ends_at) }); await refreshConfig(); setValidation("阶段设置已保存"); }
    catch (err) { setError(err instanceof Error ? err.message : "阶段设置保存失败"); }
    finally { setBusy(false); setConfirmPhase(null); }
  }
  async function validate() { setBusy(true); setError(""); try { const result = await api.validateSwaps(); setValidation(result.message || (result.ok ? "换曲预检通过" : "换曲预检未通过")); } catch (err) { setError(err instanceof Error ? err.message : "换曲预检失败"); } finally { setBusy(false); } }
  async function finalize() { setBusy(true); setError(""); try { const result = await api.finalizeSwaps(); setValidation(result.message || "换曲 Finalize 已完成"); setFinalizeOpen(false); await audit.reload(); } catch (err) { setError(err instanceof Error ? err.message : "换曲 Finalize 失败"); } finally { setBusy(false); } }
  async function reject() { if (!rejectTarget) return; setBusy(true); setError(""); try { await api.rejectSwapRequest(rejectTarget.id); setRejectTarget(null); setValidation("换曲申请已驳回"); await audit.reload(); } catch (err) { setError(err instanceof Error ? err.message : "驳回换曲申请失败"); } finally { setBusy(false); } }

  return <Stack spacing={2}>
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "center" } }}><Box><Typography variant="h3">赛事阶段</Typography><Typography variant="body2" color="text.secondary">UTC 存储，以下输入与展示使用北京时间；阶段不能重叠。</Typography></Box><Stack direction="row" spacing={1}><Button variant={form.phase_mode === "auto" ? "contained" : "outlined"} disabled={busy || form.phase_mode === "auto"} onClick={() => void save({ ...form, phase_mode: "auto", manual_phase: null })}>恢复自动</Button><FormControl size="small" sx={{ minWidth: 150 }}><InputLabel>手动阶段</InputLabel><Select label="手动阶段" value={form.phase_mode === "manual" ? form.manual_phase || "" : ""} onChange={(event) => setConfirmPhase(event.target.value as EventPhaseName)}>{PHASE_ORDER.map((phase) => <MenuItem key={phase} value={phase}>{PHASE_LABELS[phase]}</MenuItem>)}</Select></FormControl></Stack></Stack>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 1.5, mt: 2 }}>{form.phases.map((item) => <Paper key={item.phase} variant="outlined" sx={{ p: 1.5 }}><Typography variant="body2" sx={{ fontWeight: 800, mb: 1 }}>{PHASE_LABELS[item.phase]}</Typography><Stack direction={{ xs: "column", sm: "row" }} spacing={1}><TextField fullWidth size="small" type="datetime-local" label="开始" slotProps={{ inputLabel: { shrink: true } }} value={toDateTimeInput(item.starts_at)} onChange={(event) => updateWindow(item.phase, "starts_at", event.target.value)} /><TextField fullWidth size="small" type="datetime-local" label="结束" slotProps={{ inputLabel: { shrink: true } }} value={toDateTimeInput(item.ends_at)} onChange={(event) => updateWindow(item.phase, "ends_at", event.target.value)} /></Stack></Paper>)}</Box>
      <Button variant="contained" startIcon={<Save size={16} />} disabled={busy} onClick={() => void save()} sx={{ mt: 2 }}>保存时间表</Button>
    </Paper>
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}><Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><ArrowLeftRight size={19} /><Typography variant="h3">换曲处理</Typography></Stack><Stack direction="row" spacing={1}><Button variant="outlined" disabled={busy} onClick={() => void validate()}>预检</Button><Button variant="contained" disabled={busy} onClick={() => setFinalizeOpen(true)}>Finalize</Button></Stack></Stack>{audit.data?.round ? <SwapAuditSummary round={audit.data.round} requestCount={audit.data.requests.length} itemCount={audit.data.requests.reduce((total, request) => total + request.items.length, 0)} /> : null}{audit.data?.requests.length ? <Stack spacing={1.5} sx={{ mt: 2 }}>{audit.data.requests.map((request) => <SwapAuditRequestCard key={request.id} request={request} busy={busy} allowReject={isAdmin} onReject={() => setRejectTarget(request)} />)}</Stack> : <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>暂无换曲审计记录</Typography>}</Paper>
    {validation ? <Alert severity="success" aria-live="polite">{validation}</Alert> : null}{error ? <Alert severity="error" aria-live="polite">{error}</Alert> : null}
    <Dialog open={Boolean(confirmPhase)} onClose={() => setConfirmPhase(null)}><DialogTitle>确认手动切换阶段</DialogTitle><DialogContent><Alert severity="warning">手动切换至“{confirmPhase ? PHASE_LABELS[confirmPhase] : ""}”后会持续接管。提前开放猜谱会立即公开普通稿。</Alert></DialogContent><DialogActions><Button onClick={() => setConfirmPhase(null)}>取消</Button><Button color="warning" variant="contained" onClick={() => confirmPhase && void save({ ...form, phase_mode: "manual", manual_phase: confirmPhase })}>确认切换</Button></DialogActions></Dialog>
    <Dialog open={Boolean(rejectTarget)} onClose={busy ? undefined : () => setRejectTarget(null)} fullWidth maxWidth="xs"><DialogTitle>驳回换曲申请</DialogTitle><DialogContent><Alert severity="warning">驳回后该申请不会参与本轮换曲匹配，但会保留在审计记录中；用户仍可在阶段结束前重新提交。</Alert></DialogContent><DialogActions><Button disabled={busy} onClick={() => setRejectTarget(null)}>取消</Button><Button variant="contained" color="error" disabled={busy} onClick={() => void reject()}>{busy ? "驳回中…" : "确认驳回"}</Button></DialogActions></Dialog>
    <Dialog open={finalizeOpen} onClose={busy ? undefined : () => setFinalizeOpen(false)} fullWidth maxWidth="xs"><DialogTitle>确认执行换曲</DialogTitle><DialogContent><Alert severity="warning">Finalize 会以事务方式生成所有新旧曲目对应关系。执行成功后不可再次修改本轮申请。</Alert></DialogContent><DialogActions><Button disabled={busy} onClick={() => setFinalizeOpen(false)}>取消</Button><Button variant="contained" color="warning" disabled={busy} onClick={() => void finalize()}>{busy ? "处理中…" : "确认 Finalize"}</Button></DialogActions></Dialog>
  </Stack>;
}

function SwapAuditSummary({ round, requestCount, itemCount }: { round: { status: string; starts_at: string; ends_at: string; finalized_at?: string | null }; requestCount: number; itemCount: number }) { const finalized = round.status === "finalized"; return <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap sx={{ mt: 2, alignItems: { sm: "center" }, flexWrap: "wrap" }}><Chip color={finalized ? "success" : "warning"} label={finalized ? "本轮已完成" : "等待处理"} /><Chip variant="outlined" label={`${requestCount} 位用户申请 · ${itemCount} 首曲目`} /><Typography variant="caption" color="text.secondary">换曲时间：{formatTime(round.starts_at)} - {formatTime(round.ends_at)}{round.finalized_at ? ` · 完成于 ${formatTime(round.finalized_at)}` : ""}</Typography></Stack>; }

function SwapAuditRequestCard({ request, busy, allowReject, onReject }: { request: SwapAuditRequestRead; busy: boolean; allowReject: boolean; onReject: () => void }) { const status = { pending: "待处理", processing: "处理中", completed: "已完成", failed: "处理失败", rejected: "已驳回", cancelled: "已取消" }[request.status] || request.status; const color = request.status === "completed" ? "success" : request.status === "failed" || request.status === "rejected" ? "error" : request.status === "pending" || request.status === "processing" ? "warning" : "default"; const canReject = allowReject && (request.status === "pending" || request.status === "processing"); return <Paper variant="outlined" sx={{ p: { xs: 1.5, md: 2 } }}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}><Box><Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}><Typography variant="h3">{request.user.display_name || request.user.user_code}</Typography><Chip size="small" variant="outlined" label={`申请 #${request.id}`} /><Chip size="small" color={color} label={status} /></Stack><Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{request.user.user_code} · {request.items.length} 首换曲申请</Typography></Box>{canReject ? <Button size="small" variant="outlined" color="error" disabled={busy} onClick={onReject}>驳回申请</Button> : null}</Stack>{request.error_message ? <Alert severity={request.status === "cancelled" ? "info" : "error"} sx={{ mt: 1.5 }}>{request.error_message}</Alert> : null}<Stack spacing={1} sx={{ mt: 1.5 }}>{request.items.map((item) => <Paper key={`${request.id}-${item.position}`} variant="outlined" sx={{ p: 1.25, bgcolor: "background.default" }}><Stack direction={{ xs: "column", sm: "row" }} spacing={{ xs: 0.75, sm: 1.5 }} sx={{ alignItems: { sm: "center" } }}><Typography variant="caption" sx={{ minWidth: { sm: 48 }, fontWeight: 800, color: "text.secondary" }}>第 {item.position + 1} 首</Typography><SwapAuditSong label="原曲" assignment={item.original} /><ArrowRight size={18} /><SwapAuditSong label="换后" assignment={item.replacement} /></Stack></Paper>)}</Stack></Paper>; }

function SwapAuditSong({ label, assignment }: { label: string; assignment?: SwapAuditAssignmentRead | null }) { return <Box sx={{ minWidth: 0, flex: 1 }}><Typography variant="caption" color="text.secondary">{label}</Typography>{assignment ? <><Typography sx={{ fontWeight: 800, overflowWrap: "anywhere" }}>{assignment.song.song_name}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: "block", overflowWrap: "anywhere" }}>{assignment.song.artist}</Typography></> : <Typography variant="body2" color="text.secondary">等待生成</Typography>}</Box>; }

function toDateTimeInput(value?: string | null): string { if (!value) return ""; const date = new Date(value); const offset = date.getTimezoneOffset() * 60_000; return new Date(date.getTime() - offset).toISOString().slice(0, 16); }
