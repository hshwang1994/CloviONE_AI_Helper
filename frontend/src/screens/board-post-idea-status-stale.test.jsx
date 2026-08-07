import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 제안(아이디어) 상세의 "다음 상태" 선택도 댓글 초안과 같은 버그를 갖고 있었다
 * (참고: board-post-comment-stale-draft.test.jsx). IdeaStatusBar 는 CommentComposer 와
 * 달리 `key={post.id}` 가 없어서, "/board/:id" 로 다른 제안 글로 이동해도(알림 딥링크 등
 * 인앱 이동, BoardPost 인스턴스는 재사용된다) 드롭다운에서 고른 "다음 상태"·"티켓 프로젝트"
 * 값이 그대로 남는다.
 *
 * 두 제안 글이 같은 상태 어휘("진행" 등 워크플로 상태는 글마다 다시 정의되지 않는다)를
 * 공유하므로, A 글에서 "진행"을 고르고 적용을 누르기 전에 B 글로 넘어가면 B 글의 드롭다운도
 * 이미 "진행"이 선택된 채로 뜬다 — 사용자가 아무것도 고르지 않았는데 "적용" 버튼이 곧바로
 * 눌릴 수 있는 상태가 되고, 누르면 B 글이 사용자가 고르지 않은 상태로 바뀐다(진행이면 엉뚱한
 * 프로젝트에 티켓까지 만들어질 수 있다).
 *
 * B 글을 처음 여는 경우엔 detail.isPending 스켈레톤이 트리를 통째로 갈아 끼우면서 우연히
 * 다시 마운트돼 증상이 가려진다 — comment-thread 테스트와 같은 이유로 B 글을 미리 캐시에
 * 넣어 둔다. */

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
  return <button onClick={() => nav(to)}>다른 제안으로 이동</button>;
}

function wrap(entries, qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={entries}>
              <NavHelper to="/board/i2" />
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

function ideaPost(id, title) {
  return {
    post: {
      id, kind: "idea", category: "기타", title, body: "본문",
      author_user_id: "u1", author_name: "글쓴이", is_pinned: false, view_count: 1,
      can_edit: false, can_moderate: false, can_change_status: true,
      idea_status: "제안", next_statuses: ["진행", "반려"], ticket_page_id: null,
      reactions: [], attachments: [], comments: [], people: {},
      created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
    },
  };
}

beforeEach(() => { apiMock.mockReset(); });

describe("제안 상세의 '다음 상태' 선택은 다른 제안으로 이동하면 비워진다", () => {
  it("A 글에서 고른 '진행'이 B 글 드롭다운까지 따라오지 않는다(B는 이미 캐시에 있다)", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((url) => {
      const u = String(url);
      if (u === "/api/board/meta") return Promise.resolve({ categories: [], reaction_emojis: [] });
      if (u === "/api/board/posts/i1/view" || u === "/api/board/posts/i2/view") return Promise.resolve({ ok: true });
      if (u === "/api/board/posts/i1") return Promise.resolve(ideaPost("i1", "제안 A"));
      if (u === "/api/board/posts/i2") return Promise.resolve(ideaPost("i2", "제안 B"));
      return Promise.resolve({ ok: true });
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    // B 글을 이미 한 번 열어 캐시에 있는 상태를 흉내낸다 — isPending 스켈레톤이 뜨지 않아
    // IdeaStatusBar 가 우연히 리마운트되지 않는다.
    qc.setQueryData(["board-post", "i2"], ideaPost("i2", "제안 B"));

    wrap(["/board/i1"], qc);
    expect(await screen.findByText("제안 A")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "다음 상태" }));
    await user.click(await screen.findByRole("option", { name: "진행" }));
    expect(screen.getByRole("combobox", { name: "다음 상태" })).toHaveTextContent("진행");

    await user.click(screen.getByRole("button", { name: "다른 제안으로 이동" }));
    expect(await screen.findByText("제안 B")).toBeInTheDocument();

    // B 글로 넘어온 뒤에는 아무것도 고르지 않았으므로 드롭다운은 기본값("상태 바꾸기")이어야 한다.
    expect(screen.getByRole("combobox", { name: "다음 상태" })).toHaveTextContent("상태 바꾸기");
    // "진행"을 고를 때만 뜨는 프로젝트 선택도 남아 있으면 안 된다.
    expect(screen.queryByRole("combobox", { name: "티켓 프로젝트" })).toBeNull();
  });
});
