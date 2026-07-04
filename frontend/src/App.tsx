import { type ChangeEvent, type DependencyList, type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  CardMedia,
  Checkbox,
  Chip,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
  Switch,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Toolbar,
  Tooltip,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import {
  Archive,
  BarChart3,
  BookOpenText,
  Check,
  ChevronRight,
  CircleUserRound,
  ClipboardList,
  Download,
  FileArchive,
  FileDown,
  FileUp,
  Gauge,
  Heart,
  Home,
  KeyRound,
  LogIn,
  LogOut,
  Menu as MenuIcon,
  MessageSquare,
  Music2,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Upload,
  Users,
  Vote,
  X,
} from "lucide-react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  api,
  type AuthorCandidateAdmin,
  type AuthorGuessState,
  type DrawAssignmentRead,
  type EventUpdatePayload,
  formatMB,
  formatTime,
  type GuessChartRead,
  type GuessCommentRead,
  type GuessStats,
  type SongPayload,
  type SongRead,
  type StoredFileRead,
  type SubmissionTargetRead,
  type Track,
  type UserRead,
} from "./api/v1";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ConfigProvider, useConfig } from "./contexts/ConfigContext";
import beianIcon from "./assets/beian.png";

const DRAWER_WIDTH = 248;
const EMPTY_SONG: SongPayload = { song_name: "", artist: "", song_type: "A", remark: "" };
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

type Resource<T> = {
  data: T | null;
  loading: boolean;
  error: string;
  reload: () => Promise<T | null>;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
};

function useResource<T>(loader: () => Promise<T>, dependencies: DependencyList): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await loader();
      setData(result);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
      return null;
    } finally {
      setLoading(false);
    }
  }, dependencies);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { data, loading, error, reload, setData };
}

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
  const { event } = useConfig();
  const navigate = useNavigate();

  useEffect(() => setDrawerOpen(false), [location.pathname]);

  const links = [
    { label: "首页", to: "/", icon: Home },
    { label: "曲池", to: "/songs", icon: Music2 },
    { label: "抽签", to: "/draw", icon: Sparkles },
    { label: "投稿", to: "/submissions", icon: Upload },
    { label: "猜谱", to: "/guess", icon: Vote },
  ];

  const drawer = (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Toolbar sx={{ gap: 1.5, minHeight: 64 }}>
        <Box sx={{ width: 34, height: 34, bgcolor: "primary.main", color: "primary.contrastText", display: "grid", placeItems: "center", borderRadius: 1, fontWeight: 800 }}>Z</Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography noWrap sx={{ fontWeight: 800 }}>ZPPZ Arena</Typography>
          <Typography variant="caption" color="text.secondary" noWrap>{event?.name || "赛事平台"}</Typography>
        </Box>
      </Toolbar>
      <Divider />
      <List sx={{ px: 1, py: 1.5 }}>
        {links.map(({ label, to, icon: Icon }) => (
          <ListItemButton key={to} component={Link} to={to} selected={location.pathname === to} sx={{ mb: 0.5, borderRadius: 1 }}>
            <ListItemIcon sx={{ minWidth: 38 }}><Icon size={19} /></ListItemIcon>
            <ListItemText primary={label} />
          </ListItemButton>
        ))}
        {(isAdmin || isPoolEditor) ? (
          <ListItemButton component={Link} to="/admin/overview" selected={location.pathname.startsWith("/admin")} sx={{ mt: 1, borderRadius: 1 }}>
            <ListItemIcon sx={{ minWidth: 38 }}><Gauge size={19} /></ListItemIcon>
            <ListItemText primary="管理工作台" />
          </ListItemButton>
        ) : null}
      </List>
      <Box sx={{ flex: 1 }} />
      <Divider />
      <Box sx={{ p: 1.5 }}>
        {isLoggedIn ? (
          <Stack spacing={1}>
            <Stack direction="row" spacing={1.25} sx={{ px: 1, alignItems: "center" }}>
              <CircleUserRound size={20} />
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2" noWrap sx={{ fontWeight: 700 }}>{user?.display_name || user?.user_code}</Typography>
                <Typography variant="caption" color="text.secondary">{user?.identity === "participant" ? "参赛者" : "观众"}</Typography>
              </Box>
            </Stack>
            <Button color="inherit" startIcon={<LogOut size={17} />} onClick={() => void logout().then(() => navigate("/"))}>退出登录</Button>
          </Stack>
        ) : (
          <Button fullWidth variant="contained" startIcon={<LogIn size={17} />} component={Link} to="/login">登录</Button>
        )}
      </Box>
    </Box>
  );

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="fixed" color="inherit" elevation={0} sx={{ borderBottom: 1, borderColor: "divider", zIndex: theme.zIndex.drawer + 1 }}>
        <Toolbar sx={{ gap: 1.5 }}>
          {mobile ? <IconButton aria-label="打开导航" onClick={() => setDrawerOpen(true)}><MenuIcon size={21} /></IconButton> : null}
          <Typography variant="h6" sx={{ flex: 1, fontWeight: 750 }}>{event?.name || "ZPPZ Arena"}</Typography>
          {event?.settings.submissions_open ? <Chip size="small" color="success" label="投稿开放" /> : <Chip size="small" variant="outlined" label="投稿未开放" />}
        </Toolbar>
      </AppBar>
      <Drawer variant={mobile ? "temporary" : "permanent"} open={mobile ? drawerOpen : true} onClose={() => setDrawerOpen(false)} ModalProps={{ keepMounted: true }} sx={{ width: DRAWER_WIDTH, flexShrink: 0, "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box" } }}>{drawer}</Drawer>
      <Box component="main" sx={{ ml: mobile ? 0 : `${DRAWER_WIDTH}px`, pt: 8, minWidth: 0, minHeight: "100vh", display: "flex", flexDirection: "column" }}>
        <Container maxWidth="xl" sx={{ py: { xs: 2, md: 3 }, width: "100%", flex: 1 }}>
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
        </Container>
        <SiteFooter />
      </Box>
    </Box>
  );
}

function SiteFooter() {
  return (
    <Box component="footer" sx={{ borderTop: 1, borderColor: "divider", bgcolor: "background.paper", py: 2 }}>
      <Container maxWidth="xl">
        <Stack direction={{ xs: "column", sm: "row" }} spacing={{ xs: 0.75, sm: 2 }} useFlexGap sx={{ alignItems: "center", justifyContent: "center", flexWrap: "wrap", textAlign: "center" }}>
          <Typography component="a" href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer" variant="caption" color="text.secondary" sx={{ "&:hover": { color: "text.primary" } }}>
            京ICP备2026012070号-1
          </Typography>
          <Stack component="a" href="https://beian.mps.gov.cn/#/query/webSearch?code=11010802047846" target="_blank" rel="noopener noreferrer" direction="row" spacing={0.5} sx={{ alignItems: "center", color: "text.secondary", "&:hover": { color: "text.primary" } }}>
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
  if (loading) return <LoadingBlock />;
  return isLoggedIn ? children : <Navigate to="/login" replace />;
}

function RequireManager({ children }: { children: ReactNode }) {
  const { isAdmin, isPoolEditor, loading } = useAuth();
  if (loading) return <LoadingBlock />;
  return isAdmin || isPoolEditor ? children : <Navigate to="/" replace />;
}

function LoadingBlock() {
  return <Box sx={{ py: 10, display: "grid", placeItems: "center" }}><CircularProgress size={30} /></Box>;
}

function PageHeader({ icon: Icon, title, meta, actions }: { icon: typeof Home; title: string; meta?: string; actions?: ReactNode }) {
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 3, alignItems: { xs: "stretch", sm: "center" }, justifyContent: "space-between" }}>
      <Stack direction="row" spacing={1.5} sx={{ minWidth: 0, alignItems: "center" }}>
        <Box sx={{ width: 42, height: 42, borderRadius: 1, bgcolor: "primary.light", color: "primary.dark", display: "grid", placeItems: "center", flexShrink: 0 }}><Icon size={22} /></Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h2">{title}</Typography>
          {meta ? <Typography variant="body2" color="text.secondary">{meta}</Typography> : null}
        </Box>
      </Stack>
      {actions ? <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>{actions}</Stack> : null}
    </Stack>
  );
}

