import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 관리자 콘솔 사이드바의 유형별 배지(jobFailed/approvalPending/backupFailed).
 *
 * nav-badge.test.jsx는 사용자 콘솔의 chatUnread/notifUnread만 다룬다 — 이 셋은
 * /jobs·/approvals·/backup처럼 role이 있는 관리자 항목이라 별도 파일로 둔다
 * (useAuth mock이 파일 단위로 고정이라 role을 test마다 바꿀 수 없다).
 *
 * RSTR-03: backup_failed는 알림함·메일은 이미 나가지만 사이드바 배지가 없어
 * `/backup`을 안 열면 계속 안 보였다 — jobFailed/approvalPending과 같은 배선을
 * 새로 추가했다(AppShell.jsx BADGE_TYPES/BADGE_ROUTES, navConfig.js의 badge 키).
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

function mockApi(byType) {
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/team-chat/rooms")) {
      return Promise.resolve({ rooms: [], global: null, unread_total: 0 });
    }
    if (path.startsWith("/api/notifications/unread-count")) {
      return Promise.resolve({ badge: 0, by_type: byType });
    }
    return Promise.resolve({});
  });
}

describe("관리자 사이드바 — 유형별 배지", () => {
  beforeEach(() => {
    apiMock.mockReset();
    wideViewport();
    // 이 파일이 재는 것은 배지 숫자이지 그룹 접힘 상태가 아니다 — 활성 라우트가 없는
    // "/"로 들어가므로(어느 그룹도 강제로 안 펼쳐진다) 배지가 붙는 두 그룹(운영·자동화)을
    // 미리 펼친 상태로 남겨 둔다. PA-RC-0017 전에는 "기록 없음 = 펼침"이 기본값이라 이
    // 시딩 없이도 통과했지만, 지금은 "기록 없음 = 접힘"이 기본값이다(AppShell.jsx isOpen
    // 주석 참조 — 관리자 레일이 스크롤 없이 5그룹만 보이려면 그래야 한다).
    window.localStorage.setItem(
      "clovirone_nav_collapsed:a1",
      JSON.stringify({ "운영": false, "자동화": false }),
    );
  });

  it("작업 큐·승인·백업이 각자의 유형 합계만 보인다", async () => {
    mockApi({
      job_failed: 2,
      approval_requested: 5,
      approval_overdue: 1,
      backup_failed: 1,
    });
    renderShell();

    // 배지가 붙으면 링크의 접근성 이름이 "작업 큐 안 읽음 2건"처럼 라벨+배지로 합쳐지고
    // "승인"/"승인 위임"처럼 라벨끼리 겹치는 항목도 있어, 이름이 아니라 href로 링크
    // 자체를 먼저 찾는다(안정적) — 배지 숫자는 findByLabelText로 비동기 렌더를 기다린다.
    const linkTo = async (href) => {
      const link = await screen.findByRole("link", { name: (_, el) => el.getAttribute("href") === href });
      return within(link).findByLabelText(/안 읽음/);
    };

    expect(await linkTo("/jobs")).toHaveTextContent("2");
    // approval_requested(5) + approval_overdue(1) = 6 — 위임(delegated)까지 세 유형을 합친다(X7).
    expect(await linkTo("/approvals")).toHaveTextContent("6");
    expect(await linkTo("/backup")).toHaveTextContent("1");
  });

  it("백업이 정상이면(backup_failed=0) 배지를 그리지 않는다", async () => {
    mockApi({ job_failed: 0, backup_failed: 0 });
    renderShell();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    const backupLink = screen.getByRole("link", { name: "백업" });
    expect(within(backupLink).queryByLabelText(/안 읽음/)).toBeNull();
  });
});
