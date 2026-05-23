import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { HashRouter, Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import {
  AudioLines,
  BadgeCheck,
  BarChart3,
  ClipboardList,
  Dice5,
  FileArchive,
  FileText,
  Gauge,
  Heart,
  LogIn,
  LogOut,
  MessageCircle,
  Music2,
  PanelLeft,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  Users,
} from "lucide-react";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ConfigProvider, useConfig } from "./contexts/ConfigContext";
import { api, DrawAssignmentRead, formatMB, formatTime, GuessChartRead, GuessCommentRead, SongRead, StoredFileRead, UserRead } from "./api/v1";

type LoadState = "idle" | "loading" | "ready" | "error";

function useAsync<T>(loader: () => Promise<T>, deps: React.DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setState("loading");
    loader()
      .then((next) => {
        if (!alive) return;
        setData(next);
        setState("ready");
      })
      .catch((err) => {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "加载失败");
        setState("error");
      });
    return () => {
      alive = false;
    };
  }, deps);

  return { data, state, error, reload: () => loader().then(setData) };
}

function StatCard({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: React.ReactNode }) {
  return (
    <div className="metric-card">
      <Icon size={18} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Notice({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "error" | "success" }) {
  return <div className={`notice notice-${tone}`}>{children}</div>;
}

function Shell() {
  const { user, isLoggedIn, isAdmin, isPoolEditor, logout } = useAuth();
  const { event } = useConfig();
  const nav = [
    ["首页", "/", Gauge],
    ["规则", "/assets", FileText],
    ["曲池", "/songs", Music2],
    ["抽签", "/draw", Dice5],
    ["投稿", "/submissions", UploadCloud],
    ["猜谱", "/guess", Sparkles],
  ] as const;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link to="/" className="brand">
          <span className="brand-mark">谱</span>
          <span>
            <strong>这谱谱这</strong>
            <small>{event?.name || "赛事平台"}</small>
          </span>
        </Link>
        <nav>
          {nav.map(([label, to, Icon]) => (
            <Link key={to} to={to} className="nav-link">
              <Icon size={18} />
              {label}
            </Link>
          ))}
          {(isAdmin || isPoolEditor) && (
            <Link to="/admin" className="nav-link nav-admin">
              <PanelLeft size={18} />
              管理工作台
            </Link>
          )}
        </nav>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <div>
            <p className="eyebrow">ZPPZ ARENA V2</p>
            <h1>{event?.name || "赛事中枢"}</h1>
          </div>
          <div className="top-actions">
            {isLoggedIn && user ? (
              <>
                <span className="user-pill">
                  <BadgeCheck size={16} />
                  {user.display_name || user.user_code}
                </span>
                <button className="icon-button" onClick={() => void logout()} title="退出登录">
                  <LogOut size={18} />
                </button>
              </>
            ) : (
              <Link className="primary-action" to="/auth">
                <LogIn size={17} />
                登录 / 注册
              </Link>
            )}
          </div>
        </header>
        <main className="content">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/auth" element={<AuthPage />} />
            <Route path="/assets" element={<AssetsPage />} />
            <Route path="/songs" element={<Protected><SongPoolPage /></Protected>} />
            <Route path="/draw" element={<Protected><DrawPage /></Protected>} />
            <Route path="/submissions" element={<Protected><SubmissionPage /></Protected>} />
            <Route path="/guess" element={<GuessGamePage />} />
            <Route path="/admin" element={<AdminOnly><AdminWorkbench /></AdminOnly>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function Protected({ children }: { children: React.ReactNode }) {
  const { isLoggedIn, loading } = useAuth();
  if (loading) return <Notice>正在确认登录状态...</Notice>;
  if (!isLoggedIn) return <Navigate to="/auth" replace />;
  return <>{children}</>;
}

function AdminOnly({ children }: { children: React.ReactNode }) {
  const { isAdmin, isPoolEditor, loading } = useAuth();
  if (loading) return <Notice>正在确认权限...</Notice>;
  if (!isAdmin && !isPoolEditor) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function HomePage() {
  const { event, config } = useConfig();
  const { user } = useAuth();
  return (
    <section className="page-stack">
      <div className="hero-panel">
        <div>
          <p className="eyebrow">赛事进行中</p>
          <div className="hero-actions">
            <Link to={user ? "/songs" : "/auth"} className="primary-action">开始处理任务</Link>
            <Link to="/guess" className="secondary-action">进入猜谱会场</Link>
          </div>
        </div>
        <div className="hero-radar">
          <span>曲池</span>
          <span>抽签</span>
          <span>投稿</span>
          <span>猜谱</span>
        </div>
      </div>
      {config?.announcement_text && <Notice>{config.announcement_text}</Notice>}
      <div className="metric-grid">
        <StatCard icon={Users} label="参赛者曲目上限" value={event?.settings.participant_song_limit ?? "-"} />
        <StatCard icon={AudioLines} label="观众曲目上限" value={event?.settings.audience_song_limit ?? "-"} />
        <StatCard icon={Heart} label="真爱票额度" value={event?.settings.true_love_vote_limit ?? "-"} />
        <StatCard icon={Sparkles} label="乐子票额度" value={event?.settings.funny_vote_limit ?? "-"} />
      </div>
      <div className="section-grid">
        <WorkflowCard icon={Music2} title="提交曲池" text="按身份限制提交候选曲目，后台可以导入导出和修正。" to="/songs" />
        <WorkflowCard icon={Dice5} title="查看抽签" text="抽签后参赛者只看到自己的任务，后台保留全量结果。" to="/draw" />
        <WorkflowCard icon={UploadCloud} title="上传投稿" text="音频、压缩包和 J 位投稿统一走持久化文件存储。" to="/submissions" />
        <WorkflowCard icon={Sparkles} title="猜谱互动" text="支持真爱票、乐子票、评论和作者猜测。" to="/guess" />
      </div>
    </section>
  );
}

function WorkflowCard({ icon: Icon, title, text, to }: { icon: React.ElementType; title: string; text: string; to: string }) {
  return (
    <Link to={to} className="workflow-card">
      <Icon size={22} />
      <strong>{title}</strong>
      <span>{text}</span>
    </Link>
  );
}

function AuthPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ user_code: "", qq_id: "", password: "", identity: "audience" });
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      if (mode === "login") await login(form.user_code, form.password);
      else await register(form.user_code, form.qq_id, form.password, form.identity);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    }
  }

  return (
    <section className="auth-layout">
      <div className="auth-copy">
        <p className="eyebrow">账号入口</p>
      </div>
      <form className="form-panel" onSubmit={submit}>
        <div className="segmented">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>登录</button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>注册</button>
        </div>
        <label>参赛 ID<input value={form.user_code} onChange={(e) => setForm({ ...form, user_code: e.target.value })} required /></label>
        {mode === "register" && <label>QQ 号<input value={form.qq_id} onChange={(e) => setForm({ ...form, qq_id: e.target.value })} required /></label>}
        <label>密码<input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={6} /></label>
        {mode === "register" && (
          <label>身份
            <select value={form.identity} onChange={(e) => setForm({ ...form, identity: e.target.value })}>
              <option value="audience">观众</option>
              <option value="participant">参赛者</option>
            </select>
          </label>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <button className="primary-action" type="submit">{mode === "login" ? "登录" : "创建账号"}</button>
      </form>
    </section>
  );
}

function AssetsPage() {
  return (
    <section className="page-stack">
      <header className="section-heading">
        <FileText size={22} />
        <div>
          <p className="eyebrow">赛事文件</p>
          <h2>规则与 banlist</h2>
        </div>
      </header>
      <div className="section-grid two">
        <a className="workflow-card" href="/api/v1/assets/rule/download" target="_blank" rel="noreferrer">
          <FileText size={24} />
          <strong>规则 PDF</strong>
          <span>打开当前赛事规则文件。</span>
        </a>
        <a className="workflow-card" href="/api/v1/assets/banlist/download" target="_blank" rel="noreferrer">
          <FileArchive size={24} />
          <strong>Ban 曲列表</strong>
          <span>下载当前赛事 banlist 表格。</span>
        </a>
      </div>
    </section>
  );
}

function SongPoolPage() {
  const songs = useAsync(() => api.mySongs(), []);
  const [form, setForm] = useState({ song_name: "", artist: "", song_type: "A", remark: "" });
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    await api.createSong(form);
    setForm({ song_name: "", artist: "", song_type: "A", remark: "" });
    await songs.reload();
    setMessage("曲目已提交");
  }

  return (
    <section className="page-stack">
      <header className="section-heading"><Music2 size={22} /><div><p className="eyebrow">Song Pool</p><h2>我的曲池提交</h2></div></header>
      <form className="form-panel compact" onSubmit={submit}>
        <label>曲名<input value={form.song_name} onChange={(e) => setForm({ ...form, song_name: e.target.value })} required /></label>
        <label>曲师 / 艺术家<input value={form.artist} onChange={(e) => setForm({ ...form, artist: e.target.value })} required /></label>
        <label>分类<select value={form.song_type} onChange={(e) => setForm({ ...form, song_type: e.target.value })}><option value="A">A: Pop + 技术向</option><option value="B">B: 通常音游曲</option><option value="C">C: 小众宝藏</option></select></label>
        <label>备注<textarea value={form.remark} onChange={(e) => setForm({ ...form, remark: e.target.value })} /></label>
        <button className="primary-action" type="submit">提交曲目</button>
        {message && <Notice tone="success">{message}</Notice>}
      </form>
      <SongTable songs={songs.data || []} emptyText={songs.state === "loading" ? "加载中..." : "还没有提交曲目"} />
    </section>
  );
}

function SongTable({ songs, emptyText }: { songs: SongRead[]; emptyText: string }) {
  if (!songs.length) return <Notice>{emptyText}</Notice>;
  return (
    <div className="table-shell">
      <table>
        <thead><tr><th>曲名</th><th>曲师</th><th>分类</th><th>提交者</th><th>备注</th></tr></thead>
        <tbody>{songs.map((song) => <tr key={song.id}><td>{song.song_name}</td><td>{song.artist}</td><td>{song.song_type}</td><td>{song.submitter?.user_code || "-"}</td><td>{song.remark || "-"}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function DrawPage() {
  const rows = useAsync(() => api.myDraw(), []);
  return (
    <section className="page-stack">
      <header className="section-heading"><Dice5 size={22} /><div><p className="eyebrow">Draw</p><h2>我的抽签结果</h2></div></header>
      <AssignmentList rows={rows.data || []} emptyText={rows.state === "loading" ? "加载中..." : "暂未抽签"} />
    </section>
  );
}

function AssignmentList({ rows, emptyText }: { rows: DrawAssignmentRead[]; emptyText: string }) {
  if (!rows.length) return <Notice>{emptyText}</Notice>;
  return <div className="section-grid">{rows.map((row) => <div className="workflow-card" key={row.id}><Dice5 size={22} /><strong>{row.song.song_name}</strong><span>{row.song.artist} · {row.song.song_type}</span><small>分配给 {row.assigned_to.user_code}</small></div>)}</div>;
}

function SubmissionPage() {
  const files = useAsync(() => api.mySubmissions(), []);
  const [message, setMessage] = useState("");
  async function upload(file?: File) {
    if (!file) return;
    setMessage("");
    await api.uploadSubmission(file);
    await files.reload();
    setMessage("投稿已上传");
  }
  return (
    <section className="page-stack">
      <header className="section-heading"><UploadCloud size={22} /><div><p className="eyebrow">Submission</p><h2>投稿上传</h2></div></header>
      <label className="upload-drop"><UploadCloud size={30} /><strong>选择音频或压缩包</strong><span>支持后端配置的文件类型和大小限制</span><input type="file" onChange={(e) => void upload(e.target.files?.[0])} /></label>
      {message && <Notice tone="success">{message}</Notice>}
      <FileTable files={files.data || []} />
    </section>
  );
}

function FileTable({ files }: { files: StoredFileRead[] }) {
  if (!files.length) return <Notice>暂无投稿文件</Notice>;
  return (
    <div className="table-shell">
      <table><thead><tr><th>文件</th><th>大小</th><th>状态</th><th>用户</th><th>时间</th></tr></thead><tbody>{files.map((file) => <tr key={file.id}><td>{file.file_name}</td><td>{formatMB(file.file_size)}</td><td>{file.review_status}</td><td>{file.user?.user_code || "-"}</td><td>{formatTime(file.created_at)}</td></tr>)}</tbody></table>
    </div>
  );
}

function GuessGamePage() {
  const charts = useAsync(() => api.guessCharts(), []);
  const [active, setActive] = useState<GuessChartRead | null>(null);
  const [comments, setComments] = useState<GuessCommentRead[]>([]);
  const [comment, setComment] = useState("");
  const { isLoggedIn } = useAuth();

  async function openChart(chart: GuessChartRead) {
    const detail = await api.guessChart(chart.id);
    setActive(detail);
    setComments(await api.comments(chart.id));
  }

  async function vote(chart: GuessChartRead, voteType: "love" | "funny") {
    if (chart.my_votes.includes(voteType)) await api.unvote(chart.id, voteType);
    else await api.vote(chart.id, voteType);
    await charts.reload();
    if (active?.id === chart.id) setActive(await api.guessChart(chart.id));
  }

  async function sendComment(event: FormEvent) {
    event.preventDefault();
    if (!active || !comment.trim()) return;
    await api.createComment(active.id, comment.trim());
    setComment("");
    setComments(await api.comments(active.id));
  }

  return (
    <section className="guess-layout">
      <div className="page-stack">
        <header className="section-heading"><Sparkles size={22} /><div><p className="eyebrow">Guess Game</p><h2>猜谱会场</h2></div></header>
        <div className="chart-grid">
          {(charts.data || []).map((chart) => (
            <button key={chart.id} className="chart-card" onClick={() => void openChart(chart)}>
              <span>{chart.level}</span>
              <strong>{chart.title}</strong>
              <small>{chart.author} · {chart.lane}</small>
              <div><Heart size={15} /> {chart.love_votes}<MessageCircle size={15} /> {chart.funny_votes}</div>
            </button>
          ))}
        </div>
        {charts.state === "ready" && !(charts.data || []).length && <Notice>暂未开放谱面</Notice>}
      </div>
      <aside className="detail-panel">
        {active ? (
          <>
            <p className="eyebrow">#{active.id}</p>
            <h3>{active.title}</h3>
            <p>{active.author} · {active.level} · 播放 {active.plays}</p>
            <div className="button-row">
              <button onClick={() => void vote(active, "love")} disabled={!isLoggedIn} className={active.my_votes.includes("love") ? "active vote-button" : "vote-button"}><Heart size={16} /> 真爱 {active.love_votes}</button>
              <button onClick={() => void vote(active, "funny")} disabled={!isLoggedIn} className={active.my_votes.includes("funny") ? "active vote-button" : "vote-button"}><Sparkles size={16} /> 乐子 {active.funny_votes}</button>
            </div>
            <form onSubmit={sendComment} className="comment-form">
              <input placeholder={isLoggedIn ? "写一句评论" : "登录后评论"} value={comment} onChange={(e) => setComment(e.target.value)} disabled={!isLoggedIn} />
              <button disabled={!isLoggedIn}>发送</button>
            </form>
            <div className="comment-list">{comments.map((item) => <p key={item.id}><strong>{item.user.user_code}</strong>{item.content}</p>)}</div>
          </>
        ) : <Notice>选择一个谱面查看详情</Notice>}
      </aside>
    </section>
  );
}

function AdminWorkbench() {
  const [tab, setTab] = useState("overview");
  const tabs = ["overview", "users", "songs", "draw", "submissions", "guess"] as const;
  const labels: Record<string, string> = { overview: "总览", users: "用户", songs: "曲池", draw: "抽签", submissions: "投稿", guess: "猜谱" };
  return (
    <section className="page-stack">
      <header className="section-heading"><ShieldCheck size={22} /><div><p className="eyebrow">Admin Workbench</p><h2>赛事工作台</h2></div></header>
      <div className="tabbar">{tabs.map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{labels[item]}</button>)}</div>
      {tab === "overview" && <AdminOverview />}
      {tab === "users" && <AdminUsers />}
      {tab === "songs" && <AdminSongs />}
      {tab === "draw" && <AdminDraw />}
      {tab === "submissions" && <AdminSubmissions />}
      {tab === "guess" && <AdminGuess />}
    </section>
  );
}

function AdminOverview() {
  const stats = useAsync(() => api.adminStats(), []);
  const items = stats.data || {};
  return <div className="metric-grid">{Object.entries(items).map(([key, value]) => <React.Fragment key={key}><StatCard icon={BarChart3} label={key} value={Number(value)} /></React.Fragment>)}</div>;
}

function AdminUsers() {
  const users = useAsync(() => api.users(), []);
  const roleLabels: Record<string, string> = { admin: "管理员", pool_editor: "曲池编辑", participant: "参赛者", audience: "观众" };

  async function saveUser(user: UserRead, patch: Partial<{ identity: string; roles: string[]; display_name: string; is_active: boolean }>) {
    await api.updateUser(user.id, {
      identity: patch.identity ?? user.identity,
      roles: patch.roles ?? user.roles,
      display_name: patch.display_name ?? user.display_name,
      is_active: patch.is_active ?? true,
    });
    await users.reload();
  }

  async function toggleRole(user: UserRead, role: string) {
    const roles = user.roles.includes(role) ? user.roles.filter((item) => item !== role) : [...user.roles, role];
    await saveUser(user, { roles });
  }

  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr><th>ID</th><th>QQ</th><th>身份</th><th>权限</th><th>状态</th></tr>
        </thead>
        <tbody>
          {(users.data || []).map((user) => (
            <tr key={user.id}>
              <td>{user.user_code}</td>
              <td>{user.qq_id}</td>
              <td>
                <select value={user.identity} onChange={(event) => void saveUser(user, { identity: event.target.value })}>
                  <option value="audience">观众</option>
                  <option value="participant">参赛者</option>
                </select>
              </td>
              <td>
                <div className="role-toggle-grid">
                  {Object.entries(roleLabels).map(([role, label]) => (
                    <label key={role} className="role-toggle">
                      <input type="checkbox" checked={user.roles.includes(role)} onChange={() => void toggleRole(user, role)} />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
              </td>
              <td>
                <button onClick={() => void saveUser(user, { is_active: true })}>启用</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AdminSongs() {
  const songs = useAsync(() => api.adminSongs(), []);
  return <SongTable songs={songs.data || []} emptyText="曲池为空" />;
}

function AdminDraw() {
  const rows = useAsync(() => api.adminDrawResults(), []);
  async function run() {
    await api.runDraw();
    await rows.reload();
  }
  return <div className="page-stack"><button className="primary-action fit" onClick={() => void run()}><Dice5 size={17} /> 重新抽签</button><AssignmentList rows={rows.data || []} emptyText="暂无抽签结果" /></div>;
}

function AdminSubmissions() {
  const files = useAsync(() => api.adminSubmissions(), []);
  return <FileTable files={files.data || []} />;
}

function AdminGuess() {
  const charts = useAsync(() => api.adminCharts(), []);
  const [form, setForm] = useState({ title: "", author: "", level: "1", lane: "normal", guess_group_key: "", is_self_selected: false });
  async function submit(event: FormEvent) {
    event.preventDefault();
    await api.createChart(form);
    setForm({ title: "", author: "", level: "1", lane: "normal", guess_group_key: "", is_self_selected: false });
    await charts.reload();
  }
  return (
    <div className="page-stack">
      <form className="form-panel compact" onSubmit={submit}>
        <label>标题<input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required /></label>
        <label>作者<input value={form.author} onChange={(e) => setForm({ ...form, author: e.target.value })} required /></label>
        <label>等级<input value={form.level} onChange={(e) => setForm({ ...form, level: e.target.value })} required /></label>
        <label>分组<input value={form.guess_group_key} onChange={(e) => setForm({ ...form, guess_group_key: e.target.value })} /></label>
        <button className="primary-action" type="submit">新增谱面</button>
      </form>
      <div className="chart-grid">{(charts.data || []).map((chart) => <div className="chart-card static" key={chart.id}><span>{chart.level}</span><strong>{chart.title}</strong><small>{chart.author}</small></div>)}</div>
    </div>
  );
}

export default function App() {
  return (
    <HashRouter>
      <AuthProvider>
        <ConfigProvider>
          <Shell />
        </ConfigProvider>
      </AuthProvider>
    </HashRouter>
  );
}
