import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* AI-27: 드로어 컴포저가 MUI InputBase 단일행(HTML input)이었다 — (1) 여러 줄을 못 쓰고
 * (2) 폼 안의 input 은 Enter 를 누르면 IME 조합 여부와 무관하게 그대로 제출됐다(한글이
 * 조합 중 전송됨). 전체화면 Chat.jsx 는 이미 네이티브 textarea + IME 가드로 이 문제가
 * 없었다 — 드로어도 같은 useChat() 이 내주는 textareaRef 를 재사용해 같은 가드를 쓰게
 * 고쳤다. 여기서 고정하는 계약: Enter(조합 아님)는 보내고, Shift+Enter 는 줄바꿈만 하고,
 * keyCode 229(IME 조합 중 신호)는 아무것도 보내지 않는다. */

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

function renderShellAndOpenDrawer() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
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

async function openDrawer() {
  await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
  // 클로비를 여는 진입점이 셋(상단바·사이드바 카드·우하단 FAB)이라 jsdom 은 반응형 display:none
  // 을 실제로 숨기지 않으므로 같은 aria-label 이 여러 개 잡힌다 — 아무거나 하나면 충분하다.
  fireEvent.click(screen.getAllByLabelText("클로비 AI 도우미 열기")[0]);
  return screen.findByLabelText("클로비에게 질문");
}

describe("드로어 컴포저 — 여러 줄 + IME 가드 (AI-27)", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path, opts) => {
      if (path.startsWith("/api/team-chat/rooms")) return Promise.resolve({ items: [], global: null, unread_total: 0 });
      if (path.startsWith("/api/conversations") && (!opts || opts.method !== "POST")) return Promise.resolve({ items: [] });
      if (path === "/api/conversations" && opts && opts.method === "POST") return Promise.resolve({ id: "c1", conversation: { id: "c1" } });
      if (/\/api\/conversations\/.+\/messages$/.test(path) && opts && opts.method === "POST") {
        return Promise.resolve({ id: "m1", role: "user", content: opts.body.content });
      }
      if (path.startsWith("/api/notifications")) return Promise.resolve({ items: [], unread: 0, badge: 0, by_type: {} });
      return Promise.resolve({});
    });
    wideViewport();
  });

  it("textarea 이고 Shift+Enter 는 줄바꿈만 한다(전송 안 함)", async () => {
    renderShellAndOpenDrawer();
    const box = await openDrawer();
    expect(box.tagName).toBe("TEXTAREA");

    fireEvent.change(box, { target: { value: "첫 줄" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });

    // 전송 요청(POST /api/conversations)이 나가지 않았다.
    const sentConv = apiMock.mock.calls.some(
      ([path, opts]) => path === "/api/conversations" && opts && opts.method === "POST",
    );
    expect(sentConv).toBe(false);
  });

  it("Enter(조합 아님)는 메시지를 보낸다", async () => {
    renderShellAndOpenDrawer();
    const box = await openDrawer();

    fireEvent.change(box, { target: { value: "안녕" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: false });

    await waitFor(() => {
      const sentConv = apiMock.mock.calls.some(
        ([path, opts]) => path === "/api/conversations" && opts && opts.method === "POST",
      );
      expect(sentConv).toBe(true);
    });
  });

  it("IME 조합 중(keyCode 229)의 Enter 는 보내지 않는다", async () => {
    renderShellAndOpenDrawer();
    const box = await openDrawer();

    fireEvent.change(box, { target: { value: "한" } });
    fireEvent.keyDown(box, { key: "Enter", keyCode: 229 });

    const sentConv = apiMock.mock.calls.some(
      ([path, opts]) => path === "/api/conversations" && opts && opts.method === "POST",
    );
    expect(sentConv).toBe(false);
  });
});
