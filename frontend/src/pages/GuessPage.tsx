import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Card, CardActionArea, CardContent, CardMedia, Checkbox, Chip, Dialog, DialogContent, DialogTitle, Divider, FormControl, IconButton, InputLabel, MenuItem, Paper, Select, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";
import { ClipboardList, Clock3, Download, Heart, MessageSquare, Music2, SlidersHorizontal, Sparkles, Vote, X } from "lucide-react";
import { api, formatDuration, formatTime, type DesignerGuessOverview, type GuessChartRead, type GuessCommentRead } from "../api/v1";
import { PageHeader, ResourceState, useResource } from "../components/PagePrimitives";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";


const EMPTY_GUESS_CHARTS: GuessChartRead[] = [];
const EMPTY_DESIGNER_CANDIDATES: DesignerGuessOverview["candidates"] = [];
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

function GuessFilterPanel({ levels, level, lane, selfSelected, onLevelChange, onLaneChange, onSelfChange, onReset }: { levels: string[]; level: string; lane: GuessLaneFilter; selfSelected: GuessSelfFilter; onLevelChange: (value: string) => void; onLaneChange: (value: GuessLaneFilter) => void; onSelfChange: (value: GuessSelfFilter) => void; onReset: () => void }) {
  const hasFilter = level !== "all" || lane !== "all" || selfSelected !== "all";
  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><SlidersHorizontal size={18} /><Typography variant="h3">分类查看</Typography></Stack>
        <Button size="small" color="inherit" disabled={!hasFilter} onClick={onReset}>清除筛选</Button>
      </Stack>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(170px, .65fr) minmax(300px, 1fr) minmax(300px, 1fr)" }, gap: 1.5 }}>
        <FormControl size="small" fullWidth><InputLabel id="guess-level-filter-label">难度</InputLabel><Select labelId="guess-level-filter-label" label="难度" value={level} onChange={(event) => onLevelChange(event.target.value)} inputProps={{ "aria-label": "按难度筛选" }}><MenuItem value="all">全部难度</MenuItem>{levels.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}</Select></FormControl>
        <ToggleButtonGroup size="small" exclusive fullWidth value={lane} aria-label="按投稿类型筛选" onChange={(_, value: GuessLaneFilter | null) => { if (value) onLaneChange(value); }}><ToggleButton value="all">全部</ToggleButton><ToggleButton value="normal">普通</ToggleButton><ToggleButton value="j">J</ToggleButton><ToggleButton value="exhibition">场外</ToggleButton></ToggleButtonGroup>
        <ToggleButtonGroup size="small" exclusive fullWidth value={selfSelected} aria-label="按自选状态筛选" onChange={(_, value: GuessSelfFilter | null) => { if (value) onSelfChange(value); }}><ToggleButton value="all">全部来源</ToggleButton><ToggleButton value="self">自选</ToggleButton><ToggleButton value="other">非自选</ToggleButton></ToggleButtonGroup>
      </Box>
    </Paper>
  );
}

const GuessChartCard = memo(function GuessChartCard({ chart, selecting, selected, candidates, canGuess, guessedUserId, guessBusy, onOpen, onGuess }: { chart: GuessChartRead; selecting: boolean; selected: boolean; candidates: DesignerGuessOverview["candidates"]; canGuess: boolean; guessedUserId?: number | null; guessBusy: boolean; onOpen: (chart: GuessChartRead) => void; onGuess: (chart: GuessChartRead, userId: number | null) => void }) {
  const isJ = chart.lane === "j";
  const isExhibition = chart.lane === "exhibition" || chart.source_submission_type === "exhibition";
  const levelSlot = getChartLevelSlot(chart.source_level_slot);
  const levelSurface = GUESS_LEVEL_SURFACES[levelSlot] ?? "background.paper";
  const chartCanGuess = canGuess && !isJ && !isExhibition && chart.can_author_guess !== false;
  const emptyLabel = chartCanGuess ? (candidates.length ? "未选择" : "暂无谱师候选") : isJ || isExhibition ? "该类型不参与作者竞猜" : "当前不可竞猜";
  return (
    <Card variant="outlined" data-lane={isJ ? "j" : "normal"} data-level-slot={levelSlot ? `lv_${levelSlot}` : undefined} sx={{ position: "relative", height: "100%", display: "flex", flexDirection: "column", borderWidth: isJ ? 2 : 1, borderColor: selected ? "primary.main" : isJ ? "secondary.main" : "divider", outline: selected ? "2px solid" : "none", outlineColor: "primary.main" }}>
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
          <Select label="谱师猜测" displayEmpty value={guessedUserId ?? ""} inputProps={{ "aria-label": `谱师猜测 ${chart.title}` }} renderValue={(value) => value ? candidates.find((candidate) => candidate.user_id === Number(value))?.display_id || "-" : <em>{emptyLabel}</em>} onChange={(event) => onGuess(chart, event.target.value ? Number(event.target.value) : null)}>
            <MenuItem value=""><em>未选择</em></MenuItem>{candidates.map((candidate) => <MenuItem key={candidate.user_id} value={candidate.user_id}>{candidate.display_id}</MenuItem>)}
          </Select>
        </FormControl>
      </Box> : null}
      {selecting ? <Checkbox checked={selected} slotProps={{ input: { "aria-label": `选择 ${chart.title}` } }} sx={{ position: "absolute", top: 6, right: 6, bgcolor: "rgba(255,255,255,.9)", "&:hover": { bgcolor: "white" } }} onChange={() => onOpen(chart)} /> : null}
    </Card>
  );
});

