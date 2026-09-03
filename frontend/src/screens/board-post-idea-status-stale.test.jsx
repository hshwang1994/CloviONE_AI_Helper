import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 「고르고 나서 적용을 누른다」는 두 단계 손짓을 걷었다(2026-09-03 사용자 결정) — 상태는 이제 티켓처럼 배지를 눌러 그 자리에서 고르면 바로 저장된다. 그래서 「적용 전에 다른 글로 넘어가면 고른 값이 따라온다」는 결함 자체가 존재할 수 없다: 아직 적용 안 한 선택이라는 상태가 없기 때문이다. 대신 남는 성질을 잰다 — 다른 제안으로 넘어가면 배지가 그 글의 상태를 말한다. */


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

function ideaPost(id, title, status = "제안") {
  return {
    post: {
      id, kind: "idea", category: "기타", title, body: "본문",
      author_user_id: "u1", author_name: "글쓴이", is_pinned: false, view_count: 1,
      can_edit: false, can_moderate: false, can_change_status: true,
      idea_status: status, next_statuses: ["제안", "검토중", "진행", "완료", "보류"], ticket_page_id: null,
      reactions: [], attachments: [], comments: [], people: {},
      created_at: "2026-08-01T01:00:00", updated_at: "2026-08-01T01:00:00",
    },
  };
}

beforeEach(() => { apiMock.mockReset(); });

describe("다른 제안으로 넘어가면 배지가 그 글의 상태를 말한다", () => {
  it("A 글의 상태가 B 글 배지에 남지 않는다(B는 이미 캐시에 있다)", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((url) => {
      const u = String(url);
      if (u === "/api/board/meta") return Promise.resolve({ categories: [], reaction_emojis: [] });
      if (u === "/api/board/posts/i1/view" || u === "/api/board/posts/i2/view") return Promise.resolve({ ok: true });
      if (u === "/api/board/posts/i1") return Promise.resolve(ideaPost("i1", "제안 A"));
      if (u === "/api/board/posts/i2") return Promise.resolve(ideaPost("i2", "제안 B", "검토중"));
      return Promise.resolve({ ok: true });
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    /* B 글을 이미 한 번 열어 캐시에 있는 상태를 흉내낸다 — isPending 스켈레톤이 뜨지 않아
       상태 배지가 우연히 리마운트되지 않는다(이 시험이 재려는 바로 그 조건). */
    qc.setQueryData(["board-post", "i2"], ideaPost("i2", "제안 B", "검토중"));

    wrap(["/board/i1"], qc);
    expect(await screen.findByText("제안 A")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /제안 상태 바꾸기/ })).toHaveTextContent("제안");

    await user.click(screen.getByRole("button", { name: "다른 제안으로 이동" }));
    expect(await screen.findByText("제안 B")).toBeInTheDocument();

    // B 의 배지는 B 의 상태다 — A 의 값이 따라오지 않는다.
    expect(screen.getByRole("button", { name: /제안 상태 바꾸기/ })).toHaveTextContent("검토중");
  });
});