function ResourceState({ loading, error, empty }: { loading: boolean; error: string; empty?: string }) {
  if (loading) return <LoadingBlock />;
  if (error) return <Alert severity="error">{error}</Alert>;
  if (empty) return <Paper variant="outlined" sx={{ py: 7, px: 2, textAlign: "center" }}><Typography color="text.secondary">{empty}</Typography></Paper>;
  return null;
}

function HomePage() {
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

function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ user_code: "", qq_id: "", password: "", identity: "participant" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { login, register, isLoggedIn } = useAuth();
  const navigate = useNavigate();
  if (isLoggedIn) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") await login(form.user_code, form.password);
      else await register(form.user_code, form.qq_id, form.password, form.identity);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box sx={{ minHeight: "calc(100vh - 130px)", display: "grid", placeItems: "center" }}>
      <Paper component="form" onSubmit={submit} sx={{ width: "100%", maxWidth: 430, p: { xs: 2.5, sm: 4 } }}>
        <Stack direction="row" spacing={1.5} sx={{ mb: 3, alignItems: "center" }}><KeyRound size={24} /><Typography variant="h2">赛事账号</Typography></Stack>
        <Tabs value={mode} onChange={(_, value) => setMode(value)} variant="fullWidth" sx={{ mb: 3 }}><Tab value="login" label="登录" /><Tab value="register" label="注册" /></Tabs>
        <Stack spacing={2}>
          <TextField label="账号" value={form.user_code} onChange={(e) => setForm({ ...form, user_code: e.target.value })} required autoComplete="username" />
          {mode === "register" ? <TextField label="QQ" value={form.qq_id} onChange={(e) => setForm({ ...form, qq_id: e.target.value })} required /> : null}
          <TextField label="密码" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required autoComplete={mode === "login" ? "current-password" : "new-password"} />
          {mode === "register" ? <FormControl><InputLabel>身份</InputLabel><Select label="身份" value={form.identity} onChange={(e) => setForm({ ...form, identity: e.target.value })}><MenuItem value="participant">参赛者</MenuItem><MenuItem value="audience">观众</MenuItem></Select></FormControl> : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          <Button type="submit" variant="contained" disabled={busy} startIcon={busy ? <CircularProgress size={16} /> : <LogIn size={17} />}>{mode === "login" ? "登录" : "注册并登录"}</Button>
        </Stack>
      </Paper>
    </Box>
  );
}

function SongPoolPage() {
  const songs = useResource(api.mySongs, []);
  const [form, setForm] = useState<SongPayload>(EMPTY_SONG);
  const [editing, setEditing] = useState<SongRead | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const { event } = useConfig();
  const { user } = useAuth();
  const limit = user?.identity === "participant" ? event?.settings.participant_song_limit : event?.settings.audience_song_limit;

  async function createSong(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api.createSong(form);
      setForm(EMPTY_SONG);
      setMessage("曲目已加入曲池");
      await songs.reload();
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); }
  }

  async function remove(song: SongRead) {
    if (!window.confirm(`确认删除《${song.song_name}》？`)) return;
    try { await api.deleteSong(song.id); await songs.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); }
  }

  return (
    <Stack spacing={3}>
      <PageHeader icon={Music2} title="我的曲池" meta={`${songs.data?.length ?? 0} / ${limit ?? "-"} 首`} />
      <Paper component="form" onSubmit={createSong} variant="outlined" sx={{ p: 2 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "2fr 1.4fr 120px 2fr auto" }, gap: 1.5, alignItems: "center" }}>
          <TextField size="small" label="曲名" value={form.song_name} onChange={(e) => setForm({ ...form, song_name: e.target.value })} required />
          <TextField size="small" label="曲师" value={form.artist} onChange={(e) => setForm({ ...form, artist: e.target.value })} required />
          <FormControl size="small"><InputLabel>分类</InputLabel><Select label="分类" value={form.song_type} onChange={(e) => setForm({ ...form, song_type: e.target.value })}><MenuItem value="A">A</MenuItem><MenuItem value="B">B</MenuItem><MenuItem value="C">C</MenuItem></Select></FormControl>
          <TextField size="small" label="备注" value={form.remark} onChange={(e) => setForm({ ...form, remark: e.target.value })} />
          <Button type="submit" variant="contained" startIcon={<Plus size={17} />}>添加</Button>
        </Box>
      </Paper>
      {error ? <Alert severity="error">{error}</Alert> : null}
      <ResourceState loading={songs.loading} error={songs.error} empty={!songs.data?.length ? "暂无曲目" : undefined} />
      {songs.data?.length ? <SongTable songs={songs.data} onEdit={setEditing} onDelete={remove} /> : null}
      <SongDialog song={editing} onClose={() => setEditing(null)} onSave={async (payload) => { if (!editing) return; await api.updateMySong(editing.id, payload); setEditing(null); await songs.reload(); }} />
      <Snackbar open={Boolean(message)} autoHideDuration={2500} onClose={() => setMessage("")} message={message} />
    </Stack>
  );
}

