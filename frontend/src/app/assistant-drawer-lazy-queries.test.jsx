import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* AI-32: AssistantDrawer는 셸이 항상 마운트한다(닫아도 대화가 살아 있어야 하므로) — 그런데
 * useChat()의 ai-quota·conversations 쿼리는 그 사실과 무관하게 마운트 즉시 나갔다. 드로어를
 * 한 번도 열어 본 적 없는 사용자도 로그인만 하면 페이지마다 AI 관련 호출이 붙는 셈이었다.
 * 여기서 고정하는 계약: 닫혀 있는 동안은 두 쿼리 다 안 나가고, 처음 열리면 나가며, 그 뒤
 * 닫아도 다시 사라지지 않는다(대화 상태를 유지해야 하므로). */

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

function renderShell() {
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

function calledWith(pathPrefix) {
  return apiMock.mock.calls.some(([path]) => typeof path === "string" && path.startsWith(pathPrefix));
}

describe("AssistantDrawer의 쿼리는 처음 열릴 때까지 미뤄진다 (AI-32)", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/team-chat/rooms")) return Promise.resolve({ items: [], global: null, unread_total: 0 });
      if (path.startsWith("/api/conversations")) return Promise.resolve({ items: [] });
      if (path.startsWith("/api/notifications")) return Promise.resolve({ items: [], unread: 0, badge: 0, by_type: {} });
      if (path === "/api/me/ai-quota") return Promise.resolve({ used: 0, limit: 100 });
      return Promise.resolve({});
    });
    wideViewport();
  });

  it("드로어를 열기 전에는 ai-quota·conversations 호출이 안 나간다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    // 다른 셸 호출(알림·채팅 미확인 수 등)이 자리 잡을 시간을 준다 — 그 사이 AI 쿼리는
    // 나가지 않아야 한다.
    await waitFor(() => expect(calledWith("/api/notifications")).toBe(true));

    expect(calledWith("/api/me/ai-quota")).toBe(false);
    expect(calledWith("/api/conversations")).toBe(false);
  });

  it("한 번 열리면 그 즉시 두 쿼리가 나간다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    fireEvent.click(screen.getAllByLabelText("클로비 AI 도우미 열기")[0]);
    await waitFor(() => expect(calledWith("/api/conversations")).toBe(true));
    expect(calledWith("/api/me/ai-quota")).toBe(true);
  });
});
