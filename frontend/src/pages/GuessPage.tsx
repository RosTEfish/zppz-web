import { type ComponentProps, memo, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Card, CardActionArea, CardContent, CardMedia, Checkbox, Chip, Dialog, DialogContent, DialogTitle as MuiDialogTitle, Divider, FormControl, IconButton, InputLabel, MenuItem, Paper, Select, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography, useMediaQuery, useTheme } from "@mui/material";
import { useSnackbar } from "notistack";
import { CheckCheck, ClipboardList, Clock3, Download, Eye, Heart, MessageSquare, Music2, SlidersHorizontal, Sparkles, Vote, X } from "lucide-react";
import { api, formatDuration, formatTime, type DesignerGuessOverview, type GuessChartRead, type GuessCommentRead, type LoveVoteQuotaRead } from "../api/v1";
import { ChartPreviewStage } from "../components/ChartPreviewDialog";
import { DownloadPreparationDialog } from "../components/DownloadPreparationDialog";
import { PageHeader, ResourceState, useApiResource } from "../components/PagePrimitives";
import { queryKeys } from "../api/queryKeys";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";


const EMPTY_GUESS_CHARTS: GuessChartRead[] = [];
const EMPTY_DESIGNER_CANDIDATES: DesignerGuessOverview["candidates"] = [];
function DialogTitle({ children, sx }: { children: ReactNode; sx?: ComponentProps<typeof MuiDialogTitle>["sx"] }) { return <MuiDialogTitle component="div" sx={sx}>{children}</MuiDialogTitle>; }
type GuessLaneFilter = "all" | "normal" | "j" | "exhibition";
type GuessSelfFilter = "all" | "self" | "other";

const GUESS_LEVEL_SURFACES: Record<string, string> = {
  "1": "#E8F2FF",
  "2": "#E8F6ED",
  "3": "#FFF6D6",
  "4": "#FFE9E7",
  "5": "#F1E9FF",
  "6": "#FAF7FF",
  "7": "#FFF0E2",
};

function compareChartLevels(first: string, second: string): number {
  const pattern = /^(\d+(?:\.\d+)?)(\+?)$/;
  const firstMatch = pattern.exec(first.trim());
  const secondMatch = pattern.exec(second.trim());
  if (firstMatch && secondMatch) {
    const numericDifference = Number(firstMatch[1]) - Number(secondMatch[1]);
    if (numericDifference) return numericDifference;
    return Number(Boolean(firstMatch[2])) - Number(Boolean(secondMatch[2]));
  }
  return first.localeCompare(second, "zh-CN", { numeric: true });
}

function getChartLevelSlot(sourceLevelSlot?: string): string {
  return /(?:lv_)?([1-7])$/i.exec(sourceLevelSlot?.trim() ?? "")?.[1] ?? "";
}

function chartGroupIdentity(chart: GuessChartRead): string {
  return chart.guess_group_key || `chart:${chart.id}`;
}

function GuessFilterPanel({ levels, level, lane, selfSelected, disabled, onLevelChange, onLaneChange, onSelfChange, onReset }: { levels: string[]; level: string; lane: GuessLaneFilter; selfSelected: GuessSelfFilter; disabled: boolean; onLevelChange: (value: string) => void; onLaneChange: (value: GuessLaneFilter) => void; onSelfChange: (value: GuessSelfFilter) => void; onReset: () => void }) {
  const hasFilter = level !== "all" || lane !== "all" || selfSelected !== "all";
  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><SlidersHorizontal size={18} /><Typography variant="h3">分类查看</Typography></Stack>
        <Button size="small" color="inherit" disabled={disabled || !hasFilter} onClick={onReset}>清除筛选</Button>
      </Stack>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(170px, .65fr) minmax(300px, 1fr) minmax(300px, 1fr)" }, gap: 1.5 }}>
        <FormControl size="small" fullWidth disabled={disabled}><InputLabel id="guess-level-filter-label">难度</InputLabel><Select labelId="guess-level-filter-label" label="难度" value={level} onChange={(event) => onLevelChange(event.target.value)} inputProps={{ "aria-label": "按难度筛选" }}><MenuItem value="all">全部难度</MenuItem>{levels.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}</Select></FormControl>
        <ToggleButtonGroup size="small" exclusive fullWidth value={lane} aria-label="按投稿类型筛选" onChange={(_, value: GuessLaneFilter | null) => { if (value) onLaneChange(value); }}><ToggleButton value="all" disabled={disabled}>全部</ToggleButton><ToggleButton value="normal" disabled={disabled}>普通</ToggleButton><ToggleButton value="j" disabled={disabled}>J</ToggleButton><ToggleButton value="exhibition" disabled={disabled}>场外</ToggleButton></ToggleButtonGroup>
        <ToggleButtonGroup size="small" exclusive fullWidth value={selfSelected} aria-label="按自选状态筛选" onChange={(_, value: GuessSelfFilter | null) => { if (value) onSelfChange(value); }}><ToggleButton value="all" disabled={disabled}>全部来源</ToggleButton><ToggleButton value="self" disabled={disabled}>自选</ToggleButton><ToggleButton value="other" disabled={disabled}>非自选</ToggleButton></ToggleButtonGroup>
      </Box>
    </Paper>
  );
}

