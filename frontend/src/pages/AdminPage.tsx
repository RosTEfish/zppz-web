import { type ReactNode, useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, FormControlLabel, IconButton, InputLabel, MenuItem, Paper, Select, Snackbar, Stack, Switch, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Tooltip, Typography } from "@mui/material";
import { Archive, ArrowLeftRight, ArrowRight, BarChart3, CalendarClock, Check, Download, FileArchive, FileDown, FileUp, Gauge, Music2, Pencil, RefreshCw, Save, Settings, Sparkles, Trash2, Users, Vote } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { api, formatDuration, formatMB, formatTime, type AdminResetResponse, type AuthorCandidateAdmin, type EventPhaseName, type EventPhasesUpdate, type EventUpdatePayload, type GuessChartRead, type GuessStats, type SongRead, type StoredFileRead, type SwapAuditAssignmentRead, type SwapAuditRequestRead, type Track, type UserRead } from "../api/v1";
import { DrawList } from "../components/DrawList";
import { LoadingBlock, PageHeader, type Resource, ResourceState, useResource } from "../components/PagePrimitives";
import { SongDialog, SongTable } from "../components/SongComponents";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";
import { PHASE_LABELS } from "../components/EventPhaseStatus";

const ADMIN_TABS = [
  ["overview", "总览", Gauge], ["settings", "设置", Settings], ["users", "用户", Users], ["songs", "曲池", Music2],
  ["draw", "抽签", Sparkles], ["phases", "阶段与换曲", CalendarClock], ["submissions", "投稿", Archive], ["guess", "猜谱", Vote], ["stats", "统计", BarChart3],
] as const;

export default function AdminPage() {
  const { tab = "overview" } = useParams();
  const { isAdmin, isPoolEditor } = useAuth();
  const navigate = useNavigate();
  const visible = isAdmin ? ADMIN_TABS : ADMIN_TABS.filter(([key]) => isPoolEditor && key === "songs");
  const active = visible.some(([key]) => key === tab) ? tab : visible[0]?.[0] || "songs";
  useEffect(() => {
    if (!isAdmin && isPoolEditor && tab !== "songs") navigate("/admin/songs", { replace: true });
  }, [isAdmin, isPoolEditor, navigate, tab]);
  return <Stack spacing={2.5}><PageHeader icon={Gauge} title="管理工作台" /><Paper variant="outlined"><Tabs value={active} onChange={(_, value) => navigate(`/admin/${value}`)} variant="scrollable" scrollButtons="auto" sx={{ "& .MuiTabs-flexContainer": { width: { md: "100%" } }, "& .MuiTab-root": { minWidth: { xs: 112, md: 0 }, flex: { md: "1 1 0" } } }}>{visible.map(([key, label, Icon]) => <Tab key={key} value={key} icon={<Icon size={17} />} iconPosition="start" label={label} />)}</Tabs></Paper>{active === "overview" ? <AdminOverview /> : null}{active === "settings" ? <AdminSettings /> : null}{active === "users" ? <AdminUsers /> : null}{active === "songs" ? <AdminSongs /> : null}{active === "draw" ? <AdminDraw /> : null}{active === "phases" ? <AdminPhasesAndSwap /> : null}{active === "submissions" ? <AdminSubmissions /> : null}{active === "guess" ? <AdminGuess /> : null}{active === "stats" ? <AdminStats /> : null}</Stack>;
}

function BatchDeleteDialog({ open, count, label, busy, onClose, onConfirm }: { open: boolean; count: number; label: string; busy: boolean; onClose: () => void; onConfirm: () => void }) {
  return <Dialog open={open} onClose={busy ? undefined : onClose} fullWidth maxWidth="xs"><DialogTitle>确认批量删除</DialogTitle><DialogContent><Alert severity="warning">将删除选中的 {count} {label}。该操作无法撤销，任一项目不符合删除规则时整批都会取消。</Alert></DialogContent><DialogActions><Button disabled={busy} onClick={onClose}>取消</Button><Button color="error" variant="contained" startIcon={<Trash2 size={16} />} disabled={busy || !count} onClick={onConfirm}>{busy ? "删除中" : "确认删除"}</Button></DialogActions></Dialog>;
}

function AdminOverview() {
  const stats = useResource(api.siteStats, []);
  const labels: Record<string, string> = { users: "用户", songs: "曲目", assignments: "抽签结果", submissions: "投稿", guess_charts: "谱面", charts: "谱面" };
  return <><ResourceState loading={stats.loading} error={stats.error} />{stats.data ? <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, 1fr)", lg: "repeat(4, 1fr)" }, gap: 2 }}>{Object.entries(stats.data).map(([key, value]) => <Paper key={key} variant="outlined" sx={{ p: 2.5 }}><Typography variant="body2" color="text.secondary">{labels[key] || key}</Typography><Typography variant="h1" sx={{ mt: 1 }}>{value}</Typography></Paper>)}</Box> : null}</>;
}

const PHASE_ORDER = Object.keys(PHASE_LABELS) as EventPhaseName[];

