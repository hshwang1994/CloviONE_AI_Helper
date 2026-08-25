import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Navigate, Routes, Route } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* PA-RC-0022 의 요구는 «역할과 무관하게 누구나 자기 개인 설정(화면 강조색)에 닿는다» 였다
 * (acceptance_criteria 5). S19 가 그 설정을 「내 프로필」 안으로 합치면서 계정 메뉴의
 * 항목도 하나가 됐다 — 요구는 그대로이고 가는 길만 하나다. 그래서 이 시험이 지키는 것도
 * 「어느 항목이 있는가」가 아니라 **「그 길로 가면 강조색에 닿는가」** 다.
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
              <Route path="/profile" element={<div>화면 강조색</div>} />
              {/* 옛 주소는 프로필로 넘어간다 — 북마크가 죽지 않는다. */}
              <Route path="/my-display" element={<Navigate to="/profile" replace />} />
            </Routes>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => { window.localStorage.clear(); apiMock.mockReset(); });

describe("계정 메뉴 — 개인 설정으로 가는 길", () => {
  it("메뉴의 '내 프로필'이 화면 강조색이 있는 화면으로 데려간다", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole("button", { name: /테스트 메뉴/ }));
    await user.click(screen.getByRole("menuitem", { name: "내 프로필" }));
    expect(await screen.findByText("화면 강조색")).toBeInTheDocument();
  });

  it("개인 설정 항목을 둘로 나누지 않는다 — '내 화면 설정'은 더 이상 없다", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole("button", { name: /테스트 메뉴/ }));
    expect(screen.queryByRole("menuitem", { name: "내 화면 설정" })).toBeNull();
  });
});
