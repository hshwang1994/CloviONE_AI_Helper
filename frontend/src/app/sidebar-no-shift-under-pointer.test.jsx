import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 더블클릭 조사(2026-09-21): 누른 자리 아래의 줄이 움직이면 둘째 클릭이 다른 메뉴에 떨어진다.
 *
 * 관리자 레일은 접힘이 기본이고 활성 그룹만 강제로 펴진다. 다른 그룹의 항목을 누르면 방금까지
 * 활성이던 그룹이 접히며 아래 줄이 전부 위로 밀렸다 — 사용자는 같은 메뉴를 두 번 눌렀는데 둘째
 * 클릭은 밀려 올라온 다른 메뉴나 그룹 머리에 떨어졌다. 운영 로그에는 작업 보드 요청과 같은 초에
 * 스프린트 회의 요청이 찍혀 있었다.
 *
 * 여기서 못박는 것: 활성이라서만 펴져 있던 그룹은 포인터가 레일에 있는 동안 편 채로 남고, 레일을
 * 떠나면 접힌다. 그 붙잡기는 기록(localStorage)을 바꾸지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "a1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

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

function Where() {
  const loc = useLocation();
  const navigate = useNavigate();
  return (
    <div>
      <div data-testid="where">{loc.pathname}</div>
      {/* 레일 밖에서 일어나는 이동(본문의 링크 · 딥링크)의 대역 */}
      <button type="button" onClick={() => navigate("/setup")}>본문에서 초기 설정으로</button>
    </div>
  );
}

function renderShell(initialPath) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={NAV} ariaLabel="관리자 메뉴" showMenu>
                <Where />
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function groupHeader(nav, name) {
  return within(nav).getByRole("button", { name: new RegExp(`^${name}`) });
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
  window.localStorage.clear();
  setMatchMedia();
});

afterEach(() => { delete window.matchMedia; vi.restoreAllMocks(); });

describe("사이드바 — 누른 자리 아래의 줄이 움직이지 않는다", () => {
  it("다른 그룹의 항목을 누르는 동안 방금까지 활성이던 그룹이 접히지 않는다", async () => {
    const user = userEvent.setup();
    renderShell("/jobs");
    const nav = await screen.findByRole("navigation");
    // 운영(/jobs 가 든 그룹)은 활성이라 펴져 있고, 설정은 접힌 채 시작한다.
    expect(groupHeader(nav, "운영")).toHaveAttribute("aria-expanded", "true");
    expect(groupHeader(nav, "설정")).toHaveAttribute("aria-expanded", "false");

    fireEvent.pointerEnter(nav);
    await user.click(groupHeader(nav, "설정"));
    expect(groupHeader(nav, "설정")).toHaveAttribute("aria-expanded", "true");

    await user.click(within(nav).getByRole("link", { name: "초기 설정" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/setup");
    // 🔴 운영은 이제 활성이 아니지만 포인터가 레일에 있는 동안 편 채로 남는다 — 접히면 그 아래 줄이
    // 밀려 올라와 둘째 클릭이 다른 메뉴에 떨어진다.
    expect(groupHeader(nav, "운영")).toHaveAttribute("aria-expanded", "true");

    // 포인터가 레일을 떠나면 원래 규칙(기록 없음 = 접힘)으로 돌아간다.
    fireEvent.pointerLeave(nav);
    expect(groupHeader(nav, "운영")).toHaveAttribute("aria-expanded", "false");
    // 붙잡기는 화면의 형편이다 — 사용자가 편 적이 없는 그룹의 기록을 만들지 않는다.
    const stored = JSON.parse(window.localStorage.getItem("clovirassist_nav_collapsed:a1") || "{}");
    expect(stored["운영"]).not.toBe(false);
  });

  it("붙잡아 편 그룹의 머리를 누르면 닫힌다", async () => {
    const user = userEvent.setup();
    renderShell("/jobs");
    const nav = await screen.findByRole("navigation");
    fireEvent.pointerEnter(nav);
    await user.click(groupHeader(nav, "설정"));
    await user.click(within(nav).getByRole("link", { name: "초기 설정" }));
    expect(groupHeader(nav, "운영")).toHaveAttribute("aria-expanded", "true");

    await user.click(groupHeader(nav, "운영"));
    expect(groupHeader(nav, "운영")).toHaveAttribute("aria-expanded", "false");
  });

  it("레일 밖에서 일어난 이동(본문의 링크 · 딥링크)은 붙잡지 않는다", async () => {
    const user = userEvent.setup();
    renderShell("/jobs");
    const nav = await screen.findByRole("navigation");
    await user.click(groupHeader(nav, "설정"));
    // 포인터도 초점도 레일을 떠난 뒤의 이동이다 — 밀릴 줄 아래에 아무도 없으니 원래 규칙대로 곧바로 접힌다.
    await user.click(screen.getByRole("button", { name: "본문에서 초기 설정으로" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/setup");
    expect(groupHeader(nav, "운영")).toHaveAttribute("aria-expanded", "false");
  });
});
