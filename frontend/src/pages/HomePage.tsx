import { Box, Button, Card, CardActionArea, Paper, Stack, Typography } from "@mui/material";
import { BookOpenText, ChevronRight, FileDown, LogIn, Music2, Sparkles, Upload, Vote } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";


export default function HomePage() {
  const { event } = useConfig();
  const { isLoggedIn } = useAuth();
  const stages = [
    { label: "曲池", value: `${event?.settings.participant_song_limit ?? "-"} 首上限`, icon: Music2, to: "/songs" },
    { label: "抽签", value: `每人 ${event?.settings.draw_songs_per_participant ?? "-"} 首`, icon: Sparkles, to: "/draw" },
    { label: "投稿", value: event?.settings.submissions_open ? "开放中" : "等待开放", icon: Upload, to: "/submissions" },
    { label: "猜谱", value: "查看与投票", icon: Vote, to: "/guess" },
  ];
  return (
    <Stack spacing={3}>
      <Paper sx={{ p: { xs: 2.5, md: 4 }, borderLeft: 5, borderColor: "primary.main" }}>
        <Typography variant="overline" color="primary.main" sx={{ fontWeight: 800 }}>CURRENT EVENT</Typography>
        <Typography variant="h1" sx={{ mt: 0.5 }}>{event?.name || "赛事进行中"}</Typography>
        {event?.settings.announcement_text ? <Typography color="text.secondary" sx={{ mt: 1.5, maxWidth: 760, whiteSpace: "pre-wrap" }}>{event.settings.announcement_text}</Typography> : null}
        <Stack direction="row" spacing={1} useFlexGap sx={{ mt: 2.5, flexWrap: "wrap" }}>
          {!isLoggedIn ? <Button component={Link} to="/login" variant="contained" startIcon={<LogIn size={18} />}>进入赛事</Button> : null}
          <Button component="a" href="/api/v1/assets/rule/view" target="_blank" rel="noopener noreferrer" variant="outlined" startIcon={<BookOpenText size={18} />}>查看规则</Button>
          <Button component="a" href="/api/v1/assets/banlist/download" variant="outlined" startIcon={<FileDown size={18} />}>往期 Ban 曲列表</Button>
        </Stack>
      </Paper>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(4, 1fr)" }, gap: 2 }}>
        {stages.map(({ label, value, icon: Icon, to }) => (
          <Card key={label} variant="outlined">
            <CardActionArea component={Link} to={to} sx={{ p: 2.5, minHeight: 132 }}>
              <Stack direction="row" sx={{ justifyContent: "space-between" }}><Icon size={24} color="#176B52" /><ChevronRight size={18} /></Stack>
              <Typography variant="h3" sx={{ mt: 2 }}>{label}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{value}</Typography>
            </CardActionArea>
          </Card>
        ))}
      </Box>
    </Stack>
  );
}
