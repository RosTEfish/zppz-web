# Layouts — App shell

**File:** `frontend/src/App.tsx`  
**Description:** Root providers + `AppShell` (fixed AppBar, permanent/temporary Drawer 248px, main content, `SiteFooter`). Auth route `/login` uses `authLayout` to drop content padding and hide footer so AuthPage can go full-bleed under the AppBar.

---

## Provider tree

```tsx
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
```

`EventThemeProvider` nests a second MUI `ThemeProvider` with `createAppTheme(palette)` from event art.

---

## AppShell — constants & nav links

```tsx
const DRAWER_WIDTH = 248;

// inside AppShell:
const authLayout = location.pathname === "/login";
const showGuessEntry = isAdmin || isPoolEditor || guessGameAvailable;
const managerPath = isAdmin ? "/admin/overview" : "/admin/songs";

const links = [
  { label: "首页", to: "/", icon: Home, preload: loadHomePage },
  { label: "曲池", to: "/songs", icon: Music2, preload: loadSongPoolPage },
  { label: "曲目分配", to: "/draw", icon: Sparkles, preload: loadDrawPage },
  { label: "投稿", to: "/submissions", icon: Upload, preload: loadSubmissionPage },
  { label: "猜谱", to: "/guess", icon: Vote, preload: loadGuessPage },
  { label: "往届乐曲", to: "/archive", icon: Archive, preload: loadArchivePage },
].filter(({ to }) => to !== "/guess" || showGuessEntry);
```

---

## Drawer (sidebar)

Brand mark "Z" + ZPPZ Arena / event name; nav list with selected left border + `palette.wash`; bottom account card or login CTA.

```tsx
const drawer = (
  <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
    <Toolbar sx={{ gap: 1.5, minHeight: 64 }}>
      <Box
        aria-hidden="true"
        sx={{
          width: 36, height: 36, borderRadius: 2, display: "grid", placeItems: "center",
          fontWeight: 800, fontSize: 19, color: "#fff",
          background: `linear-gradient(135deg, ${palette.main} 0%, ${palette.dark} 100%)`,
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.28), 0 2px 6px -2px rgba(13,53,41,0.35)",
        }}
      >
        Z
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography noWrap sx={{ fontWeight: 800, letterSpacing: "-0.01em" }}>ZPPZ Arena</Typography>
        <Typography variant="caption" color="text.secondary" noWrap>{event?.name || "赛事平台"}</Typography>
      </Box>
    </Toolbar>
    <Divider />
    <List sx={{ px: 1, py: 1.5 }}>
      {links.map(({ label, to, icon: Icon, preload }) => (
        <ListItemButton
          key={to}
          component={Link}
          to={to}
          selected={location.pathname === to}
          onPointerEnter={() => void preload()}
          onFocus={() => void preload()}
          sx={{
            mb: 0.5, borderRadius: 1, borderLeft: "3px solid transparent",
            "&.Mui-selected": { borderLeftColor: "primary.main", bgcolor: palette.wash, color: "primary.dark" },
          }}
        >
          <ListItemIcon sx={{ minWidth: 38 }}><Icon size={19} /></ListItemIcon>
          <ListItemText primary={label} />
        </ListItemButton>
      ))}
      {(isAdmin || isPoolEditor) ? (
        <ListItemButton
          component={Link}
          to={managerPath}
          selected={location.pathname.startsWith("/admin")}
          sx={{
            mt: 1, borderRadius: 1, borderLeft: "3px solid transparent",
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
          {/* avatar initial + display_name → /account; 退出登录 button */}
          <Button size="small" color="inherit" startIcon={<LogOut size={15} />} onClick={() => void logout().then(() => navigate("/"))}>
            退出登录
          </Button>
        </Stack>
      ) : (
        <Button fullWidth variant="contained" startIcon={<LogIn size={17} />} component={Link} to="/login">
          登录
        </Button>
      )}
    </Box>
  </Box>
);
```

---

## Shell render — AppBar + Drawer + main + authLayout branch

```tsx
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
        backgroundColor: "rgba(247,247,244,0.82)",
        backdropFilter: "blur(12px) saturate(1.4)",
        WebkitBackdropFilter: "blur(12px) saturate(1.4)",
      }}
    >
      <Toolbar sx={{ gap: 1.5 }}>
        {mobile ? (
          <IconButton aria-label="打开导航" onClick={() => setDrawerOpen(true)}>
            <MenuIcon size={21} />
          </IconButton>
        ) : null}
        <Typography variant="h6" sx={{ flex: 1, fontWeight: 750 }}>
          {event?.name || "ZPPZ Arena"}
        </Typography>
        {phases?.capabilities.submission ? (
          <Chip size="small" color="success" label="投稿开放" />
        ) : (
          <Chip size="small" variant="outlined" label="投稿未开放" />
        )}
      </Toolbar>
    </AppBar>

    <Drawer
      variant={mobile ? "temporary" : "permanent"}
      open={mobile ? drawerOpen : true}
      onClose={() => setDrawerOpen(false)}
      ModalProps={{ keepMounted: true }}
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        "& .MuiDrawer-paper": {
          width: DRAWER_WIDTH,
          boxSizing: "border-box",
          backgroundColor: "#FBFBF9",
          borderRightColor: "rgba(23, 33, 28, 0.10)",
        },
      }}
    >
      {drawer}
    </Drawer>

    <Box
      component="main"
      sx={{
        ml: mobile ? 0 : `${DRAWER_WIDTH}px`,
        pt: 8,
        minWidth: 0,
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          ...(authLayout
            ? {}
            : {
                px: { xs: 2, sm: 3 },
                py: { xs: 2, md: 3 },
                width: "100%",
                maxWidth: theme.breakpoints.values.xl,
                mx: "auto",
                boxSizing: "border-box",
              }),
        }}
      >
        <Suspense fallback={location.pathname === "/" ? <HomePageSkeleton /> : <LoadingBlock />}>
          <Routes>{/* see routes.md */}</Routes>
        </Suspense>
      </Box>
      {!authLayout && (location.pathname !== "/" || homepageReady) ? <SiteFooter /> : null}
    </Box>
  </Box>
);
```

**authLayout behavior:** when `pathname === "/login"`, main content has no horizontal/vertical page padding and `SiteFooter` is omitted — AuthPage fills the viewport under the 64px AppBar with immersive stage art.

---

## SiteFooter

```tsx
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
          <Typography component="a" href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer" variant="caption" color="text.secondary">
            京ICP备2026012070号-1
          </Typography>
          <Stack component="a" href="https://beian.mps.gov.cn/#/query/webSearch?code=11010802047846" target="_blank" rel="noopener noreferrer" direction="row" spacing={0.5} sx={{ alignItems: "center", color: "text.secondary" }}>
            <Box component="img" src={beianIcon} alt="公安备案图标" sx={{ width: 18, height: 18, objectFit: "contain" }} />
            <Typography variant="caption" color="inherit">京公网安备11010802047846号</Typography>
          </Stack>
        </Stack>
      </Container>
    </Box>
  );
}
```

---

## Route guards (layout helpers)

```tsx
function RequireLogin({ children }: { children: ReactNode }) {
  const { isLoggedIn, loading } = useAuth();
  if (loading) return <LoadingBlock />;
  return isLoggedIn ? children : <Navigate to="/login" replace />;
}

function RequireManager({ children }: { children: ReactNode }) {
  const { isAdmin, isPoolEditor, loading } = useAuth();
  if (loading) return <LoadingBlock />;
  return isAdmin || isPoolEditor ? children : <Navigate to="/" replace />;
}
```
