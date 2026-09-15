import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 말풍선의 새 동작 — 내 메시지 삭제 · 1:1 읽음 표시 · 링크/멘션 렌더 (PLAN Phase 3 §F) · 말풍선 규격(핸드오프 E).
 *
 * 여기서 지키는 것 넷:
 *  1. 지우기는 **내 말에만** 보인다(서버가 다시 검사하지만 남의 말에 지우기 버튼이 보이면
 *     누를 때마다 403이 난다).
 *  2. 지우기는 되돌릴 수 없어 확인을 받는다.
 *  3. 읽음 표시는 **1:1에서 내가 마지막으로 보낸 말 한 줄에만**. 여러 명이면 '읽음'이 누구
 *     기준인지 말할 수 없고, 모든 말풍선에 붙이면 대화가 상태 라벨로 뒤덮인다.
 *  4. 본문의 링크는 http/https만, 항상 `rel="noopener noreferrer"`. `javascript:`가 한 번이라도
 *     <a href>가 되면 그건 저장형 XSS다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatPane } from "./ChatPane.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ME = "u1";
const PEER = "u2";

function msg(over = {}) {
  return {
    seq: 1, kind: "text", sender_user_id: ME, sender_name: "나",
    body: "안녕", created_at: "2026-08-03T01:02:03", mentions_me: false, images: [], ...over,
  };
}

function payload(over = {}) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "방", member_count: 2 },
    members: [
      { user_id: ME, name: "나", role: "owner", last_read_seq: 9, online: true },
      { user_id: PEER, name: "상대", role: "member", last_read_seq: 0, online: false },
    ],
    messages: [msg()],
    seq: 1,
    you: { user_id: ME, role: "owner", last_read_seq: 9, is_member: true,
           can_disband: true, can_hide: false, can_manage: true },
    ...over,
  };
}

function mount(data) {
  apiMock.mockImplementation((url) => {
    if (String(url).startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(data);
    if (String(url).startsWith("/api/team-chat/directory")) return Promise.resolve({ users: [] });
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <ChatPane roomId="r1" interval={false} />
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>
  );
}

const posted = (prefix) => apiMock.mock.calls.filter(
  (c) => String(c[0]).startsWith(prefix) && c[1] && c[1].method === "POST"
);

beforeEach(() => { apiMock.mockReset(); });

// ── 1. 내 메시지 삭제 ─────────────────────────────────────────────────────

describe("메시지 삭제", () => {
  it("내 말에만 지우기 버튼이 있다", async () => {
    mount(payload({
      seq: 2,
      messages: [msg({ seq: 1, body: "내 말" }),
                 msg({ seq: 2, sender_user_id: PEER, sender_name: "상대", body: "남의 말" })],
    }));
    await screen.findByText("내 말");
    expect(screen.getAllByRole("button", { name: /메시지 삭제/ })).toHaveLength(1);
  });

  it("확인을 받은 뒤에만 삭제 요청이 나간다", async () => {
    const user = userEvent.setup();
    mount(payload());
    await user.click(await screen.findByRole("button", { name: /메시지 삭제/ }));
    // 확인 창에서 취소하면 아무 요청도 나가지 않는다.
    await user.click(await screen.findByRole("button", { name: "취소" }));
    expect(posted("/api/team-chat/rooms/r1/messages/1/delete")).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /메시지 삭제/ }));
    await user.click(await screen.findByRole("button", { name: "삭제" }));
    await waitFor(() => expect(posted("/api/team-chat/rooms/r1/messages/1/delete")).toHaveLength(1));
  });

  it("시스템 메시지에는 지우기 버튼이 없다 — 서버도 409로 막는 동작이다", async () => {
    mount(payload({ messages: [msg({ kind: "system", sender_user_id: null, body: "방을 만들었습니다." })] }));
    await screen.findByText("방을 만들었습니다.");
    expect(screen.queryByRole("button", { name: /메시지 삭제/ })).toBeNull();
  });
});

// ── 2. 1:1 읽음 표시 ────────────────────────────────────────────────────────