function AdminPhasesAndSwap() {
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
    setForm({
      phase_mode: phases.phase_mode,
      manual_phase: phases.manual_phase,
      phases: PHASE_ORDER.map((phase) => phases.phases.find((item) => item.phase === phase) ?? { phase, starts_at: "", ends_at: "" }),
    });
  }, [phases]);
  if (!form) return <LoadingBlock />;
  const updateWindow = (phase: EventPhaseName, key: "starts_at" | "ends_at", value: string) => setForm((current) => current ? { ...current, phases: current.phases.map((item) => item.phase === phase ? { ...item, [key]: value ? new Date(value).toISOString() : "" } : item) } : current);
  async function save(nextForm = form) {
    const partial = nextForm.phases.find((item) => Boolean(item.starts_at) !== Boolean(item.ends_at));
    if (partial) { setError(`${PHASE_LABELS[partial.phase]}需要同时填写开始和结束时间`); return; }
    setBusy(true);
    setError("");
    try {
      await api.updateEventPhases({ ...nextForm, phases: nextForm.phases.filter((item) => item.starts_at && item.ends_at) });
      await refreshConfig();
      setValidation("阶段设置已保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : "阶段设置保存失败");
    } finally {
      setBusy(false);
      setConfirmPhase(null);
    }
  }
  async function validate() { setBusy(true); setError(""); try { const result = await api.validateSwaps(); setValidation(result.message || (result.ok ? "换曲预检通过" : "换曲预检未通过")); } catch (err) { setError(err instanceof Error ? err.message : "换曲预检失败"); } finally { setBusy(false); } }
  async function finalize() { setBusy(true); setError(""); try { const result = await api.finalizeSwaps(); setValidation(result.message || "换曲 Finalize 已完成"); setFinalizeOpen(false); await audit.reload(); } catch (err) { setError(err instanceof Error ? err.message : "换曲 Finalize 失败"); } finally { setBusy(false); } }
  async function reject() {
    if (!rejectTarget) return;
    setBusy(true);
    setError("");
    try {
      await api.rejectSwapRequest(rejectTarget.id);
      setRejectTarget(null);
      setValidation("换曲申请已驳回");
      await audit.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "驳回换曲申请失败");
    } finally {
      setBusy(false);
    }
  }
  return <Stack spacing={2}><Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}><Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "center" } }}><Box><Typography variant="h3">赛事阶段</Typography><Typography variant="body2" color="text.secondary">UTC 存储，以下输入与展示使用北京时间；阶段不能重叠。</Typography></Box><Stack direction="row" spacing={1}><Button variant={form.phase_mode === "auto" ? "contained" : "outlined"} disabled={busy} onClick={() => void save({ ...form, phase_mode: "auto", manual_phase: null })}>恢复自动</Button><FormControl size="small" sx={{ minWidth: 150 }}><InputLabel>手动阶段</InputLabel><Select label="手动阶段" value={form.phase_mode === "manual" ? form.manual_phase || "" : ""} onChange={(event) => setConfirmPhase(event.target.value as EventPhaseName)}>{PHASE_ORDER.map((phase) => <MenuItem key={phase} value={phase}>{PHASE_LABELS[phase]}</MenuItem>)}</Select></FormControl></Stack></Stack><Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 1.5, mt: 2 }}>{form.phases.map((item) => <Paper key={item.phase} variant="outlined" sx={{ p: 1.5 }}><Typography variant="body2" sx={{ fontWeight: 800, mb: 1 }}>{PHASE_LABELS[item.phase]}</Typography><Stack direction={{ xs: "column", sm: "row" }} spacing={1}><TextField fullWidth size="small" type="datetime-local" label="开始" slotProps={{ inputLabel: { shrink: true } }} value={toDateTimeInput(item.starts_at)} onChange={(event) => updateWindow(item.phase, "starts_at", event.target.value)} /><TextField fullWidth size="small" type="datetime-local" label="结束" slotProps={{ inputLabel: { shrink: true } }} value={toDateTimeInput(item.ends_at)} onChange={(event) => updateWindow(item.phase, "ends_at", event.target.value)} /></Stack></Paper>)}</Box><Button variant="contained" startIcon={<Save size={16} />} disabled={busy} onClick={() => void save()} sx={{ mt: 2 }}>保存时间表</Button></Paper><Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}><Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><ArrowLeftRight size={19} /><Typography variant="h3">换曲处理</Typography></Stack><Stack direction="row" spacing={1}><Button variant="outlined" disabled={busy} onClick={() => void validate()}>预检</Button><Button variant="contained" disabled={busy} onClick={() => setFinalizeOpen(true)}>Finalize</Button></Stack></Stack>{audit.data?.round ? <SwapAuditSummary round={audit.data.round} requestCount={audit.data.requests.length} itemCount={audit.data.requests.reduce((total, request) => total + request.items.length, 0)} /> : null}{audit.data?.requests.length ? <Stack spacing={1.5} sx={{ mt: 2 }}>{audit.data.requests.map((request) => <SwapAuditRequestCard key={request.id} request={request} busy={busy} allowReject={isAdmin} onReject={() => setRejectTarget(request)} />)}</Stack> : <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>暂无换曲审计记录</Typography>}</Paper>{validation ? <Alert severity="success" aria-live="polite">{validation}</Alert> : null}{error ? <Alert severity="error" aria-live="polite">{error}</Alert> : null}<Dialog open={Boolean(confirmPhase)} onClose={() => setConfirmPhase(null)}><DialogTitle>确认手动切换阶段</DialogTitle><DialogContent><Alert severity="warning">手动切换至“{confirmPhase ? PHASE_LABELS[confirmPhase] : ""}”后会持续接管。提前开放猜谱或揭晓可能立即公开普通稿。</Alert></DialogContent><DialogActions><Button onClick={() => setConfirmPhase(null)}>取消</Button><Button color="warning" variant="contained" onClick={() => confirmPhase && void save({ ...form, phase_mode: "manual", manual_phase: confirmPhase })}>确认切换</Button></DialogActions></Dialog><Dialog open={Boolean(rejectTarget)} onClose={busy ? undefined : () => setRejectTarget(null)} fullWidth maxWidth="xs"><DialogTitle>驳回换曲申请</DialogTitle><DialogContent><Alert severity="warning">驳回后该申请不会参与本轮换曲匹配，但会保留在审计记录中；用户仍可在阶段结束前重新提交。</Alert></DialogContent><DialogActions><Button disabled={busy} onClick={() => setRejectTarget(null)}>取消</Button><Button variant="contained" color="error" disabled={busy} onClick={() => void reject()}>{busy ? "驳回中…" : "确认驳回"}</Button></DialogActions></Dialog>{finalizeOpen ? <Dialog open onClose={busy ? undefined : () => setFinalizeOpen(false)} fullWidth maxWidth="xs"><DialogTitle>确认执行换曲</DialogTitle><DialogContent><Alert severity="warning">Finalize 会以事务方式生成所有新旧曲目对应关系。执行成功后不可再次修改本轮申请。</Alert></DialogContent><DialogActions><Button disabled={busy} onClick={() => setFinalizeOpen(false)}>取消</Button><Button variant="contained" color="warning" disabled={busy} onClick={() => void finalize()}>{busy ? "处理中…" : "确认 Finalize"}</Button></DialogActions></Dialog> : null}</Stack>;
}

