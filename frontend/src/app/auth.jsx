import React, { createContext, useContext } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, setCsrf } from "../lib/api.js";
import { setBrand } from "./documentTitle.js";

/* 인증·신원 상태. /api/me로 사용자·CSRF 토큰을 받아 앱 전역에 제공한다. 401이면 로그인
 * 안내 상태가 된다(권한 판단의 근거는 서버 — 프런트는 표시만). */
const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const q = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const data = await api("/api/me");
      setCsrf(data.csrf_token);
      /* 🔴 예전에는 `data.user` 만 돌려줬는데 `App.jsx` 는 `auth.data.features` 를 읽는다 —
         **항상 undefined 였고 `navWithFeatures` 는 통째로 no-op** 이었다. 즉 X4(기능 플래그가
         화면도 끈다)가 단위 테스트만 초록이고 앱에서는 아무 일도 안 하고 있었다.
         `features`/`branding` 을 사용자 객체에 **펼쳐 담는다** — 기존 `auth.data.role` 같은
         호출부를 그대로 두면서 배선을 잇는 가장 좁은 변경이다. */
      setBrand(data.branding && data.branding.product_name);
      return { ...data.user, features: data.features, branding: data.branding };
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
