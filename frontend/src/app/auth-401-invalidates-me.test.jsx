/* '세션 만료' 모드가 실제로 켜지는가 (셸 스코프 배선, 8단계 #3).
 *
 * `["me"]` 쿼리는 `retry:false` + 전역 `refetchOnWindowFocus:false` + `refetchInterval`
 * 없음이다 - 다른 API 호출이 401(세션 폐기·만료)을 맞아도 이 쿼리는 그 사실을 몰라, 마지막
 * 성공값을 계속 보여 준다. `App.jsx` 의 `minimal = auth.isError` 로 넘어가는 유일한 경로가
 * 실제로는 한 번도 안 켜졌다는 뜻이다. 여기서는 **실제 api.js + auth.jsx** 를 그대로 쓰고
 * `fetch` 만 흉내 내, 다른 API 호출의 401 이 `["me"]` 를 실제로 다시 부르는지 본다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider, useAuth } from "./auth.jsx";
import { api } from "../lib/api.js";

let sharedClient;
function wrapper({ children }) {
  sharedClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={sharedClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    headers: { get: () => null },
  };
}

describe("다른 API의 401이 세션 상태를 실제로 갱신한다", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("/api/me 가 아닌 호출이 401을 맞으면 ['me']가 다시 불려 세션 만료로 전환된다", async () => {
    let meCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (path) => {
      if (path === "/api/me") {
        meCalls += 1;
        if (meCalls === 1) {
          return jsonResponse(200, {
            user: { id: "u1", email: "a@b.c", role: "user" },
            features: {}, branding: {}, csrf_token: "t",
          });
        }
        return jsonResponse(401, { error: { message: "로그인이 필요합니다." } });
      }
      return jsonResponse(401, { error: { message: "로그인이 필요합니다." } });
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(meCalls).toBe(1);

    // 다른 화면이 흔히 하는 일 — 어떤 API 를 불렀는데 세션이 이미 죽어 401 이 온다.
    await expect(api("/api/my-tickets")).rejects.toMatchObject({ status: 401 });

    await waitFor(() => expect(meCalls).toBe(2), {
      timeout: 2000,
    });
    // `useAuth()` 훅 자체의 리렌더 타이밍보다, 실제 react-query 캐시 상태를 직접 본다 -
    // `App.jsx` 의 `minimal = auth.isError` 는 바로 이 캐시 상태에서 파생된다.
    await waitFor(() => {
      const state = sharedClient.getQueryState(["me"]);
      expect(state && state.status).toBe("error");
    }, { timeout: 2000 });
  });

  it("/api/me 자신의 401은 무한 재무효화 루프를 만들지 않는다 (회귀 - 힙 고갈로 워커가 죽었었다)", async () => {
    // `/api/me` 가 매번 401 이면: 무효화 → 재요청 → 401 → 무효화 → ... 가 될 수 있는 자리다.
    // api.js 는 `/api/me` 자신의 401 에는 무효화 핸들러를 안 부르므로 한 번만 실패해야 한다.
    let meCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (path) => {
      if (path === "/api/me") { meCalls += 1; }
      return jsonResponse(401, { error: { message: "로그인이 필요합니다." } });
    });

    renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      const state = sharedClient.getQueryState(["me"]);
      expect(state && state.status).toBe("error");
    }, { timeout: 2000 });

    // 잠시 더 기다려도 추가 호출이 없어야 한다(루프였다면 이 사이에 계속 늘었을 것이다).
    await new Promise((r) => setTimeout(r, 300));
    expect(meCalls, "무효화 루프로 /api/me 가 반복 호출됐다").toBe(1);
  });
});

/* 401 이 확정되면 로그인 화면으로 보낸다 (지시 19).
 *
 * 예전에는 확정된 뒤에도 아무도 보내지 않았다 — 셸만 `minimal` 로 축소되고 직전 데이터가
 * 화면에 남아 "로그인이 풀렸다"인지 "화면이 고장났다"인지 알 수 없었다. */
import { redirectToLogin, resetSessionRedirect } from "../lib/sessionRedirect.js";

vi.mock("../lib/sessionRedirect.js", async (orig) => {
  const real = await orig();
  return { ...real, redirectToLogin: vi.fn(() => true) };
});

describe("세션이 끊기면 로그인 화면으로 보낸다", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    redirectToLogin.mockClear();
    resetSessionRedirect();
  });

  it("/api/me 가 401 이면 로그인 화면으로 보낸다", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse(401, { error: { message: "로그인이 필요합니다." } }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    await waitFor(() => expect(redirectToLogin).toHaveBeenCalled());
  });

  it("네트워크가 끊긴 것은 로그아웃이 아니다 — 보내지 않는다", async () => {
    // 연결 자체가 안 되면 api.js 가 status 없는 network 오류를 던진다. 이때 로그인 화면으로
    // 보내면 사용자는 멀쩡한 세션으로 다시 로그인해야 하고, 하던 화면도 잃는다.
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => { throw new TypeError("failed to fetch"); });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(redirectToLogin).not.toHaveBeenCalled();
  });
});