function SwapAuditSummary({ round, requestCount, itemCount }: { round: { status: string; starts_at: string; ends_at: string; finalized_at?: string | null }; requestCount: number; itemCount: number }) {
  const finalized = round.status === "finalized";
  return <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap sx={{ mt: 2, alignItems: { sm: "center" }, flexWrap: "wrap" }}><Chip color={finalized ? "success" : "warning"} label={finalized ? "本轮已完成" : "等待处理"} /><Chip variant="outlined" label={`${requestCount} 位用户申请 · ${itemCount} 首曲目`} /><Typography variant="caption" color="text.secondary">换曲时间：{formatTime(round.starts_at)} - {formatTime(round.ends_at)}{round.finalized_at ? ` · 完成于 ${formatTime(round.finalized_at)}` : ""}</Typography></Stack>;
}

function SwapAuditRequestCard({ request, busy, allowReject, onReject }: { request: SwapAuditRequestRead; busy: boolean; allowReject: boolean; onReject: () => void }) {
  const status = { pending: "待处理", processing: "处理中", completed: "已完成", failed: "处理失败", rejected: "已驳回", cancelled: "已取消" }[request.status] || request.status;
  const color = request.status === "completed" ? "success" : request.status === "failed" || request.status === "rejected" ? "error" : request.status === "pending" || request.status === "processing" ? "warning" : "default";
  const canReject = allowReject && (request.status === "pending" || request.status === "processing");
  return <Paper variant="outlined" sx={{ p: { xs: 1.5, md: 2 } }}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}><Box><Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}><Typography variant="h3">{request.user.display_name || request.user.user_code}</Typography><Chip size="small" variant="outlined" label={`申请 #${request.id}`} /><Chip size="small" color={color} label={status} /></Stack><Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{request.user.user_code} · {request.items.length} 首换曲申请</Typography></Box>{canReject ? <Button size="small" variant="outlined" color="error" disabled={busy} onClick={onReject}>驳回申请</Button> : null}</Stack>{request.error_message ? <Alert severity={request.status === "cancelled" ? "info" : "error"} sx={{ mt: 1.5 }}>{request.error_message}</Alert> : null}<Stack spacing={1} sx={{ mt: 1.5 }}>{request.items.map((item) => <Paper key={`${request.id}-${item.position}`} variant="outlined" sx={{ p: 1.25, bgcolor: "background.default" }}><Stack direction={{ xs: "column", sm: "row" }} spacing={{ xs: 0.75, sm: 1.5 }} sx={{ alignItems: { sm: "center" } }}><Typography variant="caption" sx={{ minWidth: { sm: 48 }, fontWeight: 800, color: "text.secondary" }}>第 {item.position + 1} 首</Typography><SwapAuditSong label="原曲" assignment={item.original} /><ArrowRight size={18} color="currentColor" /><SwapAuditSong label="换后" assignment={item.replacement} /></Stack></Paper>)}</Stack></Paper>;
}

function SwapAuditSong({ label, assignment }: { label: string; assignment?: SwapAuditAssignmentRead | null }) {
  return <Box sx={{ minWidth: 0, flex: 1 }}><Typography variant="caption" color="text.secondary">{label}</Typography>{assignment ? <><Typography sx={{ fontWeight: 800, overflowWrap: "anywhere" }}>{assignment.song.song_name}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: "block", overflowWrap: "anywhere" }}>{assignment.song.artist}</Typography></> : <Typography variant="body2" color="text.secondary">等待生成</Typography>}</Box>;
}

