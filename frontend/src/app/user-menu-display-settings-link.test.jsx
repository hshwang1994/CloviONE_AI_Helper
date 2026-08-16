import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* PA-RC-0022: 계정 메뉴에 「내 화면 설정」 항목이 있고, 실제로 /my-display로 보낸다 —
 * 역할과 무관하게 누구나 자기 개인 설정(화면 강조색)에 닿아야 한다(acceptance_criteria 5).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a) }));

import { UserMenu } from "./UserMenu.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";

function renderMenu() {
  return render(
    <MemoryRouter initialEntries={["/me"]}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <UserMenu name="테스트" userId="acct-1" avatarUrl={null} />
            <Routes>
              <Route path="/me" element={<div>홈</div>} />
              <Route path="/my-display" element={<div>내 화면 설정 화면</div>} />
            </Routes>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => { window.localStorage.clear(); apiMock.mockReset(); });

describe("계정 메뉴 — 내 화면 설정", () => {
  it("메뉴에 '내 화면 설정' 항목이 있고, 누르면 /my-display로 이동한다", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole("button", { name: /테스트 메뉴/ }));
    await user.click(screen.getByRole("menuitem", { name: "내 화면 설정" }));
    expect(await screen.findByText("내 화면 설정 화면")).toBeInTheDocument();
  });
});
