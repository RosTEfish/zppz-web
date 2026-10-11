# Shared UI primitives — ZPPZ Arena

**Stack:** React 19 + Vite + **MUI 9** (`@mui/material`) + Lucide icons. No shadcn/Radix. Forms use MUI `TextField` / `Button` / `Tabs` / `Select` directly (react-hook-form + zod). Theme via `createAppTheme` + nested `EventThemeProvider`.

There is no `components/ui/` kit — shared primitives live in `frontend/src/components/PagePrimitives.tsx`. Auth UI is page-local in `AuthPage.tsx` using MUI primitives.

---

## Auth form pattern (MUI primitives)

**Source:** `frontend/src/pages/AuthPage.tsx`  
**Description:** Login/register glass form — Tabs mode switch, TextFields, identity Select, contained Button.  
**Key props/state:** `mode` (`login` | `register`), RHF `register`/`control`, `isSubmitting`, `registrationClosed`.

Imports:

```tsx
import { Alert, Box, Button, CircularProgress, FormControl, FormHelperText, InputLabel, MenuItem, Paper, Select, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { authSchema, type AuthFormValues } from "../forms/schemas";
```

Form shell + Tabs + fields (excerpt):

```tsx
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
    borderColor: "rgba(255,255,255,0.55)",
    bgcolor: "rgba(255,255,255,0.72)",
    backdropFilter: "blur(18px) saturate(1.35)",
    WebkitBackdropFilter: "blur(18px) saturate(1.35)",
    boxShadow: (theme) => theme.shadows[3],
    backgroundImage: `linear-gradient(165deg, rgba(255,255,255,0.88), rgba(255,255,255,0.66)), radial-gradient(120% 90% at 100% 0%, ${palette.washA}, transparent 55%)`,
  }}
>
  <Stack direction="row" spacing={1.5} sx={{ mb: 1.25, alignItems: "center" }}>
    <Box aria-hidden="true" sx={{ width: 42, height: 42, borderRadius: "12px", bgcolor: "primary.light", color: "primary.dark", display: "grid", placeItems: "center", flexShrink: 0 }}>
      <KeyRound size={22} />
    </Box>
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
  <Tabs
    value={mode}
    onChange={(_, value: AuthFormValues["mode"]) => { setValue("mode", value); clearErrors(); setError(""); }}
    variant="fullWidth"
    sx={{ mb: 3 }}
  >
    <Tab value="login" label="登录" />
    <Tab value="register" label="注册" />
  </Tabs>
  <Stack spacing={2}>
    <TextField label="账号" {...register("user_code")} error={Boolean(errors.user_code)} helperText={errors.user_code?.message} autoComplete="username" />
    {mode === "register" ? (
      <TextField label="QQ" {...register("qq_id")} error={Boolean(errors.qq_id)} helperText={errors.qq_id?.message} />
    ) : null}
    <TextField
      label="密码"
      type="password"
      {...register("password")}
      error={Boolean(errors.password)}
      helperText={errors.password?.message}
      autoComplete={mode === "login" ? "current-password" : "new-password"}
    />
    {/* register: identity Select via Controller + MenuItem participant/audience/guest */}
    {error ? <Alert severity="error">{error}</Alert> : null}
    <Button
      type="submit"
      variant="contained"
      disabled={isSubmitting}
      startIcon={isSubmitting ? <CircularProgress size={16} /> : <LogIn size={17} />}
    >
      {mode === "login" ? "登录" : "注册并登录"}
    </Button>
  </Stack>
</Paper>
```

Auth schema (`frontend/src/forms/schemas.ts`):

```ts
export const authSchema = z.object({
  mode: z.enum(["login", "register"]),
  user_code: z.string().trim().min(1, "请输入账号").max(64, "账号不能超过 64 个字符"),
  qq_id: z.string().trim().max(32, "QQ 不能超过 32 个字符"),
  password: z.string().min(1, "请输入密码").max(128, "密码不能超过 128 个字符"),
  identity: z.enum(["participant", "audience", "guest"]),
}).superRefine((value, context) => {
  if (value.mode !== "register") return;
  if (value.user_code.length < 2) context.addIssue({ code: "custom", path: ["user_code"], message: "账号至少 2 个字符" });
  if (!value.qq_id) context.addIssue({ code: "custom", path: ["qq_id"], message: "请输入 QQ" });
  if (value.password.length < 6) context.addIssue({ code: "custom", path: ["password"], message: "密码至少 6 个字符" });
});

export type AuthFormValues = z.infer<typeof authSchema>;
```

---

## PagePrimitives — full source

**File:** `frontend/src/components/PagePrimitives.tsx`  
**Exports:** `useApiResource`, `LoadingBlock`, `TableSkeleton`, `CardGridSkeleton`, `PageHeader`, `ResourceState`

