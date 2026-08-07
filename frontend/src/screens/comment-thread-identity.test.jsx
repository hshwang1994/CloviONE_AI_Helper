import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 댓글 타래(CommentThread)도 작성자가 누구인지 말해야 한다 (#13/#8, 2026-08-04 지시).
 *
 * 게시판(Board.jsx::AuthorLine, board-identity.test.jsx)은 이미 부서·직책·사진·보관됨을
 * 답한다. 티켓·문서 댓글은 `author_name` 하나만 그리고 있었다 — 표시 이름에는 유일성
 * 제약이 없으므로(`app/users/models.py`) 동명이인이면 댓글 머리글이 **아무것도 답하지
 * 못하는 칸**이었다. 이 파일은 CommentThread 가 Board.jsx 와 같은 AuthorLine 규칙을
 * 그대로 쓰는지 고정한다 — 새로 만들지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { CommentThread } from "./CommentThread.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function person(over = {}) {
  return {
    user_id: "u1", display_name: "박댓글", dept: "", title: "", org: "",
    archived: false, avatar_url: null, ...over,
  };
}

const COMMENT = {
  id: "c1", author_user_id: "u1", author_name: "박댓글", body: "확인했습니다.",
  deleted: false, can_edit: false, can_delete: false,
  created_at: "2026-08-01T00:00:00", updated_at: "2026-08-01T00:00:00",
};

function renderThread(payload) {
  apiMock.mockResolvedValue(payload);
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

describe("댓글 작성자 신원", () => {
  it("이름 옆에 부서와 직책이 나온다", async () => {
    renderThread({
      comments: [COMMENT],
      people: { u1: person({ dept: "인프라팀", title: "수석" }) },
    });
    expect(await screen.findByText("확인했습니다.")).toBeInTheDocument();
    expect(screen.getByText(/인프라팀 수석/)).toBeInTheDocument();
  });

  it("프로필 사진이 나온다", async () => {
    const { container } = renderThread({
      comments: [COMMENT],
      people: { u1: person({ avatar_url: "/api/profile/avatar/u1?v=3" }) },
    });
    expect(await screen.findByText("확인했습니다.")).toBeInTheDocument();
    expect(container.querySelector('img[src="/api/profile/avatar/u1?v=3"]')).toBeTruthy();
  });

  it("보관된 계정이면 그렇다고 말한다", async () => {
    renderThread({
      comments: [COMMENT],
      people: { u1: person({ dept: "인프라팀", archived: true }) },
    });
    expect(await screen.findByText("확인했습니다.")).toBeInTheDocument();
    expect(screen.getByText("(보관됨)")).toBeInTheDocument();
  });

  it("살아 있는 계정에는 보관 표시를 붙이지 않는다", async () => {
    renderThread({
      comments: [COMMENT],
      people: { u1: person({ dept: "인프라팀" }) },
    });
    expect(await screen.findByText("확인했습니다.")).toBeInTheDocument();
    expect(screen.queryByText("(보관됨)")).toBeNull();
  });

  it("소속을 모르면 빈 괄호를 그리지 않는다", async () => {
    const { container } = renderThread({ comments: [COMMENT], people: { u1: person() } });
    expect(await screen.findByText("확인했습니다.")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\(\s*\)/);
  });

  it("people 이 통째로 없어도 댓글은 그려진다(옛 캐시·응답 대비)", async () => {
    renderThread({ comments: [COMMENT] });
    expect(await screen.findByText("확인했습니다.")).toBeInTheDocument();
    expect(screen.getByText("박댓글")).toBeInTheDocument();
  });
});
