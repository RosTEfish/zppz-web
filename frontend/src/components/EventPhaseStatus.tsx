import { useEffect, useMemo, useState } from "react";
import { Box, Chip, Paper, Stack, Typography } from "@mui/material";
import { Clock3 } from "lucide-react";
import type { EventPhaseName, EventPhasesRead } from "../api/v1";

export const PHASE_LABELS: Record<EventPhaseName, string> = {
  registration: "报名",
  submission_1: "征稿一阶段",
  submission_2: "征稿二阶段",
  submission_buffer: "交稿缓冲期",
  guess: "猜谱",
};

const PHASE_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatPhaseDateTime(value: string): string {
  return PHASE_DATE_TIME_FORMATTER.format(new Date(value));
}

export function isGuessEnded(phases: EventPhasesRead, now?: number): boolean {
  if (phases.active_phase !== null) return false;
  const referenceTime = now ?? (phases.server_time ? new Date(phases.server_time).getTime() : Date.now());
  const guessWindow = phases.phases.find((item) => item.phase === "guess");
  return Boolean(guessWindow && new Date(guessWindow.ends_at).getTime() <= referenceTime);
}

export function isRegistrationClosed(phases: EventPhasesRead, now?: number): boolean {
  if (phases.phase_mode === "manual" && phases.manual_phase === "registration") return false;
  const registrationWindow = phases.phases.find((item) => item.phase === "registration");
  if (!registrationWindow) return false;
  const referenceTime = now ?? (phases.server_time ? new Date(phases.server_time).getTime() : Date.now());
  return new Date(registrationWindow.ends_at).getTime() <= referenceTime;
}

export function phaseStatusLabel(phases: EventPhasesRead, now?: number): string {
  if (phases.active_phase) return PHASE_LABELS[phases.active_phase];
  return isGuessEnded(phases, now) ? "猜谱已截止" : "暂无进行中的阶段";
}

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
  const currentWindow = phases.active_phase ? phases.phases.find((item) => item.phase === phases.active_phase) : undefined;
  const target = phases.next_transition_at || currentWindow?.ends_at;
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
      <Chip color={phases.active_phase ? "primary" : "default"} label={phases.active_phase ? `当前：${phaseStatusLabel(phases, now)}` : phaseStatusLabel(phases, now)} sx={{ fontWeight: 750 }} />
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
  const referenceTime = phases.server_time ? new Date(phases.server_time).getTime() : Date.now();
  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 }, overflowX: "auto" }}>
      <Typography variant="overline" color="text.secondary">赛事时间轴 · 北京时间</Typography>
      <Box sx={{ position: "relative", mt: 1.5 }}>
        {ordered.length > 0 && <Box aria-hidden="true" sx={{ position: "absolute", top: 7, left: 7, right: 7, height: 2, bgcolor: "rgba(23, 33, 28, 0.08)", borderRadius: 1 }} />}
        <Box sx={{ position: "relative", display: "grid", gridTemplateColumns: { xs: "repeat(2, minmax(0, 1fr))", sm: `repeat(${Math.max(ordered.length, 1)}, minmax(96px, 1fr))` }, gap: { xs: 1.5, sm: 1 } }}>
          {ordered.map((item, index) => {
            const active = item.phase === phases.active_phase;
            const completed = new Date(item.ends_at).getTime() <= referenceTime;
            const startsAt = formatPhaseDateTime(item.starts_at);
            const endsAt = formatPhaseDateTime(item.ends_at);
            return (
              <Box key={item.phase} sx={{ minWidth: 0, opacity: completed && !active ? 0.56 : 1 }}>
                <Box
                  aria-hidden="true"
                  sx={{
                    width: 14,
                    height: 14,
                    borderRadius: "50%",
                    mb: 1,
                    ...(active
                      ? { bgcolor: "#C9973B", boxShadow: "0 0 0 4px rgba(201, 151, 59, 0.22)" }
                      : completed || (currentIndex > -1 && index < currentIndex)
                        ? { bgcolor: "primary.main" }
                        : { bgcolor: "background.paper", border: "2px solid rgba(23, 33, 28, 0.16)" }),
                  }}
                />
                <Typography variant="caption" component="p" sx={{ fontWeight: active ? 800 : 650, color: active ? "primary.dark" : "text.primary" }}>{PHASE_LABELS[item.phase]}</Typography>
                <Typography component="span" variant="caption" color="text.secondary" aria-label={`开始时间 ${startsAt}，截止时间 ${endsAt}`} sx={{ display: "block", fontVariantNumeric: "tabular-nums", overflowWrap: "anywhere" }}>{startsAt} → {endsAt}</Typography>
              </Box>
            );
          })}
        </Box>
      </Box>
    </Paper>
  );
}
