import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 게시판 댓글이 티켓·문서 댓글(CommentThread.jsx)과 같은 두 가지 규약을 지키는지 본다
 * (step 9 #1·#4) — 수정/삭제 권한 분리와 삭제 댓글의 툼스톤 표시. 게시판은 답글
 * 중첩(parent_comment_id)이 있어 CommentThread.jsx 를 그대로 재사용하지 않고 자체
 * 컴포넌트(BoardPost.jsx::CommentItem)로 같은 계약을 구현한다 - 그 계약이 실제로
 * 같은지는 화면을 직접 렌더해서 봐야 증명된다. */

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

function basePost(overrides) {
  return {
    post: {
      id: "p1", kind: "free", category: "기타", title: "제목", body: "본문",
      author_user_id: "u1", author_name: "글쓴이", is_pinned: false, view_count: 1,
      can_edit: false, can_delete: false, can_moderate: false,
      reactions: [], attachments: [], people: {},
      created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
      comments: [],
      ...overrides,
    },
  };
}

function mockRoutes(post) {
  apiMock.mockImplementation((url, opts) => {
    const u = String(url);
    if (u === "/api/board/meta") return Promise.resolve({ categories: [], reaction_emojis: [] });
    if (u === "/api/board/posts/p1/view") return Promise.resolve({ ok: true });
    if (u === "/api/board/posts/p1" && (!opts || !opts.method)) return Promise.resolve(post);
    return Promise.resolve({ ok: true });
  });
}

beforeEach(() => apiMock.mockReset());

describe("게시판 댓글 — 수정/삭제 권한 분리", () => {
  it("운영자군은 남의 댓글을 삭제할 수 있지만 수정 버튼은 안 보인다", async () => {
    mockRoutes(basePost({
      comments: [{
        id: "c1", body: "작성자 댓글", author_name: "작성자", author_user_id: "u2",
        can_edit: false, can_delete: true, deleted: false,
        reactions: [], created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
      }],
    }));

    wrap(["/board/p1"]);
    expect(await screen.findByText("작성자 댓글")).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "수정" })).toBeNull();
    expect(screen.getByRole("button", { name: "삭제" })).toBeInTheDocument();
  });

  it("작성자 본인은 수정 버튼만 보이고(삭제는 별도 값) 둘 다 켜지면 둘 다 보인다", async () => {
    mockRoutes(basePost({
      comments: [{
        id: "c1", body: "내 댓글", author_name: "나", author_user_id: "u1",
        can_edit: true, can_delete: true, deleted: false,
        reactions: [], created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
      }],
    }));

    wrap(["/board/p1"]);
    const row = within(await screen.findByText("내 댓글").then((el) => el.closest("article")));
    expect(row.getByRole("button", { name: "수정" })).toBeInTheDocument();
    expect(row.getByRole("button", { name: "삭제" })).toBeInTheDocument();
  });
});

describe("게시판 댓글 — 삭제는 툼스톤으로 남는다", () => {
  it("삭제된 댓글은 사라지지 않고 본문 없는 툼스톤으로 렌더된다", async () => {
    mockRoutes(basePost({
      comments: [
        {
          id: "c1", body: "", author_name: "작성자", author_user_id: "u2",
          can_edit: false, can_delete: false, deleted: true,
          reactions: [], created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
        },
        {
          id: "c2", parent_comment_id: "c1", body: "살아있는 답글", author_name: "동료",
          author_user_id: "u3", can_edit: false, can_delete: false, deleted: false,
          reactions: [], created_at: "2026-08-01T02:00:00", updated_at: "2026-08-01T02:00:00",
        },
      ],
    }));

    wrap(["/board/p1"]);
    expect(await screen.findByText(/삭제된 댓글입니다/)).toBeInTheDocument();
    // 답글은 부모가 툼스톤이어도 그대로 남아 렌더된다(고아가 되지 않는다).
    expect(screen.getByText("살아있는 답글")).toBeInTheDocument();
  });
});

describe("게시판 댓글 — 수정 표시", () => {
  it("updated_at이 created_at과 다르면 '(수정됨)'을 보여준다", async () => {
    mockRoutes(basePost({
      comments: [{
        id: "c1", body: "고친 댓글", author_name: "작성자", author_user_id: "u2",
        can_edit: false, can_delete: false, deleted: false,
        created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T02:00:00",
        reactions: [],
      }],
    }));

    wrap(["/board/p1"]);
    expect(await screen.findByText("고친 댓글")).toBeInTheDocument();
    expect(screen.getByText("(수정됨)")).toBeInTheDocument();
  });

  it("수정된 적 없으면 '(수정됨)'을 안 보여준다", async () => {
    mockRoutes(basePost({
      comments: [{
        id: "c1", body: "원문 댓글", author_name: "작성자", author_user_id: "u2",
        can_edit: false, can_delete: false, deleted: false,
        created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
        reactions: [],
      }],
    }));

    wrap(["/board/p1"]);
    expect(await screen.findByText("원문 댓글")).toBeInTheDocument();
    expect(screen.queryByText("(수정됨)")).toBeNull();
  });
});