function AdminSettings() {
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
  useEffect(() => { if (event) setForm({ ...event.settings, name: event.name }); }, [event]);
  if (!form) return <LoadingBlock />;
  const numberField = (key: keyof EventUpdatePayload, label: string) => <TextField type="number" label={label} value={String(form[key] ?? "")} onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })} />;
  async function save() { try { await api.updateEvent(form); await refreshConfig(); setMessage("赛事设置已保存"); } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); } }
  async function resetAll() {
    setResetBusy(true);
    setResetError("");
    try {
      const result = await api.resetAllData(resetConfirmation);
      setResetResult(result);
      setResetConfirmation("");
    } catch (err) {
      setResetError(err instanceof Error ? err.message : "清除失败");
    } finally {
      setResetBusy(false);
    }
  }
  async function finishReset() {
    flushSync(() => {
      void logout();
    });
    navigate("/login", { replace: true });
  }
  const resetReady = resetConfirmation === "清除全部数据";
  return <><Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}><Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}><TextField label="赛事名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />{numberField("participant_song_limit", "参赛者曲目上限")}{numberField("audience_song_limit", "观众曲目上限")}{numberField("draw_songs_per_participant", "每人抽取曲目数")}{numberField("true_love_vote_limit", "真爱票上限")}{numberField("funny_vote_limit", "欢乐票上限")}<TextField type="datetime-local" label="投稿截止" slotProps={{ inputLabel: { shrink: true } }} value={toDateTimeInput(form.submission_deadline)} onChange={(e) => setForm({ ...form, submission_deadline: e.target.value || null })} /><TextField type="datetime-local" label="猜谱开放" slotProps={{ inputLabel: { shrink: true } }} value={toDateTimeInput(form.guess_game_open_at)} onChange={(e) => setForm({ ...form, guess_game_open_at: e.target.value || null })} /><TextField label="公告（Markdown）" multiline minRows={5} value={form.announcement_text} onChange={(e) => setForm({ ...form, announcement_text: e.target.value })} sx={{ gridColumn: { md: "1 / -1" } }} /><Paper variant="outlined" sx={{ p: 1.5, gridColumn: { md: "1 / -1" } }}><FormControlLabel control={<Switch checked={form.submissions_open} onChange={(e) => setForm({ ...form, submissions_open: e.target.checked })} />} label="开放投稿" /></Paper></Box>{error ? <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert> : null}<Button variant="contained" startIcon={<Save size={17} />} onClick={() => void save()} sx={{ mt: 2 }}>保存设置</Button><Snackbar open={Boolean(message)} autoHideDuration={2500} onClose={() => setMessage("")} message={message} /></Paper><Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, mt: 2, borderColor: "error.main", borderTopWidth: 3 }}><Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}><Box><Typography variant="h3" color="error.main">危险操作</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>清除全部赛事和普通用户数据，保留管理员与公共资源。操作不可撤销，完成后所有账号都需要重新登录。</Typography></Box><Button color="error" variant="contained" startIcon={<Trash2 size={17} />} onClick={() => { setResetError(""); setResetResult(null); setResetOpen(true); }}>清除全部数据</Button></Stack></Paper><Dialog open={resetOpen} onClose={resetBusy || resetResult ? undefined : () => setResetOpen(false)} fullWidth maxWidth="sm"><DialogTitle>{resetResult ? "清除完成" : "确认清除全部数据"}</DialogTitle><DialogContent>{resetResult ? <Stack spacing={2}><Alert severity="success">{resetResult.message}</Alert><Typography variant="body2">当前赛事“{resetResult.event_name}”已保留，赛事 ID 为 {resetResult.event_id}。</Typography>{resetResult.file_cleanup_warnings.length ? <Alert severity="warning">{resetResult.file_cleanup_warnings.join("；")}</Alert> : <Alert severity="info">赛事上传文件和猜谱文件已清理，公共资源已保留。</Alert>}</Stack> : <Stack spacing={2}><Alert severity="error">这会删除所有赛事数据、投稿、抽签、换曲、猜谱、投票、评论和普通用户账号，并注销所有登录会话。此操作无法撤销。</Alert><TextField autoFocus fullWidth label="输入确认词" helperText="请输入：清除全部数据" value={resetConfirmation} onChange={(event) => setResetConfirmation(event.target.value)} disabled={resetBusy} error={Boolean(resetError)} />{resetError ? <Alert severity="error">{resetError}</Alert> : null}</Stack>}</DialogContent><DialogActions>{resetResult ? <Button variant="contained" onClick={() => void finishReset()}>重新登录</Button> : <><Button disabled={resetBusy} onClick={() => setResetOpen(false)}>取消</Button><Button color="error" variant="contained" disabled={!resetReady || resetBusy} onClick={() => void resetAll()}>{resetBusy ? "清除中…" : "确认清除"}</Button></>}</DialogActions></Dialog></>;
}

function updateRole(roles: string[], role: string, enabled: boolean): string[] { if (enabled) return roles.includes(role) ? roles : [...roles, role]; return roles.filter((item) => item !== role); }

function AdminUsers() {
  const users = useResource(api.users, []);
  const [error, setError] = useState("");
  async function change(user: UserRead, patch: Partial<{ identity: string; roles: string[]; display_name: string; is_active: boolean }>) { try { await api.updateUser(user.id, { identity: patch.identity ?? user.identity, roles: patch.roles ?? user.roles, display_name: patch.display_name ?? user.display_name, is_active: patch.is_active ?? user.is_active ?? true }); await users.reload(); } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); } }
  return <>{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={users.loading} error={users.error} />{users.data ? <TableContainer component={Paper} variant="outlined"><Table size="small"><TableHead><TableRow><TableCell>账号</TableCell><TableCell>显示名</TableCell><TableCell>身份</TableCell><TableCell>权限</TableCell><TableCell>启用</TableCell></TableRow></TableHead><TableBody>{users.data.map((user) => <TableRow key={user.id}><TableCell>{user.user_code}</TableCell><TableCell><TextField size="small" defaultValue={user.display_name} onBlur={(e) => { if (e.target.value !== user.display_name) void change(user, { display_name: e.target.value }); }} /></TableCell><TableCell><Select size="small" value={user.identity} onChange={(e) => void change(user, { identity: e.target.value })}><MenuItem value="participant">参赛者</MenuItem><MenuItem value="audience">观众</MenuItem></Select></TableCell><TableCell><Stack spacing={0} sx={{ minWidth: 132 }}><FormControlLabel sx={{ m: 0 }} control={<Checkbox checked={user.roles.includes("admin")} onChange={(e) => void change(user, { roles: updateRole(user.roles, "admin", e.target.checked) })} />} label="管理员" /><FormControlLabel sx={{ m: 0 }} control={<Checkbox checked={user.roles.includes("pool_editor")} onChange={(e) => void change(user, { roles: updateRole(user.roles, "pool_editor", e.target.checked) })} />} label="曲池编辑" /></Stack></TableCell><TableCell><Tooltip title={user.roles.includes("admin") ? "停用最后一名管理员会被系统阻止" : ""}><span><Switch checked={user.is_active ?? true} onChange={(e) => void change(user, { is_active: e.target.checked })} /></span></Tooltip></TableCell></TableRow>)}</TableBody></Table></TableContainer> : null}</>;
}

