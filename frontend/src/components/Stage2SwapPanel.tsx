import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Chip, Divider, FormControlLabel, Paper, Stack, Typography } from "@mui/material";
import { ArrowLeftRight, PackageMinus, RefreshCw } from "lucide-react";
import { api, type SwapMeRead, type SwapMode, type SwapRollRead } from "../api/v1";
import { ResourceState, type ApiResource, useApiResource } from "./PagePrimitives";
import { queryKeys } from "../api/queryKeys";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";

export default function Stage2SwapPanel({ onUpdated }: { onUpdated?: (data: SwapMeRead) => void } = {}) {
  const { user } = useAuth();
  const { phases } = useConfig();
  const enabled = user?.identity === "participant" && Boolean(phases?.capabilities.swap);
  const resource = useApiResource(queryKeys.swap, api.mySwap, enabled);
  if (!enabled) return null;
  return <Stage2SwapPanelContent resource={resource} onUpdated={onUpdated} />;
}

function Stage2SwapPanelContent({ resource, onUpdated }: { resource: ApiResource<SwapMeRead>; onUpdated?: (data: SwapMeRead) => void }) {
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

  async function submit(mode: SwapMode) {
    if (!selected.size) return;
    setBusy(true);
    setError("");
    try {
      const next = await api.rollMySwap([...selected], mode);
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
  const selectedCount = selected.size;
  const canSubmit = Boolean(resource.data?.is_open && selectedCount && !busy);

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
            每次可选择任意数量的当前有效曲目：放回并抽取等量新曲，或仅放回不抽取。投回的曲目会永久排除给你，但仍可能被其他参赛者抽到；已投稿曲目需先删除投稿。
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
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 1.5 }}>
            <Button
              variant="contained"
              startIcon={<RefreshCw size={16} />}
              disabled={!canSubmit}
              onClick={() => void submit("return_and_draw")}
            >
              {busy ? "处理中…" : `放回并抽取（${selectedCount} 首）`}
            </Button>
            <Button
              variant="outlined"
              startIcon={<PackageMinus size={16} />}
              disabled={!canSubmit}
              onClick={() => void submit("return_only")}
            >
              {busy ? "处理中…" : `放回并不抽取（${selectedCount} 首）`}
            </Button>
          </Stack>
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
        <Alert severity={item.replacement ? "success" : "info"} key={item.id}>
          {item.replacement
            ? `${item.original.song.song_name} → ${item.replacement.song.song_name}`
            : `${item.original.song.song_name} 已放回，未抽取新曲`}
        </Alert>
      ))}
    </Stack>
  );
}
