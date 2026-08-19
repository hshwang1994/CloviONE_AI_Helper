import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 사이드바 상단 로고 묶음(마크+브랜드명)이 가운데 정렬돼야 한다 (사용자 지적).
 *
 * 예전에는 헤더 Toolbar에 justifyContent가 없어 flex 기본값(flex-start)대로
 * 로고 묶음이 왼쪽에 붙었다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import TopBrand from "./TopBrand.jsx";

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
    <MemoryRouter initialEntries={["/me"]}>
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

describe("사이드바 상단 로고 정렬", () => {
  beforeEach(() => {
    apiMock.mockReset();
    wideViewport();
    apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
  });

  it("로고+브랜드명 묶음을 담은 헤더 Toolbar가 가운데 정렬이다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    const aside = document.querySelector("#app-sidebar");
    expect(aside, "사이드바를 찾지 못했다").toBeTruthy();
    const headerToolbar = aside.querySelector(".MuiToolbar-root");
    expect(headerToolbar, "사이드바 헤더 Toolbar를 찾지 못했다").toBeTruthy();

    expect(getComputedStyle(headerToolbar).justifyContent).toBe("center");
  });
});

/* 상단바(topbar)의 로고 칸도 사이드바와 같은 폭으로 넓혀 뒀는데(사이드바 경계와 맞추려고),
 * 그 안에서 로고를 왼쪽에 붙이면(flex-start) 오른쪽에 큰 빈 공간이 남아 사이드바 자체의
 * 로고(가운데 정렬)와 다르게 보인다. 실측(하드 리프레시한 운영 화면)에서 그대로 재현됐다. */
describe("상단바 브랜드 버튼도 사이드바와 같은 정렬", () => {
  it("사이드바 폭만큼 넓힌 상단바 로고 칸도 가운데 정렬이다", () => {
    /* 제품 테마 안에서 렌더한다. 예전에는 테마 없이 렌더해도 통과했는데, 그건 `BrandLogo`
       가 MUI 기본 테마에도 있는 `palette.primary.main` 을 쓰고 있었기 때문이다 — 즉 이
       시험은 "제품 테마 밖에서도 그려진다"를 우연히 보장하고 있었지 의도한 계약이 아니었다.
       워드마크가 Brand 고정색(`palette.brand.wordmark`)으로 옮겨가면서 그 우연이 끝났다. */
    render(
      <ThemeModeProvider>
        <TopBrand onClick={() => {}} width={280} />
      </ThemeModeProvider>,
    );
    const btn = screen.getByRole("button", { name: "홈으로" });

    expect(getComputedStyle(btn).justifyContent).toBe("center");
  });
});
