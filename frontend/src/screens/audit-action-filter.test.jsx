import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 임퍼소네이션 화면의 '감사 로그에서 보기' 가 실제로 그 작업만 걸러 준다.
 *
 * 그 버튼은 `#/audit?action=impersonation.start` 로 보낸다. 감사 화면의 `filters` 에는
 * `action` 필터가 이미 있어 첫 진입(parseView)은 정상 동작하지만, `config.onQuery` 는
 * object_type/object_id/user_id/result 네 키만 읽고 `action` 은 읽지 않는다 —
 * audit-result-filter.test.jsx의 F7과 같은 결함이다: 이미 감사 화면을 열어 둔 채(같은
 * 라우트라 리마운트되지 않는다) 다시 이 링크를 타면 onQuery만이 새 값을 필터에 넣는
 * 유일한 통로인데, 거기서 `action` 조건이 조용히 사라진다 — 열린 화면은 감사 로그
 * 전체인데 사용자는 '임퍼소네이션 시작만 걸러 준 화면'을 보고 있다고 믿는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "auditor", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { REGISTRY } from "./registry.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderAudit() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/me/views")) return Promise.resolve({ items: [] });
    return Promise.resolve({ items: [], total: 0, page: 1, page_size: 100 });
  });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={REGISTRY.audit} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function auditCalls() {
  return apiMock.mock.calls.map((c) => c[0]).filter((p) => p.startsWith("/api/admin/audit"));
}

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "#/audit";
});
afterEach(() => { window.location.hash = ""; });

describe("감사 로그의 작업(action) 필터 딥링크", () => {
  it("임퍼소네이션의 '감사 로그에서 보기' 가 가리키는 주소에 action 조건이 들어 있다", () => {
    const action = REGISTRY.impersonation.headerActions.find((a) => a.label === "감사 로그에서 보기");
    expect(action, "'감사 로그에서 보기' 헤더 액션이 없다").toBeTruthy();
    expect(action.navigate()).toBe("#/audit?action=impersonation.start");
  });

  it("이미 감사 화면을 열어 둔 채 다시 그 딥링크로 들어와도 action 이 필터에 실린다", () => {
    // 딥링크가 필터가 되는 두 갈래 중, 라우트가 그대로라 리마운트되지 않는 재진입 경로 —
    // audit-result-filter.test.jsx와 동일한 이유로 onQuery가 실제로 값을 채우는지 직접 확인한다.
    const intent = REGISTRY.audit.onQuery({ action: "impersonation.start" });
    expect(intent && intent.open).toBe("filter");
    expect(intent.values.action).toBe("impersonation.start");
  });

  it("그 딥링크로 새로 들어가도 서버 조회에 action 조건이 실린다", async () => {
    window.location.hash = "#/audit?action=impersonation.start";
    renderAudit();

    await waitFor(() => expect(auditCalls().length).toBeGreaterThan(0));
    for (const url of auditCalls()) {
      expect(url).toContain("action=impersonation.start");
    }
  });
});
