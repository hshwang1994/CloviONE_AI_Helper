import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* `/api/me` 의 값이 **실제로 화면까지 도착하는가** (X4 배선 / N5).
 *
 * 🔴 이 테스트가 없어서 놓친 것: `auth.jsx` 가 `data.user` 만 돌려주는데 `App.jsx` 는
 * `auth.data.features` 를 읽었다 — **항상 `undefined`** 였고 `navWithFeatures` 는
 * `if (!features) return nav` 로 통째로 no-op 이었다. 즉 "기능 플래그를 끄면 메뉴도
 * 사라진다"(X4)가 **단위 테스트만 초록이고 앱에서는 아무 일도 안 하고 있었다.**
 *
 * `navWithFeatures` 자체는 순수 함수라 잘 증명돼 있었다. 증명되지 않은 것은 **그 함수에
 * 값이 도달하는가** 였다. 그래서 여기서는 함수가 아니라 **배선**을 본다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));

import { AuthProvider, useAuth } from "./auth.jsx";
import { brand } from "./documentTitle.js";
import { USER_NAV, navWithFeatures } from "./navConfig.js";

function wrapper({ children }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

const ME = {
  user: { id: "u1", email: "a@b.c", display_name: "나", role: "admin" },
  features: { games_enabled: false },
  branding: { product_name: "우리회사포털" },
  csrf_token: "t",
};

describe("/api/me 배선", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockResolvedValue(ME);
  });

  it("features 가 auth.data 에 실제로 도착한다", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(
      result.current.data.features,
      "features 가 안 실려 오면 navWithFeatures 가 통째로 no-op 이 된다",
    ).toEqual({ games_enabled: false });
  });

  it("그 값으로 메뉴가 실제로 걸러진다", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());

    const before = USER_NAV.flatMap((g) => g.items || []).map((i) => i.to);
    const after = navWithFeatures(USER_NAV, result.current.data.features)
      .flatMap((g) => g.items || []).map((i) => i.to);
    expect(after.length, "끈 기능의 메뉴가 그대로 남아 있다 — 눌리고 404 를 뱉는다")
      .toBeLessThan(before.length);
  });

  it("사용자 필드는 그대로 남는다", async () => {
    /* `auth.data` 를 사용자 객체로 쓰는 호출부가 많다 — 배선을 잇느라 그걸 깨면
       역할 판정이 통째로 무너진다. */
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.data.role).toBe("admin");
    expect(result.current.data.email).toBe("a@b.c");
  });

  it("설정된 제품명이 브랜드로 쓰인다", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(brand(), "제품명을 바꿔도 로그인 화면만 바뀐다(N5)").toBe("우리회사포털");
  });
});
