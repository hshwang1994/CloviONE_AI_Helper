import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

/* 대리 보기 중에는 비밀번호 변경 화면으로 밀지 않는다 (users-07).
 *
 * 실측: `#/users` 에서 계정을 하나 만들고(갓 만든 계정은 기본값이
 * `must_change_password=true` 다) 그 사람을 대리 보기로 열면, 주소가
 * `http://…/change-password#/impersonation` 이 되면서 SPA 셸이 통째로 사라졌다. 그 페이지에는
 * 대리 보기 띠도 「대리 보기 종료」 단추도 없다(둘 다 AppShell 안에 있다) — 화면 안에서
 * 되돌아올 길이 「다른 계정으로 로그인」(=로그아웃)뿐이었다. 서버는 멀쩡했다:
 * `POST /api/admin/impersonation/stop` 을 직접 부르면 200 으로 정상 복귀한다.
 *
 * 서버는 이미 같은 판단을 해 뒀다 — `app/core/deps.py::get_current_user` 는 대리 보기 중에는
 * 대상의 `must_change_password` 로 막지 않는다("읽기만 가능하므로 위험이 없고, 막으면
 * 비밀번호를 못 바꾼 계정은 지원할 수 없다는 이상한 구멍이 생긴다").
 *
 * 반례로 함께 못박는 것: 대리 보기가 **아닌** 첫 로그인 계정은 예전 그대로 밀려야 한다.
 * 그 사람은 `/api/me` 말고는 거의 모든 API 가 403 이라, 안 밀면 화면마다 막다른 403 만 본다.
 */
import { shouldForcePasswordChange } from "./App.jsx";

describe("shouldForcePasswordChange — 비밀번호 변경 강제 이동의 조건", () => {
  it("대리 보기 중이면 대상이 첫 로그인 계정이어도 밀지 않는다", () => {
    expect(shouldForcePasswordChange({
      mustChange: true, impersonationKnown: true, impersonating: true,
    })).toBe(false);
  });

  it("반례 — 대리 보기가 아닌 첫 로그인 계정은 예전 그대로 민다", () => {
    expect(shouldForcePasswordChange({
      mustChange: true, impersonationKnown: true, impersonating: false,
    })).toBe(true);
  });

  it("대리 보기 여부를 아직 모르는 동안에는 밀지 않고 기다린다", () => {
    expect(shouldForcePasswordChange({
      mustChange: true, impersonationKnown: false, impersonating: false,
    })).toBe(false);
  });

  it("비밀번호를 바꿀 필요가 없으면 어떤 조합에서도 안 민다", () => {
    expect(shouldForcePasswordChange({
      mustChange: false, impersonationKnown: true, impersonating: false,
    })).toBe(false);
    expect(shouldForcePasswordChange({
      mustChange: false, impersonationKnown: true, impersonating: true,
    })).toBe(false);
  });
});

/* 위 판단이 **실제로 배선돼 있는가.** 함수만 옳고 화면이 안 부르면 아무것도 안 고쳐진 것이다. */
const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("./AppShell.jsx", () => ({
  AppShell: ({ children }) => <div data-testid="shell">{children}</div>,
  ShellErrorFallback: () => <div>shell error</div>,
}));
vi.mock("./AdminRoutes.jsx", () => ({ default: () => <div>admin</div> }));
vi.mock("./UserRoutes.jsx", () => ({ default: () => <div>user</div> }));
vi.mock("./LoginHandoff.jsx", () => ({ LoginHandoff: () => null }));
vi.mock("./theme-store.js", () => ({ applyBootTheme: () => {} }));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App.jsx";

let pushed;

function stubHref() {
  pushed = [];
  const real = window.location;
  vi.spyOn(window, "location", "get").mockReturnValue({
    get pathname() { return real.pathname; },
    get search() { return real.search; },
    get hash() { return real.hash; },
    set hash(v) { real.hash = v; },
    get href() { return real.href; },
    set href(v) { pushed.push(v); },
    replace: (u) => real.replace(u),
    assign: (u) => real.assign(u),
    toString: () => real.href,
  });
}

function meResponse({ mustChange }) {
  return {
    user: { id: "u1", role: "user", display_name: "첫로그인대상", must_change_password: mustChange },
    features: {}, branding: { product_name: "ClovirAssist" }, csrf_token: "t",
  };
}

function mountApp({ mustChange, impersonating }) {
  apiMock.mockImplementation((path) => {
    if (String(path).startsWith("/api/me")) return Promise.resolve(meResponse({ mustChange }));
    if (String(path).startsWith("/api/admin/impersonation/state")) {
      return Promise.resolve({ impersonating, target_name: "첫로그인대상", actor_name: "UI QA" });
    }
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  // main.jsx 가 앱 바깥에 두는 provider — App 자신은 AuthProvider 부터 시작한다.
  return render(<QueryClientProvider client={qc}><App /></QueryClientProvider>);
}

beforeEach(() => { apiMock.mockReset(); stubHref(); });
afterEach(() => { vi.restoreAllMocks(); });

describe("App — 대리 보기 중에는 비밀번호 변경 화면으로 밀지 않는다", () => {
  it("대리 보기 중이면 /change-password 로 이동하지 않는다", async () => {
    mountApp({ mustChange: true, impersonating: true });
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/impersonation/state"));
    // 이동 판단은 두 응답이 다 온 뒤에 난다 — 그 뒤에도 한 번도 안 밀렸는지 본다.
    await new Promise((r) => setTimeout(r, 60));
    expect(pushed).toEqual([]);
  });

  it("반례 — 대리 보기가 아니면 예전 그대로 /change-password 로 민다", async () => {
    mountApp({ mustChange: true, impersonating: false });
    await waitFor(() => expect(pushed).toContain("/change-password"));
  });
});
