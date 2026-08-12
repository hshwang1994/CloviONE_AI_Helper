import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 통합 검색 재색인 버튼(FN-03) — 고아였던 POST /api/search/reindex 에 처음 생긴 화면 호출부.
 *
 *  1. operator 미만 role 은 버튼 자체가 안 뜬다(목록 GET 은 role 없이 열려 있어 화면에서 걸러야 한다).
 *  2. operator+ 는 버튼이 뜨고, 누르면 확인 다이얼로그가 먼저 뜬다(되돌릴 수 없는 재계산이 아니라
 *     안전한 재빌드지만, 데이터가 많으면 시간이 걸릴 수 있다는 안내는 필요).
 *  3. 확인하면 POST 를 부르고 성공 토스트를 띄운다.
 *  4. 실패 응답이면 실패 토스트를 띄운다.
 *
 * 네트워크·타이머 없음: api는 mock. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

let authRole = "operator";
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: authRole, id: "u-1" } }),
}));

import { Search } from "./Search.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";

function mockApi({ searchResult, reindexResult } = {}) {
  apiMock.mockImplementation((path, opts) => {
    const p = String(path);
    if (p.startsWith("/api/search/reindex")) {
      return Promise.resolve(reindexResult || { reindex: { status: "ok", item_count: 42 } });
    }
    if (p.startsWith("/api/search")) {
      return Promise.resolve(searchResult || { total: 0, mode: "fts", truncated: false, groups: [] });
    }
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
  authRole = "operator";
  mockApi();
});

function renderSearch(initialQuery = "?q=test") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <ConfirmProvider>
          <MemoryRouter initialEntries={["/search" + initialQuery]}>
            <Search />
          </MemoryRouter>
        </ConfirmProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("통합 검색 — 재색인 버튼 (FN-03)", () => {
  it("operator 미만이면 버튼이 안 뜬다", async () => {
    authRole = "user";
    renderSearch();
    await screen.findByText("통합 검색");
    expect(screen.queryByRole("button", { name: "지금 재색인" })).toBeNull();
  });

  it("operator+ 면 버튼이 뜨고, 누르면 확인부터 뜬다", async () => {
    const user = userEvent.setup();
    renderSearch();
    const btn = await screen.findByRole("button", { name: "지금 재색인" });
    await user.click(btn);
    expect(await screen.findByText(/데이터가 많으면 잠시 시간이 걸릴 수 있습니다/)).toBeInTheDocument();
    // 아직 요청은 안 나갔다 — 확인이 먼저다.
    expect(apiMock.mock.calls.some(([p]) => String(p).startsWith("/api/search/reindex"))).toBe(false);
  });

  it("확인하면 재색인을 요청하고 성공 토스트를 띄운다", async () => {
    const user = userEvent.setup();
    renderSearch();
    await user.click(await screen.findByRole("button", { name: "지금 재색인" }));
    await user.click(await screen.findByRole("button", { name: "재색인" }));

    expect(await screen.findByText(/검색 색인을 다시 만들었습니다 \(42건\)/)).toBeInTheDocument();
    const called = apiMock.mock.calls.some(([p, opts]) => String(p).startsWith("/api/search/reindex") && opts && opts.method === "POST");
    expect(called).toBe(true);
  });

  it("재색인이 실패로 응답하면 실패 토스트를 띄운다", async () => {
    const user = userEvent.setup();
    mockApi({ reindexResult: { reindex: { status: "error", error: "인덱스 잠김" } } });
    renderSearch();
    await user.click(await screen.findByRole("button", { name: "지금 재색인" }));
    await user.click(await screen.findByRole("button", { name: "재색인" }));

    expect(await screen.findByText(/재색인 실패: 인덱스 잠김/)).toBeInTheDocument();
  });
});

/* WF1 R4 — "티켓, 문서, 게시판, 사용자를 한 번에 찾습니다" 안내가 역할과 무관하게 늘 4종을
 * 약속했다. 그런데 app/search/service.py의 KIND_ROLE_GATE는 '사용자' 검색을
 * CONSOLE_WRITE_ROLES(admin/system_admin — 프런트 WRITE_ROLES와 같은 집합)에게만 준다.
 * 그 외 역할(운영자·감사자·일반 사용자, 이 콘솔 대부분)은 이 화면에서 '사용자' 결과를 영원히
 * 못 보는데 안내는 항상 4종이었다. */
describe("통합 검색 — 안내 문구가 역할별 검색 가능 유형과 맞는다 (WF1 R4)", () => {
  it("'사용자' 검색 권한이 없는 역할(operator)에게는 3종만 약속한다", async () => {
    authRole = "operator";
    renderSearch("");
    expect(await screen.findByText("무엇을 찾을까요?")).toBeInTheDocument();
    expect(screen.getByText("티켓, 문서, 게시판을 한 번에 찾습니다.")).toBeInTheDocument();
    expect(screen.queryByText(/사용자를 한 번에 찾습니다/)).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("티켓, 문서, 게시판 검색")).toBeInTheDocument();
  });

  it("'사용자' 검색 권한이 있는 역할(admin)에게는 4종을 약속한다", async () => {
    authRole = "admin";
    renderSearch("");
    expect(await screen.findByText("무엇을 찾을까요?")).toBeInTheDocument();
    expect(screen.getByText("티켓, 문서, 게시판, 사용자를 한 번에 찾습니다.")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("티켓, 문서, 게시판, 사용자 검색")).toBeInTheDocument();
  });
});
