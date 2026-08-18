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

/* 소비처가 실제로 이 계층을 타는가 (지시 19).
 *
 * 모듈만 만들고 화면이 각자 `window.location.href = "/login"` 을 계속하면 아무것도 안 고쳐진
 * 것이다 — 실제로 그 상태로 한동안 있었다(감사에서 발견). 소스에 그 패턴이 다시 들어오지
 * 못하게 못박는다. */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) { walk(full, out); continue; }
    if (/\.(js|jsx)$/.test(name) && !/\.test\.(js|jsx)$/.test(name)) out.push(full);
  }
  return out;
}

describe("401 이동은 공통 계층만 한다", () => {
  it("화면 코드에 맨 '/login' 이동이 남아 있지 않다 (로그아웃 제외)", () => {
    const root = join(process.cwd(), "src");
    const offenders = [];
    for (const file of walk(root)) {
      const text = readFileSync(file, "utf8");
      if (!/location\.href\s*=\s*"\/login"/.test(text)) continue;
      // 로그아웃은 **의도적으로** 되돌아갈 곳을 안 싣는다(app/UserMenu.jsx 주석 참고) —
      // 스스로 나간 사람을 방금 있던 화면으로 다시 데려가는 것은 의도와 반대다.
      // 경로 구분자는 OS 마다 다르다 — 경로에 쓰이지 않는 글자를 전부 "/" 로 바꿔 통일한다.
      const tail = file.replace(/[^A-Za-z0-9_.-]/g, "/").split("/").filter(Boolean).slice(-2).join("/");
      if (tail === "app/UserMenu.jsx" || tail === "lib/sessionRedirect.js") continue;
      offenders.push(file.replace(root, "src"));
    }
    expect(offenders, "세션 만료 이동은 redirectToLogin() 을 쓴다").toEqual([]);
  });
});
