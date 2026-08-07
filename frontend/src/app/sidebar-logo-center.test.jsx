import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 사이드바 상단 로고 묶음(마크+브랜드명)이 가운데 정렬돼야 한다 (사용자 지적).
 *
 * 예전에는 헤더 Toolbar에 justifyContent가 없어 flex 기본값(flex-start)대로
 * 로고 묶음이 왼쪽에 붙었다. */

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
  return render(
    <MemoryRouter initialEntries={["/me"]}>
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

describe("사이드바 상단 로고 정렬", () => {
  beforeEach(() => {
    apiMock.mockReset();
    wideViewport();
    apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
  });

  it("로고+브랜드명 묶음을 담은 헤더 Toolbar가 가운데 정렬이다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    const aside = document.querySelector("#app-sidebar");
    expect(aside, "사이드바를 찾지 못했다").toBeTruthy();
    const headerToolbar = aside.querySelector(".MuiToolbar-root");
    expect(headerToolbar, "사이드바 헤더 Toolbar를 찾지 못했다").toBeTruthy();

    expect(getComputedStyle(headerToolbar).justifyContent).toBe("center");
  });
});
