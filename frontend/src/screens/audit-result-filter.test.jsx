import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 감사 이상징후의 '실패만 보기' 가 실제로 실패만 보여 준다 (F7).
 *
 * 그 버튼은 `#/audit?user_id=…&result=failure` 로 보낸다. 그런데 감사 화면에는 `result`
 * 필터가 아예 없어서 `parseView`(아는 키만 읽는다)와 `onQuery`(딥링크 값을 필터로 소비한다)
 * 양쪽에서 그 조건이 조용히 버려졌다 — 열린 화면은 **그 사람의 로그 전체**인데, 사용자는
 * '실패만 걸러 준 화면'을 보고 있다고 믿는다. 잘못된 안심이 아무것도 안 거른 것보다 나쁘다.
 *
 * 서버는 이 조건을 이미 받는다(app/audit/router.py `list_audit_logs(result=…)`, 목록과 CSV
 * 내보내기가 같은 `_filtered_stmt` 를 쓴다). 그래서 화면에 필터를 만들어 실제로 보낸다.
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

describe("감사 로그의 결과 필터", () => {
  it("이상징후의 '실패만 보기' 가 가리키는 주소에 result 조건이 들어 있다", () => {
    const action = REGISTRY["audit-anomalies"].actions.find((a) => a.label === "실패만 보기");
    expect(action, "'실패만 보기' 액션이 없다").toBeTruthy();
    expect(action.navigate({ kind: "failure_burst", actor_id: "u-9" })).toContain("result=failure");
  });

  it("그 딥링크로 들어가면 서버 조회에도 result=failure 가 실린다", async () => {
    window.location.hash = "#/audit?user_id=u-9&result=failure";
    renderAudit();

    await waitFor(() => expect(auditCalls().length).toBeGreaterThan(0));
    // 조건을 반만 적용하면(행위자만) 그 사람의 로그 전체가 열린다 — 둘 다 실려야 한다.
    for (const url of auditCalls()) {
      expect(url).toContain("user_id=u-9");
      expect(url).toContain("result=failure");
    }
  });

  it("이미 감사 화면을 열어 둔 채 다시 딥링크로 들어와도 result 가 필터에 실린다", () => {
    /* 딥링크가 필터가 되는 길은 **두 갈래**다.
     *   · 첫 진입: `parseView` 가 주소를 읽어 초기 필터로 삼는다(config.filters 의 키만).
     *   · 이미 그 화면에 있는 채로 다시 링크를 탈 때: 라우트가 그대로라 다시 마운트되지 않는다 —
     *     그때는 `config.onQuery` 가 새 값을 필터에 넣는 유일한 통로다(DataScreen 의
     *     `[config.key, location.search]` 효과). 이상 징후 목록에서 사람을 바꿔 가며
     *     '실패만 보기'를 연달아 누르는 것이 정확히 그 경로다.
     * 둘 중 하나만 고치면 나머지 한 경로에서 조건이 다시 조용히 사라진다. */
    const intent = REGISTRY.audit.onQuery({ user_id: "u-9", result: "failure" });
    expect(intent && intent.open).toBe("filter");
    expect(intent.values.result).toBe("failure");
    expect(intent.values.user_id).toBe("u-9");
  });

  it("화면에서도 결과로 좁힐 수 있다(딥링크로만 되는 숨은 조건이 아니다)", async () => {
    renderAudit();
    expect(await screen.findByLabelText(/결과/)).toBeInTheDocument();
  });
});