function AdminSongs() {
  const songs = useResource(api.adminSongs, []);
  const [editing, setEditing] = useState<SongRead | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function importCsv(file?: File) { if (!file) return; try { const result = await api.importSongs(file); setMessage(result.message); await songs.reload(); } catch (err) { setError(err instanceof Error ? err.message : "导入失败"); } }
  async function remove(song: SongRead) { if (!window.confirm(`确认删除《${song.song_name}》？`)) return; try { await api.deleteAdminSong(song.id); setSelected((current) => { const next = new Set(current); next.delete(song.id); return next; }); await songs.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } }
  async function removeSelected() { setDeleting(true); setError(""); try { const result = await api.batchDeleteAdminSongs([...selected]); setMessage(result.message); setSelected(new Set()); setDeleteOpen(false); await songs.reload(); } catch (err) { setError(err instanceof Error ? err.message : "批量删除失败"); setDeleteOpen(false); } finally { setDeleting(false); } }
  function toggleSelection(songId: number) { setSelected((current) => { const next = new Set(current); if (next.has(songId)) next.delete(songId); else next.add(songId); return next; }); }
  return <Stack spacing={2}><Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}><Button variant="outlined" startIcon={<FileDown size={17} />} onClick={() => void api.exportSongs().catch((err) => setError(err.message))}>导出 CSV</Button><Button component="label" variant="contained" startIcon={<FileUp size={17} />}>导入 CSV<input hidden type="file" accept=".csv,text/csv" onChange={(e) => { void importCsv(e.target.files?.[0]); e.currentTarget.value = ""; }} /></Button><Button color="error" variant="outlined" startIcon={<Trash2 size={17} />} disabled={!selected.size} onClick={() => setDeleteOpen(true)}>删除 {selected.size} 项</Button></Stack>{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={songs.loading} error={songs.error} empty={!songs.data?.length ? "曲池为空" : undefined} />{songs.data?.length ? <SongTable songs={songs.data} showSubmitter onEdit={setEditing} onDelete={remove} selectedIds={selected} onToggleSelection={toggleSelection} onToggleAll={(checked) => setSelected(checked ? new Set(songs.data?.map((song) => song.id)) : new Set())} /> : null}<SongDialog song={editing} onClose={() => setEditing(null)} onSave={async (payload) => { if (!editing) return; await api.updateSong(editing.id, payload); setEditing(null); await songs.reload(); }} /><BatchDeleteDialog open={deleteOpen} count={selected.size} label="首曲目" busy={deleting} onClose={() => setDeleteOpen(false)} onConfirm={() => void removeSelected()} /><Snackbar open={Boolean(message)} autoHideDuration={3000} onClose={() => setMessage("")} message={message} /></Stack>;
}