```tsx
import { type Dispatch, type ReactNode, type SetStateAction, useCallback } from "react";
import { Alert, Box, CircularProgress, Paper, Skeleton, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import type { LucideIcon } from "lucide-react";
import useSWR, { type Key, type SWRConfiguration } from "swr";


export type ApiResource<T> = {
  data: T | null;
  loading: boolean;
  validating: boolean;
  error: string;
  reload: () => Promise<T | null>;
  setData: Dispatch<SetStateAction<T | null>>;
  updateData: (updater: (current: T) => T) => void;
};


export function useApiResource<T>(
  key: Key,
  loader: () => Promise<T>,
  enabled = true,
  configuration?: SWRConfiguration<T>,
): ApiResource<T> {
  const { data, error, isLoading, isValidating, mutate } = useSWR<T>(enabled ? key : null, () => loader(), {
    keepPreviousData: true,
    revalidateOnFocus: false,
    ...configuration,
  });
  const reload = useCallback(async () => (await mutate()) ?? null, [mutate]);
  const setData = useCallback<Dispatch<SetStateAction<T | null>>>((value) => {
    void mutate((current) => {
      const previous = current ?? null;
      return typeof value === "function"
        ? (value as (current: T | null) => T | null)(previous) ?? undefined
        : value ?? undefined;
    }, { revalidate: false });
  }, [mutate]);
  const updateData = useCallback((updater: (current: T) => T) => {
    void mutate((current) => current === undefined ? current : updater(current), { revalidate: false });
  }, [mutate]);
  return {
    data: data ?? null,
    loading: enabled && isLoading,
    validating: isValidating,
    error: error instanceof Error ? error.message : error ? "加载失败" : "",
    reload,
    setData,
    updateData,
  };
}


export function LoadingBlock() {
  return <Box sx={{ minHeight: "calc(100vh - 88px)", py: 10, display: "grid", placeItems: "center" }}><CircularProgress size={30} /></Box>;
}


export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <Paper variant="outlined" aria-busy="true" aria-label="正在加载内容">
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell><Skeleton variant="rounded" height={20} width="60%" /></TableCell>
              <TableCell><Skeleton variant="rounded" height={20} width="50%" /></TableCell>
              <TableCell><Skeleton variant="rounded" height={20} width="40%" /></TableCell>
              <TableCell><Skeleton variant="rounded" height={20} width="50%" /></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {Array.from({ length: rows }).map((_, index) => (
              <TableRow key={index} hover>
                <TableCell>
                  <Stack spacing={0.5}>
                    <Skeleton variant="text" height={16} width="90%" />
                    <Skeleton variant="text" height={11} width="40%" />
                  </Stack>
                </TableCell>
                <TableCell><Skeleton variant="text" height={16} width="80%" /></TableCell>
                <TableCell><Skeleton variant="rounded" height={24} width={48} /></TableCell>
                <TableCell><Skeleton variant="text" height={16} width="70%" /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}


export function CardGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", lg: "repeat(3, 1fr)", xl: "repeat(4, 1fr)" }, gap: 2 }} aria-busy="true" aria-label="正在加载内容">
      {Array.from({ length: count }).map((_, index) => (
        <Paper key={index} variant="outlined" sx={{ overflow: "hidden" }}>
          <Skeleton variant="rounded" height={164} />
          <Stack spacing={1} sx={{ p: 2 }}>
            <Skeleton variant="text" height={28} width="70%" />
            <Stack direction="row" spacing={1}>
              <Skeleton variant="rounded" height={24} width={48} />
              <Skeleton variant="rounded" height={24} width={48} />
            </Stack>
            <Skeleton variant="text" height={16} width="85%" />
            <Skeleton variant="text" height={16} width="60%" />
          </Stack>
        </Paper>
      ))}
    </Box>
  );
}


export function PageHeader({ icon: Icon, title, meta, actions }: { icon: LucideIcon; title: string; meta?: string; actions?: ReactNode }) {
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


export function ResourceState({ loading, error, empty, emptyIcon: EmptyIcon, loadingVariant = "block" }: { loading: boolean; error: string; empty?: string; emptyIcon?: LucideIcon; loadingVariant?: "block" | "table" | "cards" }) {
  if (loading) {
    if (loadingVariant === "table") return <TableSkeleton />;
    if (loadingVariant === "cards") return <CardGridSkeleton />;
    return <LoadingBlock />;
  }
  if (error) return <Alert severity="error">{error}</Alert>;
  if (empty) {
    return (
      <Paper variant="outlined" sx={{ py: 7, px: 2, textAlign: "center", display: "grid", justifyItems: "center", gap: 1 }}>
        {EmptyIcon ? (
          <Box aria-hidden="true" sx={{ width: 48, height: 48, borderRadius: 3, bgcolor: "primary.light", color: "primary.dark", display: "grid", placeItems: "center" }}>
            <EmptyIcon size={24} strokeWidth={1.75} />
          </Box>
        ) : null}
        <Typography color="text.secondary">{empty}</Typography>
      </Paper>
    );
  }
  return null;
}
```

---

## Related shared pieces (pointers)

| Component | Path | Role |
|---|---|---|
| `EventHeroArt` | `frontend/src/components/EventHeroArt.tsx` | Full-bleed hero image + palette washes |
| `HomePageSkeleton` | `frontend/src/components/HomePageSkeleton.tsx` | Home loading scaffold |
| `PhaseTimeline` / `PhaseHeadline` | `frontend/src/components/EventPhaseStatus.tsx` | Stage timeline chips |
| MUI theme overrides | `frontend/src/theme.ts` | Button, Card, Tabs, TextField, Chip, Dialog |
