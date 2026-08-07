import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 읽음 처리 증폭 (PF3).
 *
 * 메시지 한 통이 서버 요청 몇 개가 되는가를 센다. 예전에는 셋이었다:
 *   ① 메시지 폴링(변화를 발견)  ② 읽음 쓰기  ③ **방 목록 전체 재조회**
 * ③ 은 이 앱에서 가장 비싼 조회(H4)이고, 이미 모든 화면에서 주기적으로 돌고 있다.
 * 읽음이 목록에서 바꾸는 값은 그 방의 안 읽음 하나뿐이라 다시 받을 이유가 없다.
 *
 * 여기서 세는 것은 **방 목록 재조회가 사라졌는가** 다. 읽음 쓰기 자체는 남는다 — 그건
 * 서버가 알아야 하는 사실이지 캐시로 대신할 수 있는 것이 아니다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatPane } from "./ChatPane.jsx";
import { markRoomRead } from "./teamchat-unread.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";

const ROOMS = {
  items: [{ id: "r1", kind: "group", title: "방", unread: 2, member_count: 2 }],
  global: { id: "gr", is_global: true, title: "전체 채팅", unread: 1 },
  unread_total: 3,
};

function payload(seq, lastRead) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "방", member_count: 2 },
    members: [], messages: [], people: {}, seq,
    you: { user_id: "u1", role: "member", last_read_seq: lastRead, is_member: true },
  };
}

/* 방 목록은 `/api/team-chat/rooms` 이고 메시지 폴링은 `/api/team-chat/rooms/r1/messages` 다 —
   접두어로 세면 폴링이 목록으로 잘못 세어져 이 테스트가 헛것이 된다(실제로 한 번 그랬다). */
const roomListCalls = () =>
  apiMock.mock.calls.filter((c) => String(c[0]) === "/api/team-chat/rooms").length;
const readWriteCalls = () =>
  apiMock.mock.calls.filter(
    (c) => String(c[0]) === "/api/team-chat/rooms/r1/read" && c[1] && c[1].method === "POST",
  ).length;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  apiMock.mockReset();
});
afterEach(() => { vi.useRealTimers(); });

describe("읽음 처리가 부르는 요청 (PF3)", () => {
  it("읽음 쓰기는 방 목록 재조회를 부르지 않는다", async () => {
    let seq = 0;
    let lastRead = 0;
    apiMock.mockImplementation((url, opts) => {
      if (url === "/api/team-chat/rooms") return Promise.resolve(ROOMS);
      if (url.includes("/read")) { lastRead = seq; return Promise.resolve({ ok: true }); }
      if (url.includes("/messages")) return Promise.resolve(payload(seq, lastRead));
      return Promise.resolve({ ok: true });
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    // 방 목록을 캐시에 올려 둔다 — 실제 앱에서는 셸(사이드바 배지)이 이미 들고 있다.
    qc.setQueryData(["team-chat-rooms"], ROOMS);

    render(
      <QueryClientProvider client={qc}>
        <ToastProvider><ConfirmProvider>
          <ChatPane roomId="r1" interval={3000} idleMax={30000} />
        </ConfirmProvider></ToastProvider>
      </QueryClientProvider>,
    );
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

    const roomsBefore = roomListCalls();
    // 누가 말했다 → 다음 폴링에서 발견 → 읽음 쓰기.
    seq = 5;
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });

    expect(readWriteCalls(), "읽음 쓰기는 나가야 한다").toBe(1);
    expect(roomListCalls() - roomsBefore, "읽음 때문에 목록을 다시 받으면 안 된다").toBe(0);

    // 그리고 캐시의 안 읽음은 실제로 지워져 있어야 한다 — 요청만 줄이고 화면이 틀리면 안 된다.
    const cached = qc.getQueryData(["team-chat-rooms"]);
    expect(cached.items[0].unread).toBe(0);
    expect(cached.unread_total).toBe(1);   // 전체 채팅의 1건은 남는다
  });
});

describe("markRoomRead", () => {
  it("그 방만 0으로 만들고 합계를 다시 센다", () => {
    const next = markRoomRead(ROOMS, "r1");
    expect(next.items[0].unread).toBe(0);
    expect(next.global.unread).toBe(1);
    expect(next.unread_total).toBe(1);
  });

  it("전체 채팅 방도 같은 규칙을 탄다", () => {
    const next = markRoomRead(ROOMS, "gr");
    expect(next.global.unread).toBe(0);
    expect(next.items[0].unread).toBe(2);
    expect(next.unread_total).toBe(2);
  });

  it("원본을 제자리에서 고치지 않는다", () => {
    const before = JSON.stringify(ROOMS);
    markRoomRead(ROOMS, "r1");
    expect(JSON.stringify(ROOMS)).toBe(before);
  });

  it("바뀔 것이 없으면 받은 것을 그대로 돌려준다 (헛된 재렌더 방지)", () => {
    expect(markRoomRead(ROOMS, "없는방")).toBe(ROOMS);
    const zeroed = markRoomRead(ROOMS, "r1");
    expect(markRoomRead(zeroed, "r1")).toBe(zeroed);
    expect(markRoomRead(undefined, "r1")).toBe(undefined);
  });
});
