import { Alert, Box, Button, Card, CardActionArea, Paper, Stack, Typography } from "@mui/material";
import { BookOpenText, ChevronRight, FileDown, LogIn, Music2, Sparkles, Upload, Vote } from "lucide-react";
import { Link } from "react-router-dom";
import { AnnouncementMarkdown } from "../components/AnnouncementMarkdown";
import { PhaseHeadline, PhaseTimeline, PHASE_LABELS } from "../components/EventPhaseStatus";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";

export default function HomePage() {
  const { event, phases } = useConfig();
  const { user, isLoggedIn, isAdmin, isPoolEditor } = useAuth();
  const stages = [
    { label: "曲池", value: `${event?.settings.participant_song_limit ?? "-"} 首上限`, icon: Music2, to: "/songs" },
    { label: "抽签", value: `每人 ${event?.settings.draw_songs_per_participant ?? "-"} 首`, icon: Sparkles, to: "/draw" },
    { label: "投稿", value: phases?.capabilities.submission ? "开放中" : "当前未开放", icon: Upload, to: "/submissions" },
    { label: "猜谱", value: phases ? PHASE_LABELS[phases.active_phase] : "查看与投票", icon: Vote, to: "/guess" },
  ].filter(({ to }) => to !== "/guess" || isAdmin || isPoolEditor || event?.settings.guess_game_visible === true || phases?.capabilities.normal_submission_public);
  const nextAction = !isLoggedIn ? "登录或注册后选择参赛者 / 观众身份" : user?.identity === "participant" ? (phases?.capabilities.swap ? "检查抽签结果并提交换曲申请" : phases?.capabilities.submission ? "上传或检查你的投稿包" : phases?.capabilities.author_guess ? "浏览普通稿并提交作者竞猜" : "关注下一阶段开放时间") : phases?.capabilities.author_guess ? "观众也可以参与普通稿作者竞猜" : "关注赛程，猜谱阶段即可参与互动";
  return (
    <Stack spacing={3}>
      <Paper sx={{ p: { xs: 2.5, md: 4 }, borderLeft: 5, borderColor: "primary.main" }}>
        <Typography variant="overline" color="primary.main" sx={{ fontWeight: 800 }}>CURRENT EVENT</Typography>
        <Typography variant="h1" sx={{ mt: 0.5 }}>{event?.name || "赛事进行中"}</Typography>
        {phases ? <Box sx={{ mt: 2 }}><PhaseHeadline phases={phases} /></Box> : null}
        {event?.settings.announcement_text ? <Box sx={{ mt: 1.5, maxWidth: 760, color: "text.secondary", "& .announcement-markdown": { color: "inherit" } }}><AnnouncementMarkdown>{event.settings.announcement_text}</AnnouncementMarkdown></Box> : null}
        <Stack direction="row" spacing={1} useFlexGap sx={{ mt: 2.5, flexWrap: "wrap" }}>
          {!isLoggedIn ? <Button component={Link} to="/login" variant="contained" startIcon={<LogIn size={18} />}>进入赛事</Button> : null}
          <Button component="a" href="/api/v1/assets/rule/view" target="_blank" rel="noopener noreferrer" variant="outlined" startIcon={<BookOpenText size={18} />}>查看规则</Button>
          <Button component="a" href="/api/v1/assets/banlist/download" variant="outlined" startIcon={<FileDown size={18} />}>往期 Ban 曲列表</Button>
        </Stack>
      </Paper>
      {phases ? <PhaseTimeline phases={phases} /> : null}
      <Alert severity="info" icon={false}><Typography variant="caption" sx={{ fontWeight: 800, display: "block" }}>下一步</Typography>{nextAction}</Alert>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: `repeat(${stages.length}, minmax(0, 1fr))` }, gap: 2 }}>
        {stages.map(({ label, value, icon: Icon, to }) => <Card key={label} variant="outlined"><CardActionArea component={Link} to={to} sx={{ p: 2.5, minHeight: 132 }}><Stack direction="row" sx={{ justifyContent: "space-between" }}><Icon size={24} color="#176B52" /><ChevronRight size={18} /></Stack><Typography variant="h3" sx={{ mt: 2 }}>{label}</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{value}</Typography></CardActionArea></Card>)}
      </Box>
    </Stack>
  );
}
