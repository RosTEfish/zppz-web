import { createContext, type ReactNode, useCallback, useContext, useMemo } from "react";
import useSWR from "swr";
import { api, UserRead } from "../api/v1";
import { queryKeys } from "../api/queryKeys";
import type { Identity } from "../identity";

interface AuthContextType {
  user: UserRead | null;
  isLoggedIn: boolean;
  isAdmin: boolean;
  isOwner: boolean;
  isPoolEditor: boolean;
  loading: boolean;
  login: (id: string, password: string) => Promise<{ user: UserRead }>;
  logout: () => Promise<void>;
  register: (id: string, qq: string, password: string, identity?: string) => Promise<{ user: UserRead }>;
  updateProfile: (displayName: string, identity: Identity) => Promise<{ user: UserRead }>;
  changePassword: (oldPassword: string, newPassword: string, confirmPassword?: string) => Promise<unknown>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { data: bootstrap, isLoading: loading, mutate } = useSWR(queryKeys.bootstrap, api.bootstrap);
  const user = bootstrap?.user ?? null;

  const login = useCallback(async (id: string, password: string) => {
    const data = await api.login(id, password);
    await mutate((current) => current ? { ...current, user: data.user } : current, { revalidate: !bootstrap });
    return data;
  }, [bootstrap, mutate]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      await mutate((current) => current ? { ...current, user: null } : current, { revalidate: false });
    }
  }, [mutate]);

  const register = useCallback(async (id: string, qq: string, password: string, identity = "audience") => {
    const data = await api.register(id, qq, password, identity);
    await mutate((current) => current ? { ...current, user: data.user } : current, { revalidate: !bootstrap });
    return data;
  }, [bootstrap, mutate]);

  const changePassword = useCallback(async (oldPassword: string, newPassword: string, confirmPassword?: string) => {
    if (confirmPassword !== undefined && newPassword !== confirmPassword) {
      throw new Error("两次输入的新密码不一致");
    }
    return api.changePassword(oldPassword, newPassword);
  }, []);

  const updateProfile = useCallback(async (displayName: string, identity: Identity) => {
    const data = await api.updateProfile(displayName, identity);
    await mutate((current) => current ? { ...current, user: data.user } : current, { revalidate: !bootstrap });
    return data;
  }, [bootstrap, mutate]);

  const value = useMemo(
    () => ({
      user,
      isLoggedIn: Boolean(user),
      isAdmin: Boolean(user?.is_admin),
      isOwner: Boolean(user?.is_owner),
      isPoolEditor: Boolean(user?.is_pool_editor),
      loading,
      login,
      logout,
      register,
      updateProfile,
      changePassword,
    }),
    [changePassword, loading, login, logout, register, updateProfile, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
