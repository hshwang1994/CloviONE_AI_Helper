import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* WF44 배경 조사(L축 재감사, 2026-08-13) — Home.jsx의 `MyBoardStats`("내 글"·"받은 댓글"·
 * "조회") 위젯은 `["board-mine"]` 하나만 읽는데, 이 키는 게시글을 새로 써도(post_count가
 * 바뀌는데도) 지금까지 무효화된 적이 없었다 — 게시글 생성/삭제 둘 다 처음 겪는 무효화라
 * `board.test.jsx`의 기존 계약(폼 자체 동작)과는 분리해 새 파일로 둔다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { PostFormModal } from "./Board.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function wrap(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <PostFormModal open categories={["자유"]} onClose={() => {}} mode="create" kind="free" onSaved={() => {}} />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((url, opts) => {
    const u = String(url);
    if (u === "/api/board/posts" && opts && opts.method === "POST") {
      return Promise.resolve({ post: { id: "p9", title: "새 글" } });
    }
    return Promise.resolve({ ok: true });
  });
});

describe("게시글 작성 → board-mine 캐시 무효화 (WF44 L축)", () => {
  it("새 글을 저장하면 board-mine(「내 글」 위젯) 캐시가 무효화된다", async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(["board-mine"], { summary: { post_count: 0, comment_count_received: 0, view_count_total: 0 } });
    expect(qc.getQueryState(["board-mine"]).isInvalidated).toBe(false);

    wrap(qc);
    await user.type(screen.getByLabelText(/^제목/), "새 글");
    await user.click(screen.getByRole("button", { name: "등록" }));

    await waitFor(() => {
      expect(qc.getQueryState(["board-mine"]).isInvalidated, "board-mine").toBe(true);
    });
  });
});
