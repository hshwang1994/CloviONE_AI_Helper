import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* WF44 배경 조사(L축 재감사, 2026-08-13) — 게시글 상세의 댓글 작성/삭제·반응 토글·제안 상태
 * 변경 셋 다 `invalidateQueries` 없이 이 상세 화면 자신의 로컬 refetch(onChanged/onDone)만
 * 했다. 핀 고정·삭제(이 파일의 대조군, 이미 정상)는 `["board"]`+`["home"]`을 무효화하는데
 * 세 mutation만 그 배선이 빠져 있었다 — Board.jsx 목록의 comment_count/idea_status/like_count
 * 열과 Home.jsx 「최근 글」 위젯이 안 바뀌는 원인. 댓글 작성/삭제는 글쓴이 자신의 「받은 댓글」
 * (board-mine)에도 영향을 주는데, 이 키는 지금까지 **어떤** 게시판 mutation에서도 무효화된
 * 적이 없었다 — 게시글 삭제도 함께 잡는다(post_count).
 *
 * 댓글 **수정**(saveEdit)은 대조군으로 남긴다 — 본문만 바뀌고 어떤 목록 집계도 안 바뀌므로
 * 의도적으로 폭넓은 무효화를 안 한다(코드 주석 참고).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { BoardPost } from "./BoardPost.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function wrap(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/board/i1"]}>
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

// 댓글 삭제 버튼도 게시글 자신의 삭제 버튼과 이름이 똑같이 "삭제"다 — 한 시나리오에 둘 다
// 있으면 getByRole이 어느 쪽인지 모호해진다. 그래서 게시글 자신의 can_delete는 기본 꺼 두고
// (댓글 관련 시나리오는 이 버튼이 필요 없다), 게시글 삭제를 테스트할 때만 켠 채 댓글은 뺀다.
function ideaPost({ withComment = true, canDeletePost = false } = {}) {
  return {
    post: {
      id: "i1", kind: "idea", category: "기타", title: "제안 글", body: "본문",
      author_user_id: "u1", author_name: "글쓴이", is_pinned: false, view_count: 1,
      can_edit: false, can_moderate: false, can_delete: canDeletePost, can_change_status: true,
      idea_status: "제안", next_statuses: ["진행", "반려"], ticket_page_id: null,
      reactions: [], attachments: [], people: {},
      comments: withComment ? [{
        id: "c1", author_user_id: "u1", author_name: "글쓴이", body: "첫 댓글",
        can_edit: true, can_delete: true, deleted: false, reactions: [],
        parent_comment_id: null, created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
      }] : [],
      created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
    },
  };
}

function seedCaches(qc) {
  qc.setQueryData(["board"], { items: [] });
  qc.setQueryData(["home", "today"], { recent: { board: [], documents: [] } });
  qc.setQueryData(["board-mine"], { summary: { post_count: 1, comment_count_received: 0, view_count_total: 1 } });
  expect(qc.getQueryState(["board"]).isInvalidated, "board").toBe(false);
  expect(qc.getQueryState(["home", "today"]).isInvalidated, "home").toBe(false);
  expect(qc.getQueryState(["board-mine"]).isInvalidated, "board-mine").toBe(false);
}

beforeEach(() => { apiMock.mockReset(); });

function mockApi(fixtureOpts) {
  apiMock.mockImplementation((url, opts) => {
    const u = String(url);
    if (u === "/api/board/meta") return Promise.resolve({ categories: [], reaction_emojis: ["👍"] });
    if (u === "/api/board/posts/i1/view") return Promise.resolve({ ok: true });
    if (u === "/api/board/posts/i1") return Promise.resolve(ideaPost(fixtureOpts));
    if (u === "/api/board/posts/i1/comments") return Promise.resolve({ ok: true });
    if (u === "/api/board/comments/c1") return Promise.resolve({ ok: true });
    if (u === "/api/board/reactions") return Promise.resolve({ ok: true });
    if (u === "/api/board/posts/i1/status") return Promise.resolve({ ok: true });
    return Promise.resolve({ ok: true });
  });
}

