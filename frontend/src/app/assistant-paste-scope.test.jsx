import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 닫혀 있는 AI 도우미가 앱 전체의 Ctrl+V 를 가로채지 않는다.
 *
 * `AssistantDrawer` 는 셸이 **항상** 마운트한다(`keepMounted` — 닫아도 대화가 살아 있어야
 * 하므로). 그 안의 `useChat()` 이 `document` 에 붙이는 붙여넣기 리스너는 그래서 앱의 모든
 * 화면에서 살아 있었다. 팀 채팅 컴포저의 onPaste 는 `preventDefault` 만 하고
 * `stopPropagation` 을 하지 않으므로 이벤트는 계속 `document` 까지 올라간다 — 방에 보낸
 * 스샷 한 장이 **동시에** AI 도우미의 첨부 목록에 조용히 담겼다. 1:1 대화 사진이 열지도
 * 않은 AI 대화에 실려 있는 상태라, 성능 문제가 아니라 새는 경로다.
 *
 * 여기서 고정하는 계약: 드로어가 닫혀 있으면 그 리스너는 아예 없다. 그 관찰 가능한 표시가
 * `defaultPrevented` 다 — 리스너가 살아 있으면 이미지 붙여넣기를 삼키며 preventDefault 한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function wideViewport() {
  window.matchMedia = (query) => ({
    matches: /min-width/.test(query),
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
}

/** 이미지 한 장이 담긴 붙여넣기 이벤트. jsdom 의 ClipboardEvent 는 files 를 못 실으므로
 *  Event 에 clipboardData 를 직접 얹는다(리스너가 읽는 모양과 같다). */
function pasteImageOnDocument() {
  const file = new File([new Uint8Array([1, 2, 3])], "shot.png", { type: "image/png" });
  const ev = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(ev, "clipboardData", { value: { files: [file] } });
  document.dispatchEvent(ev);
  return ev;
}

function renderShell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/chat-rooms"]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
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

describe("닫힌 AI 도우미와 붙여넣기", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/team-chat/rooms")) return Promise.resolve({ items: [], global: null, unread_total: 0 });
      if (path.startsWith("/api/conversations")) return Promise.resolve({ items: [] });
      if (path.startsWith("/api/notifications")) return Promise.resolve({ items: [], unread: 0, badge: 0, by_type: {} });
      return Promise.resolve({});
    });
    wideViewport();
  });

  it("드로어가 닫혀 있으면 이미지 붙여넣기를 가로채지 않는다", async () => {
    renderShell();
    // 셸이 다 뜬 뒤에 친다 — 마운트 전에 치면 리스너가 없는 게 당연해서 헛검사가 된다.
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    await waitFor(() => expect(apiMock).toHaveBeenCalled());

    const ev = pasteImageOnDocument();
    expect(ev.defaultPrevented, "닫힌 AI 도우미가 붙여넣기를 삼켰다").toBe(false);
  });
});
