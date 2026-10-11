import { Box, Button, Card, CardActionArea, Stack, Typography } from "@mui/material";
import { Archive, BookOpenText, ChevronRight, LogIn, Music2, Sparkles, Upload, Vote } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { isGuessEnded, phaseStatusLabel, PhaseHeadline, PhaseTimeline } from "../components/EventPhaseStatus";
import EventHeroArt from "../components/EventHeroArt";
import HomePageSkeleton from "../components/HomePageSkeleton";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";
import { useEventTheme } from "../contexts/EventThemeProvider";
import { useEventBackgrounds } from "../hooks/useEventBackgrounds";
import { ViewTransitionLink } from "../navigation/ViewTransitionLink";
import { navigateWithViewTransition } from "../navigation/viewTransition";

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
  const backgrounds = useEventBackgrounds();
  const { palette } = useEventTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const skipEnter = Boolean((location.state as { zppzVt?: string } | null)?.zppzVt);
  if (loading || !event) return <HomePageSkeleton />;

  const heroArt = backgrounds.hero;
  const guessEnded = phases ? isGuessEnded(phases) : false;
  const stages = [
    { label: "曲池", value: `${event?.settings.participant_song_limit ?? "-"} 首上限`, icon: Music2, to: "/songs", open: true },
    { label: "曲目分配", value: `每人 ${event?.settings.draw_songs_per_participant ?? "-"} 首`, icon: Sparkles, to: "/draw", open: true },
    { label: "投稿", value: phases?.capabilities.submission ? "开放中" : "当前未开放", icon: Upload, to: "/submissions", open: Boolean(phases?.capabilities.submission) },
    { label: "猜谱", value: phases ? phaseStatusLabel(phases) : "查看与投票", icon: Vote, to: "/guess", open: true },
    { label: "往届乐曲", value: "按届 / 按谱师浏览", icon: Archive, to: "/archive", open: true },
  ].filter(({ to }) => to !== "/guess" || isAdmin || isPoolEditor || guessGameAvailable);
  const nextAction = !isLoggedIn
    ? "登录或注册后选择参赛者、观众或访客身份"
    : guessEnded
      ? "猜谱已截止，可查看谱面与已有互动记录"
      : user?.identity === "participant"
        ? phases?.capabilities.swap && phases?.capabilities.normal_submission_public
          ? "缓冲期内可继续投稿、换曲，并参与已公开谱面的投票与作者竞猜"
          : phases?.capabilities.swap
            ? "在 Stage2 检查曲目、连续换曲并提交投稿"
            : phases?.capabilities.submission
              ? "上传或检查你的投稿包"
              : phases?.capabilities.author_guess
                ? "浏览普通稿并提交作者竞猜"
                : "关注下一阶段开放时间"
        : phases?.capabilities.author_guess
          ? "当前身份可以参与普通稿作者竞猜"
          : "关注赛程，猜谱阶段即可参与互动";

  return (
    <Box>
      <Box
        component="section"
        sx={{
          position: "relative",
          width: "100%",
          minHeight: { xs: "92vh", md: 720 },
          display: "flex",
          alignItems: { xs: "flex-end", md: "center" },
          overflow: "hidden",
        }}
      >
        {heroArt ? (
          <EventHeroArt asset={heroArt} animate={!skipEnter} />
        ) : (
          <Box
            aria-hidden="true"
            sx={{
              position: "absolute",
              inset: 0,
              backgroundImage: `radial-gradient(520px 260px at 78% 0%, ${palette.accentSoft}, transparent 62%), radial-gradient(680px 320px at 96% 100%, ${palette.washA}, transparent 58%)`,
              bgcolor: "background.default",
            }}
          />
        )}

        <Box
          sx={{
            position: "relative",
            zIndex: 1,
            width: "100%",
            maxWidth: 1280,
            mx: "auto",
            px: { xs: 2.5, md: 8 },
            py: { xs: 4, md: 0 },
            pb: { xs: 5, md: 0 },
          }}
        >
          <Box sx={{ maxWidth: 560 }}>
            <Typography
              sx={{
                fontFamily: '"Noto Serif SC", serif',
                fontWeight: 700,
                fontSize: { xs: "1.75rem", md: "2.25rem" },
                lineHeight: 1,
                letterSpacing: "-0.01em",
              }}
            >
              ZPPZ 
            </Typography>
            <Typography
              sx={{
                mt: 1,
                fontWeight: 600,
                fontSize: { xs: 12, md: 14 },
                letterSpacing: "0.18em",
                color: "primary.main",
              }}
            >
              这谱谱这
            </Typography>
            <Box aria-hidden="true" sx={{ mt: 1.5, width: 32, height: 2, borderRadius: 1, bgcolor: "primary.main", opacity: 0.55 }} />

            <Typography variant="h1" component="h1" sx={{ mt: 2.5, mb: 0 }}>
              {event.name}
            </Typography>
            <Typography
              sx={{
                mt: 2,
                mb: 0,
                maxWidth: 420,
                fontWeight: 300,
                fontSize: { xs: "0.9375rem", md: "1.0625rem" },
                lineHeight: 1.7,
                color: "text.secondary",
              }}
            >
              
            </Typography>这谱谱这是一款类魂游戏风格的开放世界游戏，你将扮演一名谱师，在开放世界中探索、收集乐谱，并与其他谱师进行战斗。

            {phases ? (
              <Box sx={{ mt: 2.5 }}>
                <PhaseHeadline phases={phases} />
              </Box>
            ) : null}

            {event.settings.announcement_text ? (
              <Box
                sx={{
                  mt: 2,
                  p: 1.5,
                  maxWidth: 480,
                  display: "flex",
                  gap: 1,
                  alignItems: "center",
                  justifyContent: "space-between",
                  border: 1,
                  borderColor: "divider",
                  bgcolor: "rgba(255,255,255,0.86)",
                  backdropFilter: "blur(6px)",
                }}
              >
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{
                    minWidth: 0,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                  }}
                >
                  {announcementPreview(event.settings.announcement_text)}
                </Typography>
                <Button size="small" onClick={onOpenAnnouncement} sx={{ flexShrink: 0 }}>查看公告</Button>
              </Box>
            ) : null}

            <Stack direction={{ xs: "column", sm: "row" }} spacing={{ xs: 1.5, sm: 3 }} sx={{ mt: 3.5, alignItems: { sm: "center" } }}>
              {!isLoggedIn ? (
                <Button
                  variant="contained"
                  startIcon={<LogIn size={18} />}
                  onClick={() => navigateWithViewTransition(navigate, "/login")}
                  sx={{
                    minHeight: 48,
                    px: 3.5,
                    borderRadius: 1,
                    alignSelf: { xs: "stretch", sm: "auto" },
                  }}
                >
                  进入赛事
                </Button>
              ) : null}
              <Button
                component="a"
                href="/api/v1/assets/rule/view"
                target="_blank"
                rel="noopener noreferrer"
                variant="text"
                startIcon={<BookOpenText size={18} />}
                sx={{
                  minHeight: 48,
                  px: 0.5,
                  borderRadius: 0,
                  color: "text.primary",
                  borderBottom: "1px solid",
                  borderColor: "rgba(28,35,33,0.35)",
                  alignSelf: { xs: "flex-start", sm: "auto" },
                  "&:hover": { bgcolor: "transparent", color: "primary.main", borderColor: "primary.main" },
                }}
              >
                查看规则
              </Button>
            </Stack>
          </Box>
        </Box>

        {!heroArt ? (
          <Box
            aria-hidden="true"
            sx={{
              position: "absolute",
              right: { xs: -28, md: 40 },
              bottom: { xs: -30, md: -20 },
              color: palette.darker,
              opacity: 0.08,
              pointerEvents: "none",
              display: { xs: "none", md: "block" },
              zIndex: 0,
            }}
          >
            <Music2 size={224} strokeWidth={1} />
          </Box>
        ) : null}
      </Box>

      <Box sx={{ maxWidth: 1280, mx: "auto", px: { xs: 2.5, md: 8 }, py: { xs: 5, md: 10 } }}>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1fr) minmax(0, 2fr)" },
            gap: { xs: 4, lg: 8 },
            mb: { xs: 5, md: 8 },
          }}
        >
          <Box>
            <Typography variant="h2" sx={{ mb: 2.5 }}>当前阶段</Typography>
            <Box sx={{ p: 3, border: 1, borderColor: "divider", bgcolor: "#F4F6F5" }}>
              <Typography variant="caption" sx={{ fontWeight: 800, display: "block", mb: 1, color: "text.secondary" }}>下一步</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, lineHeight: 1.7 }}>{nextAction}</Typography>
              {phases ? <PhaseHeadline phases={phases} /> : null}
            </Box>
          </Box>
          <Box>
            {phases ? <PhaseTimeline phases={phases} /> : null}
          </Box>
        </Box>

        <Typography variant="h2" sx={{ mb: 3 }}>探索赛区</Typography>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(3, minmax(0, 1fr))" },
            gap: 2,
          }}
        >
          {stages.map(({ label, value, icon: Icon, to, open }) => (
            <Card
              key={label}
              variant="outlined"
              sx={{
                borderRadius: 0,
                boxShadow: "none",
                borderColor: "rgba(28,35,33,0.08)",
                borderTop: open && to === "/submissions" && phases?.capabilities.submission ? "2px solid" : undefined,
                borderTopColor: open && to === "/submissions" && phases?.capabilities.submission ? "primary.main" : undefined,
                transition: "transform 400ms cubic-bezier(0.16, 1, 0.3, 1), border-color 200ms ease, box-shadow 400ms ease",
                "&:hover": {
                  transform: "translateY(-4px)",
                  borderColor: "rgba(28,35,33,0.25)",
                  boxShadow: "0 12px 24px -8px rgba(28,35,33,0.08)",
                },
              }}
            >
              <CardActionArea
                component={ViewTransitionLink}
                to={to}
                sx={{
                  p: { xs: 2.5, md: 3.5 },
                  minHeight: { xs: 88, md: 168 },
                  display: "flex",
                  flexDirection: { xs: "row", md: "column" },
                  alignItems: { xs: "center", md: "stretch" },
                  gap: { xs: 1.5, md: 0 },
                }}
              >
                <Icon size={24} color={palette.main} style={{ flexShrink: 0 }} />
                <Box sx={{ flex: 1, minWidth: 0, mt: { md: 2 } }}>
                  <Typography variant="h3">{label}</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{value}</Typography>
                </Box>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, color: "primary.main", mt: { md: "auto" }, pt: { md: 2 } }}>
                  <Typography variant="body2" sx={{ fontWeight: 600, display: { xs: "none", md: "block" } }}>进入</Typography>
                  <ChevronRight size={18} />
                </Box>
              </CardActionArea>
            </Card>
          ))}
        </Box>
      </Box>
    </Box>
  );
}
