import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* PA-RC-0038 required_tests (2) — `/approvals` 빈 상태 회귀 테스트.
 *
 * datascreen-default-filter-empty-state.test.jsx가 DataScreen 공유 분기 로직 자체를
 * 합성 config로 검사한다면, 이 파일은 **실제** `REGISTRY.approvals`(status=pending
 * 기본 필터 + emptyTitle/emptyHelp/emptyRelatedLink)를 그대로 꽂아 실제 화면 설정이
 * 그 분기에 올바르게 걸리는지 확인한다 — 합성 config 시험이 통과해도 실제 설정에서
 * 필터 key 오타 등으로 다시 깨질 수 있다.
 *
 * qa-contract-change: 조건 때문에 0건은 「검색 결과가 없습니다」 + 「검색, 필터 지우기」 판이 아니라 표 머리 아래 한 줄 띠 「조건에 맞는 항목이
 * 없습니다.」 + 30 「필터 지우기」다(D-530 목록 상태 일곱 갈래). 「필터 때문 대 정말 없음」 판정과 지운 뒤 전체 조회 단언은 그대로다.
 *
 * qa-contract-change: 기본 조건(대기)만 걸린 0건은 「처리할 승인 요청이 없습니다.」 + 30 「전체 결과 보기」다(D-587) — 사람이 건
 * 조건이 없는데 「필터 초기화」라고 말하지 않는다. 누르면 전체 조회로 가고, 정말 0건이면 온보딩으로 떨어진다는 단언은 그대로다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { REGISTRY } from "./registry.js";
import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const FILTERED_EMPTY = "처리할 승인 요청이 없습니다.";
/* 기본 조건 때문에 0건의 띠 — 넓히는 단추는 띠 안의 「전체 결과 보기」다(조건 줄의 「필터 초기화」와 같은 일을 한다). */
async function bandClear() {
  const heading = await screen.findByRole("heading", { name: FILTERED_EMPTY });
  return within(heading.closest("[data-empty-layout='band']")).getByRole("button", { name: "전체 결과 보기" });
}

function renderApprovals() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter><DataScreen config={REGISTRY.approvals} /></MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("/approvals — 기본 필터(status=pending) 0건일 때 빈 상태", () => {
  it("대기 0건이지만 처리 이력은 있을 때, '승인 요청이 없습니다'(무조건형)가 아니라 필터 안내를 보인다", async () => {
    apiMock.mockImplementation((url) =>
      Promise.resolve(String(url).includes("status=pending")
        ? { items: [], page: 1, page_size: 20, total: 0 }
        : Promise.reject(new Error("unexpected url: " + url))));
    renderApprovals();

    expect(await screen.findByText(FILTERED_EMPTY)).toBeInTheDocument();
    expect(screen.queryByText("승인 요청이 없습니다.")).toBeNull();
    expect(await bandClear()).toBeInTheDocument();
  });

  it("'전체 결과 보기'를 누르면 대기가 아닌 처리된 요청도 보인다(전체 조회, 기본값 복귀 아님)", async () => {
    apiMock.mockImplementation((url) =>
      Promise.resolve(String(url).includes("status=pending")
        ? { items: [], page: 1, page_size: 20, total: 0 }
        : { items: [{ id: "a-1", request_type: "user.role_change", status: "approved" }], page: 1, page_size: 20, total: 1 }));
    const user = userEvent.setup();
    renderApprovals();

    await user.click(await bandClear());

    expect(apiMock.mock.calls.some(([u]) => !String(u).includes("status="))).toBe(true);
    // 기본값(status=pending)으로 되돌아갔다면 재요청도 빈 결과라 이 문구가 그대로 남는다 —
    // 실제로 사라지는 것이 "전체 조회"가 됐다는 증거다.
    await waitFor(() => expect(screen.queryByText(FILTERED_EMPTY)).toBeNull());
    expect(screen.getByText("승인됨")).toBeInTheDocument(); // badgeCol("status") — approved 행이 실제로 그려졌다
  });

  it("진짜 신규 설치(전체를 봐도 0건)면 결국 '승인 요청이 없습니다' 온보딩으로 떨어진다", async () => {
    apiMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 });
    const user = userEvent.setup();
    renderApprovals();

    await user.click(await bandClear());

    expect(await screen.findByText("승인 요청이 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("부재 시 대리 승인자 설정")).toBeInTheDocument(); // emptyRelatedLink 회귀 없음
  });
});
