import { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, FormControl, FormHelperText, InputLabel, MenuItem, Paper, Select, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { KeyRound, LogIn } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { isRegistrationClosed } from "../components/EventPhaseStatus";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";
import { useEventTheme } from "../contexts/EventThemeProvider";
import { authSchema, type AuthFormValues } from "../forms/schemas";
import { useEventBackgrounds } from "../hooks/useEventBackgrounds";

export default function AuthPage() {
  const [error, setError] = useState("");
  const { login, register: registerAccount, isLoggedIn } = useAuth();
  const { event, phases } = useConfig();
  const backgrounds = useEventBackgrounds();
  const { palette } = useEventTheme();
  const navigate = useNavigate();
  const { register, control, handleSubmit, setValue, clearErrors, watch, formState: { errors, isSubmitting } } = useForm<AuthFormValues>({
    resolver: zodResolver(authSchema),
    defaultValues: { mode: "login", user_code: "", qq_id: "", password: "", identity: "participant" },
  });
  const mode = watch("mode");
  const registrationClosed = Boolean(phases && isRegistrationClosed(phases));
  useEffect(() => {
    if (registrationClosed) setValue("identity", "guest");
  }, [registrationClosed, setValue]);
  if (isLoggedIn) return <Navigate to="/" replace />;

  const submit = handleSubmit(async (form) => {
    setError("");
    try {
      if (form.mode === "login") await login(form.user_code, form.password);
      else await registerAccount(form.user_code, form.qq_id, form.password, registrationClosed ? "guest" : form.identity);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    }
  });

  const stageArt = backgrounds.post ?? backgrounds.brand ?? backgrounds.hero;

  return (
    <Box
      sx={{
        position: "relative",
        flex: 1,
        minHeight: { xs: "calc(100vh - 64px)", md: "calc(100vh - 64px)" },
        display: "grid",
        placeItems: "center",
        overflow: "hidden",
        px: { xs: 2, sm: 3 },
        py: { xs: 3, md: 4 },
      }}
    >
      {stageArt ? (
        <Box
          aria-hidden="true"
          sx={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            "@keyframes authStageIn": {
              from: { opacity: 0, transform: "scale(1.03)" },
              to: { opacity: 1, transform: "scale(1)" },
            },
            "@media (prefers-reduced-motion: reduce)": {
              "& img": { animation: "none !important" },
            },
          }}
        >
          <Box
            component="img"
            src={stageArt.url}
            alt=""
            loading="eager"
            decoding="async"
            sx={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "center",
              animation: "authStageIn 480ms cubic-bezier(0.32, 0.72, 0, 1) both",
              filter: "saturate(1.05)",
            }}
          />
          <Box
            sx={{
              position: "absolute",
              inset: 0,
              backgroundImage: [
                `linear-gradient(115deg, rgba(247,247,244,0.92) 0%, rgba(247,247,244,0.78) 42%, rgba(247,247,244,0.34) 70%, rgba(247,247,244,0.18) 100%)`,
                `radial-gradient(720px 420px at 12% 20%, ${palette.washA}, transparent 60%)`,
                `radial-gradient(640px 380px at 88% 80%, ${palette.accentSoft}, transparent 58%)`,
              ].join(", "),
            }}
          />
        </Box>
      ) : (
        <Box
          aria-hidden="true"
          sx={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            backgroundImage: [
              `radial-gradient(900px 420px at 12% 18%, ${palette.washA}, transparent 60%)`,
              `radial-gradient(700px 380px at 88% 82%, ${palette.washC}, transparent 58%)`,
            ].join(", "),
          }}
        />
      )}

      <Paper
        component="form"
        onSubmit={submit}
        noValidate
        sx={{
          position: "relative",
          zIndex: 1,
          width: "100%",
          maxWidth: 430,
          p: { xs: 2.5, sm: 4 },
          borderRadius: "16px",
          border: "1px solid",
          borderColor: "divider",
          bgcolor: "rgba(255,255,255,0.86)",
          backdropFilter: "blur(14px) saturate(1.25)",
          WebkitBackdropFilter: "blur(14px) saturate(1.25)",
          boxShadow: (theme) => theme.shadows[3],
          backgroundImage: `linear-gradient(180deg, rgba(255,255,255,0.96), rgba(255,255,255,0.88)), radial-gradient(120% 80% at 100% 0%, ${palette.washA}, transparent 55%)`,
          "@keyframes authFormIn": {
            from: { opacity: 0, transform: "translateY(12px)" },
            to: { opacity: 1, transform: "translateY(0)" },
          },
          animation: "authFormIn 360ms cubic-bezier(0.32, 0.72, 0, 1) both",
          "@media (prefers-reduced-motion: reduce)": { animation: "none" },
        }}
      >
        <Stack direction="row" spacing={1.5} sx={{ mb: 1.25, alignItems: "center" }}>
          <Box aria-hidden="true" sx={{ width: 42, height: 42, borderRadius: "12px", bgcolor: "primary.light", color: "primary.dark", display: "grid", placeItems: "center", flexShrink: 0 }}><KeyRound size={22} /></Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h2">赛事账号</Typography>
            {event?.name ? (
              <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block", mt: 0.25 }}>
                {event.name}
              </Typography>
            ) : null}
          </Box>
        </Stack>
        <Box aria-hidden="true" sx={{ width: 26, height: 2.5, borderRadius: 1, bgcolor: palette.accent, mb: 2.25 }} />
        <Tabs value={mode} onChange={(_, value: AuthFormValues["mode"]) => { setValue("mode", value); clearErrors(); setError(""); }} variant="fullWidth" sx={{ mb: 3 }}><Tab value="login" label="登录" /><Tab value="register" label="注册" /></Tabs>
        <Stack spacing={2}>
          <TextField label="账号" {...register("user_code")} error={Boolean(errors.user_code)} helperText={errors.user_code?.message} autoComplete="username" />
          {mode === "register" ? <TextField label="QQ" {...register("qq_id")} error={Boolean(errors.qq_id)} helperText={errors.qq_id?.message} /> : null}
          <TextField label="密码" type="password" {...register("password")} error={Boolean(errors.password)} helperText={errors.password?.message} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          {mode === "register" ? <>
            {registrationClosed ? <Alert severity="warning">报名阶段已结束，新注册账号将分配为访客身份。</Alert> : null}
            <Controller name="identity" control={control} render={({ field, fieldState }) => <FormControl error={Boolean(fieldState.error)}><InputLabel>身份</InputLabel><Select {...field} label="身份" inputProps={{ "aria-label": "身份" }} disabled={registrationClosed}><MenuItem value="participant">参赛者（投曲并参与抽取）</MenuItem><MenuItem value="audience">观众（投曲但不参与抽取）</MenuItem><MenuItem value="guest">访客（不投曲、不参与抽取）</MenuItem></Select>{fieldState.error ? <FormHelperText>{fieldState.error.message}</FormHelperText> : null}</FormControl>} />
          </> : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          <Button type="submit" variant="contained" disabled={isSubmitting} startIcon={isSubmitting ? <CircularProgress size={16} /> : <LogIn size={17} />}>{mode === "login" ? "登录" : "注册并登录"}</Button>
        </Stack>
      </Paper>
    </Box>
  );
}
