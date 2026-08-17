/* PA-RC-0038 — 공용 DataScreen의 빈 상태가 "필터 때문에 0건"과 "정말 0건"을 구분하는가.
 *
 * useQueryState는 config가 준 기본 필터값(f.value)을 주소에 쓰지 않는다(D-024) — 그래서
 * 주소만 보면 기본 필터가 걸린 화면도 "필터가 없는 화면"처럼 보였다. `/approvals`가
 * status=pending 기본값으로 열려 대기 0건일 때 "승인 요청이 없습니다"라는 무조건형
 * 문장을 내고 필터를 지울 수단조차 없었던 것이 이 결함의 실제 사례다.
 *
 * 이 파일은 실제 REGISTRY 화면(각자 auth/role/endpoint 목업이 필요하다)이 아니라
 * datascreen-search.test.jsx와 같은 방식으로 합성 config를 직접 DataScreen에 꽂아
 * 공유 컴포넌트의 분기 로직 자체를 검사한다 — 이래야 새 REGISTRY 화면이 생겨도
 * 이 계약이 자동으로 적용된다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

// /approvals의 실제 모양을 그대로 축소한 합성 config — 기본값 있는 select 필터 하나 +
// 온보딩형 emptyTitle/emptyHelp(둘 다 실제 approvals 설정에 있는 필드다).
const CONFIG_WITH_DEFAULT_FILTER = {
  key: "probe", title: "검사 화면", endpoint: "/api/admin/probe",
  paginated: true,
  emptyTitle: "검사 요청이 없습니다",
  emptyHelp: "검사 요청이 생기면 여기에 표시됩니다.",
  filters: [
    { key: "status", type: "select", label: "상태", value: "pending",
      options: [{ value: "pending", label: "대기" }, { value: "done", label: "완료" }] },
  ],
  columns: [{ key: "name", label: "이름" }],
  detailFields: [],
};

// 필터 자체가 없는 화면(대다수 REGISTRY 화면) — 회귀 방지용 대조군.
const CONFIG_NO_FILTER = {
  key: "probe2", title: "필터 없는 검사 화면", endpoint: "/api/admin/probe2",
  paginated: true,
  emptyTitle: "표시할 항목이 없습니다(검사용)",
  emptyHelp: "이 화면은 필터가 없습니다.",
  columns: [{ key: "name", label: "이름" }],
  detailFields: [],
};

function renderScreen(config) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter><DataScreen config={config} /></MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("DataScreen — 기본 필터가 걸린 화면의 빈 상태 (PA-RC-0038)", () => {
  it("기본 필터로 0건이면 무조건형 온보딩이 아니라 '필터 때문' 문구 + 필터 지우기를 보인다", async () => {
    apiMock.mockImplementation((url) =>
      Promise.resolve(String(url).includes("status=pending")
        ? { items: [], page: 1, page_size: 20, total: 0 }
        : Promise.reject(new Error("unexpected url: " + url))));
    renderScreen(CONFIG_WITH_DEFAULT_FILTER);

    expect(await screen.findByText("검색 결과가 없습니다")).toBeInTheDocument();
    // 기본값 제외 로직이 되살아나면 이 온보딩 문구가 대신 뜬다 — 반드시 없어야 한다.
    expect(screen.queryByText("검사 요청이 없습니다")).toBeNull();
    expect(screen.getByRole("button", { name: "검색, 필터 지우기" })).toBeInTheDocument();
  });

  it("빈 화면이 아니어도 기본 필터만으로 툴바에 '필터 지우기'가 뜬다(acceptance 2)", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "1", name: "대기 항목" }], page: 1, page_size: 20, total: 1 });
    renderScreen(CONFIG_WITH_DEFAULT_FILTER);

    await screen.findByText("대기 항목");
    expect(screen.getByRole("button", { name: "필터 지우기" })).toBeInTheDocument();
  });

  it("'필터 지우기'를 누르면 기본값이 아니라 전체가 보인다(acceptance 2 — 기본값 복귀가 아님)", async () => {
    apiMock.mockImplementation((url) =>
      Promise.resolve(String(url).includes("status=pending")
        ? { items: [], page: 1, page_size: 20, total: 0 }
        : { items: [{ id: "1", name: "완료 항목" }], page: 1, page_size: 20, total: 1 }));
    const user = userEvent.setup();
    renderScreen(CONFIG_WITH_DEFAULT_FILTER);

    await screen.findByText("검색 결과가 없습니다");
    await user.click(screen.getByRole("button", { name: "검색, 필터 지우기" }));

    // 지운 뒤 재요청이 status= 파라미터 없이 나갔다(기본값으로 되돌아간 게 아니라 진짜 전체).
    expect(apiMock.mock.calls.some(([u]) => !String(u).includes("status="))).toBe(true);
    expect(await screen.findByText("완료 항목")).toBeInTheDocument();
  });

  it("필터가 아예 없는 화면은 0건일 때 기존 온보딩 문구가 그대로다(회귀 없음, acceptance 3)", async () => {
    apiMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 });
    renderScreen(CONFIG_NO_FILTER);

    expect(await screen.findByText("표시할 항목이 없습니다(검사용)")).toBeInTheDocument();
    expect(screen.queryByText("검색 결과가 없습니다")).toBeNull();
    expect(screen.queryByRole("button", { name: /필터 지우기/ })).toBeNull();
  });

  it("기본 필터가 있어도 진짜 0건(필터를 지워도 0건)이면 결국 온보딩 문구로 떨어진다", async () => {
    // 두 번째 fetch(필터 지운 뒤)도 0건 — '진짜 신규 설치'를 흉내낸다.
    apiMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 });
    const user = userEvent.setup();
    renderScreen(CONFIG_WITH_DEFAULT_FILTER);

    await screen.findByText("검색 결과가 없습니다");
    await user.click(screen.getByRole("button", { name: "검색, 필터 지우기" }));

    expect(await screen.findByText("검사 요청이 없습니다")).toBeInTheDocument();
  });
});
