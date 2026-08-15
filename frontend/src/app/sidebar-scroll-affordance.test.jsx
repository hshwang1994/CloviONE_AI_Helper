import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* VIS-104: 사이드바 목록이 VIS-113처럼 스크롤되는데, 바로 아래 항상 보이는 마스코트
 * 카드 때문에 "메뉴가 여기서 끝난다"로 착시된다 — 실제로는 스크롤하면 항목이 더 있다.
 * 아래쪽에 더 볼 것이 있으면 목록에 안쪽 그림자를 얹어 신호를 준다(AppShell.jsx
 * SidebarNav). 그림자는 실제로 끝까지 스크롤했거나애초에 넘치지 않으면 사라져야 한다 —
 * 늘 떠 있으면 "끝났다"는 착시를 다른 방향으로 반복하는 것일 뿐이다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "a1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { NAV } from "./navConfig.js";
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
    <MemoryRouter initialEntries={["/"]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={NAV} ariaLabel="관리자 메뉴" showMenu>
                <div>본문</div>
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function findNavList() {
  return document.querySelector("nav.MuiList-root");
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
  wideViewport();
});

afterEach(() => {
  delete window.matchMedia;
});

describe("사이드바 목록 — 스크롤 잔여 신호 (VIS-104)", () => {
  it("아래에 더 볼 항목이 있으면 그림자를 보인다", async () => {
    // jsdom은 레이아웃을 계산하지 않아 scrollHeight/clientHeight가 항상 0이다 - 내용이
    // 넘치는 목록을 흉내내려면 값을 고정으로 스텁해야 한다(게임방 스위트와 같은 처방).
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, value: 1000 });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 300 });
    renderShell();

    // MUI sx는 인라인 style이 아니라 emotion CSS 클래스로 나간다 — list.style.boxShadow는
    // 항상 빈 문자열이라 실제 계산된 값을 봐야 한다(kit.test.jsx의 VIS-58 시험과 같은 이유).
    await waitFor(() => {
      const list = findNavList();
      expect(list).not.toBeNull();
      expect(getComputedStyle(list).boxShadow).toContain("inset");
    });
  });

  it("넘치지 않으면(전부 보이면) 그림자를 그리지 않는다", async () => {
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, value: 300 });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 300 });
    renderShell();

    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    const list = findNavList();
    expect(list).not.toBeNull();
    expect(getComputedStyle(list).boxShadow).toBe("none");
  });

  it("끝까지 스크롤하면 그림자가 사라진다", async () => {
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, value: 1000 });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 300 });
    renderShell();

    const list = await waitFor(() => {
      const el = findNavList();
      expect(getComputedStyle(el).boxShadow).toContain("inset");
      return el;
    });

    list.scrollTop = 700; // 1000 - 300 = 끝
    fireEvent.scroll(list);

    await waitFor(() => expect(getComputedStyle(list).boxShadow).toBe("none"));
  });
});
