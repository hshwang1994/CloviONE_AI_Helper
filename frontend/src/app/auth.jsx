import React, { createContext, useContext, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, setCsrf } from "../lib/api.js";
import { setBrand } from "./documentTitle.js";

/* 인증·신원 상태. /api/me로 사용자·CSRF 토큰을 받아 앱 전역에 제공한다. 401이면 로그인
 * 안내 상태가 된다(권한 판단의 근거는 서버 — 프런트는 표시만). */
const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  // `["me"]` 는 `retry:false` 라 한 번 성공하면 아무도 다시 안 부르는 한 그 값 그대로다.
  // 다른 API 가 401(세션 폐기·만료)을 맞아도 이 쿼리는 모른다 - 그래서 "세션 만료"
  // 화면(`App.jsx` 의 `minimal = auth.isError`)이 실제로는 한 번도 안 켜졌다. 그 401 을
  // api.js 가 여기로 알려 주면 `["me"]` 를 무효화해 다시 묻고, 진짜로 죽은 세션이면 이번엔
  // 그 요청도 401 이라 `isError` 가 켜진다.
  useEffect(() => {
    // `api.onUnauthorized` 가 없으면(예: 테스트가 api.js 를 부분적으로만 흉내 낸 목) 아무
    // 일도 안 한다 - 실제 api.js 는 항상 이 속성을 붙이므로 프로덕션 경로에는 영향이 없다.
    if (typeof api.onUnauthorized !== "function") return undefined;
    api.onUnauthorized(() => queryClient.invalidateQueries({ queryKey: ["me"] }));
    return () => api.onUnauthorized(null);
  }, [queryClient]);

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