function SongTable({ songs, onEdit, onDelete, showSubmitter = false }: { songs: SongRead[]; onEdit: (song: SongRead) => void; onDelete: (song: SongRead) => void; showSubmitter?: boolean }) {
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small"><TableHead><TableRow><TableCell>曲目</TableCell><TableCell>曲师</TableCell><TableCell>分类</TableCell>{showSubmitter ? <TableCell>投稿人</TableCell> : null}<TableCell>备注</TableCell><TableCell align="right">操作</TableCell></TableRow></TableHead>
        <TableBody>{songs.map((song) => <TableRow key={song.id} hover><TableCell><Typography sx={{ fontWeight: 650 }}>{song.song_name}</Typography><Typography variant="caption" color="text.secondary">#{song.id}</Typography></TableCell><TableCell>{song.artist}</TableCell><TableCell><Chip size="small" label={song.song_type} /></TableCell>{showSubmitter ? <TableCell>{song.submitter?.display_name || song.submitter?.user_code || "-"}</TableCell> : null}<TableCell sx={{ maxWidth: 280, overflowWrap: "anywhere" }}>{song.remark || "-"}</TableCell><TableCell align="right"><Tooltip title="编辑"><IconButton size="small" onClick={() => onEdit(song)}><Pencil size={16} /></IconButton></Tooltip><Tooltip title="删除"><IconButton size="small" color="error" onClick={() => onDelete(song)}><Trash2 size={16} /></IconButton></Tooltip></TableCell></TableRow>)}</TableBody>
      </Table>
    </TableContainer>
  );
}

function SongDialog({ song, onClose, onSave }: { song: SongRead | null; onClose: () => void; onSave: (payload: SongPayload) => Promise<void> }) {
  const [form, setForm] = useState<SongPayload>(EMPTY_SONG);
  const [error, setError] = useState("");
  useEffect(() => { if (song) setForm({ song_name: song.song_name, artist: song.artist, song_type: song.song_type, remark: song.remark }); }, [song]);
  return <Dialog open={Boolean(song)} onClose={onClose} fullWidth maxWidth="sm"><DialogTitle>编辑曲目</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><TextField label="曲名" value={form.song_name} onChange={(e) => setForm({ ...form, song_name: e.target.value })} /><TextField label="曲师" value={form.artist} onChange={(e) => setForm({ ...form, artist: e.target.value })} /><FormControl><InputLabel>分类</InputLabel><Select label="分类" value={form.song_type} onChange={(e) => setForm({ ...form, song_type: e.target.value })}><MenuItem value="A">A</MenuItem><MenuItem value="B">B</MenuItem><MenuItem value="C">C</MenuItem></Select></FormControl><TextField label="备注" multiline minRows={2} value={form.remark} onChange={(e) => setForm({ ...form, remark: e.target.value })} />{error ? <Alert severity="error">{error}</Alert> : null}</Stack></DialogContent><DialogActions><Button onClick={onClose}>取消</Button><Button variant="contained" startIcon={<Save size={16} />} onClick={() => void onSave(form).catch((err) => setError(err instanceof Error ? err.message : "保存失败"))}>保存</Button></DialogActions></Dialog>;
}

function DrawPage() {
  const draws = useResource(api.myDraw, []);
  const { user } = useAuth();
  const { event } = useConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run() {
    setBusy(true); setError("");
    try { draws.setData(await api.drawMine()); } catch (err) { setError(err instanceof Error ? err.message : "抽签失败"); } finally { setBusy(false); }
  }
  return <Stack spacing={3}><PageHeader icon={Sparkles} title="我的抽签" meta={user?.identity === "participant" ? `应抽 ${event?.settings.draw_songs_per_participant ?? "-"} 首` : "当前账号不参与抽签"} actions={user?.identity === "participant" ? <Button variant="contained" startIcon={<Sparkles size={17} />} disabled={busy || event?.settings.submissions_open} onClick={() => void run()}>{draws.data?.length ? "重新抽签" : "开始抽签"}</Button> : undefined} />{event?.settings.submissions_open ? <Alert severity="info">投稿已开放，抽签结果已锁定。</Alert> : null}{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={draws.loading} error={draws.error} empty={!draws.data?.length ? "暂无抽签结果" : undefined} />{draws.data?.length ? <DrawList rows={draws.data} showAssignee={false} /> : null}</Stack>;
}

function DrawList({ rows, showAssignee = true }: { rows: DrawAssignmentRead[]; showAssignee?: boolean }) {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down("sm"));
  if (mobile) return <Stack spacing={1.25}>{rows.map((row) => <Paper key={row.id} variant="outlined" sx={{ p: 2 }}><Stack direction="row" sx={{ justifyContent: "space-between", gap: 1 }}><Box><Typography sx={{ fontWeight: 750 }}>{row.song.song_name}</Typography><Typography variant="body2" color="text.secondary">{row.song.artist}</Typography></Box><Chip size="small" label={row.song.song_type} /></Stack><Divider sx={{ my: 1.25 }} /><Stack spacing={0.5}><Typography variant="body2">投稿人：{row.song.submitter?.display_name || row.song.submitter?.user_code || "-"}</Typography>{showAssignee ? <Typography variant="body2">被抽取人：{row.assigned_to.display_name || row.assigned_to.user_code}</Typography> : null}<Typography variant="caption" color="text.secondary">{formatTime(row.created_at)}</Typography></Stack></Paper>)}</Stack>;
  return <TableContainer component={Paper} variant="outlined"><Table size="small"><TableHead><TableRow><TableCell>曲目</TableCell><TableCell>曲师</TableCell><TableCell>分类</TableCell><TableCell>投稿人</TableCell>{showAssignee ? <TableCell>被抽取人</TableCell> : null}<TableCell>时间</TableCell></TableRow></TableHead><TableBody>{rows.map((row) => <TableRow key={row.id}><TableCell sx={{ fontWeight: 650 }}>{row.song.song_name}</TableCell><TableCell>{row.song.artist}</TableCell><TableCell><Chip size="small" label={row.song.song_type} /></TableCell><TableCell>{row.song.submitter?.display_name || row.song.submitter?.user_code || "-"}</TableCell>{showAssignee ? <TableCell>{row.assigned_to.display_name || row.assigned_to.user_code}</TableCell> : null}<TableCell>{formatTime(row.created_at)}</TableCell></TableRow>)}</TableBody></Table></TableContainer>;
}

function SubmissionPage() {
  const targets = useResource(api.submissionTargets, []);
  const [trackChoices, setTrackChoices] = useState<Record<number, Track>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const { user } = useAuth();
  if (user?.identity !== "participant") return <Stack spacing={3}><PageHeader icon={Upload} title="投稿" /><Alert severity="info">仅参赛者账号开放谱面投稿。</Alert></Stack>;

  function choice(target: SubmissionTargetRead): Track { return trackChoices[target.song.id] || target.submission?.track || "normal"; }
  async function upload(target: SubmissionTargetRead, file?: File) {
    if (!file) return;
    setBusyId(target.song.id); setError("");
    try {
      if (target.submission) await api.replaceSubmission(target.submission.id, choice(target), file);
      else await api.uploadSubmission(target.song.id, choice(target), file);
      setMessage(target.submission ? "投稿已替换" : "投稿已上传");
      await targets.reload();
    } catch (err) { setError(err instanceof Error ? err.message : "上传失败"); } finally { setBusyId(null); }
  }
  async function remove(target: SubmissionTargetRead) {
    if (!target.submission || !window.confirm(`确认删除《${target.song.song_name}》的投稿？`)) return;
    setBusyId(target.song.id);
    try { await api.deleteSubmission(target.submission.id); await targets.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } finally { setBusyId(null); }
  }

  return (
    <Stack spacing={3}>
      <PageHeader icon={Upload} title="候选投稿" meta={`${targets.data?.targets.filter((item) => item.submission).length ?? 0} / ${targets.data?.targets.length ?? 0} 已完成`} />
      {targets.data && !targets.data.is_open ? <Alert severity="warning">抽签阶段尚未结束，投稿入口暂未开放。</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      <ResourceState loading={targets.loading} error={targets.error} empty={targets.data && !targets.data.targets.length ? "没有可投稿的候选曲目" : undefined} />
      {targets.data?.targets.length ? (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
          {targets.data.targets.map((target) => {
            const submitted = target.submission;
            const selectedTrack = choice(target);
            return (
              <Card variant="outlined" key={target.song.id}>
                <CardContent>
                  <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
                    <Box sx={{ minWidth: 0 }}>
                      <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: "center", flexWrap: "wrap" }}>
                        <Typography variant="h3" sx={{ overflowWrap: "anywhere" }}>{target.song.song_name}</Typography>
                        <Chip size="small" color={target.source_kind === "self" ? "primary" : "secondary"} label={target.source_kind === "self" ? "自选" : "抽中"} />
                      </Stack>
                      <Typography color="text.secondary" sx={{ mt: 0.5 }}>{target.song.artist}</Typography>
                    </Box>
                    {submitted ? <Chip size="small" color="success" icon={<Check size={14} />} label="已投稿" /> : <Chip size="small" variant="outlined" label="待投稿" />}
                  </Stack>
                  {submitted ? <Paper variant="outlined" sx={{ p: 1.5, mt: 2, bgcolor: "background.default" }}><Typography variant="body2" noWrap title={submitted.file_name} sx={{ fontWeight: 650 }}>{submitted.file_name}</Typography><Typography variant="caption" color="text.secondary">{formatMB(submitted.file_size)} · {formatTime(submitted.created_at)}</Typography></Paper> : null}
                  <Stack direction={{ xs: "column", sm: "row" }} sx={{ mt: 2, alignItems: { xs: "stretch", sm: "center" }, justifyContent: "space-between", gap: 1.5 }}>
                    <FormControlLabel control={<Switch checked={selectedTrack === "j"} onChange={(e) => setTrackChoices((current) => ({ ...current, [target.song.id]: e.target.checked ? "j" : "normal" }))} disabled={!targets.data?.is_open || busyId === target.song.id} />} label="J 赛道" />
                    <Stack direction="row" spacing={1}>
                      <Button component="label" variant={submitted ? "outlined" : "contained"} startIcon={submitted ? <RefreshCw size={16} /> : <Upload size={16} />} disabled={!targets.data?.is_open || busyId === target.song.id}>{submitted ? "替换" : "上传"}<input hidden type="file" accept=".zip,.7z,.rar" onChange={(event) => { void upload(target, event.target.files?.[0]); event.currentTarget.value = ""; }} /></Button>
                      {submitted ? <Tooltip title="删除"><IconButton color="error" disabled={!targets.data?.is_open || busyId === target.song.id} onClick={() => void remove(target)}><Trash2 size={18} /></IconButton></Tooltip> : null}
                    </Stack>
                  </Stack>
                </CardContent>
              </Card>
            );
          })}
        </Box>
      ) : null}
      <Snackbar open={Boolean(message)} autoHideDuration={2500} onClose={() => setMessage("")} message={message} />
    </Stack>
  );
}

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

