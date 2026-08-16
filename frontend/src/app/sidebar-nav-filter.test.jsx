import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* PA-RC-0017 acceptance_criteria 7: "레일 필터에 두 글자를 입력하면 목적지가 좁혀진다."
 * constraints: "사용자 콘솔 내비는 건드리지 않는다(이미 정상이다)" — 그래서 필터 입력 자체가
 * 관리자 셸에만 있어야 한다는 것도 이 파일이 지킨다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "a1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { NAV, USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

// sidebar-active-item-scroll.test.jsx와 같은 이유 — AppShell은 useMediaQuery(isNarrow)를,
// AssistantDrawer가 쓰는 useChat.js는 자기 매체 질의를 따로 부른다. jsdom엔 matchMedia가
// 없어 둘 다 없으면 렌더 자체가 TypeError로 죽는다.
function setMatchMedia() {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: /min-width/.test(query),
    media: query,
    onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
}

function renderShell({ nav, isUser } = {}) {
  setMatchMedia();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={nav} isUser={!!isUser} ariaLabel="메뉴" showMenu>
                <div>본문</div>
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
});

afterEach(() => vi.restoreAllMocks());

describe("사이드바 내비 필터 (PA-RC-0017)", () => {
  it("관리자 셸에는 '메뉴 찾기' 입력이 있다", async () => {
    renderShell({ nav: NAV, isUser: false });
    expect(await screen.findByRole("textbox", { name: "메뉴 찾기" })).toBeInTheDocument();
  });

  it("두 글자만 쳐도 맞는 목적지만 남고 나머지는 사라진다", async () => {
    const user = userEvent.setup();
    renderShell({ nav: NAV, isUser: false });
    const nav = screen.getByRole("navigation");
    expect(within(nav).getByText("대시보드")).toBeInTheDocument();

    const input = await screen.findByRole("textbox", { name: "메뉴 찾기" });
    await user.type(input, "감사");

    expect(within(nav).queryByText("대시보드")).not.toBeInTheDocument();
    expect(within(nav).getByText("감사 로그")).toBeInTheDocument();
    expect(within(nav).getByText("감사 이상 징후")).toBeInTheDocument();
  });

  it("맞는 게 없으면 '맞는 메뉴가 없습니다' 안내가 뜬다", async () => {
    const user = userEvent.setup();
    renderShell({ nav: NAV, isUser: false });
    const input = await screen.findByRole("textbox", { name: "메뉴 찾기" });
    await user.type(input, "존재하지않는메뉴명");
    expect(await screen.findByText(/와 맞는 메뉴가 없습니다/)).toBeInTheDocument();
  });

  it("지우면 원래 메뉴 전체로 돌아온다", async () => {
    const user = userEvent.setup();
    renderShell({ nav: NAV, isUser: false });
    const nav = screen.getByRole("navigation");
    const input = await screen.findByRole("textbox", { name: "메뉴 찾기" });
    await user.type(input, "감사");
    expect(within(nav).queryByText("대시보드")).not.toBeInTheDocument();
    await user.clear(input);
    expect(within(nav).getByText("대시보드")).toBeInTheDocument();
  });

  it("사용자 콘솔 셸에는 필터 입력이 없다 — 이미 23링크·접힘 0으로 정상이라 손대지 않는다", async () => {
    renderShell({ nav: USER_NAV, isUser: true });
    await screen.findByRole("navigation");
    expect(screen.queryByRole("textbox", { name: "메뉴 찾기" })).not.toBeInTheDocument();
  });
});
