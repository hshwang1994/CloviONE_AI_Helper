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

/* ── W5 정정: 이 자리에는 **볼 수 없는 락업**이 있었다 ─────────────────────────
 *
 * 이 시험은 사이드바 헤더 Toolbar 의 정렬을 지켰는데, 그 Toolbar 는 Drawer paper 가
 * `top:0` 에서 시작하고 그 위를 `zIndex: drawer + 1` 인 fixed AppBar 가 같은 높이로
 * 덮기 때문에 **어느 뷰포트에서도 사람이 볼 수 없었다**(서랍을 연 390 포함 — MUI 는
 * temporary Drawer 의 root zIndex 도 `zIndex.drawer` 로 낮춘다). 즉 이 시험은 아무도
 * 못 보는 마크업의 겉모습을 jsdom 으로 고정하고 있었고, 더 나쁘게는 W2 가 상단바에서
 * 태그라인을 빼면서 바로 그 «보이지 않는 자리» 를 근거로 삼았다(D-183 ⑦).
 *
 * 그래서 지키는 대상을 바꾼다 — «가려진 락업이 가운데 정렬인가» 가 아니라
 * **«가려진 자리에 내용이 있는가»** 다. 내용이 없어야 한다. 단언 수는 늘었다. */
describe("사이드바 상단 — 가려지는 자리에는 내용을 두지 않는다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    wideViewport();
    apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
  });

  it("사이드바에 두 번째 브랜드 락업이 없다 — AppBar 가 덮는 자리다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    const aside = document.querySelector("#app-sidebar");
    expect(aside, "사이드바를 찾지 못했다").toBeTruthy();
    // 락업(SVG)도, 제품명 글자도, 태그라인도 이 안에 없다.
    expect(aside.querySelector('[role="img"][aria-label*="ClovirAssist"]')).toBeNull();
    expect(aside.textContent).not.toMatch(/SMART WORKSPACE ASSISTANT/);
    expect(aside.textContent).not.toMatch(/Smart Workspace Assistant/);
  });

  it("그 자리는 여전히 AppBar 높이만큼 **자리**를 잡는다 — 메뉴가 상단바 밑으로 들어가지 않는다", async () => {
    renderShell();
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());
    const aside = document.querySelector("#app-sidebar");
    const spacer = aside.querySelector('[data-appbar-spacer]');
    expect(spacer, "AppBar 높이만큼의 자리(스페이서)를 찾지 못했다").toBeTruthy();
    // 자리만 잡는다 — 내용이 있으면 그것은 가려진다.
    expect(spacer.textContent).toBe("");
    // 그리고 그 자리는 사이드바의 **첫 번째** 것이다(그 아래부터가 보이는 영역이다).
    expect(spacer.parentElement.firstElementChild).toBe(spacer);
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
