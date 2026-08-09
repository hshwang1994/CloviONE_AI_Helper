import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 전체 채팅에서 남이 부른 `@내이름`이 강조되는가 (step 9 #3).
 *
 * `/api/team-chat/directory`는 **호출자 본인을 항상 뺀다**(1:1 상대 고르기용,
 * app/team_chat/repository.py::directory). 전체 채팅 방은 `chat_room_members` 행이
 * 없어(마이그 0021) `members`에도 내가 없다 - 렌더용 멘션 후보 목록(`mentionNames`)의
 * 두 출처(전체 채팅=디렉터리, 그 외=참여자) 어느 쪽에도 내 이름이 없는 유일한 조합이다.
 * ChatPane.jsx가 `you.display_name`(app/team_chat/router.py에 새로 실은 값)으로 그
 * 빈자리를 채운다 - 이 테스트는 그 배선이 실제로 닿아 화면에 강조가 뜨는지 본다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatPane } from "./ChatPane.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ME = "u1";
const OTHER = "u2";

function payload(over = {}) {
  return {
    room: { id: "global", kind: "group", is_global: true, title: "전체 채팅", member_count: 0 },
    // 전체 채팅은 멤버십 행이 없다 — 내 이름이 여기 없는 것 자체가 정상 상태다.
    members: [],
    messages: [{
      seq: 1, kind: "text", sender_user_id: OTHER, sender_name: "동료",
      body: "@나 확인 부탁드려요", created_at: "2026-08-03T01:02:03", mentions_me: true, images: [],
    }],
    seq: 1,
    you: {
      user_id: ME, display_name: "나", role: null, last_read_seq: 0, is_member: false,
      can_disband: false, can_hide: false, can_manage: false,
    },
    ...over,
  };
}

function mount(data, directoryUsers) {
  apiMock.mockImplementation((url) => {
    const u = String(url);
    if (u.startsWith("/api/team-chat/rooms/global/messages?")) return Promise.resolve(data);
    // 디렉터리는 호출자를 항상 뺀다 — 목업도 서버와 같은 모양으로 둔다(내가 없다).
    if (u.startsWith("/api/team-chat/directory")) {
      return Promise.resolve({ users: directoryUsers || [{ user_id: "u9", display_name: "전사멤버" }] });
    }
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <ChatPane roomId="global" interval={false} />
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("전체 채팅 — 남이 부른 내 이름이 강조된다", () => {
  it("디렉터리에 내가 없어도(항상 빠진다) @내이름이 밑줄 없는 칩으로 렌더된다", async () => {
    mount(payload());

    const mention = await screen.findByText("@나");
    // 멘션은 <Box component=\"span\">로 렌더되고 링크(<a>)가 아니다 — 누를 곳 없는
    // 밑줄이 아니라 배경 칩이어야 한다(ChatBubbleText.jsx).
    expect(mention.tagName.toLowerCase()).not.toBe("a");
    expect(mention.closest("a")).toBeNull();
  });

  it("디렉터리 응답이 비어 있어도(전사 인원 0명) 여전히 내 이름은 강조된다", async () => {
    mount(payload(), []);
    await waitFor(() => expect(screen.getByText("@나")).toBeInTheDocument());
  });
});
