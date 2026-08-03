import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* DataScreen 계약 테스트.
 *
 * 이 컴포넌트 하나가 관리자 화면 16개를 그린다. 그런데 지금까지 테스트가 한 줄도 없었다 —
 * 재설계로 마크업을 갈아엎기 전에 '무엇이 지켜져야 하는지'를 먼저 못 박는다.
 *
 * 여기서 보는 네 가지는 전부 과거에 실제로 틀렸거나, 틀리면 조용히 잘못 동작하는 것들이다:
 *   1) 필터가 서버로 갈 때의 형태 — 특히 datetime-local은 시간대가 없어서 KST(+09:00)를 붙여야 한다.
 *      안 붙이면 백엔드가 UTC로 읽어 9시간 어긋난 범위를 조회한다(화면엔 아무 오류도 안 뜬다).
 *   2) 페이지 이동 중 목록이 통째로 사라지지 않는다(placeholderData) — 예전엔 클릭마다 스켈레톤으로 깜빡였다.
 *   3) 액션 하나를 눌렀을 때 그 버튼만 '처리 중…'이 된다 — 예전엔 단일 boolean이라 화면의 모든
 *      버튼이 같이 처리 중으로 보였다.
 *   4) 401은 재시도해도 401이다 — 일반 오류 토스트로 뭉개면 사용자가 이유도 모른 채 막힌다.
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
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderScreen(config) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={config} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const BASE_CONFIG = {
  key: "audit",
  area: "운영",
  title: "감사 로그",
  endpoint: "/api/admin/audit",
  columns: [{ key: "action", label: "동작" }, { key: "actor", label: "수행자" }],
};

beforeEach(() => {
  apiMock.mockReset();
});

describe("필터가 서버로 가는 형태", () => {
  it("datetime-local 필터에 KST(+09:00)를 붙여 보낸다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();
    renderScreen({
      ...BASE_CONFIG,
      filters: [{ key: "from", label: "시작", type: "datetime-local" }],
    });
    await waitFor(() => expect(apiMock).toHaveBeenCalled());

    const input = screen.getByLabelText("시작");
    await user.type(input, "2026-08-03T09:30");

    await waitFor(() => {
      const urls = apiMock.mock.calls.map((c) => c[0]);
      expect(urls.some((u) => u.includes(encodeURIComponent("2026-08-03T09:30:00+09:00")))).toBe(true);
    });
  });

  it("빈 필터 값은 쿼리에 넣지 않는다", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    renderScreen({
      ...BASE_CONFIG,
      filters: [{ key: "actor", label: "수행자", type: "text" }],
    });
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(apiMock.mock.calls[0][0]).toBe("/api/admin/audit");
  });

  it("clientFilter 필터는 서버로 보내지 않고 화면에서 거른다", async () => {
    apiMock.mockResolvedValue({
      items: [{ id: "1", action: "login", actor: "a" }, { id: "2", action: "logout", actor: "b" }],
      total: 2,
    });
    const user = userEvent.setup();
    renderScreen({
      ...BASE_CONFIG,
      filters: [{ key: "action", label: "동작", type: "select", clientFilter: true, options: [{ value: "login", label: "로그인" }] }],
    });
    await screen.findByText("login");
    const callsBefore = apiMock.mock.calls.length;

    await user.click(screen.getByLabelText("동작"));
    await user.click(await screen.findByRole("option", { name: "로그인" }));

    // 서버 재조회 없이 화면에서만 걸러진다.
    await waitFor(() => expect(screen.queryByText("logout")).toBeNull());
    expect(screen.getByText("login")).toBeInTheDocument();
    expect(apiMock.mock.calls.length).toBe(callsBefore);
  });
});

