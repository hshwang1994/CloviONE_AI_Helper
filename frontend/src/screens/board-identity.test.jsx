import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 게시글·댓글이 **작성자가 누구인지** 말한다 (#13 / #8).
 *
 * 사용자 지시: "게시글과 댓글에는 작성자의 부서·팀·직책을 함께 표시한다",
 * "프로필 사진이 다른 사용자 화면에서도 보이는 구조인지 확인한다".
 *
 * 게시판은 `author_name` 하나만 그렸다. 표시 이름에는 유일성 제약이 없으므로
 * (`app/users/models.py`) 동명이인이면 목록의 '작성자' 칸과 댓글 머리글은 **아무것도
 * 답하지 못하는 칸**이다. 채팅 말풍선은 이미 `people` 을 읽어 소속을 그리고 있었다
 * (`ChatPane.jsx`) — 같은 질문에 화면마다 다르게 답하던 상태를 여기서 끝낸다.
 *
 * 화면 규칙 세 가지를 함께 못 박는다. 이것들은 "그리기만 하면 된다"고 넘겼다가
 * 조용히 어수선해지는 자리다:
 *   1) 소속이 없으면 **아무것도 그리지 않는다**(빈 괄호가 더 어수선하다)
 *   2) 사진이 없으면 **빈 원을 만들지 않는다**
 *   3) 보관된 계정이면 (보관됨) — 안 붙이면 답이 안 오는 글에 답글을 단다 (N3)
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { Board } from "./Board.jsx";
import { BoardPost } from "./BoardPost.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const META = { categories: ["공지", "자유"], reaction_emojis: ["👍"], can_moderate: false };

function person(over = {}) {
  return {
    user_id: "u2", display_name: "김철수", dept: "", title: "", org: "",
    archived: false, avatar_url: null, ...over,
  };
}

function wrap(node, entries) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={entries}>
              <Routes>
                <Route path="/board/:id" element={node} />
                <Route path="*" element={node} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

// ── 목록 ────────────────────────────────────────────────────────────────────
function mountList(people) {
  apiMock.mockImplementation((url) => {
    if (url === "/api/board/meta") return Promise.resolve(META);
    if (String(url).startsWith("/api/board/posts")) {
      return Promise.resolve({
        items: [{
          id: "p1", title: "사내 공지", category: "공지", author_user_id: "u2",
          author_name: "김철수", view_count: 3, comment_count: 0, is_pinned: false,
          created_at: "2026-08-01T01:00:00",
        }],
        total: 1, page: 1, page_size: 20, people,
      });
    }
    return Promise.resolve({});
  });
  return wrap(<Board />, ["/board"]);
}

// ── 상세 ────────────────────────────────────────────────────────────────────
function mountDetail({ people, comments = [] }) {
  apiMock.mockImplementation((url) => {
    if (url === "/api/board/meta") return Promise.resolve(META);
    if (String(url) === "/api/board/posts/p1") {
      return Promise.resolve({
        post: {
          id: "p1", category: "자유", title: "본문 제목", body: "본문입니다",
          author_user_id: "u2", author_name: "김철수", is_pinned: false, view_count: 1,
          can_edit: false, can_moderate: false, reactions: [], attachments: [],
          comments, people,
          created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
        },
      });
    }
    return Promise.resolve({ ok: true });
  });
  return wrap(<BoardPost />, ["/board/p1"]);
}

const COMMENT = {
  id: "c1", post_id: "p1", parent_comment_id: null, author_user_id: "u3",
  author_name: "박댓글", body: "좋은 글이네요", reactions: [], can_edit: false,
  created_at: "2026-08-01T02:00:00", updated_at: "2026-08-01T02:00:00",
};

beforeEach(() => apiMock.mockReset());

describe("목록의 작성자 칸", () => {
  it("이름 옆에 부서와 직책이 나온다", async () => {
    mountList({ u2: person({ dept: "ClovirONE팀", title: "팀장" }) });
    expect(await screen.findByText("사내 공지")).toBeInTheDocument();
    expect(screen.getByText(/ClovirONE팀 팀장/)).toBeInTheDocument();
  });

  it("프로필 사진이 목록에도 나온다", async () => {
    const { container } = mountList({ u2: person({ avatar_url: "/api/profile/avatar/u2?v=7" }) });
    expect(await screen.findByText("사내 공지")).toBeInTheDocument();
    expect(container.querySelector('img[src="/api/profile/avatar/u2?v=7"]')).toBeTruthy();
  });

  it("people 이 통째로 없어도 목록은 그려진다", async () => {
    /* 옛 응답·캐시가 섞여 들어와도 목록이 안 보이면 그건 개선이 아니라 고장이다. */
    mountList(undefined);
    expect(await screen.findByText("사내 공지")).toBeInTheDocument();
    expect(screen.getByText("김철수")).toBeInTheDocument();
  });
});

