import { lazy, type ReactNode, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { AppBar, Box, Button, Chip, Container, CssBaseline, Divider, Drawer, IconButton, List, ListItemButton, ListItemIcon, ListItemText, Stack, Toolbar, Typography, useMediaQuery, useTheme } from "@mui/material";
import { ThemeProvider } from "@mui/material/styles";
import { theme as fallbackTheme } from "./theme";
import { Archive, Gauge, Home, LogIn, LogOut, Menu as MenuIcon, Music2, Sparkles, Upload, Vote } from "lucide-react";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ViewTransitionLink } from "./navigation/ViewTransitionLink";
import { navigateWithViewTransition } from "./navigation/viewTransition";
import { SWRConfig } from "swr";
import BrandLogo from "./components/BrandLogo";
import { LoadingBlock } from "./components/PagePrimitives";
import HomePageSkeleton from "./components/HomePageSkeleton";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ConfigProvider, useConfig } from "./contexts/ConfigContext";
import { EventThemeProvider, useEventTheme } from "./contexts/EventThemeProvider";
import beianIcon from "./assets/beian.png";
import { announcementSignature, shouldShowAnnouncement } from "./components/announcementState";
import { preloadAdminTab } from "./pages/admin/adminTabLoaders";
import { identityLabel } from "./identity";

const DRAWER_WIDTH = 280;

const loadHomePage = () => import("./pages/HomePage");
const loadAuthPage = () => import("./pages/AuthPage");
const loadSongPoolPage = () => import("./pages/SongPoolPage");
const loadDrawPage = () => import("./pages/DrawPage");
const loadSubmissionPage = () => import("./pages/SubmissionPage");
const loadGuessPage = () => import("./pages/GuessPage");
const loadArchivePage = () => import("./pages/ArchivePage");
const loadAccountPage = () => import("./pages/AccountPage");
const preloadAdminPage = (pathname: string) => Promise.all([
  import("./pages/AdminPage"),
  preloadAdminTab(pathname),
]);
const loadAdminPage = async () => {
  const [page] = await preloadAdminPage(window.location.pathname);
  return page;
};
const loadAnnouncementDialog = () => import("./components/AnnouncementDialog");

const HomePage = lazy(loadHomePage);
const AuthPage = lazy(loadAuthPage);
const SongPoolPage = lazy(loadSongPoolPage);
const DrawPage = lazy(loadDrawPage);
const SubmissionPage = lazy(loadSubmissionPage);
const GuessPage = lazy(loadGuessPage);
const ArchivePage = lazy(loadArchivePage);
const AccountPage = lazy(loadAccountPage);
const AdminPage = lazy(loadAdminPage);
const AnnouncementDialog = lazy(loadAnnouncementDialog);
const InteractionProviders = lazy(() => import("./components/InteractionProviders"));

function App() {
  return (
    <ThemeProvider theme={fallbackTheme}>
      <CssBaseline />
      <SWRConfig value={{ provider: () => new Map(), shouldRetryOnError: false, revalidateOnFocus: false }}>
        <Suspense fallback={null}>
          <InteractionProviders>
            <BrowserRouter>
              <AuthProvider>
                <ConfigProvider>
                  <EventThemeProvider>
                    <AppShell />
                  </EventThemeProvider>
                </ConfigProvider>
              </AuthProvider>
            </BrowserRouter>
          </InteractionProviders>
        </Suspense>
      </SWRConfig>
    </ThemeProvider>
  );
}

