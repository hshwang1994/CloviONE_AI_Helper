import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 다크/라이트 전환은 **한 곳에만** 있다 (사용자 지적: "버튼으로 뺐는데 내 프로필을 누르면
 * 여전히 모드 변경 버튼이 있는데?").
 *
 * 두 벌을 두는 것 자체가 결함인 이유는 취향 문제가 아니다. 상단바 버튼은 `<html data-theme>`
 * 를 정본으로 읽고(ThemeModeProvider 의 MutationObserver), 사용자 메뉴는 자기 React 상태를
 * 따로 들고 있었다. 상단바로 바꾸면 메뉴 쪽 상태가 갱신되지 않아 **메뉴를 열면 방금 끈 모드를
 * 다시 켜라고 적혀 있다.** 정본을 상단바 버튼 하나로 정하고 메뉴 항목은 지운다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u1", display_name: "홍길동" } }),
}));

import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

// jsdom 에는 matchMedia 가 없다 — 없으면 셸이 좁은 화면으로 판단해 상단바 구성이 달라진다
// (nav-badge.test.jsx 가 같은 이유로 같은 처방을 쓴다).
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

describe("모드 전환은 한 곳만", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockResolvedValue({});
    wideViewport();
    document.documentElement.setAttribute("data-theme", "light");
    try { window.localStorage.clear(); } catch (e) { /* ignore */ }
  });

  it("사용자 메뉴에는 모드 전환 항목이 없다 — 상단바 버튼이 정본이다", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.click(await screen.findByLabelText("홍길동 메뉴"));
    // 메뉴가 실제로 열렸는지부터 확인한다(안 열렸는데 '없다'가 통과하면 헛검사다).
    // '내 프로필' 은 사이드바에도 있으므로 **열린 메뉴 안에서만** 찾는다.
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: "내 프로필" })).toBeInTheDocument();
    expect(within(menu).queryByText("다크 모드")).toBeNull();
    expect(within(menu).queryByText("라이트 모드")).toBeNull();
  });

  it("상단바 버튼 하나로 켜고 끈다 — 누르면 라벨이 반대로 바뀐다", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.click(await screen.findByLabelText("다크 모드로 전환"));
    await waitFor(() => expect(document.documentElement.getAttribute("data-theme")).toBe("dark"));
    expect(await screen.findByLabelText("라이트 모드로 전환")).toBeInTheDocument();
  });
});
