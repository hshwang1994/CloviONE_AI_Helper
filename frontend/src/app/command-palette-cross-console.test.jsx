import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* SRCH-01(High) 회귀 고정: 명령 팔레트(Ctrl+K)가 사이드바와 같은 `nav`(현재 콘솔 하나만)를
 * 써서, 관리자군이 사용자 콘솔(`/me`)에 있는 동안엔 "사용자"·"백업" 같은 관리자 화면을
 * Ctrl+K로 찾을 방법이 아예 없었다 — 메뉴 결과 0건. 팔레트의 존재 이유가 "어디서든
 * 어디로든"이므로, `paletteNav`(두 콘솔 전체)가 있으면 현재 콘솔과 무관하게 검색되고,
 * role이 못 보는 화면은 여전히 안 뜬다는 것까지 함께 고정한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

let currentAuth = { role: "system_admin", id: "admin1" };
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: currentAuth }) }));

import { AppShell } from "./AppShell.jsx";
import { NAV, USER_NAV, navWithFeatures } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

// jsdom엔 matchMedia가 없다 — 없으면 셸이 좁은 화면으로 판단해 사이드바를 아예 안 그린다.
function wideViewport() {
  window.matchMedia = (query) => ({
    matches: /min-width/.test(query),
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
}

function mockApi() {
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/search")) return Promise.resolve({ query: "", mode: "fts", total: 0, truncated: false, groups: [] });
    if (path.startsWith("/api/team-chat/rooms")) return Promise.resolve({ rooms: [], global: null, unread_total: 0 });
    if (path.startsWith("/api/notifications")) return Promise.resolve({ items: [], unread: 0 });
    return Promise.resolve({});
  });
}

/* App.jsx가 `useUserConsole`일 때 실제로 넘기는 것과 같은 조합 — nav는 사용자 콘솔뿐이고
 * paletteNav만 두 콘솔 전체다. system_admin이 /me(사용자 세그먼트)에 머무는 상황을 그대로
 * 재현한다. */
function renderShell({ withPaletteNav }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/me"]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell
                nav={USER_NAV}
                paletteNav={withPaletteNav ? navWithFeatures([...NAV, ...USER_NAV], undefined) : undefined}
                ariaLabel="사용자 메뉴"
                userSeg
                showMenu
              >
                <div>홈 화면</div>
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function openPalette() {
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
}

describe("명령 팔레트 — 콘솔 경계를 넘는 검색(SRCH-01)", () => {
  beforeEach(() => {
    apiMock.mockReset();
    mockApi();
    wideViewport();
    currentAuth = { role: "system_admin", id: "admin1" };
  });

  it("paletteNav가 있으면 사용자 콘솔(/me)에서도 관리자 화면을 찾을 수 있다", async () => {
    renderShell({ withPaletteNav: true });
    openPalette();
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "통합 검색" }), "사용자");
    // NAV의 "사용자"(roles: admin/system_admin) — USER_NAV에는 없는 항목이다. 상단바에도
    // 같은 글자의 콘솔 전환 탭이 있어(무관한 요소), 반드시 팔레트 다이얼로그 안으로 좁혀서 본다.
    expect(await within(dialog).findByText("사용자")).toBeInTheDocument();
  });

  it("paletteNav가 없으면(예전 동작) 사용자 콘솔에서 관리자 화면을 못 찾는다 — 이 결함의 재현", async () => {
    renderShell({ withPaletteNav: false });
    openPalette();
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "통합 검색" }), "사용자");
    expect(within(dialog).queryByText("사용자")).not.toBeInTheDocument();
  });

  it("role이 못 보는 화면은 paletteNav가 있어도 여전히 안 뜬다 — RBAC가 넓어진 검색 범위에도 그대로 적용된다", async () => {
    currentAuth = { role: "user", id: "u1" };
    renderShell({ withPaletteNav: true });
    openPalette();
    const dialog = screen.getByRole("dialog");
    // /users는 admin/system_admin 전용 — role=user에게는 paletteNav로 범위를 넓혀도 안 보여야 한다.
    await userEvent.type(within(dialog).getByRole("textbox", { name: "통합 검색" }), "사용자");
    expect(within(dialog).queryByText("사용자")).not.toBeInTheDocument();
  });
});