function GuessFilterPanel({
  levels,
  level,
  lane,
  selfSelected,
  onLevelChange,
  onLaneChange,
  onSelfChange,
  onReset,
}: {
  levels: string[];
  level: string;
  lane: GuessLaneFilter;
  selfSelected: GuessSelfFilter;
  onLevelChange: (value: string) => void;
  onLaneChange: (value: GuessLaneFilter) => void;
  onSelfChange: (value: GuessSelfFilter) => void;
  onReset: () => void;
}) {
  const hasFilter = level !== "all" || lane !== "all" || selfSelected !== "all";
  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <SlidersHorizontal size={18} />
          <Typography variant="h3">分类查看</Typography>
        </Stack>
        <Button size="small" color="inherit" disabled={!hasFilter} onClick={onReset}>清除筛选</Button>
      </Stack>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(170px, .65fr) minmax(300px, 1fr) minmax(300px, 1fr)" }, gap: 1.5 }}>
        <FormControl size="small" fullWidth>
          <InputLabel id="guess-level-filter-label">难度</InputLabel>
          <Select labelId="guess-level-filter-label" label="难度" value={level} onChange={(event) => onLevelChange(event.target.value)} inputProps={{ "aria-label": "按难度筛选" }}>
            <MenuItem value="all">全部难度</MenuItem>
            {levels.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
          </Select>
        </FormControl>
        <ToggleButtonGroup size="small" exclusive fullWidth value={lane} aria-label="按谱面类型筛选" onChange={(_, value: GuessLaneFilter | null) => { if (value) onLaneChange(value); }}>
          <ToggleButton value="all">全部类型</ToggleButton>
          <ToggleButton value="normal">普通谱</ToggleButton>
          <ToggleButton value="j">J 谱</ToggleButton>
        </ToggleButtonGroup>
        <ToggleButtonGroup size="small" exclusive fullWidth value={selfSelected} aria-label="按自选状态筛选" onChange={(_, value: GuessSelfFilter | null) => { if (value) onSelfChange(value); }}>
          <ToggleButton value="all">全部来源</ToggleButton>
          <ToggleButton value="self">自选</ToggleButton>
          <ToggleButton value="other">非自选</ToggleButton>
        </ToggleButtonGroup>
      </Box>
    </Paper>
  );
}

function GuessChartCard({ chart, selecting, selected, onOpen }: { chart: GuessChartRead; selecting: boolean; selected: boolean; onOpen: (chart: GuessChartRead) => void }) {
  const isJ = chart.lane === "j";
  const levelSlot = getChartLevelSlot(chart.source_level_slot);
  const levelSurface = GUESS_LEVEL_SURFACES[levelSlot] ?? "background.paper";
  return (
    <Card
      variant="outlined"
      data-lane={isJ ? "j" : "normal"}
      data-level-slot={levelSlot ? `lv_${levelSlot}` : undefined}
      sx={{
        position: "relative",
        height: "100%",
        borderWidth: isJ ? 2 : 1,
        borderColor: selected ? "primary.main" : isJ ? "secondary.main" : "divider",
        outline: selected ? "2px solid" : "none",
        outlineColor: "primary.main",
      }}
    >
      <CardActionArea onClick={() => onOpen(chart)} sx={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "stretch" }}>
        {chart.cover_path ? <CardMedia component="img" height="164" image={chart.cover_path} alt="" sx={{ objectFit: "cover", bgcolor: "#E4EAE6" }} /> : <Box sx={{ height: 164, flexShrink: 0, display: "grid", placeItems: "center", bgcolor: "#E4EAE6", color: "text.secondary" }}><Music2 size={38} /></Box>}
        <CardContent
          sx={{
            width: "100%",
            flex: 1,
            display: "flex",
            flexDirection: "column",
            bgcolor: levelSurface,
            color: "#17211D",
            transition: "background-color 160ms ease",
            "& .MuiTypography-colorTextSecondary": { color: "#45534D" },
          }}
        >
          <Typography variant="h3" noWrap title={chart.title}>{chart.title}</Typography>
          <Stack direction="row" spacing={0.75} useFlexGap sx={{ mt: 1, flexWrap: "wrap" }}>
            <Chip size="small" label={chart.level} />
            <Chip size="small" color={isJ ? "secondary" : "default"} variant={isJ ? "filled" : "outlined"} label={isJ ? "J 谱" : "普通谱"} />
            <Chip size="small" color={chart.is_self_selected ? "warning" : "default"} variant={chart.is_self_selected ? "filled" : "outlined"} label={chart.is_self_selected ? "自选" : "非自选"} />
          </Stack>
          <Stack spacing={0.25} sx={{ mt: 1.25, minHeight: 42 }}>
            <Typography variant="body2" color="text.secondary" noWrap title={chart.author}><Box component="span" sx={{ fontWeight: 700 }}>曲师</Box>　{chart.author}</Typography>
            {chart.designer ? <Typography variant="body2" color="text.secondary" noWrap title={chart.designer}><Box component="span" sx={{ fontWeight: 700 }}>谱师</Box>　{chart.designer}</Typography> : null}
          </Stack>
          <Stack direction="row" spacing={2} sx={{ mt: "auto", pt: 1.5 }}><Typography variant="caption"><Heart size={13} /> {chart.love_votes}</Typography><Typography variant="caption"><Sparkles size={13} /> {chart.funny_votes}</Typography><Typography variant="caption">查看 {chart.plays}</Typography></Stack>
        </CardContent>
      </CardActionArea>
      {selecting ? <Checkbox checked={selected} slotProps={{ input: { "aria-label": `选择 ${chart.title}` } }} sx={{ position: "absolute", top: 6, right: 6, bgcolor: "rgba(255,255,255,.9)", "&:hover": { bgcolor: "white" } }} onChange={() => onOpen(chart)} /> : null}
    </Card>
  );
}