function AppShell() {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("md"));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  const { user, isLoggedIn, isAdmin, isPoolEditor, logout } = useAuth();
  const { event, phases, guessGameAvailable, loading: configLoading } = useConfig();
  const { palette } = useEventTheme();
  const navigate = useNavigate();
  const authLayout = location.pathname === "/login";
  const homeLayout = location.pathname === "/";
  const showGuessEntry = isAdmin || isPoolEditor || guessGameAvailable;
  const managerPath = isAdmin ? "/admin/overview" : "/admin/songs";
  const announcement = event?.settings.announcement_text ?? "";
  const showAnnouncement = useMemo(
    () => event ? shouldShowAnnouncement(event.id, announcement) : false,
    [announcement, event?.id],
  );
  const [announcementMounted, setAnnouncementMounted] = useState(false);
  const [announcementOpen, setAnnouncementOpen] = useState(false);
  const homepageReady = Boolean(event && !configLoading);
  const openAnnouncement = useCallback(() => {
    setAnnouncementMounted(true);
    setAnnouncementOpen(true);
  }, []);

  useEffect(() => {
    if (!event || !announcement || !showAnnouncement || !homepageReady) return;
    let cancelled = false;
    const openWhenIdle = () => {
      if (!cancelled) openAnnouncement();
    };
    const idleWindow = window as Window & {
      requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
      cancelIdleCallback?: (handle: number) => void;
    };
    const idleId = idleWindow.requestIdleCallback?.(openWhenIdle, { timeout: 1800 });
    const timeoutId = idleId === undefined ? window.setTimeout(openWhenIdle, 1800) : undefined;
    return () => {
      cancelled = true;
      if (idleId !== undefined) idleWindow.cancelIdleCallback?.(idleId);
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [announcement, event, homepageReady, openAnnouncement, showAnnouncement]);

  useEffect(() => setDrawerOpen(false), [location.pathname]);

  const links = [
    { label: "首页", to: "/", icon: Home, preload: loadHomePage },
    { label: "曲池", to: "/songs", icon: Music2, preload: loadSongPoolPage },
    { label: "曲目分配", to: "/draw", icon: Sparkles, preload: loadDrawPage },
    { label: "投稿", to: "/submissions", icon: Upload, preload: loadSubmissionPage },
    { label: "猜谱", to: "/guess", icon: Vote, preload: loadGuessPage },
    { label: "往届乐曲", to: "/archive", icon: Archive, preload: loadArchivePage },
  ].filter(({ to }) => to !== "/guess" || showGuessEntry);

  const mobileDrawer = (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Toolbar sx={{ gap: 1.5, minHeight: 72 }}>
        <BrandLogo size={36} borderRadius={2} />
        <Box sx={{ minWidth: 0 }}>
          <Typography noWrap sx={{ fontFamily: '"Noto Serif SC", serif', fontWeight: 700 }}>ZPPZ </Typography>
          <Typography variant="caption" color="text.secondary" noWrap>{event?.name || "赛事平台"}</Typography>
        </Box>
      </Toolbar>
      <Divider />
      <List sx={{ px: 1, py: 1.5 }}>
        {links.map(({ label, to, icon: Icon, preload }) => (
          <ListItemButton
            key={to}
            component={ViewTransitionLink}
            to={to}
            selected={location.pathname === to}
            onPointerEnter={() => void preload()}
            onFocus={() => void preload()}
            sx={{
              mb: 0.5,
              borderRadius: 1,
              borderLeft: "3px solid transparent",
              "&.Mui-selected": { borderLeftColor: "primary.main", bgcolor: palette.wash, color: "primary.dark" },
            }}
          >
            <ListItemIcon sx={{ minWidth: 38 }}><Icon size={19} /></ListItemIcon>
            <ListItemText primary={label} />
          </ListItemButton>
        ))}
        {(isAdmin || isPoolEditor) ? (
          <ListItemButton
            component={ViewTransitionLink}
            to={managerPath}
            selected={location.pathname.startsWith("/admin")}
            onPointerEnter={() => void preloadAdminPage(managerPath)}
            onFocus={() => void preloadAdminPage(managerPath)}
            sx={{
              mt: 1,
              borderRadius: 1,
              borderLeft: "3px solid transparent",
              "&.Mui-selected": { borderLeftColor: "primary.main", bgcolor: palette.wash, color: "primary.dark" },
            }}
          >
            <ListItemIcon sx={{ minWidth: 38 }}><Gauge size={19} /></ListItemIcon>
            <ListItemText primary="管理工作台" />
          </ListItemButton>
        ) : null}
      </List>
      <Box sx={{ flex: 1 }} />
      <Divider />
      <Box sx={{ p: 1.5 }}>
        {isLoggedIn ? (
          <Stack spacing={0.75}>
            <Box
              component={ViewTransitionLink}
              to="/account"
              aria-label={`${user?.display_name || user?.user_code || "账号"}，账号设置`}
              onPointerEnter={() => void loadAccountPage()}
              onFocus={() => void loadAccountPage()}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1.25,
                minHeight: 48,
                px: 1,
                py: 0.75,
                borderRadius: 2,
                textDecoration: "none",
                color: "inherit",
                bgcolor: location.pathname === "/account" ? palette.wash.replace("0.06", "0.08") : "transparent",
                "&:hover": { bgcolor: location.pathname === "/account" ? palette.wash.replace("0.06", "0.12") : "rgba(28, 35, 33, 0.04)" },
              }}
            >
              <BrandLogo size={36} borderRadius="50%" />
              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Typography noWrap sx={{ fontWeight: 700, fontSize: 14, lineHeight: 1.25 }}>
                  {user?.display_name || user?.user_code}
                </Typography>
                <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block", lineHeight: 1.35, mt: 0.15 }}>
                  {identityLabel(user?.identity)} · 账号设置
                </Typography>
              </Box>
            </Box>
            <Button
              size="small"
              color="inherit"
              startIcon={<LogOut size={15} />}
              onClick={() => void logout().then(() => navigateWithViewTransition(navigate, "/"))}
              sx={{ justifyContent: "flex-start", px: 1.25, minHeight: 36, color: "text.secondary", fontWeight: 600 }}
            >
              退出登录
            </Button>
          </Stack>
        ) : (
          <Button
            fullWidth
            variant="contained"
            startIcon={<LogIn size={17} />}
            onPointerEnter={() => void loadAuthPage()}
            onFocus={() => void loadAuthPage()}
            onClick={() => navigateWithViewTransition(navigate, "/login")}
          >
            登录
          </Button>
        )}
      </Box>
    </Box>
  );

  const routes = (
    <Suspense fallback={location.pathname === "/" ? <HomePageSkeleton /> : <LoadingBlock />}>
      <Routes>
        <Route path="/" element={<HomePage onOpenAnnouncement={openAnnouncement} />} />
        <Route path="/login" element={<AuthPage />} />
        <Route path="/songs" element={<RequireLogin><SongPoolPage /></RequireLogin>} />
        <Route path="/banlist" element={<Navigate to="/songs?view=ban-check" replace />} />
        <Route path="/draw" element={<RequireLogin><DrawPage /></RequireLogin>} />
        <Route path="/submissions" element={<RequireLogin><SubmissionPage /></RequireLogin>} />
        <Route path="/guess" element={<GuessPage />} />
        <Route path="/archive" element={<ArchivePage />} />
        <Route path="/account" element={<RequireLogin><AccountPage /></RequireLogin>} />
        <Route path="/admin/:tab" element={<RequireManager><AdminPage /></RequireManager>} />
        <Route path="/admin" element={<Navigate to="/admin/overview" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );

  if (authLayout) {
    return (
      <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
        {routes}
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar
        position="fixed"
        color="inherit"
        elevation={0}
        sx={{
          borderBottom: 1,
          borderColor: "divider",
          zIndex: theme.zIndex.drawer + 1,
          backgroundColor: "rgba(250,251,250,0.85)",
          backdropFilter: "blur(16px) saturate(1.3)",
          WebkitBackdropFilter: "blur(16px) saturate(1.3)",
        }}
      >
        <Toolbar sx={{ gap: 1.5, minHeight: 72, px: { xs: 2, md: 3.5 } }}>
          {mobile ? (
            <IconButton aria-label="打开导航" onClick={() => setDrawerOpen(true)} edge="start">
              <MenuIcon size={21} />
            </IconButton>
          ) : null}

          <Box
            component={ViewTransitionLink}
            to="/"
            onPointerEnter={() => void loadHomePage()}
            sx={{ display: "flex", alignItems: "center", gap: 1.25, minWidth: 0, color: "inherit", textDecoration: "none" }}
          >
            <BrandLogo size={32} borderRadius={2} />
            <Typography
              noWrap
              sx={{
                fontFamily: '"Noto Serif SC", serif',
                fontWeight: 700,
                fontSize: { xs: 16, md: 18 },
                letterSpacing: "-0.01em",
                display: { xs: "none", sm: "block" },
              }}
            >
              ZPPZ
            </Typography>
          </Box>

          {!mobile ? (
            <Stack direction="row" spacing={0.5} sx={{ ml: 3, flex: 1, alignItems: "stretch", minWidth: 0 }}>
              {links.map(({ label, to, preload }) => {
                const selected = location.pathname === to;
                return (
                  <Box
                    key={to}
                    component={ViewTransitionLink}
                    to={to}
                    onPointerEnter={() => void preload()}
                    onFocus={() => void preload()}
                    sx={{
                      px: 1.5,
                      display: "grid",
                      placeItems: "center",
                      fontSize: 14,
                      fontWeight: 600,
                      color: selected ? "text.primary" : "text.secondary",
                      borderBottom: "2px solid",
                      borderColor: selected ? "primary.main" : "transparent",
                      textDecoration: "none",
                      transition: "color 160ms ease, border-color 160ms ease",
                      "&:hover": { color: "text.primary" },
                    }}
                  >
                    {label}
                  </Box>
                );
              })}
              {(isAdmin || isPoolEditor) ? (
                <Box
                  component={ViewTransitionLink}
                  to={managerPath}
                  onPointerEnter={() => void preloadAdminPage(managerPath)}
                  onFocus={() => void preloadAdminPage(managerPath)}
                  sx={{
                    px: 1.5,
                    display: "grid",
                    placeItems: "center",
                    fontSize: 14,
                    fontWeight: 600,
                    color: location.pathname.startsWith("/admin") ? "text.primary" : "text.secondary",
                    borderBottom: "2px solid",
                    borderColor: location.pathname.startsWith("/admin") ? "primary.main" : "transparent",
                    textDecoration: "none",
                    "&:hover": { color: "text.primary" },
                  }}
                >
                  管理
                </Box>
              ) : null}
            </Stack>
          ) : (
            <Box sx={{ flex: 1 }} />
          )}

          {phases?.capabilities.submission ? (
            <Chip size="small" color="success" label="投稿开放" sx={{ display: { xs: "none", sm: "inline-flex" } }} />
          ) : (
            <Chip size="small" variant="outlined" label="投稿未开放" sx={{ display: { xs: "none", sm: "inline-flex" } }} />
          )}

          {!mobile ? (
            isLoggedIn ? (
              <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", flexShrink: 0 }}>
                <Button
                  component={ViewTransitionLink}
                  to="/account"
                  color="inherit"
                  aria-label={`${user?.display_name || user?.user_code || "账号"}，账号设置`}
                  onPointerEnter={() => void loadAccountPage()}
                  sx={{ fontWeight: 600, color: "text.secondary", "&:hover": { color: "text.primary" } }}
                >
                  {user?.display_name || user?.user_code || "账号"}
                </Button>
                <Button
                  color="inherit"
                  startIcon={<LogOut size={16} />}
                  onClick={() => void logout().then(() => navigateWithViewTransition(navigate, "/"))}
                  sx={{
                    fontWeight: 600,
                    color: "text.secondary",
                    minWidth: 0,
                    "&:hover": { color: "text.primary", bgcolor: "rgba(28, 35, 33, 0.04)" },
                  }}
                >
                  退出
                </Button>
              </Stack>
            ) : (
              <Button
                color="inherit"
                startIcon={<LogIn size={17} />}
                onPointerEnter={() => void loadAuthPage()}
                onClick={() => navigateWithViewTransition(navigate, "/login")}
                sx={{ fontWeight: 600 }}
              >
                登录
              </Button>
            )
          ) : null}
        </Toolbar>
      </AppBar>

      <Drawer
        variant="temporary"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: "block", md: "none" },
          "& .MuiDrawer-paper": {
            width: DRAWER_WIDTH,
            boxSizing: "border-box",
            backgroundColor: "#FAFBFA",
            borderRightColor: "rgba(28, 35, 33, 0.10)",
          },
        }}
      >
        {mobileDrawer}
      </Drawer>

      <Box
        component="main"
        sx={{
          pt: 9,
          minWidth: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Box className="zppz-page" sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          {homeLayout ? (
            <Box sx={{ flex: 1, minWidth: 0 }}>{routes}</Box>
          ) : (
            <Box
              sx={{
                flex: 1,
                minWidth: 0,
                display: "flex",
                flexDirection: "column",
                px: { xs: 2, sm: 3 },
                py: { xs: 2, md: 3 },
                width: "100%",
                maxWidth: theme.breakpoints.values.xl,
                mx: "auto",
                boxSizing: "border-box",
              }}
            >
              {routes}
            </Box>
          )}
        </Box>
        {location.pathname !== "/" || homepageReady ? <SiteFooter /> : null}
      </Box>
      {event && announcementMounted && (showAnnouncement || announcementOpen) ? (
        <Suspense fallback={null}>
          <AnnouncementDialog
            key={`${event.id}:${announcementSignature(announcement)}`}
            eventId={event.id}
            markdown={announcement}
            open={announcementOpen}
            onClose={() => setAnnouncementOpen(false)}
          />
        </Suspense>
      ) : null}
    </Box>
  );
}