describe("게시글 상세의 글쓴이", () => {
  it("이름 옆에 부서와 직책이 나온다", async () => {
    mountDetail({ people: { u2: person({ dept: "ClovirONE팀", title: "팀장" }) } });
    expect(await screen.findByText("본문입니다")).toBeInTheDocument();
    expect(screen.getByText(/ClovirONE팀 팀장/)).toBeInTheDocument();
  });

  it("프로필 사진이 다른 사람 화면에도 나온다", async () => {
    const { container } = mountDetail({
      people: { u2: person({ avatar_url: "/api/profile/avatar/u2?v=9" }) },
    });
    expect(await screen.findByText("본문입니다")).toBeInTheDocument();
    expect(container.querySelector('img[src="/api/profile/avatar/u2?v=9"]')).toBeTruthy();
  });

  it("소속을 모르면 빈 괄호를 그리지 않는다", async () => {
    const { container } = mountDetail({ people: { u2: person() } });
    expect(await screen.findByText("본문입니다")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\(\s*\)/);
  });

  it("사진이 없으면 빈 원을 만들지 않는다", async () => {
    const { container } = mountDetail({ people: { u2: person() } });
    expect(await screen.findByText("본문입니다")).toBeInTheDocument();
    expect(container.querySelector('img[src*="/api/profile/avatar/"]')).toBeNull();
  });

  it("보관된 계정이면 그렇다고 말한다", async () => {
    mountDetail({ people: { u2: person({ dept: "ClovirONE팀", archived: true }) } });
    expect(await screen.findByText("본문입니다")).toBeInTheDocument();
    expect(screen.getByText("(보관됨)")).toBeInTheDocument();
  });

  it("살아 있는 계정에는 보관 표시를 붙이지 않는다", async () => {
    mountDetail({ people: { u2: person({ dept: "ClovirONE팀" }) } });
    expect(await screen.findByText("본문입니다")).toBeInTheDocument();
    expect(screen.queryByText("(보관됨)")).toBeNull();
  });
});

describe("댓글 작성자", () => {
  it("댓글에도 이름 옆에 소속이 나온다", async () => {
    mountDetail({
      comments: [COMMENT],
      people: {
        u2: person(),
        u3: person({ user_id: "u3", display_name: "박댓글", dept: "인프라팀", title: "수석" }),
      },
    });
    expect(await screen.findByText("좋은 글이네요")).toBeInTheDocument();
    expect(screen.getByText(/인프라팀 수석/)).toBeInTheDocument();
  });

  it("댓글 작성자의 사진도 나온다", async () => {
    const { container } = mountDetail({
      comments: [COMMENT],
      people: {
        u2: person(),
        u3: person({ user_id: "u3", display_name: "박댓글", avatar_url: "/api/profile/avatar/u3?v=3" }),
      },
    });
    expect(await screen.findByText("좋은 글이네요")).toBeInTheDocument();
    expect(container.querySelector('img[src="/api/profile/avatar/u3?v=3"]')).toBeTruthy();
  });

  it("떠난 사람의 댓글이면 그렇다고 말한다", async () => {
    mountDetail({
      comments: [COMMENT],
      people: {
        u2: person(),
        u3: person({ user_id: "u3", display_name: "박댓글", dept: "인프라팀", archived: true }),
      },
    });
    expect(await screen.findByText("좋은 글이네요")).toBeInTheDocument();
    expect(screen.getByText("(보관됨)")).toBeInTheDocument();
  });

  it("신원을 모르는 댓글 작성자여도 댓글은 그려진다", async () => {
    /* 오탐 방지 — 삭제된 계정을 참조하는 옛 댓글에서 화면이 죽으면 안 된다. */
    mountDetail({ comments: [COMMENT], people: { u2: person() } });
    expect(await screen.findByText("좋은 글이네요")).toBeInTheDocument();
    expect(screen.getByText("박댓글")).toBeInTheDocument();
  });
});
