import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* PA-RC-0039: PageHeader의 crumbRoot 기본값이 리터럴 "관리자"라, 그 prop을 빠뜨린 사용자
 * 콘솔 화면(TeamDocs.jsx·DataScreen.jsx)이 일반 사용자에게 "관리자"라고 말했다. AppShell이
 * 지금 콘솔+navConfig 그룹에서 값을 유도해 CrumbRootProvider로 흘려보내는 쪽으로 고쳤다 —
 * 여기서는 그 배선 자체를 못박는다:
 *   1) 관리자 콘솔은 손 하나 안 대도(crumbRoot 미전달) 여전히 "관리자"다(회귀 없음, 가장
 *      중요한 안전망).
 *   2) 사용자 콘솔은 crumbRoot를 안 넘긴 화면도 이제 자기 사이드바 그룹을 보인다.
 *   3) 호출부가 명시하면 그 값이 항상 이긴다(Trash.jsx가 실제로 그렇게 남아 있다 — 부모
 *      /team-docs와 같은 값이 나오는지도 함께 본다).
 *   4) AppShell 밖(Provider 없음)에서는 예전처럼 "관리자"로 떨어진다 — 격리 렌더·기존
 *      테스트가 깨지지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
const authMock = vi.fn();
vi.mock("./auth.jsx", () => ({ useAuth: () => authMock() }));

import { AppShell } from "./AppShell.jsx";
import { NAV, USER_NAV } from "./navConfig.js";
import { PageHeader, ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

// jsdom엔 matchMedia가 없다 — 없으면 MUI useMediaQuery가 전부 false라 셸이 좁은 화면으로
// 접혀 사이드바 자체가 안 그려진다(nav-badge.test.jsx와 같은 처방).
function wideViewport() {
  window.matchMedia = (query) => ({
    matches: /min-width/.test(query),
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
}

beforeEach(() => {
  wideViewport();
  apiMock.mockReset();
  apiMock.mockImplementation(() => Promise.resolve({}));
  authMock.mockReset();
  authMock.mockReturnValue({ data: { role: "user", id: "u1" } });
});

function renderAt(path, { nav, isUser, userSeg, role, screen: content }) {
  authMock.mockReturnValue({ data: { role: role || (isUser ? "user" : "system_admin"), id: "u1" } });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AppShell nav={nav} ariaLabel="메뉴" isUser={isUser} userSeg={userSeg} showMenu>
                {content}
              </AppShell>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

// crumb는 area가 있으면 "<crumbRoot> › <area>"로 뜬다(kit.jsx PageHeader) — 접두어만 보고
// 판단할 수 있게 area는 매번 다르게 준다. 사이드바 자체가 같은 그룹 이름을 텍스트로 그리므로
// (예: '문서' 그룹 머리글) 본문 랜드마크(<main>) 안으로 쿼리를 좁혀 사이드바와 헷갈리지 않는다.
function main() { return within(screen.getByRole("main")); }

describe("관리자 콘솔 — crumbRoot 회귀 없음 (PA-RC-0039 acceptance 4)", () => {
  it("/users에서 crumbRoot를 안 넘겨도 여전히 '관리자'다", () => {
    renderAt("/users", {
      nav: NAV, isUser: false, userSeg: false,
      screen: <PageHeader area="사용자와 권한" title="사용자" />,
    });
    expect(main().getByText("관리자 › 사용자와 권한")).toBeInTheDocument();
  });

  it("/audit(감사 그룹)에서도 여전히 '관리자'다 — 유도값(감사)으로 새지 않는다", () => {
    renderAt("/audit", {
      nav: NAV, isUser: false, userSeg: false,
      screen: <PageHeader area="감사" title="감사 로그" />,
    });
    expect(main().getByText("관리자 › 감사")).toBeInTheDocument();
  });
});

describe("사용자 콘솔 — crumbRoot를 유도한다 (PA-RC-0039 acceptance 1~3)", () => {
  it("TeamDocs처럼 crumbRoot를 안 넘기고 area=null이면, 예전엔 '관리자'였지만 이제 소속 그룹이 뜬다", () => {
    // /team-docs는 PA-RC-0031이 '문서' 그룹을 '팀 공간'에 합친 뒤라 그 그룹 이름이 뜬다 —
    // 그룹이 바뀌면 breadcrumb가 자동으로 따라오는 것이 derivation을 택한 이유였다
    // (DECISIONS.md D-129, 의도된 연쇄).
    renderAt("/team-docs", {
      nav: USER_NAV, isUser: true, userSeg: true,
      screen: <PageHeader area={null} title="문서 홈" />,
    });
    expect(main().getByText("팀 공간")).toBeInTheDocument();
    expect(main().queryByText(/관리자/)).not.toBeInTheDocument();
  });

  it("/notifications는 관리자 콘솔에서 '관리자 › 운영', 사용자 콘솔에서는 사용자 그룹(내 업무)이다", () => {
    renderAt("/notifications", {
      nav: USER_NAV, isUser: true, userSeg: true,
      screen: <PageHeader area="운영" title="알림" />,
    });
    expect(main().getByText("내 업무 › 운영")).toBeInTheDocument();
  });

  it("자기 메뉴 항목이 없는 상세 경로도 prefix로 소속 그룹을 찾는다(활성 메뉴 판정과 같은 함수)", () => {
    // /team-docs/trash는 PA-RC-0031로 독립 메뉴 항목을 잃었다(TeamDocs.jsx 화면 안 버튼으로
    // 이동) — /team-docs 접두 매칭으로 그 부모의 그룹('팀 공간')을 그대로 물려받는다.
    renderAt("/team-docs/trash", {
      nav: USER_NAV, isUser: true, userSeg: true,
      screen: <PageHeader area="휴지통" title="휴지통" />,
    });
    expect(main().getByText("팀 공간 › 휴지통")).toBeInTheDocument();
  });
});

describe("crumbRoot 명시 호출부는 항상 그 값이 이긴다", () => {
  it("사용자 콘솔 안에서도 명시한 crumbRoot가 유도값을 덮는다", () => {
    renderAt("/team-docs", {
      nav: USER_NAV, isUser: true, userSeg: true,
      screen: <PageHeader crumbRoot="커스텀" area={null} title="문서" />,
    });
    expect(main().getByText("커스텀")).toBeInTheDocument();
  });
});

describe("AppShell(Provider) 밖에서는 예전 기본값을 그대로 유지한다", () => {
  it("CrumbRootProvider 없이 단독 렌더하면 crumbRoot 미전달 시 '관리자'다", () => {
    render(
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <PageHeader area="사용자와 권한" title="사용자" />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>,
    );
    expect(screen.getByText("관리자 › 사용자와 권한")).toBeInTheDocument();
  });
});
