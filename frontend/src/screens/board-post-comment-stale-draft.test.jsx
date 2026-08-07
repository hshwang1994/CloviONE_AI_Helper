import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 게시글 상세의 새 댓글 입력창도 같은 버그를 갖고 있었다 — CommentThread와 별개로
 * BoardPost.jsx 안에 자체 CommentComposer가 있다(참고: comment-thread-stale-draft.test.jsx).
 *
 * "/board/:id"는 게시글을 바꿔도 같은 BoardPost 인스턴스를 재사용한다(알림 딥링크 등 인앱
 * 이동). 댓글 입력창(CommentComposer)이 postId prop만 새로 받고 리마운트되지 않으면, A 글에
 * 쓰던 초안이 B 글의 댓글창에 그대로 남아 "등록"을 누르면 B 글에 잘못 달린다.
 *
 * B 글을 처음 여는 경우엔 `detail.isPending` 스켈레톤이 트리를 통째로 갈아 끼우면서
 * CommentComposer 도 우연히 다시 마운트돼 증상이 가려진다 — 그래서 이 테스트는 B 글을
 * **미리 캐시에 넣어 둔다**(이미 한 번 열어 본 글로 다시 이동하는, staleTime 기본값(0)에서
 * 흔한 경우). 캐시가 있으면 isPending 이 곧장 false 라 스켈레톤이 뜨지 않고, 우연한 리마운트도
 * 없다 — 버그가 가려지지 않고 그대로 드러난다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { BoardPost } from "./BoardPost.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function NavHelper({ to }) {
  const nav = useNavigate();
  return <button onClick={() => nav(to)}>다른 글로 이동</button>;
}

function wrap(entries, qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={entries}>
              <NavHelper to="/board/p2" />
              <Routes>
                <Route path="/board/:id" element={<BoardPost />} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

function post(id, title) {
  return {
    post: {
      id, kind: "free", category: "기타", title, body: "본문",
      author_user_id: "u1", author_name: "글쓴이", is_pinned: false, view_count: 1,
      can_edit: false, can_moderate: false, reactions: [], attachments: [],
      comments: [], people: {},
      created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
    },
  };
}

beforeEach(() => { apiMock.mockReset(); });

describe("게시글 새 댓글 초안은 다른 글로 이동하면 비워진다", () => {
  it("A 글에 쓰던 초안이 B 글 댓글창까지 따라오지 않는다(B는 이미 캐시에 있다)", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((url) => {
      const u = String(url);
      if (u === "/api/board/meta") return Promise.resolve({ categories: [], reaction_emojis: [] });
      if (u === "/api/board/posts/p1/view" || u === "/api/board/posts/p2/view") return Promise.resolve({ ok: true });
      if (u === "/api/board/posts/p1") return Promise.resolve(post("p1", "글 A"));
      if (u === "/api/board/posts/p2") return Promise.resolve(post("p2", "글 B"));
      return Promise.resolve({ ok: true });
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    // B 글을 이미 한 번 열어 캐시에 있는 상태를 흉내낸다 — isPending 스켈레톤이 뜨지 않아
    // CommentComposer 가 우연히 리마운트되지 않는다.
    qc.setQueryData(["board-post", "p2"], post("p2", "글 B"));

    wrap(["/board/p1"], qc);
    expect(await screen.findByText("글 A")).toBeInTheDocument();

    await user.type(screen.getByLabelText("댓글 입력"), "글 A용 초안");
    expect(screen.getByLabelText("댓글 입력")).toHaveValue("글 A용 초안");

    await user.click(screen.getByRole("button", { name: "다른 글로 이동" }));
    expect(await screen.findByText("글 B")).toBeInTheDocument();

    expect(screen.getByLabelText("댓글 입력")).toHaveValue("");
  });
});
