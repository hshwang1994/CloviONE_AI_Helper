import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 말풍선이 **누가 어느 조직 어느 부서 사람인지** 말한다 (N4 / N3).
 *
 * 서버(`app/team_chat/router.py`)는 메시지 응답에 `people: {uid: identity(...)}` 를
 * **통째로 실어 보내고 있었는데 프런트 전체에서 `people` 참조가 0건이었다.**
 * 말풍선은 `sender_name` 하나만 그렸다 — 사용자 지시("채팅·대화·댓글 작성에서 어느 조직
 * 어느 부서인지 나와야 한다")가 참여자 목록에서만 이행되고 대화 본문에서는 payload 까지
 * 만들어 놓고 안 그린 상태였다. **같은 이름 두 사람이 한 방에서 대화하면 구분할 수 없다.**
 *
 * 그리고 퇴사자는 참여자·발신자로 영원히 살아 있었다(N3) — 보는 사람은 답이 안 오는
 * 대화를 며칠 기다린다. 신원에 `archived` 를 실어 화면이 그 사실을 말한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatPane } from "./ChatPane.jsx";

function payload(people) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "방", member_count: 3 },
    members: [],
    messages: [
      { seq: 1, kind: "text", sender_user_id: "u2", sender_name: "김철수",
        body: "안녕하세요", created_at: "2026-08-01T09:00:00", images: [] },
    ],
    seq: 1,
    you: { user_id: "u1", role: "member", last_read_seq: 1, is_member: true,
           can_disband: false, can_hide: false },
    people,
  };
}

function mount(p) {
  apiMock.mockImplementation((url) => {
    if (String(url).startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(p);
    return Promise.resolve({ ok: true, items: [] });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChatPane roomId="r1" interval={false} />
    </QueryClientProvider>,
  );
}

describe("말풍선 신원", () => {
  beforeEach(() => apiMock.mockReset());

  it("보낸 사람 이름 옆에 소속이 나온다", async () => {
    mount(payload({ u2: { user_id: "u2", display_name: "김철수", dept: "ClovirONE팀", title: "팀장", org: "굿모닝아이텍", archived: false } }));
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(screen.getByText(/ClovirONE팀 팀장/)).toBeInTheDocument();
  });

  it("소속을 모르면 빈 괄호를 그리지 않는다", async () => {
    const { container } = mount(payload({ u2: { user_id: "u2", display_name: "김철수", dept: "", title: "", org: "", archived: false } }));
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(container.textContent).not.toMatch(/\(\s*\)/);
  });

  it("보관된 계정이면 그렇다고 말한다", async () => {
    mount(payload({ u2: { user_id: "u2", display_name: "김철수", dept: "ClovirONE팀", title: "", org: "", archived: true } }));
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(screen.getByText("(보관됨)")).toBeInTheDocument();
  });

  it("살아 있는 계정에는 보관 표시를 붙이지 않는다", async () => {
    mount(payload({ u2: { user_id: "u2", display_name: "김철수", dept: "ClovirONE팀", title: "", org: "", archived: false } }));
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(screen.queryByText("(보관됨)")).toBeNull();
  });

  it("남의 프로필 사진이 말풍선에 나온다", async () => {
    /* X13: 사진 기능이 있는데 **자기 우상단에만** 보였다. 서빙 경로는 이미 전 직원
       대상이었고 빠져 있던 건 남의 주소를 알려 주는 payload 하나뿐이었다. */
    const { container } = mount(payload({ u2: { user_id: "u2", display_name: "김철수", dept: "", title: "", org: "", archived: false, avatar_url: "/api/profile/avatar/u2?v=7" } }));
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(container.querySelector('img[src="/api/profile/avatar/u2?v=7"]')).toBeTruthy();
  });

  it("사진이 없으면 빈 원을 만들지 않는다", async () => {
    const { container } = mount(payload({ u2: { user_id: "u2", display_name: "김철수", dept: "", title: "", org: "", archived: false, avatar_url: null } }));
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(container.querySelector('img[src*="/api/profile/avatar/"]')).toBeNull();
  });

  it("people 이 통째로 없어도 말풍선은 그려진다", async () => {
    /* 옛 응답·캐시가 섞여 들어와도 대화가 안 보이면 그건 개선이 아니라 고장이다. */
    mount(payload(undefined));
    await waitFor(() => expect(screen.getByText("안녕하세요")).toBeInTheDocument());
    expect(screen.getByText(/김철수/)).toBeInTheDocument();
  });
});
