import { useEffect, useState } from "react";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, InputLabel, MenuItem, Paper, Select, Stack, TextField, Typography } from "@mui/material";
import { ArrowLeftRight, ArrowRight, Save } from "lucide-react";
import { api, formatTime, type EventPhaseName, type EventPhasesUpdate, type SwapAuditAssignmentRead, type SwapAuditRequestRead, type SwapAuditRoundRead } from "../../api/v1";
import { PHASE_LABELS } from "../../components/EventPhaseStatus";
import { LoadingBlock, useApiResource } from "../../components/PagePrimitives";
import { queryKeys } from "../../api/queryKeys";
import { useSnackbar } from "notistack";
import { useConfig } from "../../contexts/ConfigContext";

const PHASE_ORDER = Object.keys(PHASE_LABELS) as EventPhaseName[];

export default function AdminPhasesAndSwap() {
  const { enqueueSnackbar } = useSnackbar();
  const { phases, refreshConfig } = useConfig();
  const [form, setForm] = useState<EventPhasesUpdate | null>(null);
  const [confirmPhase, setConfirmPhase] = useState<EventPhaseName | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const audit = useApiResource(queryKeys.admin.swapAudit, api.swapAudit);

  useEffect(() => {
    if (!phases) return;
    setForm({
      phase_mode: phases.phase_mode,
      manual_phase: phases.manual_phase,
      phases: PHASE_ORDER.map((phase) => phases.phases.find((item) => item.phase === phase) ?? { phase, starts_at: "", ends_at: "" }),
    });
  }, [phases]);

  if (!form) return <LoadingBlock />;

  const updateWindow = (phase: EventPhaseName, key: "starts_at" | "ends_at", value: string) => {
    setForm((current) => current ? {
      ...current,
      phases: current.phases.map((item) => item.phase === phase ? { ...item, [key]: value ? new Date(value).toISOString() : "" } : item),
    } : current);
  };

  async function save(nextForm = form) {
    const partial = nextForm.phases.find((item) => Boolean(item.starts_at) !== Boolean(item.ends_at));
    if (partial) {
      setError(`${PHASE_LABELS[partial.phase]}需要同时填写开始和结束时间`);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.updateEventPhases({ ...nextForm, phases: nextForm.phases.filter((item) => item.starts_at && item.ends_at) });
      await refreshConfig();
      enqueueSnackbar("阶段设置已保存", { variant: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "阶段设置保存失败");
    } finally {
      setBusy(false);
      setConfirmPhase(null);
    }
  }

  return (
    <Stack spacing={2}>
      <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "center" } }}>
          <Box>
            <Typography variant="h3">赛事阶段</Typography>
            <Typography variant="body2" color="text.secondary">报名 → Stage1 投稿 → Stage2 投稿 / 换曲 → 猜谱。时间以 UTC 存储，输入与展示使用北京时间。</Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button variant={form.phase_mode === "auto" ? "contained" : "outlined"} disabled={busy || form.phase_mode === "auto"} onClick={() => void save({ ...form, phase_mode: "auto", manual_phase: null })}>恢复自动</Button>
            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel>手动阶段</InputLabel>
              <Select label="手动阶段" value={form.phase_mode === "manual" ? form.manual_phase || "" : ""} onChange={(event) => setConfirmPhase(event.target.value as EventPhaseName)}>
                {PHASE_ORDER.map((phase) => <MenuItem key={phase} value={phase}>{PHASE_LABELS[phase]}</MenuItem>)}
              </Select>
            </FormControl>
          </Stack>
        </Stack>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" }, gap: 1.5, mt: 2 }}>
          {form.phases.map((item) => (
            <Paper key={item.phase} variant="outlined" sx={{ p: 1.5 }}>
              <Typography variant="body2" sx={{ fontWeight: 800, mb: 1 }}>{PHASE_LABELS[item.phase]}</Typography>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                <TextField fullWidth size="small" type="datetime-local" label="开始" slotProps={{ inputLabel: { shrink: true } }} value={toDateTimeInput(item.starts_at)} onChange={(event) => updateWindow(item.phase, "starts_at", event.target.value)} />
                <TextField fullWidth size="small" type="datetime-local" label="结束" slotProps={{ inputLabel: { shrink: true } }} value={toDateTimeInput(item.ends_at)} onChange={(event) => updateWindow(item.phase, "ends_at", event.target.value)} />
              </Stack>
            </Paper>
          ))}
        </Box>
        <Button variant="contained" startIcon={<Save size={16} />} disabled={busy} onClick={() => void save()} sx={{ mt: 2 }}>保存时间表</Button>
      </Paper>

      <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><ArrowLeftRight size={19} /><Typography variant="h3">换曲审计记录</Typography></Stack>
          <Chip color="info" variant="outlined" label="即时 roll · 无需 Finalize" />
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>保留旧批处理换曲轮次和新的连续换曲记录，仅供审计查看；管理员不再审批、驳回或 Finalize。</Typography>
        {audit.data?.rounds?.length ? <Stack spacing={1} sx={{ mt: 2 }}>{audit.data.rounds.map((round) => <SwapAuditSummary key={round.id} round={round} />)}</Stack> : null}
        {audit.data?.requests.length ? <Stack spacing={1.5} sx={{ mt: 2 }}>{audit.data.requests.map((request) => <SwapAuditRequestCard key={request.id} request={request} />)}</Stack> : <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>暂无换曲审计记录</Typography>}
      </Paper>
      {error ? <Alert severity="error" aria-live="polite">{error}</Alert> : null}

      <Dialog open={Boolean(confirmPhase)} onClose={() => setConfirmPhase(null)}>
        <DialogTitle>确认手动切换阶段</DialogTitle>
        <DialogContent><Alert severity="warning">切换至“{confirmPhase ? PHASE_LABELS[confirmPhase] : ""}”后会立即按该阶段开放能力。</Alert></DialogContent>
        <DialogActions><Button onClick={() => setConfirmPhase(null)}>取消</Button><Button color="warning" variant="contained" onClick={() => confirmPhase && void save({ ...form, phase_mode: "manual", manual_phase: confirmPhase })}>确认切换</Button></DialogActions>
      </Dialog>
    </Stack>
  );
}