function GuessPage() {
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
  const filteredCharts = useMemo(
    () => allCharts.filter((chart) => (
      (levelFilter === "all" || chart.level === levelFilter)
      && (laneFilter === "all" || chart.lane === laneFilter)
      && (selfFilter === "all" || (selfFilter === "self" ? chart.is_self_selected : !chart.is_self_selected))
    )),
    [allCharts, laneFilter, levelFilter, selfFilter],
  );

  function clearSelection() {
    setSelected(new Set());
  }

  function resetFilters() {
    setLevelFilter("all");
    setLaneFilter("all");
    setSelfFilter("all");
    clearSelection();
  }

  async function open(chart: GuessChartRead) {
    if (selecting) { setSelected((current) => { const next = new Set(current); if (next.has(chart.id)) next.delete(chart.id); else next.add(chart.id); return next; }); return; }
    try { setActive(await api.guessChart(chart.id)); } catch (err) { setError(err instanceof Error ? err.message : "加载失败"); }
  }
  return (
    <Stack spacing={3}>
      <PageHeader icon={Vote} title="猜谱" meta={`显示 ${filteredCharts.length} / 共 ${allCharts.length} 张谱面`} actions={<><Button variant={selecting ? "contained" : "outlined"} startIcon={<ClipboardList size={17} />} onClick={() => { setSelecting(!selecting); if (selecting) clearSelection(); }}>{selecting ? "结束选择" : "批量选择"}</Button>{selecting ? <Button variant="contained" startIcon={<Download size={17} />} disabled={!selected.size} onClick={() => void api.downloadCharts([...selected]).catch((err) => setError(err instanceof Error ? err.message : "下载失败"))}>下载 {selected.size} 项</Button> : null}</>} />
      {error ? <Alert severity="error">{error}</Alert> : null}
      <ResourceState loading={charts.loading} error={charts.error} empty={!allCharts.length ? "暂无谱面" : undefined} />
      {allCharts.length ? <GuessFilterPanel levels={levels} level={levelFilter} lane={laneFilter} selfSelected={selfFilter} onLevelChange={(value) => { setLevelFilter(value); clearSelection(); }} onLaneChange={(value) => { setLaneFilter(value); clearSelection(); }} onSelfChange={(value) => { setSelfFilter(value); clearSelection(); }} onReset={resetFilters} /> : null}
      {filteredCharts.length ? (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(3, 1fr)", xl: "repeat(4, 1fr)" }, gap: 2 }}>
          {filteredCharts.map((chart) => <GuessChartCard key={chart.id} chart={chart} selecting={selecting} selected={selected.has(chart.id)} onOpen={(item) => void open(item)} />)}
        </Box>
      ) : allCharts.length ? <Paper variant="outlined" sx={{ py: 7, px: 2, textAlign: "center" }}><Typography color="text.secondary">没有符合当前筛选条件的谱面</Typography><Button variant="outlined" sx={{ mt: 2 }} onClick={resetFilters}>清除筛选</Button></Paper> : null}
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
      <DialogTitle sx={{ pr: 6 }}>
        <Typography variant="h2">{chart.title}</Typography>
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ my: 1, flexWrap: "wrap" }}>
          <Chip size="small" label={chart.level} />
          <Chip size="small" color={chart.lane === "j" ? "secondary" : "default"} variant={chart.lane === "j" ? "filled" : "outlined"} label={chart.lane === "j" ? "J 谱" : "普通谱"} />
          <Chip size="small" color={chart.is_self_selected ? "warning" : "default"} variant={chart.is_self_selected ? "filled" : "outlined"} label={chart.is_self_selected ? "自选" : "非自选"} />
        </Stack>
        <Typography variant="body2" color="text.secondary">曲师：{chart.author}</Typography>
        {chart.designer ? <Typography variant="body2" color="text.secondary">谱师：{chart.designer}</Typography> : null}
        <Typography variant="caption" color="text.secondary">查看 {chart.plays} 次</Typography>
        <IconButton aria-label="关闭谱面详情" onClick={onClose} sx={{ position: "absolute", right: 12, top: 12 }}><X size={20} /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1fr) 280px" }, gap: 3 }}>
          {chart.cover_path ? <Box component="img" src={chart.cover_path} alt="" sx={{ width: "100%", maxHeight: 420, objectFit: "cover", borderRadius: 1 }} /> : <Box sx={{ minHeight: 260, display: "grid", placeItems: "center", bgcolor: "background.default" }}><Music2 size={42} /></Box>}
          <Stack spacing={2}>
            <Button variant="contained" startIcon={<Download size={17} />} onClick={() => void api.downloadChart(chart.id).catch((err) => setError(err instanceof Error ? err.message : "下载失败"))}>下载投稿</Button>
            <Stack direction="row" spacing={1}>
              <Button fullWidth variant={chart.my_votes.includes("love") ? "contained" : "outlined"} color="error" startIcon={<Heart size={16} />} disabled={!isLoggedIn} onClick={() => void toggleVote("love").catch((err) => setError(err.message))}>{chart.love_votes}</Button>
              <Button fullWidth variant={chart.my_votes.includes("funny") ? "contained" : "outlined"} color="secondary" startIcon={<Sparkles size={16} />} disabled={!isLoggedIn} onClick={() => void toggleVote("funny").catch((err) => setError(err.message))}>{chart.funny_votes}</Button>
            </Stack>
            {authorState?.can_guess && authorState.candidates.length ? <FormControl size="small"><InputLabel>作者猜测</InputLabel><Select label="作者猜测" value={authorState.my_guess_user_id || ""} onChange={(e) => void api.saveAuthorGuess(chart.id, Number(e.target.value)).then(async () => { setAuthorState(await api.authorGuess(chart.id)); })}><MenuItem value=""><em>未选择</em></MenuItem>{authorState.candidates.map((item) => <MenuItem key={item.user_id} value={item.user_id}>{item.display_id}</MenuItem>)}</Select></FormControl> : null}
            {error ? <Alert severity="error">{error}</Alert> : null}
          </Stack>
        </Box>
        <Divider sx={{ my: 3 }} />
        <Typography variant="h3" sx={{ mb: 1.5 }}>评论</Typography>
        {isLoggedIn ? <Stack direction="row" spacing={1} sx={{ mb: 2 }}><TextField size="small" fullWidth placeholder="写下你的评价" value={comment} onChange={(e) => setComment(e.target.value)} /><IconButton color="primary" aria-label="发送评论" onClick={() => void sendComment().catch((err) => setError(err.message))}><MessageSquare size={19} /></IconButton></Stack> : null}
        <Stack spacing={1}>{comments.map((item) => <Paper key={item.id} variant="outlined" sx={{ p: 1.5 }}><Typography variant="body2">{item.content}</Typography><Typography variant="caption" color="text.secondary">{item.user.display_name || item.user.user_code} · {formatTime(item.created_at)}</Typography></Paper>)}</Stack>
      </DialogContent>
    </Dialog>
  );
}

const ADMIN_TABS = [
  ["overview", "总览", Gauge], ["settings", "设置", Settings], ["users", "用户", Users], ["songs", "曲池", Music2],
  ["draw", "抽签", Sparkles], ["submissions", "投稿", Archive], ["guess", "猜谱", Vote], ["stats", "统计", BarChart3],
] as const;

function AdminPage() {
  const { tab = "overview" } = useParams();
  const { isAdmin } = useAuth();
  const navigate = useNavigate();
  const visible = ADMIN_TABS.filter(([key]) => isAdmin || !["settings", "users"].includes(key));
  const active = visible.some(([key]) => key === tab) ? tab : visible[0][0];
  return <Stack spacing={2.5}><PageHeader icon={Gauge} title="管理工作台" /><Paper variant="outlined"><Tabs value={active} onChange={(_, value) => navigate(`/admin/${value}`)} variant="scrollable" scrollButtons="auto">{visible.map(([key, label, Icon]) => <Tab key={key} value={key} icon={<Icon size={17} />} iconPosition="start" label={label} />)}</Tabs></Paper>{active === "overview" ? <AdminOverview /> : null}{active === "settings" ? <AdminSettings /> : null}{active === "users" ? <AdminUsers /> : null}{active === "songs" ? <AdminSongs /> : null}{active === "draw" ? <AdminDraw /> : null}{active === "submissions" ? <AdminSubmissions /> : null}{active === "guess" ? <AdminGuess /> : null}{active === "stats" ? <AdminStats /> : null}</Stack>;
}

