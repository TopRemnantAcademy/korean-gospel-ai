"use client";

// 全局登录态：统一管理 token 的读取/写入/登出，避免各页散落 localStorage 且依赖整页刷新。
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";

type AuthState = {
  token: string | null;
  isAuthed: boolean;
  email: string | null;
  login: (token: string) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

const TOKEN_KEY = "token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    setToken(localStorage.getItem(TOKEN_KEY));
  }, []);

  // token 变化时（登录 / 登出）拉取或清空当前用户信息
  useEffect(() => {
    let cancelled = false;
    if (token) {
      api
        .me()
        .then((m) => {
          if (!cancelled) setEmail(m.email);
        })
        .catch(() => {
          if (!cancelled) setEmail(null);
        });
    } else {
      setEmail(null);
    }
    return () => {
      cancelled = true;
    };
  }, [token]);

  function login(t: string) {
    localStorage.setItem(TOKEN_KEY, t);
    setToken(t);
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
  }

  return (
    <AuthContext.Provider value={{ token, isAuthed: !!token, email, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return ctx;
}
