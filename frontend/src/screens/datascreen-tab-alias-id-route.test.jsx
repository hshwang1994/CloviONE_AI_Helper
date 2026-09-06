import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Routes, Route } from "react-router-dom";

/* 상세 주소 동기화는 **화면 키가 아니라 올라와 있는 경로**를 본다 (R7-06).
 *
 * audit-02 가 넣은 문지기는 옳다 — 이동이 시작된 뒤에는 이 화면이 주소를 되쓰면 안 된다.
 * 그런데 그 문지기가 「이 화면의 주소」를 `"#/" + config.key` 로 계산했다. 감사 로그는 탭
 * 그릇 안에 있고, 그릇은 탭마다 옛 경로를 하나씩 더 등록한다(`AdminRoutes.jsx`) — 그래서
 * `#/audit-anomalies` 에서 「감사 로그」 탭을 누르면 `?tab=audit` 만 바뀌고 경로는 그 별칭
 * 그대로다. 그 순간 `here`("#/audit-anomalies") 와 키로 만든 이름("#/audit") 이 갈라져
 * 효과가 통째로 빠져나갔다: 행을 눌러 상세를 열어도 주소가 `/audit/:id` 가 되지 않아
 * 링크로 줄 수도 없고 F5 로 되찾을 수도 없었다.
 *
 * 여기서 고정하는 것 둘:
 *   1) 별칭 경로에서 연 상세도 주소를 얻는다(그릇이 쓴 `?tab=` 은 그대로 남는다).
 *   2) 반례 — 그래도 **이동은 여전히 이긴다**(audit-02 는 안 무너진다).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "actor-1", management: { kind: "global" } } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AUDIT = {
  key: "audit", area: "감사", title: "감사 로그", endpoint: "/api/admin/audit",
  hasIdRoute: true,
  columns: [{ key: "action", label: "동작", identifier: true }],
  actions: [{ label: "관련 항목 보기", navigate: (r) => "#/users?id=" + r.object_id }],
};

const ROW = { id: "log-1", action: "user.update", object_type: "user", object_id: "u-9" };

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (String(path).startsWith("/api/admin/audit/log-1")) return Promise.resolve(ROW);
    return Promise.resolve({ items: [ROW], total: 1 });
  });
});

afterEach(() => { window.location.hash = ""; });

/* 탭 그릇이 만드는 배선을 그대로 흉내 낸다 — 같은 목록 화면이 정규 경로와 탭 키 별칭
   **둘 다**에 올라 있고, 상세 :id 라우트는 정규 경로 쪽에만 있다. */
function renderApp() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <HashRouter>
              <Routes>
                <Route path="/audit" element={<DataScreen config={AUDIT} />} />
                <Route path="/audit/:id" element={<DataScreen config={AUDIT} />} />
                <Route path="/audit-anomalies" element={<DataScreen config={AUDIT} />} />
                <Route path="/users" element={<div>사용자 화면</div>} />
              </Routes>
            </HashRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

describe("탭 별칭 경로에서 연 상세 (R7-06)", () => {
  it("별칭 경로에서 행을 눌러도 주소가 그 기록을 가리킨다 — 그릇의 ?tab= 도 남는다", async () => {
    window.location.hash = "#/audit-anomalies?tab=audit";
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("user.update");

    await user.click(screen.getByText("user.update"));

    await waitFor(() => expect(window.location.hash).toBe("#/audit/log-1?tab=audit"));
    // 예전 증상: 주소가 `#/audit-anomalies?tab=audit` 그대로라 상세를 링크로 줄 수 없었다.
    expect(window.location.hash).not.toBe("#/audit-anomalies?tab=audit");
  });

  it("반례 — 별칭 경로에서도 이동 액션이 주소 되쓰기를 이긴다 (audit-02)", async () => {
    window.location.hash = "#/audit-anomalies?tab=audit";
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("user.update");

    await user.click(screen.getByText("user.update"));
    await waitFor(() => expect(window.location.hash).toBe("#/audit/log-1?tab=audit"));

    await user.click(await screen.findByRole("button", { name: "관련 항목 보기" }));

    expect(await screen.findByText("사용자 화면")).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe("#/users?id=u-9"));
  });
});
