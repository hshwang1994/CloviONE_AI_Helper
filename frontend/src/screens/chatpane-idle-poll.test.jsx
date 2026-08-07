import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 팀 채팅 폴링이 **조용할 때만** 느려지는가 (PF1).
 *
 * 규칙 자체는 teamchat-poll.test.js 가 순수 함수로 고정한다. 여기서 확인하는 것은 배선이다:
 *   - 아무 일도 없는 방에서 요청이 실제로 줄어드는가
 *   - **말이 오가기 시작하면 곧바로 원래 속도로 돌아오는가** ← 이게 없으면 이 최적화는
 *     그냥 "채팅이 느려졌다"이다. 성능을 고친 척하면서 기능을 깎는 가장 흔한 방식이다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatPane } from "./ChatPane.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";

function payload(seq) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "방", member_count: 2 },
    members: [], messages: [], people: {}, seq,
    you: { user_id: "u1", role: "member", last_read_seq: seq, is_member: true },
  };
}

function mount({ interval, idleMax }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider><ConfirmProvider>
        <ChatPane roomId="r1" interval={interval} idleMax={idleMax} />
      </ConfirmProvider></ToastProvider>
    </QueryClientProvider>,
  );
}

function pollCount() {
  return apiMock.mock.calls.filter(
    (c) => String(c[0]).includes("/messages?since=0") && !(c[1] && c[1].method),
  ).length;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  apiMock.mockReset();
});
afterEach(() => { vi.useRealTimers(); });

describe("팀 채팅 폴링 간격", () => {
  it("아무 말도 없는 방은 분당 20회에서 5회로 준다", async () => {
    apiMock.mockImplementation(() => Promise.resolve(payload(0)));
    mount({ interval: 3000, idleMax: 30000 });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    const before = pollCount();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(pollCount() - before).toBe(5);
  });

  it("말이 오가는 방은 base 간격을 그대로 지킨다", async () => {
    // 응답할 때마다 seq 가 오른다 = 계속 무슨 일이 일어나는 방.
    let seq = 0;
    apiMock.mockImplementation(() => Promise.resolve(payload((seq += 1))));
    mount({ interval: 3000, idleMax: 30000 });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    const before = pollCount();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    // 3초 간격이면 20회. 조용한 방(5회)과 **값이 실제로 다르다**.
    expect(pollCount() - before).toBe(20);
  });

  it("조용하던 방에 말이 들어오면 다음 폴링부터 base 로 돌아온다", async () => {
    let seq = 0;
    apiMock.mockImplementation(() => Promise.resolve(payload(seq)));
    mount({ interval: 3000, idleMax: 30000 });
    // 충분히 조용하게 둬서 간격을 상한까지 늘려 놓는다.
    await act(async () => { await vi.advanceTimersByTimeAsync(180_000); });

    // 같은 길이(9초)의 창을 두 번 잰다 — '조용할 때'와 '말이 들어온 직후'.
    // 절대 횟수를 못 박으면 폴링이 초 경계에 어떻게 걸리느냐에 따라 흔들린다.
    const idleStart = pollCount();
    await act(async () => { await vi.advanceTimersByTimeAsync(9_000); });
    const idleWindow = pollCount() - idleStart;

    // 누가 말했다. 간격이 늘어난 상태라 그 변화를 받는 시점은 최대 상한(30초) 뒤다 —
    // 그 시점을 손으로 어림하면 테스트가 타이밍에 기대게 된다. **관측될 때까지 기다린다.**
    seq = 1;
    const beforeChange = pollCount();
    for (let i = 0; i < 60 && pollCount() === beforeChange; i += 1) {
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    }
    expect(pollCount(), "상한 안에 변화를 받아야 한다").toBeGreaterThan(beforeChange);

    const after = pollCount();
    await act(async () => { await vi.advanceTimersByTimeAsync(9_000); });
    const activeWindow = pollCount() - after;

    expect(idleWindow, "조용할 때 9초 창").toBeLessThanOrEqual(1);
    expect(activeWindow, "말이 들어온 뒤 9초 창").toBeGreaterThanOrEqual(2);
    expect(activeWindow).toBeGreaterThan(idleWindow);
  });

  it("interval={false} 로 끈 폴링은 되살아나지 않는다", async () => {
    apiMock.mockImplementation(() => Promise.resolve(payload(0)));
    mount({ interval: false, idleMax: 30000 });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    const before = pollCount();
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(pollCount() - before).toBe(0);
  });
});