function SiteFooter() {
  return (
    <Box component="footer" sx={{ borderTop: 1, borderColor: "divider", bgcolor: "background.paper", py: 2 }}>
      <Container maxWidth="xl">
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={{ xs: 0.75, sm: 2 }}
          useFlexGap
          sx={{ alignItems: "center", justifyContent: "center", flexWrap: "wrap", textAlign: "center" }}
        >
          <Typography
            component="a"
            href="https://beian.miit.gov.cn/"
            target="_blank"
            rel="noopener noreferrer"
            variant="caption"
            color="text.secondary"
            sx={{ "&:hover": { color: "text.primary" } }}
          >
            京ICP备2026012070号-1
          </Typography>
          <Stack
            component="a"
            href="https://beian.mps.gov.cn/#/query/webSearch?code=11010802047846"
            target="_blank"
            rel="noopener noreferrer"
            direction="row"
            spacing={0.5}
            sx={{ alignItems: "center", color: "text.secondary", "&:hover": { color: "text.primary" } }}
          >
            <Box component="img" src={beianIcon} alt="公安备案图标" sx={{ width: 18, height: 18, objectFit: "contain" }} />
            <Typography variant="caption" color="inherit">京公网安备11010802047846号</Typography>
          </Stack>
        </Stack>
      </Container>
    </Box>
  );
}

function RequireLogin({ children }: { children: ReactNode }) {
  const { isLoggedIn, loading } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    if (!loading && !isLoggedIn) navigateWithViewTransition(navigate, "/login", { replace: true });
  }, [isLoggedIn, loading, navigate]);
  if (loading) return <LoadingBlock />;
  if (!isLoggedIn) return <LoadingBlock />;
  return children;
}
function RequireManager({ children }: { children: ReactNode }) {
  const { isAdmin, isPoolEditor, loading } = useAuth();
  if (loading) return <LoadingBlock />;
  return isAdmin || isPoolEditor ? children : <Navigate to="/" replace />;
}

export default App;
