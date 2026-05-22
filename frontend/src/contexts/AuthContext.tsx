import React, { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, UserRead } from "../api/v1";

interface AuthContextType {
  user: UserRead | null;
  token: string;
  isLoggedIn: boolean;
  isAdmin: boolean;
  isPoolEditor: boolean;
  loading: boolean;
  login: (id: string, password: string) => Promise<{ user: UserRead }>;
  logout: () => Promise<void>;
  register: (id: string, qq: string, password: string, identity?: string) => Promise<{ user: UserRead }>;
  changePassword: (oldPassword: string, newPassword: string, confirmPassword?: string) => Promise<unknown>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRead | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const data = await api.me();
      setUser(data.user);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refreshUser().finally(() => setLoading(false));
  }, [refreshUser]);

  const login = useCallback(async (id: string, password: string) => {
    const data = await api.login(id, password);
    setUser(data.user);
    return data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const register = useCallback(async (id: string, qq: string, password: string, identity = "audience") => {
    const data = await api.register(id, qq, password, identity);
    setUser(data.user);
    return data;
  }, []);

  const changePassword = useCallback(async (oldPassword: string, newPassword: string, confirmPassword?: string) => {
    if (confirmPassword !== undefined && newPassword !== confirmPassword) {
      throw new Error("两次输入的新密码不一致");
    }
    return api.changePassword(oldPassword, newPassword);
  }, []);

  const value = useMemo(
    () => ({
      user,
      token: "",
      isLoggedIn: Boolean(user),
      isAdmin: Boolean(user?.is_admin),
      isPoolEditor: Boolean(user?.is_pool_editor),
      loading,
      login,
      logout,
      register,
      changePassword,
      refreshUser,
    }),
    [changePassword, loading, login, logout, refreshUser, register, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

