import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 게시글 상세의 빵부스러기(area)는 그 글의 **종류**를 따라야 한다.
 *
 * Board.jsx(목록)는 종류마다 다른 빵부스러기를 쓴다 — 자유게시판은 "자유게시판",
 * 제안 게시판은 "기능 개선 제안". "목록" 버튼(actions)도 이미 종류로 갈려
 * 제안 글에서는 /ideas로, 자유글에서는 /board로 돌아간다.
 *
 * 그런데 상세 페이지의 PageHeader area는 세 상태 모두 "자유게시판"으로 박혀 있었다 —
 * 제안 게시판(/ideas)에서 들어온 글을 열면, "목록"은 종류를 알고 제자리로 돌려보내는데
 * 화면 맨 위 빵부스러기는 "팀 공간 › 자유게시판"이라고 말해 같은 화면 안에서
 * 두 신호가 어긋났다. area는 post.kind를 따라야 한다. */

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

function mockPost(kind) {
  apiMock.mockImplementation((url) => {
    const u = String(url);
    if (u === "/api/board/meta") return Promise.resolve({ categories: [], reaction_emojis: [] });
    if (u === "/api/board/posts/p1") {
      return Promise.resolve({
        post: {
          id: "p1", kind, category: "기타", title: "제목", body: "본문",
          author_user_id: "u1", author_name: "글쓴이", is_pinned: false, view_count: 1,
          can_edit: false, can_moderate: false, reactions: [], attachments: [],
          comments: [], people: {},
          created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
        },
      });
    }
    return Promise.resolve({ ok: true });
  });
}

beforeEach(() => apiMock.mockReset());

describe("게시글 상세의 빵부스러기는 글의 종류를 따른다", () => {
  it("자유게시글이면 '자유게시판'", async () => {
    mockPost("free");
    wrap(["/board/p1"]);
    expect(await screen.findByText("본문")).toBeInTheDocument();
    expect(screen.getByText(/팀 공간.*자유게시판/)).toBeInTheDocument();
  });

  it("제안 글이면(목록 버튼이 /ideas로 돌아가는 것과 같은 종류) '기능 개선 제안'", async () => {
    mockPost("idea");
    wrap(["/board/p1"]);
    expect(await screen.findByText("본문")).toBeInTheDocument();
    expect(screen.getByText(/팀 공간.*기능 개선 제안/)).toBeInTheDocument();
    expect(screen.queryByText(/팀 공간.*자유게시판/)).toBeNull();
  });

  /* 로딩·오류 상태는 아직 post.kind를 모른다(주소 하나("/board/:id")를 자유·제안 글이 함께
   * 쓴다 — BoardPost.jsx 위쪽 boardArea 주석 참고). 이 두 상태에서 area를 "자유게시판"으로
   * 단정해 두면, 실제로는 제안 글인데(또는 어느 쪽인지 아직 모르는데) 화면이 확정된 답을
   * 잘못 말한다 — 로딩된 뒤의 상태만 고치고 이 두 상태를 놓치면 위 두 시험은 여전히 통과한다. */
  it("아직 응답이 없는 로딩 중에는 '자유게시판'이라 단정하지 않는다", async () => {
    let resolvePost;
    apiMock.mockImplementation((url) => {
      const u = String(url);
      if (u === "/api/board/meta") return Promise.resolve({ categories: [], reaction_emojis: [] });
      if (u === "/api/board/posts/p1") return new Promise((res) => { resolvePost = res; });
      return Promise.resolve({ ok: true });
    });
    wrap(["/board/p1"]);
    expect(screen.getByText("게시글")).toBeInTheDocument();   // 제목은 즉시 뜬다(로딩 스켈레톤)
    expect(screen.queryByText(/자유게시판/)).toBeNull();
    resolvePost({
      post: {
        id: "p1", kind: "idea", category: "기타", title: "제목", body: "본문",
        author_user_id: "u1", author_name: "글쓴이", is_pinned: false, view_count: 1,
        can_edit: false, can_moderate: false, reactions: [], attachments: [],
        comments: [], people: {},
        created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
      },
    });
    expect(await screen.findByText(/팀 공간.*기능 개선 제안/)).toBeInTheDocument();
  });

  /* SEM-03 재검증(2026-08-13) — 2026-08-12 "구현완료" 기록이 이 화면도 h1 정확히 1개라고
   * 했지만, 그 확인은 이 파일 소스에 리터럴로 적힌 component="h1"만 grep으로 셌다 —
   * PageHeader(kit.jsx)가 내부적으로 만드는 h1은 다른 파일이라 그 grep에 안 잡혀, 실제로는
   * PageHeader의 "게시글"과 카드 안 진짜 제목까지 h1이 둘이었다(실제 렌더로 재확인). */
  it("h1이 하나뿐이다 — PageHeader가 이제 진짜 제목을 보여준다", async () => {
    mockPost("free");
    wrap(["/board/p1"]);
    expect(await screen.findByText("본문")).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent("제목");
  });

  it("조회가 실패해도 '자유게시판'이라 단정하지 않는다", async () => {
    apiMock.mockImplementation((url) => {
      const u = String(url);
      if (u === "/api/board/meta") return Promise.resolve({ categories: [], reaction_emojis: [] });
      if (u === "/api/board/posts/p1") return Promise.reject(new Error("찾을 수 없습니다."));
      return Promise.resolve({ ok: true });
    });
    wrap(["/board/p1"]);
    expect(await screen.findByText("찾을 수 없습니다.")).toBeInTheDocument();
    expect(screen.queryByText(/자유게시판/)).toBeNull();
  });
});
