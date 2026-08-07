import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useNavigate } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 라우트가 바뀌면 포커스가 본문으로 간다 (접근성 감사 5, Z14).
 *
 * 감사가 본 상태: 사이드바 메뉴를 눌러 화면을 바꿔도 포커스가 사이드바에 남고, 화면이
 * 바뀐 사실이 낭독되지 않는다. 키보드 사용자는 Tab 을 사이드바 스무 항목만큼 더 눌러야
 * 본문에 닿고, 스크린리더 사용자는 화면이 바뀐 줄을 모른다.
 *
 * 무엇을 언제 알리는지의 계약도 여기서 못박는다 - 매 이동마다 시끄럽게 낭독하면
 * 그것도 못 쓴다. 첫 진입에는 알리지 않고, 경로가 실제로 바뀔 때만 화면 이름 한 줄을
 * polite 로 알린다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { AppShell } from "./AppShell.jsx";
import { USER_NAV } from "./navConfig.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* jsdom 에는 matchMedia 가 없어 MUI useMediaQuery 가 늘 false 를 준다 - 셸이 좁은 화면으로
   판단해 사이드바를 아예 안 그린다(nav-badge.test.jsx 가 같은 처방을 쓴다). */
function wideViewport() {
  window.matchMedia = (query) => ({
    matches: /min-width/.test(query),
    media: query,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null,
    dispatchEvent: () => false,
  });
}

function Go({ to, label }) {
  const navigate = useNavigate();
  return <button type="button" onClick={() => navigate(to)}>{label}</button>;
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
                <Go to="/my-tickets" label="내 티켓으로" />
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
  apiMock.mockImplementation(() => Promise.resolve({}));
  wideViewport();
});

describe("화면 전환과 포커스", () => {
  it("첫 진입에는 아무것도 낭독하지 않는다", async () => {
    renderShell();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(screen.queryByText(/화면으로 이동했습니다/)).toBeNull();
  });

  it("경로가 바뀌면 포커스가 본문으로 옮겨간다", async () => {
    renderShell();
    const main = document.getElementById("main-content");
    expect(document.activeElement).not.toBe(main);
    await userEvent.click(screen.getByRole("button", { name: "내 티켓으로" }));
    await waitFor(() => expect(document.activeElement).toBe(main));
  });

  it("바뀐 화면 이름을 polite 로 한 줄 알린다", async () => {
    renderShell();
    await userEvent.click(screen.getByRole("button", { name: "내 티켓으로" }));
    const said = await screen.findByText("내 티켓 화면으로 이동했습니다.");
    const live = said.closest("[aria-live]");
    expect(live).not.toBeNull();
    expect(live).toHaveAttribute("aria-live", "polite");
  });
});
