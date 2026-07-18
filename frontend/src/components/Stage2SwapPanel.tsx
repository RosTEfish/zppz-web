import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Chip, Divider, FormControlLabel, Paper, Stack, Typography } from "@mui/material";
import { ArrowLeftRight, RefreshCw } from "lucide-react";
import { api, type SwapMeRead, type SwapRollRead } from "../api/v1";
import { ResourceState, type Resource, useResource } from "./PagePrimitives";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";

export default function Stage2SwapPanel({ onUpdated }: { onUpdated?: (data: SwapMeRead) => void } = {}) {
  const { user } = useAuth();
  const { phases } = useConfig();
  const enabled = user?.identity === "participant" && Boolean(phases?.capabilities.swap);
  const resource = useResource(api.mySwap, [], enabled);
  if (!enabled) return null;
  return <Stage2SwapPanelContent resource={resource} onUpdated={onUpdated} />;
}

function Stage2SwapPanelContent({ resource, onUpdated }: { resource: Resource<SwapMeRead>; onUpdated?: (data: SwapMeRead) => void }) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const assignmentKey = resource.data?.assignments.map((row) => `${row.id}:${row.can_swap}`).join(",") ?? "";

  useEffect(() => {
    setSelected(new Set());
  }, [assignmentKey]);

  const toggle = (id: number) => setSelected((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  async function roll() {
    if (!selected.size) return;
    setBusy(true);
    setError("");
    try {
      const next = await api.rollMySwap([...selected]);
      resource.setData(next);
      onUpdated?.(next);
      setSelected(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "换曲失败");
    } finally {
      setBusy(false);
    }
  }

  const lastRoll = resource.data?.last_roll;
  const endAt = resource.data?.round?.ends_at;

  return (
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 } }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <ArrowLeftRight size={20} />
          <Typography variant="h3">Stage2 投稿与换曲</Typography>
          {resource.data ? <Chip size="small" color={resource.data.is_open ? "success" : "default"} label={resource.data.is_open ? "换曲开放" : "换曲已关闭"} /> : null}
        </Stack>
        {endAt ? <Typography variant="caption" color="text.secondary">截止：{new Date(endAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}</Typography> : null}
      </Stack>
      <Divider sx={{ my: 1.5 }} />
      <ResourceState loading={resource.loading} error={resource.error} />
      {error ? <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert> : null}
      {resource.data ? (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            每次可选择任意数量的当前有效曲目并立即 roll 等量替换。投回的曲目会永久排除给你，但仍可能被其他参赛者抽到；已投稿曲目需先删除投稿。
          </Typography>
          <Stack>
            {resource.data.assignments.map((row) => (
              <FormControlLabel
                key={row.id}
                control={<Checkbox checked={selected.has(row.id)} disabled={busy || !resource.data?.is_open || !row.can_swap} onChange={() => toggle(row.id)} />}
                label={(
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={{ sm: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 700, color: row.has_submission ? "text.disabled" : undefined }}>{row.song.song_name}</Typography>
                    <Typography variant="caption" color="text.secondary">{row.song.artist}</Typography>
                    {row.has_submission ? <Chip size="small" variant="outlined" label="已投稿，请先删除投稿" /> : null}
                  </Stack>
                )}
                sx={{ opacity: row.has_submission ? 0.65 : 1 }}
              />
            ))}
          </Stack>
          <Button
            variant="contained"
            startIcon={<RefreshCw size={16} />}
            disabled={!resource.data.is_open || !selected.size || busy}
            onClick={() => void roll()}
            sx={{ mt: 1.5 }}
          >
            {busy ? "换曲中…" : `立即换曲（${selected.size} 首）`}
          </Button>
          {lastRoll ? <RollResult roll={lastRoll} /> : null}
        </>
      ) : null}
    </Paper>
  );
}

function RollResult({ roll }: { roll: SwapRollRead }) {
  return (
    <Stack spacing={1} sx={{ mt: 2 }}>
      <Typography variant="subtitle2">最近一次换曲结果</Typography>
      {roll.items.map((item) => (
        <Alert severity="success" key={item.id}>
          {item.original.song.song_name} → {item.replacement?.song.song_name || "暂无替换曲目"}
        </Alert>
      ))}
    </Stack>
  );
}