function LoveVoteQuotaPanel({ quota }: { quota: LoveVoteQuotaRead }) {
  return <Paper variant="outlined" aria-live="polite" aria-label="真爱票额度" sx={{ p: 1.5 }}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: { sm: "center" } }}><Typography variant="body2" sx={{ fontWeight: 800 }}>真爱票额度</Typography><Chip size="small" variant="outlined" label={`14 以下：已用 ${quota.below_14.used}/${quota.below_14.limit}，剩余 ${quota.below_14.remaining}`} /><Chip size="small" variant="outlined" label={`14 及以上：已用 ${quota.at_least_14.used}/${quota.at_least_14.limit}，剩余 ${quota.at_least_14.remaining}`} /></Stack></Paper>;
}

const GuessChartCard = memo(function GuessChartCard({ chart, selecting, selected, selectionDisabled, candidates, candidateLabels, canGuess, guessedUserId, guessBusy, onOpen, onGuess }: { chart: GuessChartRead; selecting: boolean; selected: boolean; selectionDisabled: boolean; candidates: DesignerGuessOverview["candidates"]; candidateLabels: ReadonlyMap<number, string>; canGuess: boolean; guessedUserId?: number | null; guessBusy: boolean; onOpen: (chart: GuessChartRead) => void; onGuess: (chart: GuessChartRead, userId: number | null) => void }) {
  const isJ = chart.lane === "j";
  const isExhibition = chart.lane === "exhibition" || chart.source_submission_type === "exhibition";
  const levelSlot = getChartLevelSlot(chart.source_level_slot);
  const levelSurface = GUESS_LEVEL_SURFACES[levelSlot] ?? "background.paper";
  const chartCanGuess = canGuess && !isJ && !isExhibition && chart.can_author_guess !== false;
  const emptyLabel = chartCanGuess ? (candidates.length ? "未选择" : "暂无谱师候选") : isJ || isExhibition ? "该类型不参与作者竞猜" : "当前不可竞猜";
  return (
    <Card variant="outlined" data-lane={isJ ? "j" : "normal"} data-level-slot={levelSlot ? `lv_${levelSlot}` : undefined} sx={{ position: "relative", height: "100%", display: "flex", flexDirection: "column", borderWidth: isJ ? 2 : 1, borderColor: selected ? "primary.main" : isJ ? "secondary.main" : "divider", outline: selected ? "2px solid" : "none", outlineColor: "primary.main", contentVisibility: "auto", containIntrinsicSize: "420px" }}>
      <CardActionArea onClick={() => onOpen(chart)} sx={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "stretch" }}>
        {chart.cover_path ? <CardMedia component="img" height="164" image={chart.cover_path} alt="" loading="lazy" decoding="async" sx={{ objectFit: "cover", bgcolor: "#E4EAE6" }} /> : <Box sx={{ height: 164, flexShrink: 0, display: "grid", placeItems: "center", bgcolor: "#E4EAE6", color: "text.secondary" }}><Music2 size={38} /></Box>}
        <CardContent sx={{ width: "100%", flex: 1, display: "flex", flexDirection: "column", bgcolor: levelSurface, color: "#17211D", transition: "background-color 160ms ease", "& .MuiTypography-colorTextSecondary": { color: "#45534D" } }}>
          <Typography variant="h3" noWrap title={chart.title}>{chart.title}</Typography>
          <Stack direction="row" spacing={0.75} useFlexGap sx={{ mt: 1, flexWrap: "wrap" }}><Chip size="small" label={chart.level} /><Chip size="small" color={isJ ? "secondary" : isExhibition ? "info" : "default"} variant={isJ || isExhibition ? "filled" : "outlined"} label={isJ ? "J 谱" : isExhibition ? "场外" : "普通谱"} /><Chip size="small" color={chart.is_self_selected ? "warning" : "default"} variant={chart.is_self_selected ? "filled" : "outlined"} label={chart.is_self_selected ? "自选" : "非自选"} /></Stack>
          <Stack spacing={0.5} sx={{ mt: 1.25, minHeight: 62 }}><Typography variant="body2" color="text.secondary" noWrap title={chart.author}><Box component="span" sx={{ fontWeight: 700 }}>曲师</Box>　{chart.author}</Typography><Typography variant="body2" color="text.secondary" noWrap title={chart.designer || "请填写做谱人"}><Box component="span" sx={{ fontWeight: 700 }}>谱师</Box>　{chart.designer || "请填写做谱人"}</Typography><Stack direction="row" spacing={0.75} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}><Typography variant="caption" color="text.secondary" aria-label={`音频时长 ${formatDuration(chart.track_duration_seconds)}`} sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}><Clock3 size={13} aria-hidden="true" />{formatDuration(chart.track_duration_seconds)}</Typography>{chart.is_long_track || (chart.track_duration_seconds ?? 0) > 240 ? <Chip size="small" color="warning" variant="outlined" label="Long Track" aria-label="Long Track，音频超过 4 分钟" /> : null}</Stack></Stack>
          <Stack direction="row" spacing={2} sx={{ mt: "auto", pt: 1.5 }}>{!isExhibition ? <><Typography variant="caption"><Heart size={13} /> {chart.love_votes}</Typography><Typography variant="caption"><Sparkles size={13} /> {chart.funny_votes}</Typography></> : null}<Typography variant="caption">查看 {chart.plays}</Typography></Stack>
        </CardContent>
      </CardActionArea>
      {!isJ && !isExhibition ? <Box sx={{ p: 1.5, borderTop: 1, borderColor: "divider", bgcolor: "background.paper" }}>
        <FormControl size="small" fullWidth disabled={selecting || guessBusy || !chartCanGuess || !candidates.length}>
          <InputLabel shrink>谱师猜测</InputLabel>
          <Select label="谱师猜测" displayEmpty value={guessedUserId ?? ""} inputProps={{ "aria-label": `谱师猜测 ${chart.title}` }} renderValue={(value) => value ? candidateLabels.get(Number(value)) || "-" : <em>{emptyLabel}</em>} onChange={(event) => onGuess(chart, event.target.value ? Number(event.target.value) : null)}>
            <MenuItem value=""><em>未选择</em></MenuItem>{candidates.map((candidate) => <MenuItem key={candidate.user_id} value={candidate.user_id}>{candidate.display_id}</MenuItem>)}
          </Select>
        </FormControl>
      </Box> : null}
      {selecting ? <Checkbox checked={selected} disabled={selectionDisabled} slotProps={{ input: { "aria-label": `选择 ${chart.title}` } }} sx={{ position: "absolute", top: 6, right: 6, bgcolor: "rgba(255,255,255,.9)", "&:hover": { bgcolor: "white" } }} onChange={() => onOpen(chart)} /> : null}
    </Card>
  );
});

