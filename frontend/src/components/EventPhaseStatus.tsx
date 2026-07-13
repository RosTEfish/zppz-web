import { useEffect, useMemo, useState } from "react";
import { Box, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import { Clock3 } from "lucide-react";
import type { EventPhaseName, EventPhasesRead } from "../api/v1";

export const PHASE_LABELS: Record<EventPhaseName, string> = {
  registration: "报名",
  draw: "抽签",
  submission_1: "征稿一阶段",
  swap: "换曲",
  submission_2: "征稿二阶段",
  guess: "猜谱",
  reveal: "揭晓",
  closed: "已结束",
};

export function formatCountdown(target?: string | null, now = Date.now()): string {
  if (!target) return "暂无下一阶段时间";
  const remaining = Math.max(0, new Date(target).getTime() - now);
  if (!remaining) return "即将切换阶段";
  const seconds = Math.floor(remaining / 1000);
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days ? `${days} 天 ` : ""}${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

export function PhaseHeadline({ phases }: { phases: EventPhasesRead }) {
  const clockOffset = useMemo(() => {
    if (!phases.server_time) return 0;
    const serverTime = new Date(phases.server_time).getTime();
    return Number.isFinite(serverTime) ? serverTime - Date.now() : 0;
  }, [phases.server_time]);
  const [now, setNow] = useState(() => Date.now() + clockOffset);
  useEffect(() => {
    setNow(Date.now() + clockOffset);
    const timer = window.setInterval(() => setNow(Date.now() + clockOffset), 1000);
    return () => window.clearInterval(timer);
  }, [clockOffset]);
  const currentWindow = phases.phases.find((item) => item.phase === phases.active_phase);
  const target = phases.next_transition_at || currentWindow?.ends_at;
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
      <Chip color="primary" label={`当前：${PHASE_LABELS[phases.active_phase]}`} sx={{ fontWeight: 750 }} />
      {phases.phase_mode === "manual" ? <Chip color="warning" variant="outlined" label="管理员手动接管" /> : null}
      <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", color: "text.secondary" }}>
        <Clock3 size={16} aria-hidden="true" />
        <Typography variant="body2" aria-live="polite" aria-atomic="true"><Box component="span" sx={{ fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>{formatCountdown(target, now)}</Box>{target ? ` · ${new Date(target).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}` : ""}</Typography>
      </Stack>
    </Stack>
  );
}

export function PhaseTimeline({ phases }: { phases: EventPhasesRead }) {
  const ordered = useMemo(() => phases.phases, [phases.phases]);
  const currentIndex = ordered.findIndex((item) => item.phase === phases.active_phase);
  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 }, overflow: "hidden" }}>
      <Typography variant="overline" color="text.secondary">赛事时间轴 · 北京时间</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, minmax(0, 1fr))", sm: `repeat(${Math.max(ordered.length, 1)}, minmax(90px, 1fr))` }, gap: 1, mt: 1 }}>
        {ordered.map((item, index) => {
          const active = item.phase === phases.active_phase;
          return <Box key={item.phase} sx={{ minWidth: 0, opacity: index < currentIndex ? 0.56 : 1 }}><LinearProgress variant="determinate" value={index <= currentIndex ? 100 : 0} color={active ? "primary" : "inherit"} sx={{ height: active ? 5 : 3, mb: 0.75 }} /><Typography variant="caption" sx={{ display: "block", fontWeight: active ? 800 : 650 }}>{PHASE_LABELS[item.phase]}</Typography><Typography variant="caption" color="text.secondary">{new Date(item.ends_at).toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric" })}</Typography></Box>;
        })}
      </Box>
    </Paper>
  );
}
