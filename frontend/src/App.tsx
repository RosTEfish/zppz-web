import { lazy, type ReactNode, Suspense, useEffect, useMemo, useState } from "react";
import { AppBar, Box, Button, Chip, Container, Divider, Drawer, IconButton, List, ListItemButton, ListItemIcon, ListItemText, Stack, Toolbar, Typography, useMediaQuery, useTheme } from "@mui/material";
import { CircleUserRound, Gauge, Home, LogIn, LogOut, Menu as MenuIcon, Music2, Sparkles, Upload, Vote } from "lucide-react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { LoadingBlock } from "./components/PagePrimitives";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ConfigProvider, useConfig } from "./contexts/ConfigContext";
import beianIcon from "./assets/beian.png";
import { announcementSignature, shouldShowAnnouncement } from "./components/announcementState";
import { preloadAdminTab } from "./pages/admin/adminTabLoaders";

const DRAWER_WIDTH = 248;

const loadHomePage = () => import("./pages/HomePage");
const loadAuthPage = () => import("./pages/AuthPage");
const loadSongPoolPage = () => import("./pages/SongPoolPage");
const loadDrawPage = () => import("./pages/DrawPage");
const loadSubmissionPage = () => import("./pages/SubmissionPage");
const loadGuessPage = () => import("./pages/GuessPage");
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
const AdminPage = lazy(loadAdminPage);
const AnnouncementDialog = lazy(loadAnnouncementDialog);

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ConfigProvider>
          <AppShell />
        </ConfigProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

function AppShell() {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("md"));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  const { user, isLoggedIn, isAdmin, isPoolEditor, logout } = useAuth();
  const { event, guessGameAvailable } = useConfig();
  const navigate = useNavigate();
  const showGuessEntry = isAdmin || isPoolEditor || guessGameAvailable;
  const managerPath = isAdmin ? "/admin/overview" : "/admin/songs";
  const announcement = event?.settings.announcement_text ?? "";
  const showAnnouncement = useMemo(
    () => event ? shouldShowAnnouncement(event.id, announcement) : false,
    [announcement, event?.id],
  );

  useEffect(() => setDrawerOpen(false), [location.pathname]);

  const links = [
    { label: "首页", to: "/", icon: Home, preload: loadHomePage },
    { label: "曲池", to: "/songs", icon: Music2, preload: loadSongPoolPage },
    { label: "抽签", to: "/draw", icon: Sparkles, preload: loadDrawPage },
    { label: "投稿", to: "/submissions", icon: Upload, preload: loadSubmissionPage },
    { label: "猜谱", to: "/guess", icon: Vote, preload: loadGuessPage },
  ].filter(({ to }) => to !== "/guess" || showGuessEntry);

  const drawer = (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Toolbar sx={{ gap: 1.5, minHeight: 64 }}>
        <Box sx={{ width: 34, height: 34, bgcolor: "primary.main", color: "primary.contrastText", display: "grid", placeItems: "center", borderRadius: 1, fontWeight: 800 }}>Z</Box>
        <Box sx={{ minWidth: 0 }}><Typography noWrap sx={{ fontWeight: 800 }}>ZPPZ Arena</Typography><Typography variant="caption" color="text.secondary" noWrap>{event?.name || "赛事平台"}</Typography></Box>
      </Toolbar>
      <Divider />
      <List sx={{ px: 1, py: 1.5 }}>
        {links.map(({ label, to, icon: Icon, preload }) => (
          <ListItemButton key={to} component={Link} to={to} selected={location.pathname === to} onPointerEnter={() => void preload()} onFocus={() => void preload()} sx={{ mb: 0.5, borderRadius: 1 }}>
            <ListItemIcon sx={{ minWidth: 38 }}><Icon size={19} /></ListItemIcon><ListItemText primary={label} />
          </ListItemButton>
        ))}
        {(isAdmin || isPoolEditor) ? <ListItemButton component={Link} to={managerPath} selected={location.pathname.startsWith("/admin")} onPointerEnter={() => void preloadAdminPage(managerPath)} onFocus={() => void preloadAdminPage(managerPath)} sx={{ mt: 1, borderRadius: 1 }}><ListItemIcon sx={{ minWidth: 38 }}><Gauge size={19} /></ListItemIcon><ListItemText primary="管理工作台" /></ListItemButton> : null}
      </List>
      <Box sx={{ flex: 1 }} />
      <Divider />
      <Box sx={{ p: 1.5 }}>
        {isLoggedIn ? <Stack spacing={1}><Stack direction="row" spacing={1.25} sx={{ px: 1, alignItems: "center" }}><CircleUserRound size={20} /><Box sx={{ minWidth: 0 }}><Typography variant="body2" noWrap sx={{ fontWeight: 700 }}>{user?.display_name || user?.user_code}</Typography><Typography variant="caption" color="text.secondary">{user?.identity === "participant" ? "参赛者" : "观众"}</Typography></Box></Stack><Button color="inherit" startIcon={<LogOut size={17} />} onClick={() => void logout().then(() => navigate("/"))}>退出登录</Button></Stack> : <Button fullWidth variant="contained" startIcon={<LogIn size={17} />} component={Link} to="/login" onPointerEnter={() => void loadAuthPage()} onFocus={() => void loadAuthPage()}>登录</Button>}
      </Box>
    </Box>
  );

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="fixed" color="inherit" elevation={0} sx={{ borderBottom: 1, borderColor: "divider", zIndex: theme.zIndex.drawer + 1 }}><Toolbar sx={{ gap: 1.5 }}>{mobile ? <IconButton aria-label="打开导航" onClick={() => setDrawerOpen(true)}><MenuIcon size={21} /></IconButton> : null}<Typography variant="h6" sx={{ flex: 1, fontWeight: 750 }}>{event?.name || "ZPPZ Arena"}</Typography>{event?.settings.submissions_open ? <Chip size="small" color="success" label="投稿开放" /> : <Chip size="small" variant="outlined" label="投稿未开放" />}</Toolbar></AppBar>
      <Drawer variant={mobile ? "temporary" : "permanent"} open={mobile ? drawerOpen : true} onClose={() => setDrawerOpen(false)} ModalProps={{ keepMounted: true }} sx={{ width: DRAWER_WIDTH, flexShrink: 0, "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box" } }}>{drawer}</Drawer>
      <Box component="main" sx={{ ml: mobile ? 0 : `${DRAWER_WIDTH}px`, pt: 8, minWidth: 0, minHeight: "100vh", display: "flex", flexDirection: "column" }}>
        <Container maxWidth="xl" sx={{ py: { xs: 2, md: 3 }, width: "100%", flex: 1 }}>
          <Suspense fallback={<LoadingBlock />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/login" element={<AuthPage />} />
              <Route path="/songs" element={<RequireLogin><SongPoolPage /></RequireLogin>} />
              <Route path="/draw" element={<RequireLogin><DrawPage /></RequireLogin>} />
              <Route path="/submissions" element={<RequireLogin><SubmissionPage /></RequireLogin>} />
              <Route path="/guess" element={<GuessPage />} />
              <Route path="/admin/:tab" element={<RequireManager><AdminPage /></RequireManager>} />
              <Route path="/admin" element={<Navigate to="/admin/overview" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </Container>
        <SiteFooter />
      </Box>
      {event && showAnnouncement ? <Suspense fallback={null}><AnnouncementDialog key={`${event.id}:${announcementSignature(announcement)}`} eventId={event.id} markdown={announcement} /></Suspense> : null}
    </Box>
  );
}

