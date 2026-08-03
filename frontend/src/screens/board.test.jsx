import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 자유게시판 목록 계약 테스트.
 *
 * MUI 재설계로 마크업을 통째로 바꾸기 때문에, '무엇이 지켜져야 하는지'를 먼저 못 박는다.
 * 여기서 보는 것들은 전부 조용히 틀릴 수 있는 것들이다:
 *   1) 빈 화면 두 종류를 구분한다 — '아직 글이 없다'와 '검색·필터에 걸리는 글이 없다'는
 *      사용자가 해야 할 일이 정반대다(첫 글을 쓰라 vs 필터를 지워라). 예전엔 둘 다
 *      "아직 게시글이 없습니다 / 첫 이야기를 남겨 보세요"로 뭉개져 있었다.
 *   2) 카테고리 칩이 서버 쿼리에 실제로 반영된다(눌러도 아무 일 없는 필터 방지).
 *   3) 고정 글 배지와 댓글 수가 목록에 남아 있다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Board } from "./Board.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderBoard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Board />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const META = { categories: ["공지", "질문", "자유"], reaction_emojis: ["👍", "🎉"] };

function mockApi(postsByQuery) {
  apiMock.mockImplementation((url) => {
    if (url === "/api/board/meta") return Promise.resolve(META);
    if (String(url).startsWith("/api/board/posts")) return Promise.resolve(postsByQuery(String(url)));
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("빈 화면은 '아직 글이 없음'과 '검색 결과 없음'을 구분한다", () => {
  it("필터가 없으면 첫 글을 쓰라고 안내한다", async () => {
    mockApi(() => ({ items: [] }));
    renderBoard();
    expect(await screen.findByRole("heading", { name: "아직 게시글이 없습니다" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "검색 결과가 없습니다" })).toBeNull();
  });

  it("카테고리를 고른 뒤 0건이면 '검색 결과가 없습니다' + 지우기 CTA", async () => {
    mockApi((url) => (url.includes("category=") ? { items: [] } : { items: [] }));
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("heading", { name: "아직 게시글이 없습니다" });

    await user.click(await screen.findByRole("button", { name: "질문" }));

    expect(await screen.findByRole("heading", { name: "검색 결과가 없습니다" })).toBeInTheDocument();
    const clear = screen.getByRole("button", { name: "검색, 카테고리 지우기" });
    expect(clear).toBeInTheDocument();

    // CTA를 누르면 실제로 필터가 풀려 원래의 온보딩 빈 상태로 돌아온다.
    await user.click(clear);
    expect(await screen.findByRole("heading", { name: "아직 게시글이 없습니다" })).toBeInTheDocument();
  });
});

describe("카테고리 칩은 서버 쿼리에 반영된다", () => {
  it("칩을 누르면 category= 파라미터가 붙은 요청이 나간다", async () => {
    mockApi(() => ({ items: [] }));
    const user = userEvent.setup();
    renderBoard();
    await screen.findByRole("heading", { name: "아직 게시글이 없습니다" });

    await user.click(await screen.findByRole("button", { name: "공지" }));

    await waitFor(() => {
      const urls = apiMock.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("category=" + encodeURIComponent("공지")))).toBe(true);
    });
  });
});

describe("목록 표시", () => {
  it("고정 배지와 댓글 수가 함께 보인다", async () => {
    mockApi(() => ({
      items: [
        { id: "p1", title: "사내 보안 공지", category: "공지", author_name: "김운영", view_count: 12, comment_count: 3, is_pinned: true, created_at: "2026-08-01T01:00:00" },
        { id: "p2", title: "점심 추천", category: "자유", author_name: "박개발", view_count: 4, comment_count: 0, is_pinned: false, created_at: "2026-08-02T01:00:00" },
      ],
    }));
    renderBoard();

    expect(await screen.findByText("사내 보안 공지")).toBeInTheDocument();
    expect(screen.getByText("고정")).toBeInTheDocument();
    expect(screen.getByText("[3]")).toBeInTheDocument();
    // 댓글이 0건인 글에는 대괄호 표시를 붙이지 않는다.
    expect(screen.queryByText("[0]")).toBeNull();
    // 첫 열이 render()를 써도 행 열기 버튼이 이름을 갖는다(openLabel).
    expect(screen.getByRole("button", { name: "상세 보기: 사내 보안 공지" })).toBeInTheDocument();
  });
});
