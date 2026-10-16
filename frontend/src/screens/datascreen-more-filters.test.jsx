import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Routes, Route } from "react-router-dom";

/* 감사 로그의 「추가 필터」(D-596) — 실제 `REGISTRY.audit` 를 꽂는다.
 *
 * 필터가 여덟 칸이라 1366 에서 세 줄로 접혔다. 정확한 값을 붙여넣는 세 축(대상 ID · 작업 · 문의 번호)은 주소로 오거나
 * 상세에서 옮겨 적는 값이라 첫 줄에 늘 설 이유가 없다 — 접는다. 다만 그 칸에 조건이 걸려 있으면(상세의 「감사 로그에서
 * 보기」 딥링크) 접힌 칸에 숨기지 않는다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }) }));

import { REGISTRY } from "./registry.js";
import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const url = String(path);
    if (url.startsWith("/api/admin/audit")) {
      return Promise.resolve({ items: [{ id: "1", action: "user.login", result: "success" }], total: 1 });
    }
    return Promise.resolve({ items: [], total: 0 });
  });
});

afterEach(() => { window.location.hash = ""; });

function renderAudit() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <HashRouter>
              <Routes><Route path="/audit" element={<DataScreen config={REGISTRY.audit} />} /></Routes>
            </HashRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const MORE = ["대상 ID", "작업(정확히, 예: user.update)", "문의 번호(요청 ID)"];
const MAIN = ["대상", "표시 범위", "결과"];

describe("감사 로그 — 추가 필터 (D-596)", () => {
  it("정확한 값을 붙여넣는 세 칸은 접혀 있고, 「추가 필터」가 연다", async () => {
    window.location.hash = "#/audit";
    const user = userEvent.setup();
    renderAudit();
    const toggle = await screen.findByRole("button", { name: "추가 필터" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    for (const label of MAIN) expect(screen.getByLabelText(label)).toBeInTheDocument();
    for (const label of MORE) expect(screen.queryByLabelText(label)).toBeNull();

    await user.click(toggle);
    const row = document.querySelector("[data-filter-more]");
    expect(row).not.toBeNull();
    for (const label of MORE) expect(within(row).getByLabelText(label)).toBeInTheDocument();
  });

  it("딥링크가 접힌 칸에 값을 걸면 처음부터 펼치고 값이 보인다 — 칩과 질의에도 그대로 실린다", async () => {
    window.location.hash = "#/audit?object_type=approval&object_id=a-1";
    renderAudit();
    const toggle = await screen.findByRole("button", { name: "추가 필터 1" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(within(document.querySelector("[data-filter-more]")).getByLabelText("대상 ID")).toHaveValue("a-1");
    await waitFor(() => expect(apiMock.mock.calls.some(([u]) => String(u).includes("object_id=a-1"))).toBe(true));
    expect([...document.querySelectorAll("[data-condition-chip]")].some((c) => c.textContent.includes("a-1"))).toBe(true);
  });
});
