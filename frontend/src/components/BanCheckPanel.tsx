import { useEffect, useState } from "react";
import { Alert, Box, Checkbox, Chip, FormControlLabel, Stack, Typography } from "@mui/material";
import { api, type BanCheckRead, type BanCheckStatus } from "../api/v1";


export interface BanCheckState {
  result: BanCheckRead | null;
  loading: boolean;
  error: string;
  acknowledged: boolean;
  setAcknowledged: (value: boolean) => void;
  hasInput: boolean;
  ready: boolean;
}


export function useBanCheck(title: string, artist: string): BanCheckState {
  const [result, setResult] = useState<BanCheckRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const hasInput = title.trim().length > 0 && artist.trim().length > 0;

  useEffect(() => {
    const cleanTitle = title.trim();
    const cleanArtist = artist.trim();
    setResult(null);
    setError("");
    setAcknowledged(false);
    if (!cleanTitle || !cleanArtist) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      void api.checkBan(cleanTitle, cleanArtist, controller.signal)
        .then(setResult)
        .catch((err) => {
          if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "查重失败");
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 500);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [artist, title]);

  return { result, loading, error, acknowledged, setAcknowledged, hasInput, ready: !hasInput || (!loading && result !== null) };
}


function statusCopy(status: BanCheckStatus): { severity: "error" | "warning" | "success" | "info"; title: string } {
  if (status === "exact") return { severity: "error", title: "已命中往届 Ban 曲，不能保存" };
  if (status === "review") return { severity: "warning", title: "疑似命中往届 Ban 曲，请人工确认" };
  if (status === "unavailable") return { severity: "info", title: "当前没有可用的 Ban 曲版本，已跳过本地判断" };
  return { severity: "success", title: "未发现往届 Ban 记录" };
}


export function BanCheckPanel({ state, compact = false }: { state: BanCheckState; compact?: boolean }) {
  if (!state.hasInput) return <Typography variant="caption" color="text.secondary">填写曲名和曲师后自动查重。</Typography>;
  if (state.loading) return <Typography variant="caption" color="text.secondary">正在检查往届 Ban 曲…</Typography>;
  if (state.error) return <Alert severity="warning" sx={{ py: compact ? 0.25 : 0.75 }}>{state.error}，保存时后端仍会再次校验。</Alert>;
  if (!state.result) return null;
  const copy = statusCopy(state.result.status);
  return (
    <Alert severity={copy.severity} sx={{ py: compact ? 0.5 : 1 }}>
      <Stack spacing={0.75}>
        <Typography variant="body2" sx={{ fontWeight: 750 }}>{copy.title}</Typography>
        {state.result.matches.length ? (
          <Stack spacing={0.75}>
            {state.result.matches.map((match) => (
              <Box key={`${match.entry_id}-${match.match_type}`} sx={{ minWidth: 0 }}>
                <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                  《{match.title}》 · {match.artist} · {match.round}
                  {match.score !== null && match.score !== undefined ? ` · ${match.score.toFixed(1)}%` : ""}
                </Typography>
                <Typography variant="caption" color="text.secondary">{match.reason}{match.note ? `；备注：${match.note}` : ""}</Typography>
                <Chip size="small" variant="outlined" label={match.match_type === "alias" ? "别名命中" : match.match_type === "exact" ? "精确匹配" : "疑似匹配"} sx={{ mt: 0.5 }} />
              </Box>
            ))}
          </Stack>
        ) : null}
        {state.result.status === "review" ? (
          <FormControlLabel
            control={<Checkbox size="small" checked={state.acknowledged} onChange={(event) => state.setAcknowledged(event.target.checked)} />}
            label="我已核对上述记录，确认这不是同一首曲目"
            sx={{ mt: 0.25, mr: 0 }}
          />
        ) : null}
      </Stack>
    </Alert>
  );
}


export function canSubmitWithBanCheck(state: BanCheckState): boolean {
  if (!state.hasInput || !state.ready || !state.result) return false;
  return state.result.status !== "exact" && (state.result.status !== "review" || state.acknowledged);
}