function AdminDraw() {
  const rows = useResource(api.adminDrawResults, []);
  const [error, setError] = useState("");
  async function run() { if (!window.confirm("确认清空并重建全部抽签结果？")) return; try { rows.setData(await api.runDraw()); } catch (err) { setError(err instanceof Error ? err.message : "抽签失败"); } }
  return <Stack spacing={2}><Button variant="contained" startIcon={<RefreshCw size={17} />} onClick={() => void run()} sx={{ alignSelf: "flex-start" }}>全局重新抽签</Button>{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={rows.loading} error={rows.error} empty={!rows.data?.length ? "暂无抽签结果" : undefined} />{rows.data?.length ? <DrawList rows={rows.data} /> : null}</Stack>;
}

function AdminSubmissions() {
  const [filter, setFilter] = useState<Track | "all">("all");
  const files = useResource(() => api.adminSubmissions(filter), [filter]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  async function remove(file: StoredFileRead) { if (!window.confirm(`确认删除 ${file.file_name}？`)) return; try { await api.deleteAdminSubmission(file.id); setSelected((current) => { const next = new Set(current); next.delete(file.id); return next; }); await files.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } }
  async function removeSelected() { setDeleting(true); setError(""); try { await api.batchDeleteAdminSubmissions([...selected]); setSelected(new Set()); setDeleteOpen(false); await files.reload(); } catch (err) { setError(err instanceof Error ? err.message : "批量删除失败"); setDeleteOpen(false); } finally { setDeleting(false); } }
  return <Stack spacing={2}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}><Tabs value={filter} onChange={(_, value) => { setFilter(value); setSelected(new Set()); }}><Tab value="all" label="全部" /><Tab value="normal" label="普通" /><Tab value="j" label="J 赛道" /><Tab value="exhibition" label="场外" /></Tabs><Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}><Button variant="outlined" startIcon={<Check size={16} />} onClick={() => setSelected(new Set(files.data?.map((item) => item.id) || []))}>全选</Button><Button variant="contained" startIcon={<Download size={16} />} disabled={!selected.size} onClick={() => void api.downloadAdminSubmissions([...selected], filter).catch((err) => setError(err.message))}>下载 {selected.size} 份</Button><Button color="error" variant="outlined" startIcon={<Trash2 size={16} />} disabled={!selected.size} onClick={() => setDeleteOpen(true)}>删除 {selected.size} 份</Button></Stack></Stack>{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={files.loading} error={files.error} empty={!files.data?.length ? "暂无投稿" : undefined} />{files.data?.length ? <TableContainer component={Paper} variant="outlined"><Table size="small"><TableHead><TableRow><TableCell padding="checkbox"><Checkbox checked={selected.size === files.data.length} indeterminate={selected.size > 0 && selected.size < files.data.length} onChange={(e) => setSelected(e.target.checked ? new Set(files.data?.map((item) => item.id)) : new Set())} slotProps={{ input: { "aria-label": "选择全部投稿" } }} /></TableCell><TableCell>曲目 / 文件</TableCell><TableCell>投稿人</TableCell><TableCell>来源</TableCell><TableCell>赛道</TableCell><TableCell>时长</TableCell><TableCell>时间</TableCell><TableCell align="right">操作</TableCell></TableRow></TableHead><TableBody>{files.data.map((file) => <TableRow key={file.id} selected={selected.has(file.id)}><TableCell padding="checkbox"><Checkbox checked={selected.has(file.id)} onChange={() => setSelected((current) => { const next = new Set(current); if (next.has(file.id)) next.delete(file.id); else next.add(file.id); return next; })} slotProps={{ input: { "aria-label": `选择 ${file.file_name}` } }} /></TableCell><TableCell><Typography sx={{ fontWeight: 650 }}>{file.source_song?.song_name || "未关联曲目"}</Typography><Typography variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>{file.file_name} · {formatMB(file.file_size)}</Typography></TableCell><TableCell>{file.user?.display_name || file.user?.user_code || "-"}</TableCell><TableCell>{file.track === "exhibition" ? "场外" : file.source_kind === "self" ? "自选" : "抽中"}</TableCell><TableCell><Chip size="small" color={file.track === "j" ? "secondary" : file.track === "exhibition" ? "info" : "default"} label={file.track === "j" ? "J" : file.track === "exhibition" ? "场外" : "普通"} /></TableCell><TableCell>{formatDuration(file.track_duration_seconds)}</TableCell><TableCell>{formatTime(file.created_at)}</TableCell><TableCell align="right"><Tooltip title="下载"><IconButton size="small" aria-label={`下载投稿 ${file.file_name}`} onClick={() => void api.downloadAdminSubmission(file.id).catch((err) => setError(err.message))}><Download size={16} /></IconButton></Tooltip><Tooltip title="替换"><IconButton component="label" size="small" aria-label={`替换投稿 ${file.file_name}`}><RefreshCw size={16} /><input hidden type="file" accept=".zip,.7z,.rar" onChange={(e) => { const next = e.target.files?.[0]; if (next) void api.replaceAdminSubmission(file.id, next).then(() => files.reload()).catch((err) => setError(err.message)); e.currentTarget.value = ""; }} /></IconButton></Tooltip><Tooltip title="删除"><IconButton size="small" color="error" aria-label={`删除投稿 ${file.file_name}`} onClick={() => void remove(file)}><Trash2 size={16} /></IconButton></Tooltip></TableCell></TableRow>)}</TableBody></Table></TableContainer> : null}<BatchDeleteDialog open={deleteOpen} count={selected.size} label="份投稿" busy={deleting} onClose={() => setDeleteOpen(false)} onConfirm={() => void removeSelected()} /></Stack>;
}

function AdminGuess() {
  const charts = useResource(api.adminCharts, []);
  const issues = useResource(api.importIssues, []);
  const candidates = useResource(api.authorCandidates, []);
  const [editing, setEditing] = useState<GuessChartRead | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [summary, setSummary] = useState("");
  const [error, setError] = useState("");
  async function importArchive(file?: File) { if (!file) return; try { const result = await api.importCharts(file); setSummary(`已新增 ${result.charts.length} 张谱面`); setSelected(new Set()); await Promise.all([charts.reload(), issues.reload()]); } catch (err) { setError(err instanceof Error ? err.message : "导入失败"); } }
  async function parseAll() { try { const result = await api.parseSubmissions(); setSummary(`扫描 ${result.scanned}，新增 ${result.created}，更新 ${result.updated}，删除 ${result.deleted}，问题 ${result.issues}`); setSelected(new Set()); await Promise.all([charts.reload(), issues.reload()]); } catch (err) { setError(err instanceof Error ? err.message : "解析失败"); } }
  async function remove(chart: GuessChartRead) { if (!window.confirm(`确认删除《${chart.title}》${chart.level}？`)) return; try { await api.deleteChart(chart.id); setSelected((current) => { const next = new Set(current); next.delete(chart.id); return next; }); await charts.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } }
  async function removeSelected() { setDeleting(true); setError(""); try { const result = await api.batchDeleteAdminCharts([...selected]); setSummary(result.message); setSelected(new Set()); setDeleteOpen(false); await Promise.all([charts.reload(), issues.reload()]); } catch (err) { setError(err instanceof Error ? err.message : "批量删除失败"); setDeleteOpen(false); } finally { setDeleting(false); } }
  return <Stack spacing={3}><Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}><Button component="label" variant="contained" startIcon={<FileArchive size={17} />}>新增谱面<input hidden type="file" accept=".zip,.7z,.rar" onChange={(e) => { void importArchive(e.target.files?.[0]); e.currentTarget.value = ""; }} /></Button><Button variant="outlined" startIcon={<RefreshCw size={17} />} onClick={() => void parseAll()}>重新解析全部来源</Button><Button variant="outlined" startIcon={<Check size={17} />} disabled={!charts.data?.length} onClick={() => setSelected(new Set(charts.data?.map((chart) => chart.id) || []))}>全选</Button><Button color="error" variant="outlined" startIcon={<Trash2 size={17} />} disabled={!selected.size} onClick={() => setDeleteOpen(true)}>删除 {selected.size} 项</Button></Stack>{summary ? <Alert severity="success">{summary}</Alert> : null}{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={charts.loading} error={charts.error} empty={!charts.data?.length ? "暂无谱面" : undefined} />{charts.data?.length ? <TableContainer component={Paper} variant="outlined"><Table size="small"><TableHead><TableRow><TableCell padding="checkbox"><Checkbox checked={selected.size === charts.data.length} indeterminate={selected.size > 0 && selected.size < charts.data.length} onChange={(event) => setSelected(event.target.checked ? new Set(charts.data?.map((chart) => chart.id)) : new Set())} slotProps={{ input: { "aria-label": "选择全部谱面" } }} /></TableCell><TableCell>谱面</TableCell><TableCell>曲师</TableCell><TableCell>谱师</TableCell><TableCell>等级</TableCell><TableCell>赛道</TableCell><TableCell>来源</TableCell><TableCell align="right">操作</TableCell></TableRow></TableHead><TableBody>{charts.data.map((chart) => <TableRow key={chart.id} selected={selected.has(chart.id)}><TableCell padding="checkbox"><Checkbox checked={selected.has(chart.id)} onChange={() => setSelected((current) => { const next = new Set(current); if (next.has(chart.id)) next.delete(chart.id); else next.add(chart.id); return next; })} slotProps={{ input: { "aria-label": `选择 ${chart.title} ${chart.level}` } }} /></TableCell><TableCell sx={{ fontWeight: 650 }}>{chart.title}</TableCell><TableCell>{chart.author}</TableCell><TableCell>{chart.designer || "-"}</TableCell><TableCell>{chart.level}</TableCell><TableCell>{chart.lane === "j" ? "J" : "普通"}</TableCell><TableCell>{chart.source_submission_type}</TableCell><TableCell align="right"><Tooltip title="编辑"><IconButton size="small" aria-label={`编辑谱面 ${chart.title} ${chart.level}`} onClick={() => setEditing(chart)}><Pencil size={16} /></IconButton></Tooltip><Tooltip title="删除"><IconButton size="small" color="error" aria-label={`删除谱面 ${chart.title} ${chart.level}`} onClick={() => void remove(chart)}><Trash2 size={16} /></IconButton></Tooltip></TableCell></TableRow>)}</TableBody></Table></TableContainer> : null}<AuthorCandidatesEditor resource={candidates} setError={setError} />{issues.data?.length ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h3" sx={{ mb: 1.5 }}>解析问题</Typography><Stack spacing={1}>{issues.data.map((issue) => <Alert key={issue.id} severity="warning"><strong>{issue.file_name || issue.source_type}</strong>：{issue.message}</Alert>)}</Stack></Paper> : null}<ChartEditDialog chart={editing} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await charts.reload(); }} /><BatchDeleteDialog open={deleteOpen} count={selected.size} label="张谱面" busy={deleting} onClose={() => setDeleteOpen(false)} onConfirm={() => void removeSelected()} /></Stack>;
}

function AuthorCandidatesEditor({ resource, setError }: { resource: Resource<AuthorCandidateAdmin[]>; setError: (value: string) => void }) {
  const [rows, setRows] = useState<AuthorCandidateAdmin[]>([]);
  useEffect(() => { if (resource.data) setRows(resource.data); }, [resource.data]);
  async function save() { try { await api.saveAuthorCandidates(rows.map((row) => ({ user_id: row.user.id, display_id: row.display_id }))); await resource.reload(); } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); } }
  return <Paper variant="outlined" sx={{ p: 2 }}><Stack direction="row" sx={{ mb: 1.5, justifyContent: "space-between", alignItems: "center" }}><Typography variant="h3">谱师候选展示 ID</Typography><Button variant="outlined" size="small" startIcon={<Save size={15} />} onClick={() => void save()}>保存展示 ID</Button></Stack><Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 1 }}>{rows.map((row, index) => <Paper key={row.user.id} variant="outlined" sx={{ p: 1.25 }}><Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="body2" sx={{ fontWeight: 650 }}>{row.user.user_code}</Typography><Typography variant="caption" color="text.secondary">{row.user.identity === "participant" ? "参赛者" : "观众"} · {row.song_count} 首曲目</Typography></Box><TextField size="small" label="展示 ID" value={row.display_id} onChange={(e) => setRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, display_id: e.target.value } : item))} sx={{ width: 150 }} /></Stack></Paper>)}</Box></Paper>;
}

