import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 사이드바 '채팅방' 안 읽음 배지.
 *
 * 배지는 navConfig의 `badge` 키로만 선언하고 숫자는 셸이 채운다. 셸에 경로를
 * 하드코딩(`it.to === "/chat-rooms"`)하면 다음 배지를 붙일 때 if가 또 는다.
 *
 * 그리고 **폴링을 새로 만들지 않는다** — 채팅방 화면이 이미 같은 queryKey로 방 목록을
 * 받고 있고 서버가 그 응답에 unread_total을 실어 준다. 배지 하나 때문에 엔드포인트나
 * 폴링을 늘리면 가장 뜨거운 경로가 두 배가 된다. 아래 마지막 테스트가 그걸 고정한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* jsdom에는 matchMedia가 없다. 그러면 MUI의 useMediaQuery가 항상 false를 돌려주고,
   셸은 좁은 화면으로 판단해 사이드바를 아예 렌더하지 않는다 — 배지도 당연히 안 나온다.
   (chat-state.test.jsx가 같은 이유로 같은 처방을 쓴다.)
   min-width 질의에 true를 주어 '넓은 화면'으로 만든다. */
function wideViewport() {
  window.matchMedia = (query) => ({
    matches: /min-width/.test(query),
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
}

function renderShell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              {/* App.jsx가 넘기는 것과 같은 조합. nav나 showMenu를 빠뜨리면 사이드바가
                  통째로 안 그려져서, 배지가 없는 게 아니라 사이드바가 없는 상태를
                  시험하게 된다(실제로 그렇게 두 번 헛짚었다). */}
              <AppShell nav={USER_NAV} ariaLabel="사용자 메뉴" isUser showMenu>
                <div>본문</div>
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** 셸이 부르는 모든 엔드포인트에 답한다. 방 목록만 unread_total을 바꿔 끼운다. */
function mockApi(unreadTotal) {
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/team-chat/rooms")) {
      return Promise.resolve({ rooms: [], global: null, unread_total: unreadTotal });
    }
    if (path.startsWith("/api/notifications")) return Promise.resolve({ items: [], unread: 0 });
    return Promise.resolve({});
  });
}

describe("사이드바 안 읽음 배지", () => {
  beforeEach(() => { apiMock.mockReset(); wideViewport(); });

  it("안 읽음이 있으면 숫자를 보인다", async () => {
    mockApi(3);
    renderShell();
    await waitFor(() => expect(screen.getByLabelText("안 읽음 3건")).toHaveTextContent("3"));
  });

  it("안 읽음이 0이면 배지를 아예 그리지 않는다", async () => {
    mockApi(0);
    renderShell();
    // 방 목록 요청이 끝난 뒤에도 없어야 한다 — 렌더 순서 때문에 우연히 통과하지 않게.
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(screen.queryByLabelText(/안 읽음/)).toBeNull();
  });

  it("99를 넘으면 99+로 자른다", async () => {
    // 세 자리를 넘기면 배지 폭이 늘어 항목 이름을 밀어낸다.
    mockApi(128);
    renderShell();
    await waitFor(() => expect(screen.getByLabelText("안 읽음 128건")).toHaveTextContent("99+"));
  });

  it("배지 때문에 방 목록을 두 번 받지 않는다", async () => {
    mockApi(3);
    renderShell();
    await waitFor(() => expect(screen.getByLabelText("안 읽음 3건")).toBeInTheDocument());
    const roomCalls = apiMock.mock.calls.filter(([p]) => p.startsWith("/api/team-chat/rooms"));
    expect(roomCalls).toHaveLength(1);
  });
});
