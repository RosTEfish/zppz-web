import { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, FormControl, FormHelperText, InputLabel, MenuItem, Paper, Select, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { LogIn } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import BrandLogo from "../components/BrandLogo";
import { isRegistrationClosed } from "../components/EventPhaseStatus";
import { useAuth } from "../contexts/AuthContext";
import { useConfig } from "../contexts/ConfigContext";
import { useEventTheme } from "../contexts/EventThemeProvider";
import { authSchema, type AuthFormValues } from "../forms/schemas";
import { useEventBackgrounds } from "../hooks/useEventBackgrounds";
import { navigateWithViewTransition } from "../navigation/viewTransition";

export default function AuthPage() {
  const [error, setError] = useState("");
  const holdRedirect = useRef(false);
  const { login, register: registerAccount, isLoggedIn } = useAuth();
  const { event, phases } = useConfig();
  const backgrounds = useEventBackgrounds();
  const { palette } = useEventTheme();
  const navigate = useNavigate();
  const location = useLocation();
  // Skip local enter keyframes when arriving via View Transition (avoids double-motion).
  const skipEnter = Boolean((location.state as { zppzVt?: string } | null)?.zppzVt);
  const { register, control, handleSubmit, setValue, clearErrors, watch, formState: { errors, isSubmitting } } = useForm<AuthFormValues>({
    resolver: zodResolver(authSchema),
    defaultValues: { mode: "login", user_code: "", qq_id: "", password: "", identity: "participant" },
  });
  const mode = watch("mode");
  const registrationClosed = Boolean(phases && isRegistrationClosed(phases));
  useEffect(() => {
    if (registrationClosed) setValue("identity", "guest");
  }, [registrationClosed, setValue]);
  // Keep the auth shell mounted until View Transition navigation runs after login/register.
  if (isLoggedIn && !holdRedirect.current) return <Navigate to="/" replace />;

  const submit = handleSubmit(async (form) => {
    setError("");
    holdRedirect.current = true;
    try {
      if (form.mode === "login") await login(form.user_code, form.password);
      else await registerAccount(form.user_code, form.qq_id, form.password, registrationClosed ? "guest" : form.identity);
      navigateWithViewTransition(navigate, "/", { replace: true });
    } catch (err) {
      holdRedirect.current = false;
      setError(err instanceof Error ? err.message : "操作失败");
    }
  });

  const stageArt = backgrounds.post ?? backgrounds.brand ?? backgrounds.hero;

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "grid",
        gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1.15fr) minmax(320px, 0.85fr)" },
        bgcolor: "background.default",
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          position: "relative",
          minHeight: { xs: 220, md: "100vh" },
          overflow: "hidden",
          bgcolor: palette.tint,
          display: { xs: stageArt ? "block" : "none", md: "block" },
          "@keyframes authArtIn": {
            from: { opacity: 0, transform: "scale(1.03)" },
            to: { opacity: 1, transform: "scale(1)" },
          },
          "@media (prefers-reduced-motion: reduce)": {
            "& img": { animation: "none !important" },
          },
        }}
      >
        {stageArt ? (
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
              animation: skipEnter ? "none" : "authArtIn 420ms cubic-bezier(0.32, 0.72, 0, 1) both",
            }}
          />
        ) : null}
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            backgroundImage: stageArt
              ? [
                  "linear-gradient(90deg, transparent 55%, rgba(247,247,244,0.55) 100%)",
                  "linear-gradient(180deg, rgba(23,33,28,0.08), transparent 35%)",
                ].join(", ")
              : [
                  `radial-gradient(720px 420px at 20% 20%, ${palette.washA}, transparent 60%)`,
                  `radial-gradient(640px 380px at 80% 80%, ${palette.accentSoft}, transparent 58%)`,
                  "linear-gradient(135deg, #FAFBFA, #F4F6F5)",
                ].join(", "),
          }}
        />
        {event?.name ? (
          <Box
            sx={{
              position: "absolute",
              left: 28,
              bottom: 28,
              zIndex: 1,
              color: "#fff",
              textShadow: "0 2px 16px rgba(0,0,0,0.25)",
              display: { xs: "none", md: "block" },
            }}
          >
            <Typography sx={{ fontWeight: 800, fontSize: "1.35rem", lineHeight: 1.2 }}>
              {event.name}
            </Typography>
            <Typography sx={{ mt: 0.5, fontWeight: 600, fontSize: "0.85rem", opacity: 0.92 }}>
              ZPPZ · 赛事入口
            </Typography>
          </Box>
        ) : null}
      </Box>

      <Box
        sx={{
          display: "grid",
          placeItems: "center",
          px: { xs: 2, sm: 3.5 },
          py: { xs: 3, md: 5 },
          minHeight: { xs: "auto", md: "100vh" },
          backgroundImage: `radial-gradient(600px 280px at 100% 0%, ${palette.washA}, transparent 60%)`,
          bgcolor: "background.default",
        }}
      >
        <Paper
          component="form"
          onSubmit={submit}
          noValidate
          sx={{
            width: "100%",
            maxWidth: 380,
            p: { xs: 2.5, sm: 3.5 },
            borderRadius: "16px",
            border: "1px solid",
            borderColor: "divider",
            bgcolor: "background.paper",
            boxShadow: (theme) => theme.shadows[3],
            "@keyframes authFormIn": {
              from: { opacity: 0, transform: "translateY(10px)" },
              to: { opacity: 1, transform: "translateY(0)" },
            },
            animation: skipEnter ? "none" : "authFormIn 360ms cubic-bezier(0.32, 0.72, 0, 1) both",
            "@media (prefers-reduced-motion: reduce)": { animation: "none" },
          }}
        >
          <Stack direction="row" spacing={1.5} sx={{ mb: 2.25, alignItems: "center" }}>
            <BrandLogo size={40} borderRadius="12px" />
            <Box sx={{ minWidth: 0 }}>
              <Typography sx={{ fontFamily: '"Noto Serif SC", serif', fontWeight: 700, lineHeight: 1.2 }}>ZPPZ </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25, fontWeight: 600 }}>
                这谱谱这 · 登录入口
              </Typography>
            </Box>
          </Stack>

          <Typography variant="overline" color="primary.dark" sx={{ fontWeight: 800 }}>
            CURRENT EVENT
          </Typography>
          <Box aria-hidden="true" sx={{ width: 26, height: 2.5, borderRadius: 1, bgcolor: palette.accent, mt: 0.75, mb: 1.25 }} />
          <Typography variant="h2" component="h1" sx={{ m: 0 }}>
            赛事账号
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, fontWeight: 600 }}>
            {event?.name ? `${event.name} · 投稿 / 抽曲 / 猜谱` : "投稿 / 抽曲 / 猜谱"}
          </Typography>

          <Tabs
            value={mode}
            onChange={(_, value: AuthFormValues["mode"]) => { setValue("mode", value); clearErrors(); setError(""); }}
            variant="fullWidth"
            sx={{ mt: 2.5, mb: 2.5 }}
          >
            <Tab value="login" label="登录" />
            <Tab value="register" label="注册" />
          </Tabs>

          <Stack spacing={2}>
            <TextField label="账号" {...register("user_code")} error={Boolean(errors.user_code)} helperText={errors.user_code?.message} autoComplete="username" />
            {mode === "register" ? <TextField label="QQ" {...register("qq_id")} error={Boolean(errors.qq_id)} helperText={errors.qq_id?.message} /> : null}
            <TextField label="密码" type="password" {...register("password")} error={Boolean(errors.password)} helperText={errors.password?.message} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            {mode === "register" ? <>
              {registrationClosed ? <Alert severity="warning">报名阶段已结束，新注册账号将分配为访客身份。</Alert> : null}
              <Controller
                name="identity"
                control={control}
                render={({ field, fieldState }) => (
                  <FormControl error={Boolean(fieldState.error)}>
                    <InputLabel>身份</InputLabel>
                    <Select {...field} label="身份" inputProps={{ "aria-label": "身份" }} disabled={registrationClosed}>
                      <MenuItem value="participant">参赛者（投曲并参与抽取）</MenuItem>
                      <MenuItem value="audience">观众（投曲但不参与抽取）</MenuItem>
                      <MenuItem value="guest">访客（不投曲、不参与抽取）</MenuItem>
                    </Select>
                    {fieldState.error ? <FormHelperText>{fieldState.error.message}</FormHelperText> : null}
                  </FormControl>
                )}
              />
            </> : null}
            {error ? <Alert severity="error">{error}</Alert> : null}
            <Button type="submit" variant="contained" disabled={isSubmitting} startIcon={isSubmitting ? <CircularProgress size={16} /> : <LogIn size={17} />}>
              {mode === "login" ? "登录" : "注册并登录"}
            </Button>
          </Stack>
        </Paper>
      </Box>
    </Box>
  );
}