function ChartEditDialog({ chart, onClose, onSaved }: { chart: GuessChartRead | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const [form, setForm] = useState({ title: "", author: "", designer: "", level: "", lane: "normal", guess_group_key: "", is_self_selected: false });
  const [error, setError] = useState("");
  useEffect(() => { if (chart) setForm({ title: chart.title, author: chart.author, designer: chart.designer, level: chart.level, lane: chart.lane, guess_group_key: chart.guess_group_key, is_self_selected: chart.is_self_selected }); }, [chart]);
  if (!chart) return null;
  return <Dialog open onClose={onClose} fullWidth maxWidth="sm"><DialogTitle>编辑谱面</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><TextField label="标题" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /><TextField label="曲师" value={form.author} onChange={(e) => setForm({ ...form, author: e.target.value })} /><TextField label="谱师" value={form.designer} onChange={(e) => setForm({ ...form, designer: e.target.value })} /><TextField label="等级" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })} /><FormControl><InputLabel>赛道</InputLabel><Select label="赛道" value={form.lane} onChange={(e) => setForm({ ...form, lane: e.target.value })}><MenuItem value="normal">普通</MenuItem><MenuItem value="j">J</MenuItem></Select></FormControl><TextField label="猜测分组" value={form.guess_group_key} onChange={(e) => setForm({ ...form, guess_group_key: e.target.value })} /><FormControlLabel control={<Switch checked={form.is_self_selected} onChange={(e) => setForm({ ...form, is_self_selected: e.target.checked })} />} label="自选谱面" />{error ? <Alert severity="error">{error}</Alert> : null}</Stack></DialogContent><DialogActions><Button onClick={onClose}>取消</Button><Button variant="contained" startIcon={<Save size={16} />} onClick={() => void api.updateChart(chart.id, form).then(onSaved).catch((err) => setError(err.message))}>保存</Button></DialogActions></Dialog>;
}