describe("페이지네이션", () => {
  const paged = { ...BASE_CONFIG, paginated: true, pageSize: 2 };

  it("다음/이전으로 page 파라미터가 바뀌고, 이동 중에도 목록이 비지 않는다", async () => {
    apiMock.mockImplementation((url) => {
      const page = /page=(\d+)/.exec(url);
      const n = page ? Number(page[1]) : 1;
      return Promise.resolve({
        items: [{ id: `p${n}`, action: `동작-${n}`, actor: "a" }],
        total: 4, page_size: 2,
      });
    });
    const user = userEvent.setup();
    renderScreen(paged);
    await screen.findByText("동작-1");

    await user.click(screen.getByRole("button", { name: "다음" }));
    // 새 페이지가 오기 전에도 이전 결과가 남아 있어야 한다(placeholderData).
    // getAllByText로 센다 — 전환 순간에는 옛 행과 새 행이 잠깐 함께 있을 수 있고,
    // getByText는 그때 '여러 개 찾음'으로 던져서 테스트가 간헐적으로 실패했다.
    expect(screen.getAllByText(/동작-/).length).toBeGreaterThan(0);
    await screen.findByText("동작-2");
    expect(apiMock.mock.calls.some((c) => String(c[0]).includes("page=2"))).toBe(true);

    await user.click(screen.getByRole("button", { name: "이전" }));
    await screen.findByText("동작-1");
  });

  it("마지막 페이지가 사라지면 페이지 번호만 유효한 값으로 되돌린다", async () => {
    let total = 4;
    apiMock.mockImplementation((url) => {
      const m = /page=(\d+)/.exec(url);
      const n = m ? Number(m[1]) : 1;
      const items = n * 2 <= total ? [{ id: `p${n}`, action: `동작-${n}`, actor: "a" }] : [];
      return Promise.resolve({ items, total, page_size: 2 });
    });
    const user = userEvent.setup();
    renderScreen(paged);
    await screen.findByText("동작-1");
    await user.click(screen.getByRole("button", { name: "다음" }));
    await screen.findByText("동작-2");

    total = 2; // 마지막 페이지의 항목이 사라진 상황
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "다음" })).toBeDisabled();
    });
  });
});

describe("액션 진행 표시는 누른 버튼에만", () => {
  it("헤더 작업 하나를 눌러도 다른 버튼이 '처리 중…'이 되지 않는다", async () => {
    let resolveAction;
    apiMock.mockImplementation((url, opts) => {
      if (opts && opts.method === "POST") return new Promise((r) => { resolveAction = r; });
      return Promise.resolve({ items: [{ id: "1", action: "login", actor: "a" }], total: 1 });
    });
    const user = userEvent.setup();
    renderScreen({
      ...BASE_CONFIG,
      headerActions: [
        { label: "내보내기", path: () => "/api/admin/audit/export" },
        { label: "정리", path: () => "/api/admin/audit/purge" },
      ],
    });
    await screen.findByText("login");

    await user.click(screen.getByRole("button", { name: "내보내기" }));

    // 누른 버튼만 라벨이 바뀐다. 나머지는 비활성화되되 라벨은 그대로다.
    await screen.findByRole("button", { name: "처리 중…" });
    const other = screen.getByRole("button", { name: "정리" });
    expect(other).toBeDisabled();
    expect(screen.queryAllByRole("button", { name: "처리 중…" })).toHaveLength(1);

    resolveAction({ ok: true });
  });
});

describe("세션 만료(401)", () => {
  let originalLocation;
  beforeEach(() => {
    originalLocation = window.location;
    delete window.location;
    window.location = { ...originalLocation, href: "", hash: "" };
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    window.location = originalLocation;
  });

  it("액션이 401이면 안내 후 로그인 화면으로 보낸다 — 일반 오류로 뭉개지 않는다", async () => {
    apiMock.mockImplementation((url, opts) => {
      if (opts && opts.method === "POST") {
        const e = new Error("세션이 만료되었습니다");
        e.status = 401;
        return Promise.reject(e);
      }
      return Promise.resolve({ items: [{ id: "1", action: "login", actor: "a" }], total: 1 });
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderScreen({
      ...BASE_CONFIG,
      headerActions: [{ label: "정리", path: () => "/api/admin/audit/purge" }],
    });
    await screen.findByText("login");

    await user.click(screen.getByRole("button", { name: "정리" }));
    expect(await screen.findByText(/로그인이 필요합니다/)).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(1500);
    expect(window.location.href).toBe("/login");
  });
});

describe("빈 상태는 '데이터 없음'과 '검색 결과 없음'을 구분한다", () => {
  it("필터가 걸려 있으면 지우기 CTA가 있는 검색 결과 없음", async () => {
    apiMock.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();
    renderScreen({
      ...BASE_CONFIG,
      searchable: true,
      emptyTitle: "감사 로그가 없습니다",
    });
    // 필터 없을 때는 온보딩 성격의 빈 상태
    expect(await screen.findByRole("heading", { name: "감사 로그가 없습니다" })).toBeInTheDocument();

    await user.type(screen.getByRole("searchbox"), "없는값");
    expect(await screen.findByRole("heading", { name: "검색 결과가 없습니다" })).toBeInTheDocument();
    // 빈 상태 안의 CTA. 툴바에도 '필터 지우기'가 함께 떠 있으므로 이름을 정확히 지정한다.
    expect(screen.getByRole("button", { name: "검색, 필터 지우기" })).toBeInTheDocument();
  });
});
