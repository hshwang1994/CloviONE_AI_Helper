import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

/* 사이드바 그룹이 "저절로" 접히는 버그.
 *
 * 활성 라우트가 든 그룹은 접힌 상태(collapsed:true)가 저장돼 있어도 강제로 펼쳐 보인다
 * (딥링크로 접힌 그룹 안에 도착해도 길을 잃지 않게). 문제는 그 "펼쳐 보임"이 진짜로
 * 펼친 것으로 기록되지 않는다는 것 — 그 그룹을 벗어나는 순간 다시 저장된 collapsed:true로
 * 조용히 되돌아간다. 사용자 입장에서는 방금 열려 있던 그룹을 접은 적이 없는데 다른 곳을
 * 클릭했더니 저절로 접힌 것처럼 보인다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
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

function renderShell(initialPath) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
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

describe("사이드바 그룹이 저절로 접히지 않는다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    wideViewport();
    apiMock.mockResolvedValue({ items: [], unread: 0, badge: 0, by_type: {}, unread_total: 0 });
    window.localStorage.clear();
    // PA-RC-0031: 예전엔 독립 "문서" 그룹이 있었지만 이제 /team-docs는 "팀 공간"에 합쳐졌다
    // — 그 그룹이 예전 세션에서 접힌 채로 저장돼 있다고 가정한다. "내 업무"(홈이 속한
    // 그룹)는 이 시험의 실제 관심사가 아니라 "다른 그룹의 항목을 눌러 벗어난다"는 절차를
    // 수행하기 위한 발판일 뿐이라 — "기록 없음 = 접힘"이 기본값인 지금(PA-RC-0017, AppShell.jsx
    // isOpen 주석 참조) 명시적으로 펼쳐 둔다. 접힌 채로 두면 "홈" 링크 자체가 안 보여
    // 시험이 본론(팀 공간 그룹의 펼침 유지)에 닿기도 전에 죽는다.
    window.localStorage.setItem(
      "clovirone_nav_collapsed:u1",
      JSON.stringify({ "팀 공간": true, "내 업무": false }),
    );
  });

  it("접혀 있던 그룹이 활성 라우트로 강제로 펼쳐진 뒤, 다른 곳을 클릭해도 계속 펼쳐져 있다", async () => {
    // '팀 공간' 그룹의 라우트(/team-docs, PA-RC-0031로 이 그룹에 합쳐짐)로 바로 진입 —
    // 접혀 있었어도 강제로 펼쳐진다.
    renderShell("/team-docs");
    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    const groupHeader = screen.getByRole("button", { name: /팀 공간/ });
    expect(groupHeader).toHaveAttribute("aria-expanded", "true");

    // 사용자는 이 그룹을 한 번도 직접 접은 적이 없다 — 다른 그룹의 항목("홈")을 클릭해
    // 그룹을 벗어난다.
    const user = userEvent.setup();
    await user.click(screen.getByRole("link", { name: /^홈$/ }));

    await waitFor(() => expect(screen.getByText("본문")).toBeInTheDocument());

    // 사용자가 직접 접은 적이 없으므로 '팀 공간' 그룹은 계속 펼쳐져 있어야 한다.
    expect(groupHeader).toHaveAttribute("aria-expanded", "true");
  });
});