function AdminStats() {
  const [scope, setScope] = useState<"all" | "j">("all");
  const stats = useResource(() => api.guessStats(scope), [scope]);
  return <Stack spacing={2}><Tabs value={scope} onChange={(_, value) => setScope(value)}><Tab value="all" label="全部" /><Tab value="j" label="J 赛道" /></Tabs><ResourceState loading={stats.loading} error={stats.error} />{stats.data ? <StatsContent stats={stats.data} /> : null}</Stack>;
}

function StatsContent({ stats }: { stats: GuessStats }) {
  const overview = [["谱面", stats.overview.charts], ["查看", stats.overview.views], ["真爱票", stats.overview.love_votes], ["欢乐票", stats.overview.funny_votes], ["有效猜测", stats.overview.counted_guesses], ["猜对", stats.overview.correct_guesses], ["准确率", stats.overview.accuracy === null ? "-" : `${stats.overview.accuracy}%`], ["参与用户", stats.overview.users_guessing]];
  return <Stack spacing={3}><Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, 1fr)", md: "repeat(4, 1fr)" }, gap: 1.5 }}>{overview.map(([label, value]) => <Paper key={String(label)} variant="outlined" sx={{ p: 2 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h2" sx={{ mt: 0.5 }}>{value}</Typography></Paper>)}</Box><StatsTable title="逐谱统计" rows={stats.chart_stats} columns={["title", "level", "lane", "views", "love_votes", "funny_votes", "guess_count", "accuracy"]} /><StatsTable title="用户准确率" rows={stats.user_stats} columns={["user", "guesses", "counted", "correct", "accuracy"]} /><StatsTable title="候选选择" rows={stats.candidate_stats} columns={["display_id", "user", "selected_count"]} /><StatsTable title="猜测明细" rows={stats.guess_details} columns={["title", "guesser", "guessed_display_id", "actual_author", "is_correct"]} /></Stack>;
}

function StatsTable({ title, rows, columns }: { title: string; rows: Array<Record<string, unknown>>; columns: string[] }) {
  const labels: Record<string, string> = { title: "曲目", level: "等级", lane: "赛道", views: "查看", love_votes: "真爱票", funny_votes: "欢乐票", guess_count: "猜测", accuracy: "准确率", user: "用户", guesses: "提交", counted: "有效", correct: "正确", display_id: "展示 ID", selected_count: "被选次数", guesser: "猜测人", guessed_display_id: "选择", actual_author: "实际作者", is_correct: "结果" };
  return <Paper variant="outlined" sx={{ overflow: "hidden" }}><Typography variant="h3" sx={{ p: 2 }}>{title}</Typography><TableContainer sx={{ maxHeight: 420 }}><Table size="small" stickyHeader><TableHead><TableRow>{columns.map((column) => <TableCell key={column}>{labels[column] || column}</TableCell>)}</TableRow></TableHead><TableBody>{rows.length ? rows.map((row, index) => <TableRow key={index}>{columns.map((column) => <TableCell key={column}>{formatStatValue(column, row[column])}</TableCell>)}</TableRow>) : <TableRow><TableCell colSpan={columns.length} align="center">暂无数据</TableCell></TableRow>}</TableBody></Table></TableContainer></Paper>;
}

function formatStatValue(key: string, value: unknown): ReactNode { if (value === null || value === undefined) return "-"; if (key === "accuracy" && typeof value === "number") return `${value}%`; if (key === "is_correct") return value ? <Chip size="small" color="success" label="正确" /> : <Chip size="small" variant="outlined" label="错误" />; if (typeof value === "object") { const user = value as { user_code?: string; display_name?: string }; return user.display_name || user.user_code || "-"; } return String(value); }

function toDateTimeInput(value?: string | null): string { if (!value) return ""; const date = new Date(value); const offset = date.getTimezoneOffset() * 60_000; return new Date(date.getTime() - offset).toISOString().slice(0, 16); }
