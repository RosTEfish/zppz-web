import { api } from "../api/v1";
import { queryKeys } from "../api/queryKeys";
import { useApiResource } from "../components/PagePrimitives";
import { useConfig } from "../contexts/ConfigContext";
import { resolveBackgrounds, type ResolvedBackgrounds } from "../utils/backgroundAssets";

export function useEventBackgrounds(): ResolvedBackgrounds & { loading: boolean } {
  const { event } = useConfig();
  const { data, loading } = useApiResource(queryKeys.backgrounds, () => api.backgrounds(), true, {
    shouldRetryOnError: false,
    revalidateOnFocus: false,
  });
  return { ...resolveBackgrounds(data, event), loading };
}
