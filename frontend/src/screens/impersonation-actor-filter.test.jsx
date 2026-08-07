import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 임퍼소네이션(대리 보기) 목록의 '이 관리자의 기록만' 이 실제로 그 관리자만 걸러 준다.
 *
 * 그 버튼은 `#/impersonation?actor_user_id=…` 로 보낸다. registry.js의 onQuery는 그 값을
 * filters 상태에 넣지만(open:'filter'), 이 화면의 `filters` 배열에는 'active' 뿐이고
 * actor_user_id/target_user_id 정의가 없었다 — DataScreen.buildUrl()은 config.filters에 있는
 * 키만 서버로 보내므로(serverFilterDefs), 그 값은 상태에만 남고 실제 요청에는 실리지 않는다.
 * 열린 화면은 **전체 임퍼소네이션 기록**인데, 사용자는 '이 관리자만 걸러 준 화면'을 보고
 * 있다고 믿는다 — audit-result-filter.test.jsx의 F7과 동일한 부류의 결함이다.
 *
 * 서버는 이 조건을 이미 받는다(app/impersonation/router.py list_sessions(actor_user_id=…,
 * target_user_id=…)). 그래서 화면에 필터를 만들어 실제로 보낸다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { REGISTRY } from "./registry.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderImpersonation() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/me/views")) return Promise.resolve({ items: [] });
    return Promise.resolve({ items: [], total: 0, page: 1, page_size: 20 });
  });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={REGISTRY.impersonation} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function impersonationCalls() {
  return apiMock.mock.calls.map((c) => c[0]).filter((p) => p.startsWith("/api/admin/impersonation/sessions"));
}

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "#/impersonation";
});
afterEach(() => { window.location.hash = ""; });

describe("임퍼소네이션의 관리자/대상 필터", () => {
  it("'이 관리자의 기록만' 이 가리키는 주소에 actor_user_id 조건이 들어 있다", () => {
    const action = REGISTRY.impersonation.actions.find((a) => a.label === "이 관리자의 기록만");
    expect(action, "'이 관리자의 기록만' 액션이 없다").toBeTruthy();
    expect(action.navigate({ actor_user_id: "admin-9" })).toContain("actor_user_id=admin-9");
  });

  it("그 딥링크로 들어가면 서버 조회에도 actor_user_id 가 실린다", async () => {
    window.location.hash = "#/impersonation?actor_user_id=admin-9";
    renderImpersonation();

    await waitFor(() => expect(impersonationCalls().length).toBeGreaterThan(0));
    for (const url of impersonationCalls()) {
      expect(url).toContain("actor_user_id=admin-9");
    }
  });

  it("이미 화면을 열어 둔 채 다시 딥링크로 들어와도 actor_user_id 가 필터에 실린다", () => {
    // 딥링크가 필터가 되는 두 갈래(첫 진입의 parseView / 재진입의 onQuery) 중 재진입 경로 —
    // audit-result-filter.test.jsx와 동일한 이유로 onQuery가 실제로 값을 채우는지 직접 확인한다.
    const intent = REGISTRY.impersonation.onQuery({ actor_user_id: "admin-9" });
    expect(intent && intent.open).toBe("filter");
    expect(intent.values.actor_user_id).toBe("admin-9");
  });

  it("화면에서도 관리자 ID로 좁힐 수 있다(딥링크로만 되는 숨은 조건이 아니다)", async () => {
    renderImpersonation();
    expect(await screen.findByLabelText(/관리자 ID/)).toBeInTheDocument();
  });
});