describe("읽음 표시", () => {
  const direct = (peerRead) => payload({
    room: { id: "r1", kind: "direct", is_global: false, title: "상대", member_count: 2 },
    members: [
      { user_id: ME, name: "나", role: "member", last_read_seq: 9, online: true },
      { user_id: PEER, name: "상대", role: "member", last_read_seq: peerRead, online: true },
    ],
    you: { user_id: ME, role: "member", last_read_seq: 9, is_member: true,
           can_disband: false, can_hide: true, can_manage: false },
  });

  it("상대가 읽었으면 '읽음', 아니면 '안 읽음'", async () => {
    const { unmount } = mount(direct(0));
    expect(await screen.findByText("안 읽음")).toBeInTheDocument();
    unmount();
    mount(direct(1));
    expect(await screen.findByText("읽음")).toBeInTheDocument();
  });

  it("내가 마지막으로 보낸 한 줄에만 붙는다", async () => {
    mount({
      ...direct(0),
      seq: 3,
      messages: [msg({ seq: 1, body: "첫 말" }), msg({ seq: 2, body: "둘째 말" }),
                 msg({ seq: 3, sender_user_id: PEER, sender_name: "상대", body: "답" })],
    });
    await screen.findByText("둘째 말");
    expect(screen.getAllByText(/^(읽음|안 읽음)$/)).toHaveLength(1);
  });

  it("여러 명 있는 그룹 방에는 그리지 않는다 — '읽음'이 누구 기준인지 말할 수 없다", async () => {
    mount(payload());
    await screen.findByText("안녕");
    expect(screen.queryByText(/^(읽음|안 읽음)$/)).toBeNull();
  });
});

// ── 3. 링크·멘션 렌더 ───────────────────────────────────────────────────────