function SiteFooter() {
  return <Box component="footer" sx={{ borderTop: 1, borderColor: "divider", bgcolor: "background.paper", py: 2 }}><Container maxWidth="xl"><Stack direction={{ xs: "column", sm: "row" }} spacing={{ xs: 0.75, sm: 2 }} useFlexGap sx={{ alignItems: "center", justifyContent: "center", flexWrap: "wrap", textAlign: "center" }}><Typography component="a" href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer" variant="caption" color="text.secondary" sx={{ "&:hover": { color: "text.primary" } }}>京ICP备2026012070号-1</Typography><Stack component="a" href="https://beian.mps.gov.cn/#/query/webSearch?code=11010802047846" target="_blank" rel="noopener noreferrer" direction="row" spacing={0.5} sx={{ alignItems: "center", color: "text.secondary", "&:hover": { color: "text.primary" } }}><Box component="img" src={beianIcon} alt="公安备案图标" sx={{ width: 18, height: 18, objectFit: "contain" }} /><Typography variant="caption" color="inherit">京公网安备11010802047846号</Typography></Stack></Stack></Container></Box>;
}

function RequireLogin({ children }: { children: ReactNode }) { const { isLoggedIn, loading } = useAuth(); if (loading) return <LoadingBlock />; return isLoggedIn ? children : <Navigate to="/login" replace />; }
function RequireManager({ children }: { children: ReactNode }) { const { isAdmin, isPoolEditor, loading } = useAuth(); if (loading) return <LoadingBlock />; return isAdmin || isPoolEditor ? children : <Navigate to="/" replace />; }

export default App;
