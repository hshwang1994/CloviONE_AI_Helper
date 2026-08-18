import React, { createContext, useContext, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, setCsrf } from "../lib/api.js";
import { redirectToLogin } from "../lib/sessionRedirect.js";
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
  /* 세션이 정말 끊겼으면 로그인 화면으로 보낸다 (지시 19).
   *
   * 위 `onUnauthorized` 가 `["me"]` 를 다시 묻고, 그 재질의까지 401 이면 이제 확정이다 —
   * 예전에는 여기서 셸만 `minimal` 로 축소해서, 사이드바가 사라진 화면에 직전 데이터가
   * 그대로 남아 "로그인이 풀렸다"인지 "화면이 고장났다"인지 알 수 없었다.
   *
   * 401 만 본다. 네트워크 단절(`kind === "network"`)이나 5xx 는 로그아웃이 아니다 — 그
   * 경우 셸은 지금처럼 오류 상태로 남고, 사용자가 다시 시도할 수 있다.
   *
   * ⚠️ 여기서 `queryClient.clear()` 를 부르지 않는다. `["me"]` 까지 지워지면 이 쿼리가 곧장
   * 다시 뜨고 → 401 → 이 효과 → clear → ... 로 되돌아온다(실제로 재현했다). 남은 데이터는
   * 이동이 처리하고, 이동이 막힌 경우(이미 로그인 화면)에는 셸의 `minimal` 이 화면을
   * 축소해 그대로 서 있는 것처럼 보이지 않게 한다. */
  const status = q.error && q.error.status;
  useEffect(() => {
    if (!q.isError || status !== 401) return;
    redirectToLogin();
  }, [q.isError, status]);

  return <AuthCtx.Provider value={q}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) { throw new Error("useAuth must be used within AuthProvider"); }
  return ctx;
}
