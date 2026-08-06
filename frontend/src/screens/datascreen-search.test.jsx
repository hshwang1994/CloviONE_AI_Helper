/* 검색창 타이핑이 **화면 전체를 다시 그리지 않는다** (PF4).
 *
 * `DataScreen` 은 관리자 40화면이 공유하는 1,000줄짜리 컴포넌트다. 타이핑 중인 값이 그
 * 컴포넌트에 살면 **글자 하나마다** 표 100행·필터 일곱 개·상세 드로어가 전부 다시 실행된다.
 *
 * 이 테스트는 "메모를 붙였다" 를 보지 않는다. **행 렌더 함수가 몇 번 불렸는지**를 센다 —
 * 그게 사용자가 겪는 층(입력 지연)에 실제로 대응하는 값이다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

let renderCount = 0;

const CONFIG = {
  key: "probe",
  title: "검사 화면",
  endpoint: "/api/admin/probe",
  searchable: true,
  searchPlaceholder: "이름 검색",
  paginated: true,
  columns: [
    { key: "name", label: "이름", render: (row) => { renderCount += 1; return row.name; } },
  ],
  detailFields: [],
};

const ITEMS = Array.from({ length: 20 }, (_, i) => ({ id: `r${i}`, name: `행 ${i}` }));

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter><DataScreen config={CONFIG} /></MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  renderCount = 0;
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: ITEMS, page: 1, page_size: 20, total: 20 });
});

describe("관리자 목록 검색", () => {
  it("글자를 쳐도 표가 다시 그려지지 않는다 (디바운스가 끝나기 전까지)", async () => {
    renderScreen();
    await screen.findByText("행 0");

    const before = renderCount;
    const input = screen.getByRole("searchbox", { name: "이름 검색" });
    for (const ch of ["가", "나", "다", "라", "마", "바", "사", "아"]) {
      fireEvent.change(input, { target: { value: input.value + ch } });
    }

    // 여덟 글자를 쳤는데 행 렌더가 한 번도 더 일어나면 안 된다.
    expect(renderCount).toBe(before);
  });

  it("입력한 값은 그대로 보이고, 잠시 뒤 서버 질의로 확정된다", async () => {
    renderScreen();
    await screen.findByText("행 0");
    apiMock.mockClear();

    const input = screen.getByRole("searchbox", { name: "이름 검색" });
    fireEvent.change(input, { target: { value: "회의" } });
    expect(input.value).toBe("회의");   // 타이핑은 즉시 보인다

    await waitFor(
      () => expect(apiMock.mock.calls.some(([path]) => String(path).includes("q=%ED%9A%8C%EC%9D%98")
                                                || String(path).includes("q=회의"))).toBe(true),
      { timeout: 2000 },
    );
  });
});
