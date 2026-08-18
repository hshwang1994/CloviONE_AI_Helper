import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

import { redirectToLogin, resetSessionRedirect } from "./sessionRedirect.js";

/* 세션 만료 시 로그인 화면으로 (지시 19).
 *
 * 예전에는 SPA 가 401 을 확정해도 **아무도 보내지 않았다** — 셸만 축소되고 직전 데이터가
 * 화면에 남았다. 서버 렌더 경로는 이미 `303 /login?next=<path>` 규약을 갖고 있었고
 * (app/main.py), SPA 는 그 규약을 쓰지 않았다.
 *
 * 여기서 지키는 것:
 *   1. 되돌아올 곳(`next`)을 싣는다 — 해시 라우트까지 그대로.
 *   2. 만료였음을 알린다(`expired=1`) — 로그인 화면이 문맥 있는 안내를 띄운다.
 *   3. 뒤로가기로 죽은 세션 화면에 돌아가지 않는다(`replace`).
 *   4. 한 번만 보낸다 — 이동 중 또 부르면 로그인 화면이 자기 자신으로 계속 튕긴다.
 *   5. 로그인 화면에서는 보내지 않는다.
 */

let replaced;

function stubLocation(pathname, hash = "", search = "") {
  replaced = [];
  const loc = { pathname, hash, search, replace: (u) => replaced.push(u) };
  vi.spyOn(window, "location", "get").mockReturnValue(loc);
}

beforeEach(() => {
  resetSessionRedirect();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("redirectToLogin", () => {
  it("현재 해시 라우트를 next 로 싣고 만료를 알린다", () => {
    stubLocation("/", "#/tickets/abc");
    expect(redirectToLogin()).toBe(true);
    expect(replaced).toHaveLength(1);

    const url = new URL(replaced[0], "https://example.test");
    expect(url.pathname).toBe("/login");
    expect(url.searchParams.get("next")).toBe("/#/tickets/abc");
    expect(url.searchParams.get("expired")).toBe("1");
  });

  it("쿼리 문자열도 함께 보존한다", () => {
    stubLocation("/", "#/users?q=kim", "?ref=mail");
    redirectToLogin();
    const url = new URL(replaced[0], "https://example.test");
    expect(url.searchParams.get("next")).toBe("/?ref=mail#/users?q=kim");
  });

  it("두 번째 호출은 아무 일도 하지 않는다 (튕김 방지)", () => {
    stubLocation("/", "#/me");
    expect(redirectToLogin()).toBe(true);
    expect(redirectToLogin()).toBe(false);
    expect(replaced).toHaveLength(1);
  });

  it("로그인 화면에서는 보내지 않는다", () => {
    stubLocation("/login", "");
    expect(redirectToLogin()).toBe(false);
    expect(replaced).toHaveLength(0);
  });
});