export default function GuessPage() {
  const { enqueueSnackbar } = useSnackbar();
  const { phases } = useConfig();
  const { isLoggedIn } = useAuth();
  const charts = useApiResource(queryKeys.guess.charts, api.guessCharts);
  const designerGuesses = useApiResource(queryKeys.guess.designer, api.designerGuesses);
  const voteQuota = useApiResource(queryKeys.guess.quota, api.loveVoteQuota, isLoggedIn);
  const [active, setActive] = useState<GuessChartRead | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [selecting, setSelecting] = useState(false);
  const [levelFilter, setLevelFilter] = useState("all");
  const [laneFilter, setLaneFilter] = useState<GuessLaneFilter>("all");
  const [selfFilter, setSelfFilter] = useState<GuessSelfFilter>("all");
  const [busyGuessGroup, setBusyGuessGroup] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const allCharts = charts.data ?? EMPTY_GUESS_CHARTS;
  const candidates = designerGuesses.data?.candidates ?? EMPTY_DESIGNER_CANDIDATES;
  const candidateLabels = useMemo(() => new Map(candidates.map((candidate) => [candidate.user_id, candidate.display_id])), [candidates]);
  const canGuess = designerGuesses.data?.can_guess ?? false;
  const levels = useMemo(() => [...new Set(allCharts.map((chart) => chart.level))].sort(compareChartLevels), [allCharts]);
  const filteredCharts = useMemo(() => allCharts.filter((chart) => (levelFilter === "all" || chart.level === levelFilter) && (laneFilter === "all" || (laneFilter === "exhibition" ? chart.source_submission_type === "exhibition" || chart.lane === "exhibition" : chart.lane === laneFilter && chart.source_submission_type !== "exhibition")) && (selfFilter === "all" || (selfFilter === "self" ? chart.is_self_selected : !chart.is_self_selected))), [allCharts, laneFilter, levelFilter, selfFilter]);
  const allFilteredSelected = filteredCharts.length > 0 && filteredCharts.every((chart) => selected.has(chart.id));
  const guessedByChart = useMemo(() => new Map(designerGuesses.data?.states.map((state) => [state.chart_id, state.guessed_user_id]) ?? []), [designerGuesses.data?.states]);
  const setDesignerGuessData = designerGuesses.setData;

  function clearSelection() { setSelected(new Set()); }
  function resetFilters() { setLevelFilter("all"); setLaneFilter("all"); setSelfFilter("all"); clearSelection(); }
  function toggleAllFiltered() {
    if (downloading || !filteredCharts.length) return;
    const filteredIds = filteredCharts.map((chart) => chart.id);
    setSelected((current) => {
      const next = new Set(current);
      if (allFilteredSelected) filteredIds.forEach((id) => next.delete(id));
      else filteredIds.forEach((id) => next.add(id));
      return next;
    });
  }
  const updateChart = charts.updateData;
  const open = useCallback((chart: GuessChartRead) => {
    if (selecting) {
      if (downloading) return;
      setSelected((current) => { const next = new Set(current); if (next.has(chart.id)) next.delete(chart.id); else next.add(chart.id); return next; });
      return;
    }
    void api.guessChart(chart.id).then((next) => { setActive(next); updateChart((items) => items.map((item) => item.id === next.id ? next : item)); }).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, [downloading, selecting, updateChart]);
  const saveDesignerGuess = useCallback(async (chart: GuessChartRead, userId: number | null) => {
    const groupIdentity = chartGroupIdentity(chart);
    setBusyGuessGroup(groupIdentity);
    setError("");
    try {
      if (userId === null) await api.clearDesignerGuess(chart.id);
      else await api.saveDesignerGuess(chart.id, userId);
      const groupedChartIds = new Set(allCharts.filter((item) => chartGroupIdentity(item) === groupIdentity).map((item) => item.id));
      setDesignerGuessData((current) => current ? { ...current, states: current.states.map((state) => groupedChartIds.has(state.chart_id) ? { ...state, guessed_user_id: userId } : state) } : current);
    } catch (err) {
      setError(err instanceof Error ? err.message : "谱师猜测保存失败");
    } finally {
      setBusyGuessGroup("");
    }
  }, [allCharts, setDesignerGuessData]);
  async function downloadSelected() {
    if (!selected.size || downloading) return;
    setDownloading(true);
    setError("");
    try {
      await api.downloadCharts([...selected]);
      enqueueSnackbar("下载请求已开始，请查看浏览器下载列表", { variant: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "下载失败");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Stack spacing={3}>
      <PageHeader icon={Vote} title="猜谱" meta={`显示 ${filteredCharts.length} / 共 ${allCharts.length} 张谱面`} actions={<><Button variant={selecting ? "contained" : "outlined"} startIcon={<ClipboardList size={17} />} disabled={downloading} onClick={() => { setSelecting(!selecting); if (selecting) clearSelection(); }}>{selecting ? "结束选择" : "批量选择"}</Button>{selecting ? <><Button variant="outlined" startIcon={<CheckCheck size={17} />} disabled={downloading || !filteredCharts.length} onClick={toggleAllFiltered}>{allFilteredSelected ? "取消全选" : "全选当前结果"}</Button><Button variant="contained" startIcon={<Download size={17} />} disabled={!selected.size || downloading} onClick={() => void downloadSelected()}>{downloading ? "正在准备…" : `下载 ${selected.size} 项`}</Button></> : null}</>} />
      {error || designerGuesses.error || voteQuota.error ? <Alert severity="error">{error || designerGuesses.error || voteQuota.error}</Alert> : null}
      {isLoggedIn && voteQuota.data ? <LoveVoteQuotaPanel quota={voteQuota.data} /> : null}
      <ResourceState loading={charts.loading} error={charts.error} empty={!allCharts.length ? "暂无谱面" : undefined} />
      {allCharts.length ? <GuessFilterPanel levels={levels} level={levelFilter} lane={laneFilter} selfSelected={selfFilter} disabled={downloading} onLevelChange={(value) => { setLevelFilter(value); clearSelection(); }} onLaneChange={(value) => { setLaneFilter(value); clearSelection(); }} onSelfChange={(value) => { setSelfFilter(value); clearSelection(); }} onReset={resetFilters} /> : null}
      {filteredCharts.length ? <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(3, 1fr)", xl: "repeat(4, 1fr)" }, gap: 2 }}>{filteredCharts.map((chart) => <GuessChartCard key={chart.id} chart={chart} selecting={selecting} selected={selected.has(chart.id)} selectionDisabled={downloading} candidates={candidates} candidateLabels={candidateLabels} canGuess={canGuess} guessedUserId={guessedByChart.get(chart.id)} guessBusy={busyGuessGroup === chartGroupIdentity(chart)} onOpen={open} onGuess={saveDesignerGuess} />)}</Box> : allCharts.length ? <Paper variant="outlined" sx={{ py: 7, px: 2, textAlign: "center" }}><Typography color="text.secondary">没有符合当前筛选条件的谱面</Typography><Button variant="outlined" sx={{ mt: 2 }} disabled={downloading} onClick={resetFilters}>清除筛选</Button></Paper> : null}
      <GuessDetailDialog chart={active} designerGuesses={designerGuesses.data} candidateLabels={candidateLabels} voteQuota={voteQuota.data} guessedUserId={active ? guessedByChart.get(active.id) : null} guessBusy={Boolean(active && busyGuessGroup === chartGroupIdentity(active))} canVote={phases?.capabilities.quality_vote ?? true} onGuess={saveDesignerGuess} onClose={() => setActive(null)} onChanged={(next) => { setActive(next); updateChart((items) => items.map((item) => item.id === next.id ? next : item)); }} onQuotaChanged={voteQuota.setData} />
      <DownloadPreparationDialog open={downloading} count={selected.size} unit="项" />
    </Stack>
  );
}

function GuessDetailDialog({ chart, designerGuesses, candidateLabels, voteQuota, guessedUserId, guessBusy, canVote, onGuess, onClose, onChanged, onQuotaChanged }: { chart: GuessChartRead | null; designerGuesses: DesignerGuessOverview | null; candidateLabels: ReadonlyMap<number, string>; voteQuota: LoveVoteQuotaRead | null; guessedUserId?: number | null; guessBusy: boolean; canVote: boolean; onGuess: (chart: GuessChartRead, userId: number | null) => void; onClose: () => void; onChanged: (chart: GuessChartRead) => void; onQuotaChanged: (quota: LoveVoteQuotaRead | null) => void }) {
  const [comments, setComments] = useState<GuessCommentRead[]>([]);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [previewActive, setPreviewActive] = useState(false);
  const { isLoggedIn } = useAuth();
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("sm"));

  useEffect(() => {
    if (!chart) return;
    setComments([]);
    setComment("");
    setError("");
    setPreviewActive(false);
    void api.comments(chart.id).then(setComments).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, [chart?.id]);

  if (!chart) return null;
  const isJ = chart.lane === "j";
  const isExhibition = chart.source_submission_type === "exhibition" || chart.lane === "exhibition";
  const candidates = designerGuesses?.candidates ?? EMPTY_DESIGNER_CANDIDATES;
  const canGuess = designerGuesses?.can_guess ?? false;
  const emptyLabel = canGuess ? (candidates.length ? "未选择" : "暂无谱师候选") : "当前不可竞猜";
  const loveSelected = chart.my_votes.includes("love");
  const loveQuotaExhausted = !loveSelected && voteQuota !== null && voteQuota[chart.love_vote_bucket]?.remaining <= 0;

  function closeDetail() {
    setPreviewActive(false);
    onClose();
  }

  async function download() {
    try {
      await api.downloadChart(chart.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "下载失败");
      throw reason;
    }
  }

  async function toggleVote(type: "love" | "funny") {
    const selected = chart.my_votes.includes(type);
    const result = selected ? await api.unvote(chart.id, type) : await api.vote(chart.id, type);
    if (result.love_vote_quota) onQuotaChanged(result.love_vote_quota);
    const myVotes = result.my_votes ?? (selected ? chart.my_votes.filter((item) => item !== type) : [...chart.my_votes, type]);
    onChanged({
      ...chart,
      love_votes: result.vote_counts?.love ?? chart.love_votes + (type === "love" ? selected ? -1 : 1 : 0),
      funny_votes: result.vote_counts?.funny ?? chart.funny_votes + (type === "funny" ? selected ? -1 : 1 : 0),
      my_votes: myVotes,
    });
  }

  async function sendComment() {
    if (!comment.trim()) return;
    const created = await api.createComment(chart.id, comment.trim());
    setComments((current) => [created, ...current]);
    setComment("");
  }

  return (
    <Dialog
      open
      onClose={closeDetail}
      fullWidth
      maxWidth="lg"
      fullScreen={mobile}
      slotProps={{ paper: { sx: { overflow: "hidden", maxHeight: { sm: "calc(100dvh - 32px)" } } } }}
    >
      <DialogTitle sx={{ px: { xs: 2, sm: 3 }, py: 1.75, borderBottom: 1, borderColor: "divider" }}>
        <Stack direction="row" spacing={2} sx={{ justifyContent: "space-between", alignItems: "center" }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="overline" color="primary.main" sx={{ fontWeight: 800, letterSpacing: ".12em" }}>谱面详情</Typography>
            <Typography variant="h2" noWrap title={chart.title}>{chart.title}</Typography>
          </Box>
          <IconButton aria-label="关闭谱面详情" onClick={closeDetail}><X size={20} /></IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent sx={{ p: { xs: 0, sm: 3 }, bgcolor: "background.default" }}>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 1fr) 320px" },
            gap: { xs: 0, sm: 3 },
            alignItems: "start",
          }}
        >
          <ChartPreviewStage
            active={previewActive}
            source="guess"
            sourceId={chart.id}
            title={chart.title}
            coverUrl={chart.cover_path}
            levelLabel={chart.level}
            canPreview={chart.can_preview !== false}
            onActivate={() => setPreviewActive(true)}
            onDownload={download}
          />

          <Stack
            spacing={2}
            sx={{
              p: { xs: 2, sm: 0 },
              position: { md: "sticky" },
              top: { md: 0 },
            }}
          >
            <Box>
              <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap", mb: 1.5 }}>
                <Chip label={chart.level} color="primary" />
                <Chip
                  color={isJ ? "secondary" : isExhibition ? "info" : "default"}
                  variant={isJ || isExhibition ? "filled" : "outlined"}
                  label={isJ ? "J 谱" : isExhibition ? "场外" : "普通谱"}
                />
                <Chip
                  color={chart.is_self_selected ? "warning" : "default"}
                  variant={chart.is_self_selected ? "filled" : "outlined"}
                  label={chart.is_self_selected ? "自选" : "非自选"}
                />
              </Stack>
              <Typography variant="h2" sx={{ overflowWrap: "anywhere" }}>{chart.title}</Typography>
              <Stack spacing={0.5} sx={{ mt: 1.5 }}>
                <Typography variant="body2" color="text.secondary"><Box component="span" sx={{ fontWeight: 750, color: "text.primary" }}>曲师</Box>　{chart.author}</Typography>
                <Typography variant="body2" color="text.secondary"><Box component="span" sx={{ fontWeight: 750, color: "text.primary" }}>谱师</Box>　{chart.designer || "请填写做谱人"}</Typography>
              </Stack>
              <Stack direction="row" spacing={1.5} useFlexGap sx={{ mt: 1.5, alignItems: "center", flexWrap: "wrap" }}>
                <Typography variant="caption" color="text.secondary">查看 {chart.plays} 次</Typography>
                <Typography variant="caption" color="text.secondary" aria-label={`音频时长 ${formatDuration(chart.track_duration_seconds)}`} sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                  <Clock3 size={13} aria-hidden="true" />{formatDuration(chart.track_duration_seconds)}
                </Typography>
                {chart.is_long_track || (chart.track_duration_seconds ?? 0) > 240 ? <Chip size="small" color="warning" variant="outlined" label="Long Track" aria-label="Long Track，音频超过 4 分钟" /> : null}
              </Stack>
            </Box>

            <Stack spacing={1}>
              <Button
                variant={previewActive ? "outlined" : "contained"}
                startIcon={<Eye size={17} />}
                disabled={chart.can_preview === false}
                onClick={() => setPreviewActive((current) => !current)}
              >
                {previewActive ? "退出预览并释放播放器" : "开始在线预览"}
              </Button>
              <Button variant="outlined" startIcon={<Download size={17} />} disabled={chart.can_download === false} onClick={() => void download().catch(() => {})}>下载投稿</Button>
            </Stack>

            {!isExhibition ? (
              <Paper variant="outlined" sx={{ p: 1.5, bgcolor: "background.paper" }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>为这张谱面投票</Typography>
                <Stack direction="row" spacing={1}>
                  <Button
                    fullWidth
                    variant={loveSelected ? "contained" : "outlined"}
                    color="error"
                    startIcon={<Heart size={16} />}
                    disabled={!isLoggedIn || !canVote || chart.can_vote === false || loveQuotaExhausted}
                    aria-label={`真爱票 ${chart.love_votes}`}
                    onClick={() => void toggleVote("love").catch((err) => setError(err.message))}
                  >
                    {chart.love_votes}
                  </Button>
                  <Button
                    fullWidth
                    variant={chart.my_votes.includes("funny") ? "contained" : "outlined"}
                    color="secondary"
                    startIcon={<Sparkles size={16} />}
                    disabled={!isLoggedIn || !canVote || chart.can_vote === false}
                    aria-label={`欢乐票 ${chart.funny_votes}`}
                    onClick={() => void toggleVote("funny").catch((err) => setError(err.message))}
                  >
                    {chart.funny_votes}
                  </Button>
                </Stack>
              </Paper>
            ) : null}

            {!isJ && !isExhibition ? (
              <FormControl size="small" disabled={guessBusy || !canGuess || !candidates.length || chart.can_author_guess === false}>
                <InputLabel shrink>谱师猜测</InputLabel>
                <Select
                  label="谱师猜测"
                  displayEmpty
                  value={guessedUserId ?? ""}
                  inputProps={{ "aria-label": `谱师猜测 ${chart.title}` }}
                  renderValue={(value) => value ? candidateLabels.get(Number(value)) || "-" : <em>{emptyLabel}</em>}
                  onChange={(event) => onGuess(chart, event.target.value ? Number(event.target.value) : null)}
                >
                  <MenuItem value=""><em>未选择</em></MenuItem>
                  {candidates.map((item) => <MenuItem key={item.user_id} value={item.user_id}>{item.display_id}</MenuItem>)}
                </Select>
              </FormControl>
            ) : null}
            {error ? <Alert severity="error" aria-live="polite">{error}</Alert> : null}
          </Stack>
        </Box>

        <Box sx={{ px: { xs: 2, sm: 0 }, pb: { xs: 4, sm: 1 } }}>
          <Divider sx={{ my: { xs: 2, sm: 3 } }} />
          <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", justifyContent: "space-between", mb: 1.5 }}>
            <Typography variant="h3">评论</Typography>
            {comments.length ? <Typography variant="caption" color="text.secondary">{comments.length} 条</Typography> : null}
          </Stack>
          {isLoggedIn && chart.can_comment !== false ? (
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 2 }}>
              <TextField size="small" fullWidth label="评论内容" placeholder="写下你的评价" value={comment} onChange={(event) => setComment(event.target.value)} />
              <Button variant="contained" startIcon={<MessageSquare size={17} />} disabled={!comment.trim()} onClick={() => void sendComment().catch((err) => setError(err.message))}>发送</Button>
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {isLoggedIn ? "该谱面暂不可评论。" : "登录后可对已公开谱面发表评论。"}
            </Typography>
          )}
          <Stack spacing={1}>
            {comments.length ? comments.map((item) => (
              <Paper key={item.id} variant="outlined" sx={{ p: 1.5, bgcolor: "background.paper" }}>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{item.content}</Typography>
                <Typography variant="caption" color="text.secondary">{item.user.display_name || item.user.user_code} · {formatTime(item.created_at)}</Typography>
              </Paper>
            )) : <Typography variant="body2" color="text.secondary">还没有评论。</Typography>}
          </Stack>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
