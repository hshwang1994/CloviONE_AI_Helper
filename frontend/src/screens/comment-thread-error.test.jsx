import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* 댓글 타래(CommentThread) — 로딩·오류 상태.
 *
 * 티켓·문서 댓글이 함께 쓰는 부품이다(CommentThread.jsx 상단 주석). 목록 조회가 실패했을 때
 * 화면 대부분(Dashboard·Search·Users·…)은 `ErrorState` 로 재시도 버튼과 원인별 안내를
 * 준다. 이 부품만 맨 `Callout` 한 줄로 실패를 말하면, 같은 화면(티켓 상세) 안에서 본문은
 * "다시 시도" 버튼이 있는데 바로 아래 댓글은 그 버튼이 없는 — 나란히 놓인 두 실패가
 * 다르게 생기는 화면이 된다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { CommentThread } from "./CommentThread.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderThread() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <CommentThread
              queryKey={["ticket-comments", "t1"]}
              listUrl="/api/tickets/t1/comments"
              itemUrl={(id) => "/api/tickets/comments/" + id}
              emptyHint="아직 댓글이 없습니다."
            />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("댓글 타래 — 로딩·오류", () => {
  it("불러오는 동안 스켈레톤을 보여준다", async () => {
    apiMock.mockImplementation(() => new Promise(() => {})); // 영원히 대기
    renderThread();
    // Skeleton은 장식(aria-hidden)이고, 스크린리더용 안내는 별도 sr-only 노드다.
    expect(await screen.findByText("불러오는 중…")).toBeInTheDocument();
  });

  it("조회가 실패하면 다시 시도할 길이 있는 오류 화면을 보여준다", async () => {
    apiMock.mockRejectedValue(Object.assign(new Error("서버 오류"), { status: 500 }));
    renderThread();

    // ErrorState의 표준 제목 — 화면 전역에서 실패를 말하는 한 가지 방식이다.
    expect(await screen.findByText("불러오지 못했습니다")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
  });
});
