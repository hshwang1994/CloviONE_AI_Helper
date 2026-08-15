import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* VIS-116/VIS-156: /chat 은 이미 AI 도우미 화면인데, 사이드바 하단의 "클로비에게
 * 물어보기" 카드는 그 위에 또 다른 대화 드로어를 여는 막다른 진입점으로 남아 있었다.
 * 상단바 버튼·플로팅 FAB은 이미 같은 이유(AppShell.jsx::onAssistant)로 /chat 에서
 * 숨는데 사이드바 카드만 빠져 있었다 - 그 게이트를 맞춘다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

// AssistantDrawer가 항상 마운트라(AI-32) AppShell을 그리면 그 안의 useChat()도 같이
// 돌고, 거기 matchMedia 이펙트가 jsdom 기본값(undefined)에 바로 걸린다 - sidebar-logo
// -center.test.jsx의 같은 스텁을 재사용한다.
function wideViewport() {
  window.matchMedia = (query) => ({
    matches: /min-width/.test(query),
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
}

function renderShellAt(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
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

describe("사이드바 클로비 카드 — /chat 중복 진입점 (VIS-116/VIS-156)", () => {
  beforeEach(() => {
    apiMock.mockReset();
    wideViewport();
    apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
  });

  it("/chat 에서는 사이드바 카드를 그리지 않는다 - 이미 그 화면이 AI 도우미다", async () => {
    renderShellAt("/chat");
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    expect(screen.queryByText("클로비에게 물어보기")).toBeNull();
  });

  it("다른 화면에서는 그대로 보인다 - AppShell 전체 게이트가 아니라 /chat 한정이다", async () => {
    renderShellAt("/me");
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    expect(screen.getByText("클로비에게 물어보기")).toBeInTheDocument();
  });
});
