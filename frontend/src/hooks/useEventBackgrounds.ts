import { useMemo } from "react";
import { api } from "../api/v1";
import { queryKeys } from "../api/queryKeys";
import { useApiResource } from "../components/PagePrimitives";
import { useConfig } from "../contexts/ConfigContext";
import { resolveBackgrounds, type ResolvedBackgrounds } from "../utils/backgroundAssets";

export function useEventBackgrounds(): ResolvedBackgrounds & { loading: boolean } {
  const { event, backgrounds: bootBackgrounds, loading: configLoading } = useConfig();
  const hasBootstrapAssets = bootBackgrounds.length > 0;
  const { data, loading } = useApiResource(queryKeys.backgrounds, () => api.backgrounds(), true, {
    fallbackData: hasBootstrapAssets ? bootBackgrounds : undefined,
    // Bootstrap already carried the list — skip an extra round-trip on first paint.
    revalidateIfStale: !hasBootstrapAssets,
    revalidateOnMount: !hasBootstrapAssets,
    shouldRetryOnError: false,
    revalidateOnFocus: false,
  });
  const resolved = useMemo(
    () => resolveBackgrounds(data ?? bootBackgrounds, event),
    [bootBackgrounds, data, event],
  );
  return { ...resolved, loading: configLoading || (loading && !hasBootstrapAssets && !data) };
}
