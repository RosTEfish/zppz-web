import { createContext, type ReactNode, useContext } from "react";
import useSWR, { type KeyedMutator } from "swr";
import { api, type BootstrapRead } from "../api/v1";
import { queryKeys } from "../api/queryKeys";

interface BootstrapContextValue {
  data: BootstrapRead | undefined;
  isLoading: boolean;
  mutate: KeyedMutator<BootstrapRead>;
}

const BootstrapContext = createContext<BootstrapContextValue | null>(null);

export function BootstrapProvider({ children }: { children: ReactNode }) {
  const { data, isLoading, mutate } = useSWR(queryKeys.bootstrap, api.bootstrap, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
    dedupingInterval: 5000,
  });
  return (
    <BootstrapContext.Provider value={{ data, isLoading, mutate }}>
      {children}
    </BootstrapContext.Provider>
  );
}

export function useBootstrap() {
  const ctx = useContext(BootstrapContext);
  if (!ctx) throw new Error("useBootstrap must be used within BootstrapProvider");
  return ctx;
}
