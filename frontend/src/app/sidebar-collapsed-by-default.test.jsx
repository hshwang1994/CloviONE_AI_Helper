import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* PA-RC-0017 실브라우저 재측정에서 발견: 관리자 레일이 처음 방문(또는 이번 그룹 이름
 * 변경으로 예전 접힘 기록이 새 이름과 안 맞게 된 뒤)엔 5그룹이 **전부** 펼쳐져
 * scrollHeight 1716 / clientHeight 794로 acceptance_criteria 1("5개 이하·스크롤 없이
 * 전부 보인다")을 깼다 — "기록 없음 = 펼침"이 예전 기본값이었기 때문이다. 활성 그룹만
 * 펼치고 나머지는 접힌 채로 시작하도록 고쳤다(AppShell.jsx isOpen). 이 파일은 그 기본값을
 * 못박는다.
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

function renderShell(initialPath) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
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

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
  window.localStorage.clear();
  setMatchMedia();
});

afterEach(() => { delete window.matchMedia; vi.restoreAllMocks(); });

describe("관리자 레일 — 첫 방문(접힘 기록 없음)의 기본 상태", () => {
  it("5그룹 헤더는 전부 보이지만, 활성 그룹(운영) 외 나머지는 접힌 채로 시작한다", async () => {
    renderShell("/dashboard");
    const nav = await screen.findByRole("navigation");

    // 5그룹 헤더 전부 존재.
    for (const name of ["운영", "사용자와 권한", "자동화", "연동", "감사"]) {
      expect(within(nav).getByRole("button", { name: new RegExp(name) })).toBeInTheDocument();
    }

    // 활성 그룹("운영", /dashboard가 속함)의 항목은 보인다.
    expect(within(nav).getByText("대시보드")).toBeInTheDocument();

    // 활성 그룹이 아닌 그룹은 기록이 없으면 접힌 채 시작한다. MUI Collapse는 접혀도
    // unmountOnExit={false}라 내용이 DOM에는 남는다(ARIA disclosure 규약 — AppShell.jsx
    // 주석 참조) — 그래서 "안 보인다"의 정본은 텍스트의 DOM 존재 여부가 아니라
    // aria-expanded다.
    const auditHeader = within(nav).getByRole("button", { name: /감사/ });
    expect(auditHeader).toHaveAttribute("aria-expanded", "false");
  });

  it("접힌 그룹을 눌러 펼치면 aria-expanded가 true로 바뀐다", async () => {
    const user = userEvent.setup();
    renderShell("/dashboard");
    const nav = await screen.findByRole("navigation");

    const auditHeader = within(nav).getByRole("button", { name: /감사/ });
    expect(auditHeader).toHaveAttribute("aria-expanded", "false");
    await user.click(auditHeader);
    expect(auditHeader).toHaveAttribute("aria-expanded", "true");
  });
});