describe("게시글 상세 — 댓글/반응/상태 변경이 목록·홈·내 활동 캐시를 무효화한다 (WF44 L축)", () => {
  it("댓글 등록이 board/home/board-mine 캐시를 무효화한다", async () => {
    const user = userEvent.setup();
    mockApi();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedCaches(qc);
    wrap(qc);

    expect(await screen.findByText("제안 글")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "댓글 입력" }), "새 댓글");
    await user.click(screen.getByRole("button", { name: "댓글 추가" }));

    await waitFor(() => {
      expect(qc.getQueryState(["board"]).isInvalidated, "board").toBe(true);
      expect(qc.getQueryState(["home", "today"]).isInvalidated, "home").toBe(true);
      expect(qc.getQueryState(["board-mine"]).isInvalidated, "board-mine").toBe(true);
    });
  });

  it("댓글 삭제가 board/home/board-mine 캐시를 무효화한다", async () => {
    const user = userEvent.setup();
    mockApi();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedCaches(qc);
    wrap(qc);

    expect(await screen.findByText("첫 댓글")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "삭제" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "삭제" }));

    await waitFor(() => {
      expect(qc.getQueryState(["board"]).isInvalidated, "board").toBe(true);
      expect(qc.getQueryState(["home", "today"]).isInvalidated, "home").toBe(true);
      expect(qc.getQueryState(["board-mine"]).isInvalidated, "board-mine").toBe(true);
    });
  });

  it("댓글 수정은 목록 집계를 안 바꾸므로 board 캐시를 무효화하지 않는다(대조군)", async () => {
    const user = userEvent.setup();
    mockApi();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedCaches(qc);
    wrap(qc);

    expect(await screen.findByText("첫 댓글")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "수정" }));
    await user.click(screen.getByRole("button", { name: "저장" }));

    // saveEdit의 onSuccess(setEditing(false))가 실제로 끝난 뒤 확인한다 — API 호출만 보고
    // 확인하면 onSuccess가 아직 안 끝났을 때를 "무효화 안 됨"으로 오판할 수 있다.
    await waitFor(() => expect(screen.getByRole("button", { name: "수정" })).toBeInTheDocument());
    expect(qc.getQueryState(["board"]).isInvalidated, "board는 그대로여야 한다").toBe(false);
  });

  it("반응 토글이 board 캐시를 무효화한다(like_count 열)", async () => {
    const user = userEvent.setup();
    mockApi();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedCaches(qc);
    wrap(qc);

    expect(await screen.findByText("제안 글")).toBeInTheDocument();
    const [postReaction] = screen.getAllByRole("button", { name: "👍" });
    await user.click(postReaction);

    await waitFor(() => {
      expect(qc.getQueryState(["board"]).isInvalidated, "board").toBe(true);
    });
  });

  it("제안 상태 변경이 board 캐시를 무효화한다(idea_status 열)", async () => {
    const user = userEvent.setup();
    mockApi();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedCaches(qc);
    wrap(qc);

    expect(await screen.findByText("제안 글")).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "다음 상태" }));
    await user.click(await screen.findByRole("option", { name: "반려" }));
    await user.click(screen.getByRole("button", { name: "적용" }));

    await waitFor(() => {
      expect(qc.getQueryState(["board"]).isInvalidated, "board").toBe(true);
    });
  });

  it("게시글 삭제가 board-mine 캐시까지 무효화한다(post_count)", async () => {
    const user = userEvent.setup();
    mockApi({ withComment: false, canDeletePost: true });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    seedCaches(qc);
    wrap(qc);

    expect(await screen.findByText("제안 글")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "삭제" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "삭제" }));

    await waitFor(() => {
      expect(qc.getQueryState(["board"]).isInvalidated, "board").toBe(true);
      expect(qc.getQueryState(["home", "today"]).isInvalidated, "home").toBe(true);
      expect(qc.getQueryState(["board-mine"]).isInvalidated, "board-mine").toBe(true);
    });
  });
});
