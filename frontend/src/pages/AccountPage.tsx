import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Divider,
  FormControl,
  FormControlLabel,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { Eye, KeyRound, Save, ShieldCheck, Trophy, UserRoundCog } from "lucide-react";
import { PageHeader } from "../components/PagePrimitives";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";

type Identity = "participant" | "audience";

export default function AccountPage() {
  const { user, updateProfile, changePassword } = useAuth();
  const { phases, loading: configLoading } = useConfig();
  const [profile, setProfile] = useState({ displayName: user?.display_name ?? "", identity: (user?.identity ?? "audience") as Identity });
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [passwords, setPasswords] = useState({ current: "", next: "", confirm: "" });
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const identityEditable = !configLoading && phases?.active_phase === "registration";

  useEffect(() => {
    if (!user) return;
    setProfile({ displayName: user.display_name, identity: user.identity as Identity });
  }, [user]);

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    const displayName = profile.displayName.trim();
    setProfileError("");
    setProfileMessage("");
    if (!displayName) {
      setProfileError("显示名不能为空");
      return;
    }
    if (displayName.length > 100) {
      setProfileError("显示名不能超过 100 个字符");
      return;
    }
    setProfileBusy(true);
    try {
      await updateProfile(displayName, profile.identity);
      setProfileMessage("个人资料已保存");
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setProfileBusy(false);
    }
  }

  async function savePassword(event: FormEvent) {
    event.preventDefault();
    setPasswordError("");
    setPasswordMessage("");
    if (passwords.next !== passwords.confirm) {
      setPasswordError("两次输入的新密码不一致");
      return;
    }
    setPasswordBusy(true);
    try {
      await changePassword(passwords.current, passwords.next, passwords.confirm);
      setPasswords({ current: "", next: "", confirm: "" });
      setPasswordMessage("密码已更新，其他设备上的登录已注销");
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : "密码更新失败");
    } finally {
      setPasswordBusy(false);
    }
  }

  return (
    <Box sx={{ maxWidth: 1120, mx: "auto" }}>
      <PageHeader icon={UserRoundCog} title="账号设置" meta="管理你的赛事身份、公开名称与账号安全" />
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.15fr) minmax(340px, 0.85fr)" }, gap: 2.5, alignItems: "start" }}>
        <Paper component="form" onSubmit={saveProfile} variant="outlined" sx={{ overflow: "hidden" }}>
          <Box sx={{ height: 5, bgcolor: "primary.main" }} />
          <Stack spacing={2.5} sx={{ p: { xs: 2, sm: 3 } }}>
            <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 38, height: 38, borderRadius: 1, display: "grid", placeItems: "center", bgcolor: "primary.light", color: "primary.dark" }}><UserRoundCog size={20} /></Box>
              <Box><Typography variant="h3">个人资料</Typography><Typography variant="body2" color="text.secondary">这些信息会显示在赛事页面中</Typography></Box>
            </Stack>
            <Divider />
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
              <TextField label="登录账号" value={user?.user_code ?? ""} disabled helperText="登录账号不可自行修改" />
              <TextField label="注册 QQ" value={user?.qq_id ?? ""} disabled helperText="如需修改请联系管理员" />
            </Box>
            <TextField
              label="显示名"
              value={profile.displayName}
              onChange={(event) => setProfile((current) => ({ ...current, displayName: event.target.value }))}
              required
              slotProps={{ htmlInput: { maxLength: 100 } }}
              helperText={`${profile.displayName.trim().length}/100，将用于投稿、评论和榜单展示`}
              autoComplete="nickname"
            />
            <FormControl>
              <Typography component="legend" variant="body2" sx={{ mb: 1, fontWeight: 700 }}>赛事身份</Typography>
              <RadioGroup row value={profile.identity} onChange={(event) => setProfile((current) => ({ ...current, identity: event.target.value as Identity }))} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)" }, gap: 1.25 }}>
                <IdentityChoice value="participant" selected={profile.identity === "participant"} disabled={!identityEditable} icon={<Trophy size={20} />} title="参赛者" description="参与曲目分配并提交参赛作品" />
                <IdentityChoice value="audience" selected={profile.identity === "audience"} disabled={!identityEditable} icon={<Eye size={20} />} title="观众" description="浏览赛事并参与开放的互动环节" />
              </RadioGroup>
            </FormControl>
            {!identityEditable ? <Alert severity="info">{configLoading || !phases ? "正在确认当前赛事阶段，身份暂不可修改。" : "身份仅可在报名阶段修改；当前仍可保存显示名。"}</Alert> : <Alert severity="success" icon={<ShieldCheck size={20} />}>当前处于报名阶段，可以自由选择参赛者或观众身份。</Alert>}
            {profileError ? <Alert severity="error">{profileError}</Alert> : null}
            {profileMessage ? <Alert severity="success">{profileMessage}</Alert> : null}
            <Button type="submit" variant="contained" disabled={profileBusy} startIcon={profileBusy ? <CircularProgress size={16} color="inherit" /> : <Save size={17} />} sx={{ alignSelf: { sm: "flex-start" }, minWidth: 132 }}>保存资料</Button>
          </Stack>
        </Paper>

        <Paper component="form" onSubmit={savePassword} variant="outlined" sx={{ overflow: "hidden" }}>
          <Box sx={{ height: 5, bgcolor: "secondary.main" }} />
          <Stack spacing={2.25} sx={{ p: { xs: 2, sm: 3 } }}>
            <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 38, height: 38, borderRadius: 1, display: "grid", placeItems: "center", bgcolor: "secondary.light", color: "secondary.dark" }}><KeyRound size={20} /></Box>
              <Box><Typography variant="h3">账号安全</Typography><Typography variant="body2" color="text.secondary">更新密码并保护你的登录会话</Typography></Box>
            </Stack>
            <Divider />
            <TextField label="当前密码" type="password" value={passwords.current} onChange={(event) => setPasswords((current) => ({ ...current, current: event.target.value }))} required autoComplete="current-password" />
            <TextField label="新密码" type="password" value={passwords.next} onChange={(event) => setPasswords((current) => ({ ...current, next: event.target.value }))} required slotProps={{ htmlInput: { minLength: 6, maxLength: 128 } }} helperText="至少 6 个字符" autoComplete="new-password" />
            <TextField label="确认新密码" type="password" value={passwords.confirm} onChange={(event) => setPasswords((current) => ({ ...current, confirm: event.target.value }))} required slotProps={{ htmlInput: { minLength: 6, maxLength: 128 } }} autoComplete="new-password" />
            <Alert severity="info">修改成功后，当前设备保持登录，其他设备将需要使用新密码重新登录。</Alert>
            {passwordError ? <Alert severity="error">{passwordError}</Alert> : null}
            {passwordMessage ? <Alert severity="success">{passwordMessage}</Alert> : null}
            <Button type="submit" variant="contained" color="secondary" disabled={passwordBusy} startIcon={passwordBusy ? <CircularProgress size={16} color="inherit" /> : <KeyRound size={17} />}>更新密码</Button>
          </Stack>
        </Paper>
      </Box>
    </Box>
  );
}

function IdentityChoice({ value, selected, disabled, icon, title, description }: { value: Identity; selected: boolean; disabled: boolean; icon: ReactNode; title: string; description: string }) {
  return (
    <FormControlLabel
      value={value}
      disabled={disabled}
      control={<Radio />}
      label={<Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}><Box sx={{ color: selected ? "primary.main" : "text.secondary", display: "grid" }}>{icon}</Box><Box><Typography variant="body2" sx={{ fontWeight: 700 }}>{title}</Typography><Typography variant="caption" color="text.secondary">{description}</Typography></Box></Stack>}
      sx={{ m: 0, p: 1.25, pr: 1.5, minHeight: 76, alignItems: "center", border: 1, borderColor: selected ? "primary.main" : "divider", borderRadius: 1, bgcolor: selected ? "primary.light" : "background.paper", transition: "border-color 160ms ease, background-color 160ms ease", opacity: disabled ? 0.68 : 1, "&:hover": disabled ? undefined : { borderColor: "primary.main" }, "& .MuiFormControlLabel-label": { flex: 1 } }}
    />
  );
}
