import { type FormEvent, useState } from "react";
import { Alert, Box, Button, CircularProgress, FormControl, InputLabel, MenuItem, Paper, Select, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { KeyRound, LogIn } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";


export default function AuthPage() {
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
