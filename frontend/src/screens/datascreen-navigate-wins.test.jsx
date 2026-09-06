import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Routes, Route } from "react-router-dom";

/* 상세에서 **다른 화면으로 나가는 일이, 이 화면이 자기 주소를 되쓰는 일을 이긴다** (audit-02).
 *
 * `hasIdRoute` 화면(감사 로그)은 상세가 열리고 닫힐 때마다 주소를 `/audit/<id>` ↔ `/audit`
 * 로 맞춘다. 그런데 「관련 항목 보기」는 `setSel(null)` 을 하고 해시를 목적지로 바꾼다 —
 * 해시 대입은 그 자리에서 주소를 바꾸지만 `hashchange` 는 다음 차례에 온다. 그 사이 React 가
 * sel 변화를 흘려 동기화 효과를 깨웠고, 효과는 **이미 목적지의 것인 질의**를 들고 경로만
 * 이 화면으로 되돌려 놨다. 그래서 이동은 늘 `#/audit` 으로 튕겼고, 이어서 `onQuery` 청소가
 * 남의 키(`id`)를 지워 걸어 둔 필터까지 사라졌다(실브라우저 실측: 최종 주소 `#/audit`).
 *
 * MemoryRouter 로는 이 결함이 안 보인다 — 되돌리는 쪽이 `window.location.hash` 를 건드리지
 * 않기 때문이다. 그래서 여기서는 **실제 HashRouter** 를 쓴다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AUDIT = {
  key: "audit", area: "감사", title: "감사 로그", endpoint: "/api/admin/audit",
  hasIdRoute: true,
  columns: [{ key: "action", label: "동작", identifier: true }],
  filters: [{ key: "object_type", label: "대상", type: "select", options: [{ value: "user", label: "사용자" }] }],
  actions: [
    { label: "관련 항목 보기", navigate: (r) => "#/users?id=" + r.object_id },
  ],
  // 실제 감사 화면과 같은 딥링크 소비 — 되돌아온 주소에서 남의 키를 지우는 그 효과다.
  onQuery: (p) => (p.object_type ? { open: "filter", values: { object_type: p.object_type } } : null),
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
                <Route path="/users" element={<div>사용자 화면</div>} />
              </Routes>
            </HashRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

describe("hasIdRoute 화면의 이동 액션", () => {
  it("상세에서 누르면 목적지에 도착한다 — 이 화면으로 되돌아오지 않는다", async () => {
    window.location.hash = "#/audit?object_type=user";
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("user.update");

    await user.click(screen.getByText("user.update"));
    // 상세가 열리면 주소가 그 기록을 가리킨다(이 화면의 정상 동작 — 아래 이동이 이것을 이겨야 한다).
    await waitFor(() => expect(window.location.hash).toBe("#/audit/log-1?object_type=user"));

    await user.click(await screen.findByRole("button", { name: "관련 항목 보기" }));

    expect(await screen.findByText("사용자 화면")).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe("#/users?id=u-9"));
    // 예전 증상: 최종 주소가 `#/audit` 이고 걸어 둔 필터까지 사라졌다.
    expect(window.location.hash).not.toBe("#/audit");
  });

  it("반례 — 그냥 상세를 닫으면 이 화면이 자기 주소를 되쓴다(조건도 그대로 남는다)", async () => {
    window.location.hash = "#/audit?object_type=user";
    const user = userEvent.setup();
    renderApp();
    await screen.findByText("user.update");

    await user.click(screen.getByText("user.update"));
    await waitFor(() => expect(window.location.hash).toBe("#/audit/log-1?object_type=user"));

    await user.click(screen.getByRole("button", { name: "닫기" }));

    await waitFor(() => expect(window.location.hash).toBe("#/audit?object_type=user"));
  });
});
