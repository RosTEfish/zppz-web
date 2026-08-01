import { type Dispatch, type ReactNode, type SetStateAction, useCallback } from "react";
import { Alert, Box, CircularProgress, Paper, Stack, Typography } from "@mui/material";
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


export function ResourceState({ loading, error, empty }: { loading: boolean; error: string; empty?: string }) {
  if (loading) return <LoadingBlock />;
  if (error) return <Alert severity="error">{error}</Alert>;
  if (empty) {
    return (
      <Paper variant="outlined" sx={{ py: 7, px: 2, textAlign: "center" }}>
        <Typography color="text.secondary">{empty}</Typography>
      </Paper>
    );
  }
  return null;
}
