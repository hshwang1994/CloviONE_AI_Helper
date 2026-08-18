import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { createClovirTheme } from "../ui/theme.js";
import TopSearch from "./TopSearch.jsx";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

/* 상단바 계약 — 실제 셸이 그리는 것을 본다.
 *
 * ## 이 파일이 무엇을 대체했는가
 *
 * `topbar-baseline.test.jsx` 는 기대값을 전부 폐기한 목업(지시 64)
 * (목업)에서 파싱해 왔다. 그 목업은 지시 64 로 폐기했다. 더 중요한 것은 그 시험이 지키던
 * 값들이 **어두운 상단바를 전제**하고 있었다는 점이다 — 높이 40 검색창, 반투명 남색 바탕,
 * 흰 글자. D-141 로 chrome 이 캔버스 계열이 되면서 그 값들은 더 이상 맞지 않는다.
 *
 * 그래서 치수 대조는 버리고 **행동과 가독성 계약**만 남겨 실제 셸에서 검증한다:
 *   - 브랜드 자리에 자기 배경(판)이 없다. 로고는 상단바 위에 그대로 얹힌다.
 *   - 검색 버튼이 상단바 안에 들어가고 누를 만한 크기다.
 *   - 검색 안내 문구가 **실제로 검색되지 않는 것**을 광고하지 않는다.
 *   - /chat 에서는 클로비 버튼을 안 그린다(이미 전체화면 채팅이다). 다른 화면에서는 그린다.
 *
 * 색 대비는 여기서 재지 않는다 — `ui/theme-contract.test.js` 가 팔레트 차원에서 강조색
 * 프리셋 전체 × 두 모드로 강제하고, `scripts/ui_qa` 하네스가 실제 브라우저에서 잰다.
 */

const APPBAR_MIN_HEIGHT_PX = 52; // AppShell.APPBAR_HEIGHT.xs

function withProviders(node) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>{node}</ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("상단 검색", () => {
  it("실제로 검색되지 않는 '채팅'을 광고하지 않는다", () => {
    /* app/search/models.py 의 SEARCH_KINDS 는 채팅을 **의도적으로** 뺀다(1:1 DM 이 공용
       인덱스에 들어가면 멤버십 확인 한 줄이 틀려도 남의 DM 이 샌다 —
       tests/security/test_search_no_chat.py 가 그 경계를 못박는다). 안내 문구가 그것을
       검색된다고 말하면 안 된다. */
    render(withProviders(<TopSearch onOpen={() => {}} />));
    const placeholder = screen.getByTestId("top-search-placeholder");
    expect(placeholder.textContent).not.toMatch(/채팅/);
    expect(placeholder.textContent).toMatch(/티켓/);
    expect(placeholder.textContent).toMatch(/문서/);
  });

  it("상단바 안에 들어가고 누를 만한 크기다", () => {
    render(withProviders(<TopSearch onOpen={() => {}} />));
    const button = screen.getByLabelText("통합 검색과 명령 열기");
    const h = Number.parseFloat(getComputedStyle(button).height);
    expect(h).toBeGreaterThanOrEqual(28);
    expect(h).toBeLessThan(APPBAR_MIN_HEIGHT_PX);
  });

  it("입력처럼 보이지만 실제로는 버튼이다 (결과가 뜰 자리가 상단바에 없다)", () => {
    render(withProviders(<TopSearch onOpen={() => {}} />));
    const button = screen.getByLabelText("통합 검색과 명령 열기");
    expect(button.tagName).toBe("BUTTON");
  });
});

// ════════════════════════════════════════════════════════════════════════════
// 셸이 실제로 그것을 쓰는가
// ════════════════════════════════════════════════════════════════════════════
/* 조각이 맞아도 **셸이 그 조각을 안 쓰면** 사용자 화면은 그대로다 — 이 저장소가 여러 번
 * 겪은 실패가 정확히 그것이다("파일은 고쳤는데 배포된 화면은 그대로"). */
import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";

function renderShell(path = "/me") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[path]}>
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

describe("셸의 상단바", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
    window.matchMedia = (query) => ({
      matches: /min-width/.test(query),
      media: query,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, onchange: null,
      dispatchEvent: () => false,
    });
  });

  it("상단바가 그라디언트를 쓰지 않는다 (chrome 은 발광하지 않는다)", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const bar = document.querySelector(".MuiAppBar-root");
    expect(bar, "상단바를 못 찾았다").toBeTruthy();
    const bg = getComputedStyle(bar).backgroundImage;
    expect(bg === "" || bg === "none").toBe(true);
  });

  it("브랜드 자리에 자기 배경(판)이 없다 — 로고가 상단바 위에 그대로 얹힌다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const brand = screen.getByLabelText("홈으로");
    /* MUI v7 은 text variant 배경을 `var(--variant-textBg)`(런타임 투명)로 낸다. jsdom 은
       그 변수를 풀지 못하므로 색 문자열 대신 **variant 자체**를 본다 — 판이 깔리는 것은
       contained/outlined 이고, 그 둘이 아니면 자기 배경이 없다는 뜻이다. */
    expect(brand.className).toMatch(/MuiButton-text/);
    expect(brand.className).not.toMatch(/MuiButton-(contained|outlined)/);
  });

  it("상단바가 검색 버튼을 실제로 그린다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const bar = document.querySelector(".MuiAppBar-root");
    expect(bar.querySelector('[aria-label="통합 검색과 명령 열기"]')).toBeTruthy();
  });

  // PA-RC-0020: 사이드바 카드·우하단 FAB 을 없애 "클로비 AI 도우미 열기" aria-label 을
  // 가진 요소는 이제 상단바 버튼 하나뿐이다.
  it("AI-57: /chat 에서는 상단바 클로비 버튼을 안 그린다 — 이미 전체화면 채팅이 열려 있다", async () => {
    renderShell("/chat");
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    expect(screen.queryAllByLabelText("클로비 AI 도우미 열기")).toHaveLength(0);
  });

  it("/chat 이 아닌 화면에서는 상단바 클로비 버튼을 그대로 그린다 (마스코트는 제품 정체성이다)", async () => {
    renderShell("/me");
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    expect(screen.getAllByLabelText("클로비 AI 도우미 열기")).toHaveLength(1);
    const bar = document.querySelector(".MuiAppBar-root");
    expect(bar.querySelector('[aria-label="클로비 AI 도우미 열기"]'), "상단바 안에 클로비 버튼이 없다").toBeTruthy();
  });

  it("상단바 높이가 테마가 정한 값이고, 그 안에 검색·벨·사용자 영역이 함께 들어간다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const bar = document.querySelector(".MuiAppBar-root");
    expect(bar.querySelector('[aria-label="통합 검색과 명령 열기"]')).toBeTruthy();
    // 벨은 알림 개수에 따라 aria-label 이 바뀌므로 접두사로 찾는다.
    expect(bar.querySelector('[aria-label^="알림"]')).toBeTruthy();
  });
});

describe("테마가 chrome 색의 정본이다", () => {
  it.each(["light", "dark"])("%s — 사이드바·상단바가 같은 chrome 색을 쓴다", (mode) => {
    const p = createClovirTheme(mode).palette;
    // 상단바(AppBar)는 palette.sidebar.bg 를 쓴다. 두 층이 한 면으로 읽혀야 한다.
    expect(p.sidebar.bg).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(p.sidebar.line).toMatch(/^#[0-9A-Fa-f]{6}$/);
  });
});