function AdminOverview() {
  const stats = useResource(api.siteStats, []);
  const labels: Record<string, string> = { users: "用户", songs: "曲目", assignments: "抽签结果", submissions: "投稿", guess_charts: "谱面", charts: "谱面" };
  return <><ResourceState loading={stats.loading} error={stats.error} />{stats.data ? <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, 1fr)", lg: "repeat(4, 1fr)" }, gap: 2 }}>{Object.entries(stats.data).map(([key, value]) => <Paper key={key} variant="outlined" sx={{ p: 2.5 }}><Typography variant="body2" color="text.secondary">{labels[key] || key}</Typography><Typography variant="h1" sx={{ mt: 1 }}>{value}</Typography></Paper>)}</Box> : null}</>;
}

function AdminSettings() {
  const { event, refreshConfig } = useConfig();
  const [form, setForm] = useState<EventUpdatePayload | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { if (event) setForm({ ...event.settings, name: event.name }); }, [event]);
  if (!form) return <LoadingBlock />;
  const numberField = (key: keyof EventUpdatePayload, label: string) => <TextField type="number" label={label} value={String(form[key] ?? "")} onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })} />;
  async function save() { try { await api.updateEvent(form); await refreshConfig(); setMessage("赛事设置已保存"); } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); } }
  return <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 } }}><Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}><TextField label="赛事名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />{numberField("participant_song_limit", "参赛者曲目上限")}{numberField("audience_song_limit", "观众曲目上限")}{numberField("draw_songs_per_participant", "每人抽取曲目数")}{numberField("true_love_vote_limit", "真爱票上限")}{numberField("funny_vote_limit", "欢乐票上限")}<TextField type="datetime-local" label="投稿截止" slotProps={{ inputLabel: { shrink: true } }} value={toDateTimeInput(form.submission_deadline)} onChange={(e) => setForm({ ...form, submission_deadline: e.target.value || null })} /><TextField type="datetime-local" label="猜谱开放" slotProps={{ inputLabel: { shrink: true } }} value={toDateTimeInput(form.guess_game_open_at)} onChange={(e) => setForm({ ...form, guess_game_open_at: e.target.value || null })} /><TextField label="公告" multiline minRows={3} value={form.announcement_text} onChange={(e) => setForm({ ...form, announcement_text: e.target.value })} sx={{ gridColumn: { md: "1 / -1" } }} /><Paper variant="outlined" sx={{ p: 1.5, gridColumn: { md: "1 / -1" } }}><FormControlLabel control={<Switch checked={form.submissions_open} onChange={(e) => setForm({ ...form, submissions_open: e.target.checked })} />} label="开放投稿" /></Paper></Box>{error ? <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert> : null}<Button variant="contained" startIcon={<Save size={17} />} onClick={() => void save()} sx={{ mt: 2 }}>保存设置</Button><Snackbar open={Boolean(message)} autoHideDuration={2500} onClose={() => setMessage("")} message={message} /></Paper>;
}

function updateRole(roles: string[], role: string, enabled: boolean): string[] {
  if (enabled) return roles.includes(role) ? roles : [...roles, role];
  return roles.filter((item) => item !== role);
}

function AdminUsers() {
  const users = useResource(api.users, []);
  const [error, setError] = useState("");
  async function change(user: UserRead, patch: Partial<{ identity: string; roles: string[]; display_name: string; is_active: boolean }>) {
    try { await api.updateUser(user.id, { identity: patch.identity ?? user.identity, roles: patch.roles ?? user.roles, display_name: patch.display_name ?? user.display_name, is_active: patch.is_active ?? user.is_active ?? true }); await users.reload(); } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); }
  }
  return <>
    {error ? <Alert severity="error">{error}</Alert> : null}
    <ResourceState loading={users.loading} error={users.error} />
    {users.data ? <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead><TableRow><TableCell>账号</TableCell><TableCell>显示名</TableCell><TableCell>身份</TableCell><TableCell>权限</TableCell><TableCell>启用</TableCell></TableRow></TableHead>
        <TableBody>{users.data.map((user) => <TableRow key={user.id}>
          <TableCell>{user.user_code}</TableCell>
          <TableCell><TextField size="small" defaultValue={user.display_name} onBlur={(e) => { if (e.target.value !== user.display_name) void change(user, { display_name: e.target.value }); }} /></TableCell>
          <TableCell><Select size="small" value={user.identity} onChange={(e) => void change(user, { identity: e.target.value })}><MenuItem value="participant">参赛者</MenuItem><MenuItem value="audience">观众</MenuItem></Select></TableCell>
          <TableCell>
            <Stack spacing={0} sx={{ minWidth: 132 }}>
              <FormControlLabel sx={{ m: 0 }} control={<Checkbox checked={user.roles.includes("admin")} onChange={(e) => void change(user, { roles: updateRole(user.roles, "admin", e.target.checked) })} />} label="管理员" />
              <FormControlLabel sx={{ m: 0 }} control={<Checkbox checked={user.roles.includes("pool_editor")} onChange={(e) => void change(user, { roles: updateRole(user.roles, "pool_editor", e.target.checked) })} />} label="曲池编辑" />
            </Stack>
          </TableCell>
          <TableCell><Tooltip title={user.roles.includes("admin") ? "停用最后一名管理员会被系统阻止" : ""}><span><Switch checked={user.is_active ?? true} onChange={(e) => void change(user, { is_active: e.target.checked })} /></span></Tooltip></TableCell>
        </TableRow>)}</TableBody>
      </Table>
    </TableContainer> : null}
  </>;
}

function AdminSongs() {
  const songs = useResource(api.adminSongs, []);
  const [editing, setEditing] = useState<SongRead | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function importCsv(file?: File) { if (!file) return; try { const result = await api.importSongs(file); setMessage(result.message); await songs.reload(); } catch (err) { setError(err instanceof Error ? err.message : "导入失败"); } }
  async function remove(song: SongRead) { if (!window.confirm(`确认删除《${song.song_name}》？`)) return; try { await api.deleteAdminSong(song.id); await songs.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } }
  return <Stack spacing={2}><Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}><Button variant="outlined" startIcon={<FileDown size={17} />} onClick={() => void api.exportSongs().catch((err) => setError(err.message))}>导出 CSV</Button><Button component="label" variant="contained" startIcon={<FileUp size={17} />}>导入 CSV<input hidden type="file" accept=".csv,text/csv" onChange={(e) => { void importCsv(e.target.files?.[0]); e.currentTarget.value = ""; }} /></Button></Stack>{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={songs.loading} error={songs.error} empty={!songs.data?.length ? "曲池为空" : undefined} />{songs.data?.length ? <SongTable songs={songs.data} showSubmitter onEdit={setEditing} onDelete={remove} /> : null}<SongDialog song={editing} onClose={() => setEditing(null)} onSave={async (payload) => { if (!editing) return; await api.updateSong(editing.id, payload); setEditing(null); await songs.reload(); }} /><Snackbar open={Boolean(message)} autoHideDuration={3000} onClose={() => setMessage("")} message={message} /></Stack>;
}