describe("본문 렌더", () => {
  it("http(s) 링크는 새 창 + rel=noopener noreferrer 로 그린다", async () => {
    mount(payload({ messages: [msg({ body: "문서는 https://intra.example/deploy 참고" })] }));
    const a = await screen.findByRole("link", { name: "https://intra.example/deploy" });
    expect(a).toHaveAttribute("href", "https://intra.example/deploy");
    expect(a).toHaveAttribute("rel", "noopener noreferrer");
    expect(a).toHaveAttribute("target", "_blank");
  });

  it("javascript:/data: 는 링크가 되지 않고 글자로 남는다", async () => {
    mount(payload({ messages: [msg({ body: "javascript:alert(1) 와 data:text/html,x 조심" })] }));
    await screen.findByText(/javascript:alert\(1\)/);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("아는 참여자의 @이름은 강조 조각이 되고, 모르는 이름은 그냥 글자다", async () => {
    mount(payload({ messages: [msg({ body: "@상대 와 @없는사람 확인" })] }));
    const known = await screen.findByText("@상대");
    expect(known.tagName).toBe("SPAN");             // 조각으로 떨어져 나왔다
    expect(screen.queryByText("@없는사람")).toBeNull(); // 쪼개지지 않고 주변 글자에 붙어 있다
    expect(screen.getByText(/@없는사람 확인/)).toBeInTheDocument();
  });

  it("나를 부른 말에는 표시가 붙는다(판정은 서버의 mentions_me)", async () => {
    /* 표식이 붙는 자리가 말풍선에서 **줄 전체**로 옮겼다(지시 17). 말풍선이 없어졌기
       때문이다 — 지금은 모든 줄이 아바타·이름·시각·본문이라는 같은 구조다. 지키는
       성질은 그대로다: 알림은 갔는데 대화에서 어느 줄인지 못 찾으면 알림만 시끄럽다. */
    mount(payload({
      messages: [msg({ seq: 1, sender_user_id: PEER, sender_name: "상대", body: "@나 봐주세요", mentions_me: true })],
    }));
    const row = (await screen.findByText("@나")).closest("[data-chat-row]");
    expect(row).toBeTruthy();
    const style = getComputedStyle(row);
    expect(style.borderInlineStartStyle || style.borderLeftStyle).toBe("solid");
  });

  it("🔴 부르지 않은 말에는 그 표시가 없다 — 전부 표시되면 아무것도 표시가 아니다", async () => {
    mount(payload({
      messages: [msg({ seq: 1, sender_user_id: PEER, sender_name: "상대", body: "그냥 하는 말" })],
    }));
    const row = (await screen.findByText("그냥 하는 말")).closest("[data-chat-row]");
    const style = getComputedStyle(row);
    expect(style.borderInlineStartStyle || style.borderLeftStyle || "none").not.toBe("solid");
  });
});

// ── 4. 말풍선 규격 (핸드오프 RULES §9 · ui/chat.js::CHAT) ─────────────────────

describe("말풍선 규격", () => {
  it("상대는 왼쪽 함몰면 말풍선이고 묶음 첫 말풍선의 시작 모서리가 모인다, 나는 오른쪽 Primary 말풍선이고 묶음 마지막의 끝 모서리가 모인다", async () => {
    mount(payload({
      seq: 4,
      messages: [
        msg({ seq: 1, sender_user_id: PEER, sender_name: "상대", body: "상대 첫 말", created_at: "2026-08-03T01:00:00" }),
        msg({ seq: 2, sender_user_id: PEER, sender_name: "상대", body: "상대 둘째 말", created_at: "2026-08-03T01:00:30" }),
        msg({ seq: 3, body: "내 첫 말", created_at: "2026-08-03T01:01:00" }),
        msg({ seq: 4, body: "내 마지막 말", created_at: "2026-08-03T01:01:30" }),
      ],
    }));
    const bubbleOf = async (text) => (await screen.findByText(text)).closest("[data-chat-bubble]");
    const theirsFirst = getComputedStyle(await bubbleOf("상대 첫 말"));
    const theirsNext = getComputedStyle(await bubbleOf("상대 둘째 말"));
    const mineFirst = getComputedStyle(await bubbleOf("내 첫 말"));
    const mineLast = getComputedStyle(await bubbleOf("내 마지막 말"));

    expect((await bubbleOf("상대 첫 말")).getAttribute("data-chat-bubble")).toBe("theirs");
    expect((await bubbleOf("내 첫 말")).getAttribute("data-chat-bubble")).toBe("mine");
    // 모서리 12, 연결 모서리 4 — 상대는 첫 말풍선의 시작, 나는 마지막 말풍선의 끝.
    expect(theirsFirst.borderStartStartRadius).toBe("4px");
    expect(theirsNext.borderStartStartRadius).not.toBe("4px");
    expect(mineLast.borderEndEndRadius).toBe("4px");
    expect(mineFirst.borderEndEndRadius).not.toBe("4px");
    // 폭은 내용만큼이다 — 한두 글자 말풍선이 줄 폭으로 넓어지지 않는다.
    expect(mineFirst.width).toBe("fit-content");
    // 면: 상대는 테두리가 있는 함몰면, 나는 테두리 없는 Primary 면.
    expect(theirsFirst.borderTopStyle).toBe("solid");
    expect(mineFirst.borderTopStyle === "none" || mineFirst.borderTopWidth === "0px" || mineFirst.borderTopStyle === "").toBe(true);
    expect(mineFirst.backgroundColor).not.toBe(theirsFirst.backgroundColor);
  });

  it("말풍선 묶음은 줄 폭의 68% 에서 멈추고, 시각은 말풍선 밖에 선다", async () => {
    mount(payload({ messages: [msg({ seq: 1, body: "밖의 시각" })] }));
    const bubble = (await screen.findByText("밖의 시각")).closest("[data-chat-bubble]");
    const group = bubble.parentElement;
    expect(getComputedStyle(group).maxWidth).toBe("68%");
    const time = group.querySelector("time");
    expect(time).toBeTruthy();
    expect(bubble.contains(time)).toBe(false);
    expect(getComputedStyle(time).fontSize).toBe("0.6875rem");
  });
});
