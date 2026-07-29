import React, { createContext, useContext } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, setCsrf } from "../lib/api.js";

/* 인증·신원 상태. /api/me로 사용자·CSRF 토큰을 받아 앱 전역에 제공한다. 401이면 로그인
 * 안내 상태가 된다(권한 판단의 근거는 서버 — 프런트는 표시만). */
const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const q = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const data = await api("/api/me");
      setCsrf(data.csrf_token);
      return data.user;
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  return <AuthCtx.Provider value={q}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) { throw new Error("useAuth must be used within AuthProvider"); }
  return ctx;
}
