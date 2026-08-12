import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 홈 화면의 **분당 요청 수** 예산 (PF1).
 *
 * 왜 이 파일이 있는가. 백로그의 "홈에서 분당 24.7요청"은 손으로 센 숫자였고, 손으로 센
 * 숫자는 코드가 바뀌는 순간 낡는다. 폴링 하나만 새로 붙여도 아무도 모르게 두 배가 되는데,
 * 증상은 "요즘 좀 느리다"라 원인이 안 보인다. 그래서 **세는 일을 코드에 둔다.**
 *
 * 세는 방법: 진짜 셸(AppShell) 안에 진짜 홈(Home)을 띄우고, 가짜 타이머로 60초를 흘린 뒤
 * `api()` 호출 수를 센다. 초기 로드분은 세지 않는다 — 문제는 "탭을 열어 둔 채로 계속
 * 나가는 요청"이지 첫 화면이 아니다.
 *
 * 이 테스트가 실제로 값을 본다는 증거: 아래 첫 케이스가 **폴링 출처별 내역**을 함께
 * 단언한다. 총합만 보면 한쪽이 늘고 다른 쪽이 줄어 합이 같아지는 경우를 놓친다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1", display_name: "나" } }) }));

import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { Home } from "../screens/Home.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* jsdom 에는 matchMedia 가 없다 — 없으면 MUI 가 전부 '좁은 화면'으로 판단해 사이드바가
   통째로 안 그려지고, 그러면 사이드바 폴링을 세지 못한 채 통과한다. */
function wideViewport() {
  window.matchMedia = (query) => ({
    matches: /min-width/.test(query),
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
}

const ROOM = { id: "gr", kind: "group", is_global: true, title: "전체 채팅", member_count: 3 };

/* 조용한 서버 — 아무 일도 일어나지 않는 평범한 오후. 이 상태에서 나가는 요청이
   '가만히 있어도 드는 비용'이다. */
function quietServer() {
  apiMock.mockImplementation((url) => {
    if (url.startsWith("/api/team-chat/rooms/") && url.includes("/messages")) {
      return Promise.resolve({
        room: ROOM, members: [], messages: [], seq: 0, people: {},
        you: { user_id: "u1", role: null, last_read_seq: 0, is_member: false },
      });
    }
    if (url === "/api/team-chat/rooms") return Promise.resolve({ items: [], global: { id: "gr" }, unread_total: 0 });
    if (url === "/api/team-chat/directory") return Promise.resolve({ users: [] });
    if (url === "/api/notifications/unread-count") return Promise.resolve({ unread: 0, badge: 0, by_type: {} });
    if (url === "/api/home/today") return Promise.resolve({ ok: true, tickets: {}, inbox: {}, recent: {}, sync: null });
    if (url === "/api/board/mine") return Promise.resolve({ summary: {} });
    if (url === "/api/system/status") return Promise.resolve({ notices: [], poll_seconds: 120 });
    if (url === "/api/announcements") return Promise.resolve({ items: [] });
    if (url === "/api/admin/impersonation/state") return Promise.resolve({ impersonating: false });
    if (url.startsWith("/api/assistant/")) return Promise.resolve({ ok: true });
    return Promise.resolve({ items: [] });
  });
}

function mountHome() {
  const qc = new QueryClient({
    defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30 * 1000, retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/me"]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={USER_NAV} ariaLabel="사용자 메뉴" isUser showMenu>
                <Home />
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** 60초를 흘리고, 그동안 나간 요청을 경로별로 센다(초기 로드는 뺀다). */
async function requestsPerMinute() {
  mountHome();
  // 초기 로드가 다 끝날 때까지 흘린다(여기까지는 세지 않는다).
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  apiMock.mockClear();
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

  const byPath = {};
  for (const call of apiMock.mock.calls) {
    const path = String(call[0]).split("?")[0];
    byPath[path] = (byPath[path] || 0) + 1;
  }
  return { total: apiMock.mock.calls.length, byPath };
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  wideViewport();
  apiMock.mockReset();
  quietServer();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("홈 화면 요청 예산 (PF1)", () => {
  it("가만히 둔 홈은 분당 10요청을 넘지 않는다", async () => {
    // VIS-160(2026-08-12): 예산이 8 → 10으로 올랐다 — 늘어난 2가 우연한 회귀가 아니라
    // /api/home/today의 refetchInterval(Home.jsx)이다. staleTime만으로는 화면이 떠 있는
    // 동안 절대 재조회가 안 일어나는 버그를 고치며 의도적으로 늘었다(30초마다 1회 ×
    // 60초 측정 구간 = 2). 다음에 이 숫자가 또 뛰면 이번처럼 "무엇이 늘었는지"부터 본다.
    const { total, byPath } = await requestsPerMinute();
    // 실패했을 때 어디가 범인인지 바로 보이게 내역을 메시지에 싣는다.
    expect(total, `분당 ${total}요청, 내역: ${JSON.stringify(byPath)}`).toBeLessThanOrEqual(10);
  });

  it("가장 뜨거운 경로(팀 채팅 메시지 폴링)가 분당 6회를 넘지 않는다", async () => {
    const { byPath } = await requestsPerMinute();
    const msgs = byPath["/api/team-chat/rooms/gr/messages"] || 0;
    expect(msgs, `메시지 폴링 분당 ${msgs}회`).toBeLessThanOrEqual(6);
  });

  it("VIS-160: 홈을 띄워 둔 채로 있으면 /api/home/today가 실제로 다시 불린다", async () => {
    // staleTime만 있고 refetchInterval이 없으면 이 경로는 초기 로드 이후 0회로 남는다
    // (다음 mount나 refetchOnWindowFocus를 기다려야 하는데, 홈은 탭을 오래 열어 두는
    // 화면이라 둘 다 한참 뒤에나 온다) — 그 상태가 이 버그였다.
    const { byPath } = await requestsPerMinute();
    const today = byPath["/api/home/today"] || 0;
    expect(today, `/api/home/today 분당 ${today}회`).toBeGreaterThan(0);
  });

  it("세는 장치가 실제로 요청을 본다", async () => {
    // 이 단언이 없으면 위 두 개는 "아무것도 안 세고 통과"할 수 있다.
    const { total } = await requestsPerMinute();
    expect(total).toBeGreaterThan(0);
  });
});
