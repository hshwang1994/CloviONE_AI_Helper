import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* VIS-113: 관리자 내비가 5그룹 35항목이라 1080 높이에 다 안 들어간다. 활성 그룹은 강제로
 * 펼쳐지지만(sidebar-group-sticky-open.test.jsx), 펼친 뒤 그 활성 항목이 스크롤 영역 밖에
 * 있으면(예: /dev-report — 마지막 그룹 "감사"의 마지막 항목) "내가 어디 있는지" 보여주는
 * 표시가 화면에 하나도 없었다 — 하이라이트 자체는 이미 있는데 스크롤이 안 따라가 안 보일
 * 뿐이었다. PA-RC-0017 이전엔 /llm-console이 이 예시였다 — 그 화면이 /settings의 탭이
 * 되며 더는 사이드바 항목이 아니라(활성 항목 자체가 없어 스크롤할 대상도 없다) 여전히
 * 아래쪽에 남는 항목으로 바꿨다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "a1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function setMatchMedia(reduce) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: /prefers-reduced-motion/.test(query) ? reduce : /min-width/.test(query),
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
});

afterEach(() => {
  delete window.matchMedia;
  vi.restoreAllMocks();
});

describe("사이드바 활성 항목 스크롤 (VIS-113)", () => {
  it("스크롤 영역 아래쪽 그룹의 항목으로 진입하면 그 항목을 목록 안으로 스크롤한다", async () => {
    setMatchMedia(false);
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;

    renderShell("/dev-report");
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    expect(scrollSpy).toHaveBeenCalledWith(
      expect.objectContaining({ block: "nearest", behavior: "smooth" }),
    );
  });

  it("동작 최소화 사용자에게는 behavior: auto로 스크롤한다", async () => {
    setMatchMedia(true);
    const scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;

    renderShell("/dev-report");
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    expect(scrollSpy).toHaveBeenCalledWith(
      expect.objectContaining({ block: "nearest", behavior: "auto" }),
    );
  });
});
