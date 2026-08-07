import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 댓글 "수정" 버튼은 누르는 그 순간의 댓글 내용을 편집창에 채워야 한다.
 *
 * CommentItem의 `text` 상태는 `useState(comment.body)`로 **마운트 시 한 번만** 초깃값을
 * 받는다. 그 뒤 이 세션에서 다른 동작(새 댓글 등록, 반응 등)이 상세 조회를 다시 부르면
 * `comment` prop은 새 값을 받지만(화면에 보이는 본문은 `comment.body`를 직접 그려 맞게
 * 나온다), `text` state는 리마운트가 없는 한 그대로 남는다.
 *
 * 이 댓글을 다른 세션(다른 탭, 또는 운영자가 여러 사람의 댓글을 고칠 수 있는 게시판이라
 * 다른 사람)이 먼저 고쳐 두었고, 그 변경이 이 세션의 어떤 새로고침으로 반영된 뒤 이 사용자가
 * 처음으로 "수정"을 누르면 — 편집창에 옛 내용이 뜬다. 그 상태로 "저장"을 누르면 방금
 * 반영된 새 내용을 옛 내용으로 덮어써 버린다(잃어버린 갱신). "수정" 버튼은 지금 state가
 * 아니라 지금 `comment.body`로 편집창을 채워야 한다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { BoardPost } from "./BoardPost.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function wrap(entries) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={entries}>
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

function postWith(commentBody) {
  return {
    post: {
      id: "p1", kind: "free", category: "기타", title: "제목", body: "본문",
      author_user_id: "u1", author_name: "글쓴이", is_pinned: false, view_count: 1,
      // post 자체는 수정 버튼이 없게 해서(can_edit:false) 화면에 "수정" 텍스트 버튼이
      // 댓글 것 하나만 남게 한다 — 접근 이름 충돌 없이 바로 찾을 수 있게.
      can_edit: false, can_moderate: false, reactions: [], attachments: [],
      comments: [
        {
          id: "c1", body: commentBody, author_name: "동료", author_user_id: "u2",
          can_edit: true, reactions: [], created_at: "2026-08-01T01:00:00",
        },
      ],
      people: {},
      created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
    },
  };
}

beforeEach(() => apiMock.mockReset());

describe("댓글 수정 버튼은 지금 내용으로 편집창을 채운다", () => {
  it("배경 새로고침으로 본문이 바뀐 뒤 처음 '수정'을 눌러도 최신 내용이 뜬다", async () => {
    const user = userEvent.setup();
    let call = 0;
    apiMock.mockImplementation((url, opts) => {
      const u = String(url);
      if (u === "/api/board/meta") return Promise.resolve({ categories: [], reaction_emojis: [] });
      if (u === "/api/board/posts/p1/view") return Promise.resolve({ ok: true });
      if (u === "/api/board/posts/p1" && (!opts || !opts.method)) {
        call += 1;
        // 첫 조회는 원본, 그 뒤(이 세션 안의 다른 동작이 부른 재조회)는 다른 세션에서
        // 이미 반영된 새 내용을 돌려준다.
        return Promise.resolve(postWith(call === 1 ? "원본 댓글" : "다른 세션이 먼저 고친 댓글"));
      }
      if (u === "/api/board/posts/p1/comments" && opts && opts.method === "POST") {
        return Promise.resolve({ comment: { id: "c2", body: "새 댓글" } });
      }
      return Promise.resolve({ ok: true });
    });

    wrap(["/board/p1"]);
    expect(await screen.findByText("원본 댓글")).toBeInTheDocument();

    // 댓글 대상 댓글이 아니라 이 세션의 다른 동작(맨 아래 댓글 작성)이 상세 재조회를 부른다 —
    // 이 사용자는 아직 "수정"을 한 번도 누르지 않았다.
    await user.type(screen.getByLabelText("댓글 입력"), "새 댓글");
    await user.click(screen.getByRole("button", { name: "댓글 등록" }));

    // 재조회가 반영되어 화면(비편집 상태)의 본문은 이미 새 내용을 보인다.
    expect(await screen.findByText("다른 세션이 먼저 고친 댓글")).toBeInTheDocument();

    // 이제 처음으로 "수정"을 누른다 — 편집창은 방금 확인한 최신 내용으로 채워져야 한다.
    await user.click(screen.getByRole("button", { name: "수정" }));
    await waitFor(() => {
      expect(screen.getByLabelText("댓글 수정")).toHaveValue("다른 세션이 먼저 고친 댓글");
    });
  });
});
