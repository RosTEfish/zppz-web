import { type DependencyList, type Dispatch, type ReactNode, type SetStateAction, useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, CircularProgress, Paper, Stack, Typography } from "@mui/material";
import type { LucideIcon } from "lucide-react";


export type Resource<T> = {
  data: T | null;
  loading: boolean;
  error: string;
  reload: () => Promise<T | null>;
  setData: Dispatch<SetStateAction<T | null>>;
  updateData: (updater: (current: T) => T) => void;
};


export function useResource<T>(loader: (signal: AbortSignal) => Promise<T>, dependencies: DependencyList, enabled = true): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestRef = useRef<{ id: number; controller: AbortController } | null>(null);
  const requestSequenceRef = useRef(0);
  const reload = useCallback(async () => {
    requestRef.current?.controller.abort();
    const request = { id: ++requestSequenceRef.current, controller: new AbortController() };
    requestRef.current = request;
    setLoading(true);
    setError("");
    try {
      const result = await loader(request.controller.signal);
      if (requestRef.current?.id !== request.id) return null;
      setData(result);
      return result;
    } catch (err) {
      if (request.controller.signal.aborted || requestRef.current?.id !== request.id) return null;
      setError(err instanceof Error ? err.message : "加载失败");
      return null;
    } finally {
      if (requestRef.current?.id === request.id) setLoading(false);
    }
  }, dependencies);
  useEffect(() => {
    if (!enabled) {
      requestRef.current?.controller.abort();
      requestRef.current = null;
      setLoading(false);
      setError("");
      return;
    }
    void reload();
    return () => {
      requestRef.current?.controller.abort();
      requestRef.current = null;
    };
  }, [enabled, reload]);
  const updateData = useCallback((updater: (current: T) => T) => {
    setData((current) => current === null ? current : updater(current));
  }, []);
  return { data, loading, error, reload, setData, updateData };
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
