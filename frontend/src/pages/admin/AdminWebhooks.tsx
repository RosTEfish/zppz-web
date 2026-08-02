import { useState } from "react";
import useSWR from "swr";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Paper,
  Skeleton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { Copy, KeyRound, Plus, RadioTower, RefreshCw, RotateCw, Send, ShieldCheck, Trash2 } from "lucide-react";
import { useSnackbar } from "notistack";
import { api, formatTime, type WebhookCredentialsRead, type WebhookIntegrationRead } from "../../api/v1";
import { PageHeader } from "../../components/PagePrimitives";

const STATUS_META: Record<string, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  active: { label: "运行中", color: "success" },
  failing: { label: "投递异常", color: "error" },
  pending: { label: "等待验证", color: "warning" },
  revoked: { label: "已停用", color: "default" },
};

const fetchWebhookIntegrations = () => api.webhookIntegrations();

function SecretField({ label, value, onCopy }: { label: string; value: string; onCopy: (value: string) => void }) {
  return <TextField
    label={label}
    value={value}
    fullWidth
    multiline
    minRows={2}
    slotProps={{ input: { readOnly: true, endAdornment: <Tooltip title="复制"><Button size="small" onClick={() => onCopy(value)} startIcon={<Copy size={15} />}>复制</Button></Tooltip> } }}
    sx={{ "& textarea": { fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace", fontSize: 13, wordBreak: "break-all" } }}
  />;
}

function IntegrationCard({
  item,
  busy,
  onTest,
  onRetry,
  onRotate,
  onRevoke,
}: {
  item: WebhookIntegrationRead;
  busy: string;
  onTest: (item: WebhookIntegrationRead) => void;
  onRetry: (item: WebhookIntegrationRead) => void;
  onRotate: (item: WebhookIntegrationRead) => void;
  onRevoke: (item: WebhookIntegrationRead) => void;
}) {
  const endpoint = item.endpoint;
  const meta = STATUS_META[endpoint?.status ?? (item.is_active ? "pending" : "revoked")] ?? STATUS_META.pending;
  const disabled = Boolean(busy) || !item.is_active;
  return <Paper variant="outlined" sx={{ overflow: "hidden", borderColor: endpoint?.status === "failing" ? "error.light" : "divider" }}>
    <Box sx={{ height: 4, bgcolor: endpoint?.status === "active" ? "success.main" : endpoint?.status === "failing" ? "error.main" : "warning.main" }} />
    <Stack spacing={2} sx={{ p: { xs: 2, md: 2.5 } }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-start" }}>
        <Box sx={{ width: 38, height: 38, display: "grid", placeItems: "center", bgcolor: "action.hover", borderRadius: 1 }}><RadioTower size={20} /></Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Typography variant="h3" sx={{ fontSize: 18 }}>{item.name}</Typography>
            <Chip size="small" color={meta.color} label={meta.label} />
          </Stack>
          <Typography variant="caption" color="text.secondary">{item.token_prefix} · 创建于 {formatTime(item.created_at)}</Typography>
        </Box>
      </Stack>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" }, gap: 1 }}>
        {[
          ["待投递", item.pending_deliveries],
          ["失败", item.failed_deliveries],
          ["连续失败", endpoint?.consecutive_failures ?? 0],
          ["协议", `v${endpoint?.schema_version ?? 1}`],
        ].map(([label, value]) => <Box key={label} sx={{ p: 1.25, bgcolor: "action.hover", borderRadius: 1 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography sx={{ fontWeight: 800, fontSize: 18 }}>{value}</Typography></Box>)}
      </Box>

      <Box>
        <Typography variant="caption" color="text.secondary">回调地址</Typography>
        <Typography variant="body2" sx={{ fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace", overflowWrap: "anywhere" }}>{endpoint?.callback_url || "Bot 尚未注册回调地址"}</Typography>
      </Box>
      {endpoint?.events.length ? <Stack direction="row" spacing={1}>{endpoint.events.map((event) => <Chip key={event} size="small" variant="outlined" label={event} />)}</Stack> : null}
      {endpoint?.last_error ? <Alert severity="error">{endpoint.last_error}</Alert> : null}
      <Typography variant="caption" color="text.secondary">最近成功：{endpoint?.last_success_at ? formatTime(endpoint.last_success_at) : "暂无"}　最近失败：{endpoint?.last_failure_at ? formatTime(endpoint.last_failure_at) : "暂无"}</Typography>
      <Divider />
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
        <Button size="small" disabled={disabled || !endpoint} startIcon={<Send size={15} />} onClick={() => onTest(item)}>测试</Button>
        <Button size="small" disabled={disabled || item.failed_deliveries === 0} startIcon={<RefreshCw size={15} />} onClick={() => onRetry(item)}>重试失败</Button>
        <Button size="small" disabled={disabled} startIcon={<RotateCw size={15} />} onClick={() => onRotate(item)}>轮换凭据</Button>
        <Button size="small" color="error" disabled={disabled} startIcon={<Trash2 size={15} />} onClick={() => onRevoke(item)}>撤销</Button>
      </Stack>
    </Stack>
  </Paper>;
}

export default function AdminWebhooks() {
  const { enqueueSnackbar } = useSnackbar();
  const { data, error, isLoading, mutate } = useSWR("admin-webhook-integrations", fetchWebhookIntegrations);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [credentials, setCredentials] = useState<WebhookCredentialsRead | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<WebhookIntegrationRead | null>(null);
  const [busy, setBusy] = useState("");

  async function copy(value: string) {
    await navigator.clipboard.writeText(value);
    enqueueSnackbar("已复制", { variant: "success" });
  }

  async function create() {
    if (!name.trim()) return;
    setBusy("create");
    try {
      setCredentials(await api.createWebhookIntegration(name.trim()));
      setCreateOpen(false);
      setName("");
      await mutate();
    } catch (err) {
      enqueueSnackbar(err instanceof Error ? err.message : "创建失败", { variant: "error" });
    } finally {
      setBusy("");
    }
  }

  async function action(id: string, task: () => Promise<unknown>, success: string) {
    setBusy(id);
    try {
      await task();
      enqueueSnackbar(success, { variant: "success" });
      await mutate();
    } catch (err) {
      enqueueSnackbar(err instanceof Error ? err.message : "操作失败", { variant: "error" });
    } finally {
      setBusy("");
    }
  }

  async function rotate(item: WebhookIntegrationRead) {
    setBusy(item.id);
    try {
      setCredentials(await api.rotateWebhookCredentials(item.id));
      await mutate();
    } catch (err) {
      enqueueSnackbar(err instanceof Error ? err.message : "轮换失败", { variant: "error" });
    } finally {
      setBusy("");
    }
  }

  async function revoke() {
    if (!revokeTarget) return;
    const target = revokeTarget;
    setRevokeTarget(null);
    await action(target.id, () => api.revokeWebhookIntegration(target.id), "接入方已撤销");
  }

  return <Stack spacing={2.5}>
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, position: "relative", overflow: "hidden" }}>
      <Box sx={{ position: "absolute", inset: "0 auto 0 0", width: 5, bgcolor: "primary.main" }} />
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ alignItems: { md: "center" }, justifyContent: "space-between" }}>
        <PageHeader icon={ShieldCheck} title="Webhook 接入" meta="签发独立凭据，让外部 Bot 自助注册并可靠接收谱面事件" />
        <Button variant="contained" startIcon={<Plus size={17} />} onClick={() => setCreateOpen(true)}>创建接入方</Button>
      </Stack>
      <Alert severity="info" icon={<KeyRound size={19} />} sx={{ mt: 2 }}>Token 与签名密钥只显示一次。每个接入方应使用独立凭据，并由 Bot 在监听服务启动后调用订阅 API。</Alert>
    </Paper>

    {error ? <Alert severity="error">{error instanceof Error ? error.message : "加载 Webhook 接入失败"}</Alert> : null}
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", xl: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
      {isLoading ? [0, 1].map((item) => <Skeleton key={item} variant="rounded" height={330} />) : null}
      {data?.map((item) => <IntegrationCard key={item.id} item={item} busy={busy} onTest={(row) => void action(row.id, () => api.testWebhookIntegration(row.id), "测试事件已排队")} onRetry={(row) => void action(row.id, () => api.retryWebhookDeliveries(row.id), "失败投递已重新排队")} onRotate={(row) => void rotate(row)} onRevoke={setRevokeTarget} />)}
    </Box>
    {!isLoading && !data?.length ? <Paper variant="outlined" sx={{ p: 5, textAlign: "center" }}><RadioTower size={34} /><Typography variant="h3" sx={{ mt: 1 }}>尚未创建接入方</Typography><Typography color="text.secondary" sx={{ mt: 0.5 }}>创建凭据后，将 Token 与签名密钥安全交给 Bot 维护者。</Typography></Paper> : null}

    <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>创建 Webhook 接入方</DialogTitle>
      <DialogContent><TextField autoFocus fullWidth label="接入方名称" value={name} onChange={(event) => setName(event.target.value)} slotProps={{ htmlInput: { maxLength: 120 } }} sx={{ mt: 1 }} helperText="例如：主群通知 Bot" /></DialogContent>
      <DialogActions><Button onClick={() => setCreateOpen(false)}>取消</Button><Button variant="contained" disabled={!name.trim() || busy === "create"} onClick={() => void create()}>创建并生成凭据</Button></DialogActions>
    </Dialog>

    <Dialog open={Boolean(credentials)} onClose={() => setCredentials(null)} fullWidth maxWidth="md">
      <DialogTitle>保存一次性接入凭据</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{ mt: 1 }}><Alert severity="warning">关闭此窗口后，网站不会再次显示明文。请立即复制并通过安全渠道交给 Bot 维护者。</Alert>{credentials ? <><SecretField label="Integration Token" value={credentials.integration_token} onCopy={(value) => void copy(value)} /><SecretField label="Webhook Secret" value={credentials.webhook_secret} onCopy={(value) => void copy(value)} /></> : null}</Stack></DialogContent>
      <DialogActions><Button variant="contained" onClick={() => setCredentials(null)}>我已安全保存</Button></DialogActions>
    </Dialog>

    <Dialog open={Boolean(revokeTarget)} onClose={() => setRevokeTarget(null)} fullWidth maxWidth="sm">
      <DialogTitle>撤销 Webhook 接入</DialogTitle>
      <DialogContent><Alert severity="error">撤销后，该 Token 立即失效，所有待投递事件都会取消。此操作不能恢复。</Alert><Typography sx={{ mt: 2 }}>确认撤销“{revokeTarget?.name}”吗？</Typography></DialogContent>
      <DialogActions><Button onClick={() => setRevokeTarget(null)}>取消</Button><Button color="error" variant="contained" onClick={() => void revoke()}>确认撤销</Button></DialogActions>
    </Dialog>
  </Stack>;
}
