import { useState } from "react";
import { Alert, Box, Button, CircularProgress, FormControl, FormHelperText, InputLabel, MenuItem, Paper, Select, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { KeyRound, LogIn } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useAuth } from "../contexts/AuthContext";
import { authSchema, type AuthFormValues } from "../forms/schemas";

export default function AuthPage() {
  const [error, setError] = useState("");
  const { login, register: registerAccount, isLoggedIn } = useAuth();
  const navigate = useNavigate();
  const { register, control, handleSubmit, setValue, clearErrors, watch, formState: { errors, isSubmitting } } = useForm<AuthFormValues>({
    resolver: zodResolver(authSchema),
    defaultValues: { mode: "login", user_code: "", qq_id: "", password: "", identity: "participant" },
  });
  const mode = watch("mode");
  if (isLoggedIn) return <Navigate to="/" replace />;

  const submit = handleSubmit(async (form) => {
    setError("");
    try {
      if (form.mode === "login") await login(form.user_code, form.password);
      else await registerAccount(form.user_code, form.qq_id, form.password, form.identity);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    }
  });

  return (
    <Box sx={{ minHeight: "calc(100vh - 130px)", display: "grid", placeItems: "center" }}>
      <Paper component="form" onSubmit={submit} noValidate sx={{ width: "100%", maxWidth: 430, p: { xs: 2.5, sm: 4 } }}>
        <Stack direction="row" spacing={1.5} sx={{ mb: 3, alignItems: "center" }}><KeyRound size={24} /><Typography variant="h2">赛事账号</Typography></Stack>
        <Tabs value={mode} onChange={(_, value: AuthFormValues["mode"]) => { setValue("mode", value); clearErrors(); setError(""); }} variant="fullWidth" sx={{ mb: 3 }}><Tab value="login" label="登录" /><Tab value="register" label="注册" /></Tabs>
        <Stack spacing={2}>
          <TextField label="账号" {...register("user_code")} error={Boolean(errors.user_code)} helperText={errors.user_code?.message} autoComplete="username" />
          {mode === "register" ? <TextField label="QQ" {...register("qq_id")} error={Boolean(errors.qq_id)} helperText={errors.qq_id?.message} /> : null}
          <TextField label="密码" type="password" {...register("password")} error={Boolean(errors.password)} helperText={errors.password?.message} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          {mode === "register" ? <Controller name="identity" control={control} render={({ field, fieldState }) => <FormControl error={Boolean(fieldState.error)}><InputLabel>身份</InputLabel><Select {...field} label="身份"><MenuItem value="participant">参赛者（投曲并参与抽取）</MenuItem><MenuItem value="audience">观众（投曲但不参与抽取）</MenuItem><MenuItem value="guest">访客（不投曲、不参与抽取）</MenuItem></Select>{fieldState.error ? <FormHelperText>{fieldState.error.message}</FormHelperText> : null}</FormControl>} /> : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          <Button type="submit" variant="contained" disabled={isSubmitting} startIcon={isSubmitting ? <CircularProgress size={16} /> : <LogIn size={17} />}>{mode === "login" ? "登录" : "注册并登录"}</Button>
        </Stack>
      </Paper>
    </Box>
  );
}