function AdminDraw() {
  const rows = useResource(api.adminDrawResults, []);
  const [error, setError] = useState("");
  async function run() { if (!window.confirm("确认清空并重建全部抽签结果？")) return; try { rows.setData(await api.runDraw()); } catch (err) { setError(err instanceof Error ? err.message : "抽签失败"); } }
  return <Stack spacing={2}><Button variant="contained" startIcon={<RefreshCw size={17} />} onClick={() => void run()} sx={{ alignSelf: "flex-start" }}>全局重新抽签</Button>{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={rows.loading} error={rows.error} empty={!rows.data?.length ? "暂无抽签结果" : undefined} />{rows.data?.length ? <DrawList rows={rows.data} /> : null}</Stack>;
}

function AdminSubmissions() {
  const [filter, setFilter] = useState<Track | "all">("all");
  const files = useResource(() => api.adminSubmissions(filter), [filter]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [error, setError] = useState("");
  async function remove(file: StoredFileRead) { if (!window.confirm(`确认删除 ${file.file_name}？`)) return; try { await api.deleteAdminSubmission(file.id); setSelected((current) => { const next = new Set(current); next.delete(file.id); return next; }); await files.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } }
  return <Stack spacing={2}><Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}><Tabs value={filter} onChange={(_, value) => { setFilter(value); setSelected(new Set()); }}><Tab value="all" label="全部" /><Tab value="normal" label="普通" /><Tab value="j" label="J 赛道" /></Tabs><Stack direction="row" spacing={1}><Button variant="outlined" startIcon={<Check size={16} />} onClick={() => setSelected(new Set(files.data?.map((item) => item.id) || []))}>全选</Button><Button variant="contained" startIcon={<Download size={16} />} disabled={!selected.size} onClick={() => void api.downloadAdminSubmissions([...selected], filter).catch((err) => setError(err.message))}>下载 {selected.size} 份</Button></Stack></Stack>{error ? <Alert severity="error">{error}</Alert> : null}<ResourceState loading={files.loading} error={files.error} empty={!files.data?.length ? "暂无投稿" : undefined} />{files.data?.length ? <TableContainer component={Paper} variant="outlined"><Table size="small"><TableHead><TableRow><TableCell padding="checkbox"><Checkbox checked={selected.size === files.data.length} indeterminate={selected.size > 0 && selected.size < files.data.length} onChange={(e) => setSelected(e.target.checked ? new Set(files.data?.map((item) => item.id)) : new Set())} /></TableCell><TableCell>曲目 / 文件</TableCell><TableCell>投稿人</TableCell><TableCell>来源</TableCell><TableCell>赛道</TableCell><TableCell>时间</TableCell><TableCell align="right">操作</TableCell></TableRow></TableHead><TableBody>{files.data.map((file) => <TableRow key={file.id}><TableCell padding="checkbox"><Checkbox checked={selected.has(file.id)} onChange={() => setSelected((current) => { const next = new Set(current); if (next.has(file.id)) next.delete(file.id); else next.add(file.id); return next; })} /></TableCell><TableCell><Typography sx={{ fontWeight: 650 }}>{file.source_song?.song_name || "未关联曲目"}</Typography><Typography variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>{file.file_name} · {formatMB(file.file_size)}</Typography></TableCell><TableCell>{file.user?.display_name || file.user?.user_code || "-"}</TableCell><TableCell>{file.source_kind === "self" ? "自选" : "抽中"}</TableCell><TableCell><Chip size="small" color={file.track === "j" ? "secondary" : "default"} label={file.track === "j" ? "J" : "普通"} /></TableCell><TableCell>{formatTime(file.created_at)}</TableCell><TableCell align="right"><Tooltip title="下载"><IconButton size="small" onClick={() => void api.downloadAdminSubmission(file.id).catch((err) => setError(err.message))}><Download size={16} /></IconButton></Tooltip><Tooltip title="替换"><IconButton component="label" size="small"><RefreshCw size={16} /><input hidden type="file" accept=".zip,.7z,.rar" onChange={(e) => { const next = e.target.files?.[0]; if (next) void api.replaceAdminSubmission(file.id, next).then(() => files.reload()).catch((err) => setError(err.message)); e.currentTarget.value = ""; }} /></IconButton></Tooltip><Tooltip title="删除"><IconButton size="small" color="error" onClick={() => void remove(file)}><Trash2 size={16} /></IconButton></Tooltip></TableCell></TableRow>)}</TableBody></Table></TableContainer> : null}</Stack>;
}

function AdminGuess() {
  const charts = useResource(api.adminCharts, []);
  const issues = useResource(api.importIssues, []);
  const candidates = useResource(api.authorCandidates, []);
  const [editing, setEditing] = useState<GuessChartRead | null>(null);
  const [summary, setSummary] = useState("");
  const [error, setError] = useState("");
  async function importArchive(file?: File) { if (!file) return; try { const result = await api.importCharts(file); setSummary(`已新增 ${result.charts.length} 张谱面`); await Promise.all([charts.reload(), issues.reload()]); } catch (err) { setError(err instanceof Error ? err.message : "导入失败"); } }
  async function parseAll() { try { const result = await api.parseSubmissions(); setSummary(`扫描 ${result.scanned}，新增 ${result.created}，更新 ${result.updated}，删除 ${result.deleted}，问题 ${result.issues}`); await Promise.all([charts.reload(), issues.reload()]); } catch (err) { setError(err instanceof Error ? err.message : "解析失败"); } }
  async function remove(chart: GuessChartRead) { if (!window.confirm(`确认删除《${chart.title}》${chart.level}？`)) return; try { await api.deleteChart(chart.id); await charts.reload(); } catch (err) { setError(err instanceof Error ? err.message : "删除失败"); } }
  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
        <Button component="label" variant="contained" startIcon={<FileArchive size={17} />}>新增谱面<input hidden type="file" accept=".zip,.7z,.rar" onChange={(e) => { void importArchive(e.target.files?.[0]); e.currentTarget.value = ""; }} /></Button>
        <Button variant="outlined" startIcon={<RefreshCw size={17} />} onClick={() => void parseAll()}>重新解析全部来源</Button>
      </Stack>
      {summary ? <Alert severity="success">{summary}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      <ResourceState loading={charts.loading} error={charts.error} empty={!charts.data?.length ? "暂无谱面" : undefined} />
      {charts.data?.length ? <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead><TableRow><TableCell>谱面</TableCell><TableCell>曲师</TableCell><TableCell>谱师</TableCell><TableCell>等级</TableCell><TableCell>赛道</TableCell><TableCell>来源</TableCell><TableCell align="right">操作</TableCell></TableRow></TableHead>
          <TableBody>{charts.data.map((chart) => <TableRow key={chart.id}>
            <TableCell sx={{ fontWeight: 650 }}>{chart.title}</TableCell>
            <TableCell>{chart.author}</TableCell>
            <TableCell>{chart.designer || "-"}</TableCell>
            <TableCell>{chart.level}</TableCell>
            <TableCell>{chart.lane === "j" ? "J" : "普通"}</TableCell>
            <TableCell>{chart.source_submission_type}</TableCell>
            <TableCell align="right"><Tooltip title="编辑"><IconButton size="small" onClick={() => setEditing(chart)}><Pencil size={16} /></IconButton></Tooltip><Tooltip title="删除"><IconButton size="small" color="error" onClick={() => void remove(chart)}><Trash2 size={16} /></IconButton></Tooltip></TableCell>
          </TableRow>)}</TableBody>
        </Table>
      </TableContainer> : null}
      <AuthorCandidatesEditor resource={candidates} setError={setError} />
      {issues.data?.length ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h3" sx={{ mb: 1.5 }}>解析问题</Typography><Stack spacing={1}>{issues.data.map((issue) => <Alert key={issue.id} severity="warning"><strong>{issue.file_name || issue.source_type}</strong>：{issue.message}</Alert>)}</Stack></Paper> : null}
      <ChartEditDialog chart={editing} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await charts.reload(); }} />
    </Stack>
  );
}

