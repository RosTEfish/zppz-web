import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Card, CardActionArea, CardContent, CardMedia, Checkbox, Chip, Dialog, DialogContent, DialogTitle, Divider, FormControl, IconButton, InputLabel, MenuItem, Paper, Select, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";
import { ClipboardList, Download, Heart, MessageSquare, Music2, SlidersHorizontal, Sparkles, Vote, X } from "lucide-react";
import { api, formatTime, type AuthorGuessState, type GuessChartRead, type GuessCommentRead } from "../api/v1";
import { PageHeader, ResourceState, useResource } from "../components/PagePrimitives";
import { useAuth } from "../contexts/AuthContext";


const EMPTY_GUESS_CHARTS: GuessChartRead[] = [];
type GuessLaneFilter = "all" | "normal" | "j";
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

function getChartLevelSlot(sourceLevelSlot: string): string {
  return /(?:lv_)?([1-7])$/i.exec(sourceLevelSlot.trim())?.[1] ?? "";
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
        <ToggleButtonGroup size="small" exclusive fullWidth value={lane} aria-label="按谱面类型筛选" onChange={(_, value: GuessLaneFilter | null) => { if (value) onLaneChange(value); }}><ToggleButton value="all">全部类型</ToggleButton><ToggleButton value="normal">普通谱</ToggleButton><ToggleButton value="j">J 谱</ToggleButton></ToggleButtonGroup>
        <ToggleButtonGroup size="small" exclusive fullWidth value={selfSelected} aria-label="按自选状态筛选" onChange={(_, value: GuessSelfFilter | null) => { if (value) onSelfChange(value); }}><ToggleButton value="all">全部来源</ToggleButton><ToggleButton value="self">自选</ToggleButton><ToggleButton value="other">非自选</ToggleButton></ToggleButtonGroup>
      </Box>
    </Paper>
  );
}

const GuessChartCard = memo(function GuessChartCard({ chart, selecting, selected, onOpen }: { chart: GuessChartRead; selecting: boolean; selected: boolean; onOpen: (chart: GuessChartRead) => void }) {
  const isJ = chart.lane === "j";
  const levelSlot = getChartLevelSlot(chart.source_level_slot);
  const levelSurface = GUESS_LEVEL_SURFACES[levelSlot] ?? "background.paper";
  return (
    <Card variant="outlined" data-lane={isJ ? "j" : "normal"} data-level-slot={levelSlot ? `lv_${levelSlot}` : undefined} sx={{ position: "relative", height: "100%", borderWidth: isJ ? 2 : 1, borderColor: selected ? "primary.main" : isJ ? "secondary.main" : "divider", outline: selected ? "2px solid" : "none", outlineColor: "primary.main" }}>
      <CardActionArea onClick={() => onOpen(chart)} sx={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "stretch" }}>
        {chart.cover_path ? <CardMedia component="img" height="164" image={chart.cover_path} alt="" loading="lazy" decoding="async" sx={{ objectFit: "cover", bgcolor: "#E4EAE6" }} /> : <Box sx={{ height: 164, flexShrink: 0, display: "grid", placeItems: "center", bgcolor: "#E4EAE6", color: "text.secondary" }}><Music2 size={38} /></Box>}
        <CardContent sx={{ width: "100%", flex: 1, display: "flex", flexDirection: "column", bgcolor: levelSurface, color: "#17211D", transition: "background-color 160ms ease", "& .MuiTypography-colorTextSecondary": { color: "#45534D" } }}>
          <Typography variant="h3" noWrap title={chart.title}>{chart.title}</Typography>
          <Stack direction="row" spacing={0.75} useFlexGap sx={{ mt: 1, flexWrap: "wrap" }}><Chip size="small" label={chart.level} /><Chip size="small" color={isJ ? "secondary" : "default"} variant={isJ ? "filled" : "outlined"} label={isJ ? "J 谱" : "普通谱"} /><Chip size="small" color={chart.is_self_selected ? "warning" : "default"} variant={chart.is_self_selected ? "filled" : "outlined"} label={chart.is_self_selected ? "自选" : "非自选"} /></Stack>
          <Stack spacing={0.25} sx={{ mt: 1.25, minHeight: 42 }}><Typography variant="body2" color="text.secondary" noWrap title={chart.author}><Box component="span" sx={{ fontWeight: 700 }}>曲师</Box>　{chart.author}</Typography>{chart.designer ? <Typography variant="body2" color="text.secondary" noWrap title={chart.designer}><Box component="span" sx={{ fontWeight: 700 }}>谱师</Box>　{chart.designer}</Typography> : null}</Stack>
          <Stack direction="row" spacing={2} sx={{ mt: "auto", pt: 1.5 }}><Typography variant="caption"><Heart size={13} /> {chart.love_votes}</Typography><Typography variant="caption"><Sparkles size={13} /> {chart.funny_votes}</Typography><Typography variant="caption">查看 {chart.plays}</Typography></Stack>
        </CardContent>
      </CardActionArea>
      {selecting ? <Checkbox checked={selected} slotProps={{ input: { "aria-label": `选择 ${chart.title}` } }} sx={{ position: "absolute", top: 6, right: 6, bgcolor: "rgba(255,255,255,.9)", "&:hover": { bgcolor: "white" } }} onChange={() => onOpen(chart)} /> : null}
    </Card>
  );
});