export default function GuessPage() {
  const { phases } = useConfig();
  const charts = useResource(api.guessCharts, []);
  const designerGuesses = useResource(api.designerGuesses, []);
  const [active, setActive] = useState<GuessChartRead | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [selecting, setSelecting] = useState(false);
  const [levelFilter, setLevelFilter] = useState("all");
  const [laneFilter, setLaneFilter] = useState<GuessLaneFilter>("all");
  const [selfFilter, setSelfFilter] = useState<GuessSelfFilter>("all");
  const [busyGuessGroup, setBusyGuessGroup] = useState("");
  const [error, setError] = useState("");
  const allCharts = charts.data ?? EMPTY_GUESS_CHARTS;
  const candidates = designerGuesses.data?.candidates ?? EMPTY_DESIGNER_CANDIDATES;
  const canGuess = designerGuesses.data?.can_guess ?? false;
  const levels = useMemo(() => [...new Set(allCharts.map((chart) => chart.level))].sort(compareChartLevels), [allCharts]);
  const filteredCharts = useMemo(() => allCharts.filter((chart) => (levelFilter === "all" || chart.level === levelFilter) && (laneFilter === "all" || (laneFilter === "exhibition" ? chart.source_submission_type === "exhibition" || chart.lane === "exhibition" : chart.lane === laneFilter && chart.source_submission_type !== "exhibition")) && (selfFilter === "all" || (selfFilter === "self" ? chart.is_self_selected : !chart.is_self_selected))), [allCharts, laneFilter, levelFilter, selfFilter]);
  const guessedByChart = useMemo(() => new Map(designerGuesses.data?.states.map((state) => [state.chart_id, state.guessed_user_id]) ?? []), [designerGuesses.data?.states]);
  const setDesignerGuessData = designerGuesses.setData;

  function clearSelection() { setSelected(new Set()); }
  function resetFilters() { setLevelFilter("all"); setLaneFilter("all"); setSelfFilter("all"); clearSelection(); }
  const open = useCallback((chart: GuessChartRead) => {
    if (selecting) { setSelected((current) => { const next = new Set(current); if (next.has(chart.id)) next.delete(chart.id); else next.add(chart.id); return next; }); return; }
    void api.guessChart(chart.id).then(setActive).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, [selecting]);
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

  return (
    <Stack spacing={3}>
      <PageHeader icon={Vote} title="猜谱" meta={`显示 ${filteredCharts.length} / 共 ${allCharts.length} 张谱面`} actions={<><Button variant={selecting ? "contained" : "outlined"} startIcon={<ClipboardList size={17} />} onClick={() => { setSelecting(!selecting); if (selecting) clearSelection(); }}>{selecting ? "结束选择" : "批量选择"}</Button>{selecting ? <Button variant="contained" startIcon={<Download size={17} />} disabled={!selected.size} onClick={() => void api.downloadCharts([...selected]).catch((err) => setError(err instanceof Error ? err.message : "下载失败"))}>下载 {selected.size} 项</Button> : null}</>} />
      {error || designerGuesses.error ? <Alert severity="error">{error || designerGuesses.error}</Alert> : null}
      <ResourceState loading={charts.loading} error={charts.error} empty={!allCharts.length ? "暂无谱面" : undefined} />
      {allCharts.length ? <GuessFilterPanel levels={levels} level={levelFilter} lane={laneFilter} selfSelected={selfFilter} onLevelChange={(value) => { setLevelFilter(value); clearSelection(); }} onLaneChange={(value) => { setLaneFilter(value); clearSelection(); }} onSelfChange={(value) => { setSelfFilter(value); clearSelection(); }} onReset={resetFilters} /> : null}
      {filteredCharts.length ? <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(3, 1fr)", xl: "repeat(4, 1fr)" }, gap: 2 }}>{filteredCharts.map((chart) => <GuessChartCard key={chart.id} chart={chart} selecting={selecting} selected={selected.has(chart.id)} candidates={candidates} canGuess={canGuess} guessedUserId={guessedByChart.get(chart.id)} guessBusy={busyGuessGroup === chartGroupIdentity(chart)} onOpen={open} onGuess={saveDesignerGuess} />)}</Box> : allCharts.length ? <Paper variant="outlined" sx={{ py: 7, px: 2, textAlign: "center" }}><Typography color="text.secondary">没有符合当前筛选条件的谱面</Typography><Button variant="outlined" sx={{ mt: 2 }} onClick={resetFilters}>清除筛选</Button></Paper> : null}
      <GuessDetailDialog chart={active} designerGuesses={designerGuesses.data} guessedUserId={active ? guessedByChart.get(active.id) : null} guessBusy={Boolean(active && busyGuessGroup === chartGroupIdentity(active))} canVote={phases?.capabilities.quality_vote ?? true} canComment={phases?.capabilities.quality_vote ?? true} onGuess={saveDesignerGuess} onClose={() => setActive(null)} onChanged={async () => { const next = await charts.reload(); if (active && next) setActive(next.find((item) => item.id === active.id) || null); }} />
    </Stack>
  );
}

function GuessDetailDialog({ chart, designerGuesses, guessedUserId, guessBusy, canVote, canComment, onGuess, onClose, onChanged }: { chart: GuessChartRead | null; designerGuesses: DesignerGuessOverview | null; guessedUserId?: number | null; guessBusy: boolean; canVote: boolean; canComment: boolean; onGuess: (chart: GuessChartRead, userId: number | null) => void; onClose: () => void; onChanged: () => Promise<void> }) {
  const [comments, setComments] = useState<GuessCommentRead[]>([]);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const { isLoggedIn } = useAuth();
  useEffect(() => {
    if (!chart) return;
    setComments([]);
    setError("");
    if (canComment && chart.can_comment !== false) void api.comments(chart.id).then(setComments).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, [canComment, chart?.can_comment, chart?.id]);
  if (!chart) return null;
  const isExhibition = chart.source_submission_type === "exhibition" || chart.lane === "exhibition";
  const candidates = designerGuesses?.candidates ?? EMPTY_DESIGNER_CANDIDATES;
  const canGuess = designerGuesses?.can_guess ?? false;
  const emptyLabel = canGuess ? (candidates.length ? "未选择" : "暂无谱师候选") : "当前不可竞猜";
  async function toggleVote(type: "love" | "funny") { if (chart.my_votes.includes(type)) await api.unvote(chart.id, type); else await api.vote(chart.id, type); await onChanged(); }
  async function sendComment() { if (!comment.trim()) return; const created = await api.createComment(chart.id, comment.trim()); setComments((current) => [created, ...current]); setComment(""); }
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md" fullScreen={false}>
      <DialogTitle sx={{ pr: 6 }}><Typography variant="h2">{chart.title}</Typography><Stack direction="row" spacing={0.75} useFlexGap sx={{ my: 1, flexWrap: "wrap" }}><Chip size="small" label={chart.level} /><Chip size="small" color={chart.lane === "j" ? "secondary" : chart.source_submission_type === "exhibition" ? "info" : "default"} variant={chart.lane === "j" || chart.source_submission_type === "exhibition" ? "filled" : "outlined"} label={chart.lane === "j" ? "J 谱" : chart.source_submission_type === "exhibition" ? "场外" : "普通谱"} /><Chip size="small" color={chart.is_self_selected ? "warning" : "default"} variant={chart.is_self_selected ? "filled" : "outlined"} label={chart.is_self_selected ? "自选" : "非自选"} /></Stack><Typography variant="body2" color="text.secondary">曲师：{chart.author}</Typography><Typography variant="body2" color="text.secondary">谱师：{chart.designer || "请填写做谱人"}</Typography><Stack direction="row" spacing={1} useFlexGap sx={{ mt: 0.5, alignItems: "center", flexWrap: "wrap" }}><Typography variant="caption" color="text.secondary">查看 {chart.plays} 次</Typography><Typography variant="caption" color="text.secondary" aria-label={`音频时长 ${formatDuration(chart.track_duration_seconds)}`} sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}><Clock3 size={13} aria-hidden="true" />{formatDuration(chart.track_duration_seconds)}</Typography>{chart.is_long_track || (chart.track_duration_seconds ?? 0) > 240 ? <Chip size="small" color="warning" variant="outlined" label="Long Track" aria-label="Long Track，音频超过 4 分钟" /> : null}</Stack><IconButton aria-label="关闭谱面详情" onClick={onClose} sx={{ position: "absolute", right: 12, top: 12 }}><X size={20} /></IconButton></DialogTitle>
      <DialogContent dividers>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1fr) 280px" }, gap: 3 }}>
          {chart.cover_path ? <Box component="img" src={chart.cover_path} alt="" sx={{ width: "100%", maxHeight: 420, objectFit: "cover", borderRadius: 1 }} /> : <Box sx={{ minHeight: 260, display: "grid", placeItems: "center", bgcolor: "background.default" }}><Music2 size={42} /></Box>}
          <Stack spacing={2}><Button variant="contained" startIcon={<Download size={17} />} disabled={chart.can_download === false} onClick={() => void api.downloadChart(chart.id).catch((err) => setError(err instanceof Error ? err.message : "下载失败"))}>下载投稿</Button>{!isExhibition ? <Stack direction="row" spacing={1}><Button fullWidth variant={chart.my_votes.includes("love") ? "contained" : "outlined"} color="error" startIcon={<Heart size={16} />} disabled={!isLoggedIn || !canVote || chart.can_vote === false} aria-label={`真爱票 ${chart.love_votes}`} onClick={() => void toggleVote("love").catch((err) => setError(err.message))}>{chart.love_votes}</Button><Button fullWidth variant={chart.my_votes.includes("funny") ? "contained" : "outlined"} color="secondary" startIcon={<Sparkles size={16} />} disabled={!isLoggedIn || !canVote || chart.can_vote === false} aria-label={`欢乐票 ${chart.funny_votes}`} onClick={() => void toggleVote("funny").catch((err) => setError(err.message))}>{chart.funny_votes}</Button></Stack> : null}<FormControl size="small" sx={{ display: chart.lane === "j" || chart.source_submission_type === "exhibition" ? "none" : undefined }} disabled={guessBusy || !canGuess || !candidates.length || chart.can_author_guess === false}><InputLabel shrink>谱师猜测</InputLabel><Select label="谱师猜测" displayEmpty value={guessedUserId ?? ""} inputProps={{ "aria-label": `谱师猜测 ${chart.title}` }} renderValue={(value) => value ? candidates.find((candidate) => candidate.user_id === Number(value))?.display_id || "-" : <em>{emptyLabel}</em>} onChange={(event) => onGuess(chart, event.target.value ? Number(event.target.value) : null)}><MenuItem value=""><em>未选择</em></MenuItem>{candidates.map((item) => <MenuItem key={item.user_id} value={item.user_id}>{item.display_id}</MenuItem>)}</Select></FormControl>{error ? <Alert severity="error" aria-live="polite">{error}</Alert> : null}</Stack>
        </Box>
        <Divider sx={{ my: 3 }} /><Typography variant="h3" sx={{ mb: 1.5 }}>评论</Typography>{isLoggedIn && canComment && chart.can_comment !== false ? <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 2 }}><TextField size="small" fullWidth label="评论内容" placeholder="写下你的评价" value={comment} onChange={(event) => setComment(event.target.value)} /><IconButton color="primary" aria-label="发送评论" disabled={!comment.trim()} onClick={() => void sendComment().catch((err) => setError(err.message))} sx={{ alignSelf: { xs: "flex-end", sm: "center" } }}><MessageSquare size={19} /></IconButton></Stack> : <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{isLoggedIn ? "当前阶段未开放评论。" : "登录后可在开放阶段发表评论。"}</Typography>}<Stack spacing={1}>{comments.map((item) => <Paper key={item.id} variant="outlined" sx={{ p: 1.5 }}><Typography variant="body2">{item.content}</Typography><Typography variant="caption" color="text.secondary">{item.user.display_name || item.user.user_code} · {formatTime(item.created_at)}</Typography></Paper>)}</Stack>
      </DialogContent>
    </Dialog>
  );
}