function AuthorCandidatesEditor({ resource, setError }: { resource: Resource<AuthorCandidateAdmin[]>; setError: (value: string) => void }) {
  const [rows, setRows] = useState<AuthorCandidateAdmin[]>([]);
  useEffect(() => { if (resource.data) setRows(resource.data); }, [resource.data]);
  async function save() { try { await api.saveAuthorCandidates(rows.filter((row) => row.selected).map((row) => ({ user_id: row.user.id, display_id: row.display_id }))); await resource.reload(); } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); } }
  return <Paper variant="outlined" sx={{ p: 2 }}><Stack direction="row" sx={{ mb: 1.5, justifyContent: "space-between", alignItems: "center" }}><Typography variant="h3">作者候选</Typography><Button variant="outlined" size="small" startIcon={<Save size={15} />} onClick={() => void save()}>保存候选</Button></Stack><Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 1 }}>{rows.map((row, index) => <Paper key={row.user.id} variant="outlined" sx={{ p: 1.25 }}><Stack direction="row" spacing={1} sx={{ alignItems: "center" }}><Checkbox checked={row.selected} onChange={(e) => setRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, selected: e.target.checked } : item))} /><Box sx={{ flex: 1, minWidth: 0 }}><Typography variant="body2" sx={{ fontWeight: 650 }}>{row.user.user_code}</Typography><Typography variant="caption" color="text.secondary">{row.song_count} 首曲目</Typography></Box><TextField size="small" label="展示 ID" value={row.display_id} onChange={(e) => setRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, display_id: e.target.value } : item))} sx={{ width: 150 }} /></Stack></Paper>)}</Box></Paper>;
}

function ChartEditDialog({ chart, onClose, onSaved }: { chart: GuessChartRead | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const [form, setForm] = useState({ title: "", author: "", designer: "", level: "", lane: "normal", guess_group_key: "", is_self_selected: false });
  const [error, setError] = useState("");
  useEffect(() => { if (chart) setForm({ title: chart.title, author: chart.author, designer: chart.designer, level: chart.level, lane: chart.lane, guess_group_key: chart.guess_group_key, is_self_selected: chart.is_self_selected }); }, [chart]);
  if (!chart) return null;
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>编辑谱面</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField label="标题" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <TextField label="曲师" value={form.author} onChange={(e) => setForm({ ...form, author: e.target.value })} />
          <TextField label="谱师" value={form.designer} onChange={(e) => setForm({ ...form, designer: e.target.value })} />
          <TextField label="等级" value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })} />
          <FormControl><InputLabel>赛道</InputLabel><Select label="赛道" value={form.lane} onChange={(e) => setForm({ ...form, lane: e.target.value })}><MenuItem value="normal">普通</MenuItem><MenuItem value="j">J</MenuItem></Select></FormControl>
          <TextField label="猜测分组" value={form.guess_group_key} onChange={(e) => setForm({ ...form, guess_group_key: e.target.value })} />
          <FormControlLabel control={<Switch checked={form.is_self_selected} onChange={(e) => setForm({ ...form, is_self_selected: e.target.checked })} />} label="自选谱面" />
          {error ? <Alert severity="error">{error}</Alert> : null}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>取消</Button><Button variant="contained" startIcon={<Save size={16} />} onClick={() => void api.updateChart(chart.id, form).then(onSaved).catch((err) => setError(err.message))}>保存</Button></DialogActions>
    </Dialog>
  );
}

function AdminStats() {
  const [scope, setScope] = useState<"all" | "j">("all");
  const stats = useResource(() => api.guessStats(scope), [scope]);
  return <Stack spacing={2}><Tabs value={scope} onChange={(_, value) => setScope(value)}><Tab value="all" label="全部" /><Tab value="j" label="J 赛道" /></Tabs><ResourceState loading={stats.loading} error={stats.error} />{stats.data ? <StatsContent stats={stats.data} /> : null}</Stack>;
}

function StatsContent({ stats }: { stats: GuessStats }) {
  const overview = [
    ["谱面", stats.overview.charts], ["查看", stats.overview.views], ["真爱票", stats.overview.love_votes], ["欢乐票", stats.overview.funny_votes],
    ["有效猜测", stats.overview.counted_guesses], ["猜对", stats.overview.correct_guesses], ["准确率", stats.overview.accuracy === null ? "-" : `${stats.overview.accuracy}%`], ["参与用户", stats.overview.users_guessing],
  ];
  return <Stack spacing={3}><Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, 1fr)", md: "repeat(4, 1fr)" }, gap: 1.5 }}>{overview.map(([label, value]) => <Paper key={String(label)} variant="outlined" sx={{ p: 2 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="h2" sx={{ mt: 0.5 }}>{value}</Typography></Paper>)}</Box><StatsTable title="逐谱统计" rows={stats.chart_stats} columns={["title", "level", "lane", "views", "love_votes", "funny_votes", "guess_count", "accuracy"]} /><StatsTable title="用户准确率" rows={stats.user_stats} columns={["user", "guesses", "counted", "correct", "accuracy"]} /><StatsTable title="候选选择" rows={stats.candidate_stats} columns={["display_id", "user", "selected_count"]} /><StatsTable title="猜测明细" rows={stats.guess_details} columns={["title", "guesser", "guessed_display_id", "actual_author", "is_correct"]} /></Stack>;
}

function StatsTable({ title, rows, columns }: { title: string; rows: Array<Record<string, unknown>>; columns: string[] }) {
  const labels: Record<string, string> = { title: "曲目", level: "等级", lane: "赛道", views: "查看", love_votes: "真爱票", funny_votes: "欢乐票", guess_count: "猜测", accuracy: "准确率", user: "用户", guesses: "提交", counted: "有效", correct: "正确", display_id: "展示 ID", selected_count: "被选次数", guesser: "猜测人", guessed_display_id: "选择", actual_author: "实际作者", is_correct: "结果" };
  return <Paper variant="outlined" sx={{ overflow: "hidden" }}><Typography variant="h3" sx={{ p: 2 }}>{title}</Typography><TableContainer sx={{ maxHeight: 420 }}><Table size="small" stickyHeader><TableHead><TableRow>{columns.map((column) => <TableCell key={column}>{labels[column] || column}</TableCell>)}</TableRow></TableHead><TableBody>{rows.length ? rows.map((row, index) => <TableRow key={index}>{columns.map((column) => <TableCell key={column}>{formatStatValue(column, row[column])}</TableCell>)}</TableRow>) : <TableRow><TableCell colSpan={columns.length} align="center">暂无数据</TableCell></TableRow>}</TableBody></Table></TableContainer></Paper>;
}

function formatStatValue(key: string, value: unknown): ReactNode {
  if (value === null || value === undefined) return "-";
  if (key === "accuracy" && typeof value === "number") return `${value}%`;
  if (key === "is_correct") return value ? <Chip size="small" color="success" label="正确" /> : <Chip size="small" variant="outlined" label="错误" />;
  if (typeof value === "object") {
    const user = value as { user_code?: string; display_name?: string };
    return user.display_name || user.user_code || "-";
  }
  return String(value);
}

function toDateTimeInput(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export default App;