export default function GuessPage() {
  const charts = useResource(api.guessCharts, []);
  const [active, setActive] = useState<GuessChartRead | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [selecting, setSelecting] = useState(false);
  const [levelFilter, setLevelFilter] = useState("all");
  const [laneFilter, setLaneFilter] = useState<GuessLaneFilter>("all");
  const [selfFilter, setSelfFilter] = useState<GuessSelfFilter>("all");
  const [error, setError] = useState("");
  const allCharts = charts.data ?? EMPTY_GUESS_CHARTS;
  const levels = useMemo(() => [...new Set(allCharts.map((chart) => chart.level))].sort(compareChartLevels), [allCharts]);
  const filteredCharts = useMemo(() => allCharts.filter((chart) => (levelFilter === "all" || chart.level === levelFilter) && (laneFilter === "all" || chart.lane === laneFilter) && (selfFilter === "all" || (selfFilter === "self" ? chart.is_self_selected : !chart.is_self_selected))), [allCharts, laneFilter, levelFilter, selfFilter]);

  function clearSelection() { setSelected(new Set()); }
  function resetFilters() { setLevelFilter("all"); setLaneFilter("all"); setSelfFilter("all"); clearSelection(); }
  const open = useCallback((chart: GuessChartRead) => {
    if (selecting) { setSelected((current) => { const next = new Set(current); if (next.has(chart.id)) next.delete(chart.id); else next.add(chart.id); return next; }); return; }
    void api.guessChart(chart.id).then(setActive).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, [selecting]);

  return (
    <Stack spacing={3}>
      <PageHeader icon={Vote} title="猜谱" meta={`显示 ${filteredCharts.length} / 共 ${allCharts.length} 张谱面`} actions={<><Button variant={selecting ? "contained" : "outlined"} startIcon={<ClipboardList size={17} />} onClick={() => { setSelecting(!selecting); if (selecting) clearSelection(); }}>{selecting ? "结束选择" : "批量选择"}</Button>{selecting ? <Button variant="contained" startIcon={<Download size={17} />} disabled={!selected.size} onClick={() => void api.downloadCharts([...selected]).catch((err) => setError(err instanceof Error ? err.message : "下载失败"))}>下载 {selected.size} 项</Button> : null}</>} />
      {error ? <Alert severity="error">{error}</Alert> : null}
      <ResourceState loading={charts.loading} error={charts.error} empty={!allCharts.length ? "暂无谱面" : undefined} />
      {allCharts.length ? <GuessFilterPanel levels={levels} level={levelFilter} lane={laneFilter} selfSelected={selfFilter} onLevelChange={(value) => { setLevelFilter(value); clearSelection(); }} onLaneChange={(value) => { setLaneFilter(value); clearSelection(); }} onSelfChange={(value) => { setSelfFilter(value); clearSelection(); }} onReset={resetFilters} /> : null}
      {filteredCharts.length ? <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(3, 1fr)", xl: "repeat(4, 1fr)" }, gap: 2 }}>{filteredCharts.map((chart) => <GuessChartCard key={chart.id} chart={chart} selecting={selecting} selected={selected.has(chart.id)} onOpen={open} />)}</Box> : allCharts.length ? <Paper variant="outlined" sx={{ py: 7, px: 2, textAlign: "center" }}><Typography color="text.secondary">没有符合当前筛选条件的谱面</Typography><Button variant="outlined" sx={{ mt: 2 }} onClick={resetFilters}>清除筛选</Button></Paper> : null}
      <GuessDetailDialog chart={active} onClose={() => setActive(null)} onChanged={async () => { const next = await charts.reload(); if (active && next) setActive(next.find((item) => item.id === active.id) || null); }} />
    </Stack>
  );
}

function GuessDetailDialog({ chart, onClose, onChanged }: { chart: GuessChartRead | null; onClose: () => void; onChanged: () => Promise<void> }) {
  const [comments, setComments] = useState<GuessCommentRead[]>([]);
  const [authorState, setAuthorState] = useState<AuthorGuessState | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const { isLoggedIn } = useAuth();
  useEffect(() => {
    if (!chart) return;
    Promise.all([api.comments(chart.id), api.authorGuess(chart.id)]).then(([nextComments, nextAuthor]) => { setComments(nextComments); setAuthorState(nextAuthor); }).catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, [chart?.id]);
  if (!chart) return null;
  async function toggleVote(type: "love" | "funny") { if (chart.my_votes.includes(type)) await api.unvote(chart.id, type); else await api.vote(chart.id, type); await onChanged(); }
  async function sendComment() { if (!comment.trim()) return; const created = await api.createComment(chart.id, comment.trim()); setComments((current) => [created, ...current]); setComment(""); }
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md" fullScreen={false}>
      <DialogTitle sx={{ pr: 6 }}><Typography variant="h2">{chart.title}</Typography><Stack direction="row" spacing={0.75} useFlexGap sx={{ my: 1, flexWrap: "wrap" }}><Chip size="small" label={chart.level} /><Chip size="small" color={chart.lane === "j" ? "secondary" : "default"} variant={chart.lane === "j" ? "filled" : "outlined"} label={chart.lane === "j" ? "J 谱" : "普通谱"} /><Chip size="small" color={chart.is_self_selected ? "warning" : "default"} variant={chart.is_self_selected ? "filled" : "outlined"} label={chart.is_self_selected ? "自选" : "非自选"} /></Stack><Typography variant="body2" color="text.secondary">曲师：{chart.author}</Typography>{chart.designer ? <Typography variant="body2" color="text.secondary">谱师：{chart.designer}</Typography> : null}<Typography variant="caption" color="text.secondary">查看 {chart.plays} 次</Typography><IconButton aria-label="关闭谱面详情" onClick={onClose} sx={{ position: "absolute", right: 12, top: 12 }}><X size={20} /></IconButton></DialogTitle>
      <DialogContent dividers>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1fr) 280px" }, gap: 3 }}>
          {chart.cover_path ? <Box component="img" src={chart.cover_path} alt="" sx={{ width: "100%", maxHeight: 420, objectFit: "cover", borderRadius: 1 }} /> : <Box sx={{ minHeight: 260, display: "grid", placeItems: "center", bgcolor: "background.default" }}><Music2 size={42} /></Box>}
          <Stack spacing={2}><Button variant="contained" startIcon={<Download size={17} />} onClick={() => void api.downloadChart(chart.id).catch((err) => setError(err instanceof Error ? err.message : "下载失败"))}>下载投稿</Button><Stack direction="row" spacing={1}><Button fullWidth variant={chart.my_votes.includes("love") ? "contained" : "outlined"} color="error" startIcon={<Heart size={16} />} disabled={!isLoggedIn} onClick={() => void toggleVote("love").catch((err) => setError(err.message))}>{chart.love_votes}</Button><Button fullWidth variant={chart.my_votes.includes("funny") ? "contained" : "outlined"} color="secondary" startIcon={<Sparkles size={16} />} disabled={!isLoggedIn} onClick={() => void toggleVote("funny").catch((err) => setError(err.message))}>{chart.funny_votes}</Button></Stack>{authorState?.can_guess && authorState.candidates.length ? <FormControl size="small"><InputLabel>作者猜测</InputLabel><Select label="作者猜测" value={authorState.my_guess_user_id || ""} onChange={(e) => void api.saveAuthorGuess(chart.id, Number(e.target.value)).then(async () => { setAuthorState(await api.authorGuess(chart.id)); })}><MenuItem value=""><em>未选择</em></MenuItem>{authorState.candidates.map((item) => <MenuItem key={item.user_id} value={item.user_id}>{item.display_id}</MenuItem>)}</Select></FormControl> : null}{error ? <Alert severity="error">{error}</Alert> : null}</Stack>
        </Box>
        <Divider sx={{ my: 3 }} /><Typography variant="h3" sx={{ mb: 1.5 }}>评论</Typography>{isLoggedIn ? <Stack direction="row" spacing={1} sx={{ mb: 2 }}><TextField size="small" fullWidth placeholder="写下你的评价" value={comment} onChange={(e) => setComment(e.target.value)} /><IconButton color="primary" aria-label="发送评论" onClick={() => void sendComment().catch((err) => setError(err.message))}><MessageSquare size={19} /></IconButton></Stack> : null}<Stack spacing={1}>{comments.map((item) => <Paper key={item.id} variant="outlined" sx={{ p: 1.5 }}><Typography variant="body2">{item.content}</Typography><Typography variant="caption" color="text.secondary">{item.user.display_name || item.user.user_code} · {formatTime(item.created_at)}</Typography></Paper>)}</Stack>
      </DialogContent>
    </Dialog>
  );
}