function SwapAuditSummary({ round }: { round: SwapAuditRoundRead }) {
  const legacy = round.round_kind === "legacy";
  return <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap sx={{ alignItems: { sm: "center" }, flexWrap: "wrap" }}><Chip color={legacy ? "default" : "success"} label={legacy ? "旧批处理轮次（只读）" : "连续换曲轮次"} /><Chip variant="outlined" label={`${round.roll_count} 次 roll`} /><Typography variant="caption" color="text.secondary">{formatTime(round.starts_at)} - {formatTime(round.ends_at)}</Typography></Stack>;
}

function SwapAuditRequestCard({ request }: { request: SwapAuditRequestRead }) {
  return <Paper variant="outlined" sx={{ p: { xs: 1.5, md: 2 } }}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}><Box><Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}><Typography variant="h3">{request.user.display_name || request.user.user_code}</Typography><Chip size="small" variant="outlined" label={`Roll #${request.id}`} /><Chip size="small" color={request.status === "completed" ? "success" : "default"} label={request.status} /></Stack><Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{request.user.user_code} · {request.items.length} 首 · {request.created_at ? formatTime(request.created_at) : ""}</Typography></Box></Stack><Stack spacing={1} sx={{ mt: 1.5 }}>{request.items.map((item) => <Paper key={`${request.id}-${item.position}`} variant="outlined" sx={{ p: 1.25, bgcolor: "background.default" }}><Stack direction={{ xs: "column", sm: "row" }} spacing={{ xs: 0.75, sm: 1.5 }} sx={{ alignItems: { sm: "center" } }}><Typography variant="caption" sx={{ minWidth: { sm: 48 }, fontWeight: 800, color: "text.secondary" }}>第 {item.position + 1} 首</Typography><SwapAuditSong label="原曲" assignment={item.original} /><ArrowRight size={18} /><SwapAuditSong label="换后" assignment={item.replacement} /></Stack></Paper>)}</Stack></Paper>;
}

function SwapAuditSong({ label, assignment }: { label: string; assignment?: SwapAuditAssignmentRead | null }) {
  return <Box sx={{ minWidth: 0, flex: 1 }}><Typography variant="caption" color="text.secondary">{label}</Typography>{assignment ? <><Typography sx={{ fontWeight: 800, overflowWrap: "anywhere" }}>{assignment.song.song_name}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: "block", overflowWrap: "anywhere" }}>{assignment.song.artist}</Typography></> : <Typography variant="body2" color="text.secondary">暂无替换曲目</Typography>}</Box>;
}

function toDateTimeInput(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
