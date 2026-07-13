import { lazy, Suspense, useEffect } from "react";
import { Gauge, Music2, Settings, Users, Sparkles, CalendarClock, Archive, Vote, BarChart3 } from "lucide-react";
import { Paper, Stack, Tab, Tabs } from "@mui/material";
import { useNavigate, useParams } from "react-router-dom";
import { LoadingBlock, PageHeader } from "../components/PagePrimitives";
import { useAuth } from "../contexts/AuthContext";
import { adminTabLoaders } from "./admin/adminTabLoaders";

const ADMIN_TABS = [
  ["overview", "总览", Gauge], ["settings", "设置", Settings], ["users", "用户", Users], ["songs", "曲池", Music2],
  ["draw", "抽签", Sparkles], ["phases", "阶段与换曲", CalendarClock], ["submissions", "投稿", Archive], ["guess", "猜谱", Vote], ["stats", "统计", BarChart3],
] as const;

const AdminOverview = lazy(adminTabLoaders.overview);
const AdminSettings = lazy(adminTabLoaders.settings);
const AdminUsers = lazy(adminTabLoaders.users);
const AdminSongs = lazy(adminTabLoaders.songs);
const AdminDraw = lazy(adminTabLoaders.draw);
const AdminPhasesAndSwap = lazy(adminTabLoaders.phases);
const AdminSubmissions = lazy(adminTabLoaders.submissions);
const AdminGuess = lazy(adminTabLoaders.guess);
const AdminStats = lazy(adminTabLoaders.stats);

const CONTENT: Record<string, React.LazyExoticComponent<() => React.JSX.Element>> = {
  overview: AdminOverview,
  settings: AdminSettings,
  users: AdminUsers,
  songs: AdminSongs,
  draw: AdminDraw,
  phases: AdminPhasesAndSwap,
  submissions: AdminSubmissions,
  guess: AdminGuess,
  stats: AdminStats,
};

export default function AdminPage() {
  const { tab = "overview" } = useParams();
  const { isAdmin, isPoolEditor } = useAuth();
  const navigate = useNavigate();
  const visible = isAdmin ? ADMIN_TABS : ADMIN_TABS.filter(([key]) => isPoolEditor && key === "songs");
  const active = visible.some(([key]) => key === tab) ? tab : visible[0]?.[0] || "songs";
  const ActiveContent = CONTENT[active];
  useEffect(() => {
    if (!isAdmin && isPoolEditor && tab !== "songs") navigate("/admin/songs", { replace: true });
  }, [isAdmin, isPoolEditor, navigate, tab]);
  return <Stack spacing={2.5}><PageHeader icon={Gauge} title="管理工作台" /><Paper variant="outlined"><Tabs value={active} onChange={(_, value) => navigate(`/admin/${value}`)} variant="scrollable" scrollButtons="auto" sx={{ "& .MuiTabs-flexContainer": { width: { md: "100%" } }, "& .MuiTab-root": { minWidth: { xs: 112, md: 0 }, flex: { md: "1 1 0" } } }}>{visible.map(([key, label, Icon]) => <Tab key={key} value={key} icon={<Icon size={17} />} iconPosition="start" label={label} />)}</Tabs></Paper><Suspense fallback={<LoadingBlock />}><ActiveContent /></Suspense></Stack>;
}
