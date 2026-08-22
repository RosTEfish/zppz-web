import { Alert, Box, Button, Card, CardActionArea, Paper, Stack, Typography } from "@mui/material";
import { BookOpenText, ChevronRight, LogIn, Music2, Sparkles, Upload, Vote } from "lucide-react";
import { Link } from "react-router-dom";
import { isGuessEnded, phaseStatusLabel, PhaseHeadline, PhaseTimeline } from "../components/EventPhaseStatus";
import HomePageSkeleton from "../components/HomePageSkeleton";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";

function announcementPreview(markdown: string) {
  const text = markdown
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/[\[\]`*_>#-]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return text.length > 180 ? `${text.slice(0, 180)}…` : text;
}

export default function HomePage({ onOpenAnnouncement }: { onOpenAnnouncement?: () => void }) {
  const { event, phases, guessGameAvailable, loading } = useConfig();
  const { user, isLoggedIn, isAdmin, isPoolEditor } = useAuth();
  if (loading || !event) return <HomePageSkeleton />;

  const guessEnded = phases ? isGuessEnded(phases) : false;
  const stages = [
    { label: "曲池", value: `${event?.settings.participant_song_limit ?? "-"} 首上限`, icon: Music2, to: "/songs" },
    { label: "曲目分配", value: `每人 ${event?.settings.draw_songs_per_participant ?? "-"} 首`, icon: Sparkles, to: "/draw" },
    { label: "投稿", value: phases?.capabilities.submission ? "开放中" : "当前未开放", icon: Upload, to: "/submissions" },
    { label: "猜谱", value: phases ? phaseStatusLabel(phases) : "查看与投票", icon: Vote, to: "/guess" },
  ].filter(({ to }) => to !== "/guess" || isAdmin || isPoolEditor || guessGameAvailable);
  const nextAction = !isLoggedIn ? "登录或注册后选择参赛者、观众或访客身份" : guessEnded ? "猜谱已截止，可查看谱面与已有互动记录" : user?.identity === "participant" ? (phases?.capabilities.swap ? "在 Stage2 检查曲目、连续换曲并提交投稿" : phases?.capabilities.submission ? "上传或检查你的投稿包" : phases?.capabilities.author_guess ? "浏览普通稿并提交作者竞猜" : "关注下一阶段开放时间") : phases?.capabilities.author_guess ? "当前身份可以参与普通稿作者竞猜" : "关注赛程，猜谱阶段即可参与互动";
  return (
    <Stack spacing={3}>
      <Paper sx={{ p: { xs: 2.5, md: 4 }, minHeight: { xs: 292, md: 246 }, borderLeft: 5, borderColor: "primary.main", position: "relative", overflow: "hidden", borderRadius: "16px", backgroundImage: "radial-gradient(520px 260px at 78% 0%, rgba(201,151,59,0.13), transparent 62%), radial-gradient(680px 320px at 96% 100%, rgba(23,107,82,0.11), transparent 58%)" }}>
        <Typography variant="overline" color="primary.dark" sx={{ fontWeight: 800 }}>CURRENT EVENT</Typography>
        <Box aria-hidden="true" sx={{ width: 26, height: 2.5, borderRadius: 1, bgcolor: "#C9973B", mt: 0.5, mb: 0.75 }} />
        <Typography variant="h1" component="p" sx={{ m: 0 }}>{event.name}</Typography>
        {phases ? <Box sx={{ mt: 2 }}><PhaseHeadline phases={phases} /></Box> : null}
        {event.settings.announcement_text ? (
          <Paper variant="outlined" sx={{ mt: 1.5, p: 1.25, maxWidth: 760, color: "text.secondary", display: "flex", gap: 1, alignItems: "center", justifyContent: "space-between" }}>
            <Typography variant="body2" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
              {announcementPreview(event.settings.announcement_text)}
            </Typography>
            <Button size="small" onClick={onOpenAnnouncement} sx={{ flexShrink: 0 }}>查看公告</Button>
          </Paper>
        ) : null}
        <Stack direction="row" spacing={1} useFlexGap sx={{ mt: 2.5, flexWrap: "wrap" }}>
          {!isLoggedIn ? <Button component={Link} to="/login" variant="contained" startIcon={<LogIn size={18} />}>进入赛事</Button> : null}
          <Button component="a" href="/api/v1/assets/rule/view" target="_blank" rel="noopener noreferrer" variant="outlined" startIcon={<BookOpenText size={18} />}>查看规则</Button>
        </Stack>
        <Box aria-hidden="true" sx={{ position: "absolute", right: { xs: -28, md: 16 }, bottom: { xs: -30, md: -34 }, color: "#0A3B2D", opacity: 0.09, pointerEvents: "none", display: { xs: "none", md: "block" } }}>
          <Music2 size={224} strokeWidth={1} />
        </Box>
      </Paper>
      {phases ? <PhaseTimeline phases={phases} /> : null}
      <Alert severity="info" icon={false}><Typography variant="caption" sx={{ fontWeight: 800, display: "block" }}>下一步</Typography>{nextAction}</Alert>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: `repeat(${stages.length}, minmax(0, 1fr))` }, gap: 2 }}>
        {stages.map(({ label, value, icon: Icon, to }) => <Card key={label} variant="outlined"><CardActionArea component={Link} to={to} sx={{ p: 2.5, minHeight: 132 }}><Stack direction="row" sx={{ justifyContent: "space-between" }}><Icon size={24} color="#176B52" /><ChevronRight size={18} /></Stack><Typography variant="h3" sx={{ mt: 2 }}>{label}</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{value}</Typography></CardActionArea></Card>)}
      </Box>
    </Stack>
  );
}
