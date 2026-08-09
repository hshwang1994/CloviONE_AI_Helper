/* 로그아웃 실패를 삼키지 않는다.
 *
 * 예전에는 `/logout` 이 5xx·망 순단으로 실패해도 무조건 `/login` 으로 보냈다. 세션·쿠키가
 * 아직 살아 있으면 `GET /login` 이 303 으로 `/` 로 되돌리므로, 사용자는 "로그아웃 중…"을
 * 보고 기다렸다가 대시보드로 돌아오고 오류 메시지가 없다 - 로그아웃된 줄 알고 자리를 뜨면
 * 다음 사람이 그 세션을 그대로 쓴다(공용 PC 위험). 주석이 정당화하는 건 **401(세션이 이미
 * 없음)** 뿐이다 - 그 경우는 쿠키가 죽었으니 이동해도 안전하다.
 */
import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a) }));

import { UserMenu } from "./UserMenu.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";

function renderMenu() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <ConfirmProvider>
          <UserMenu name="테스트" userId="u1" avatarUrl={null} />
        </ConfirmProvider>
      </ToastProvider>
    </MemoryRouter>
  );
}

async function openAndClickLogout() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /메뉴/ }));
  await user.click(await screen.findByText("로그아웃"));
}

describe("로그아웃 실패 처리", () => {
  let originalLocation;
  beforeEach(() => {
    apiMock.mockReset();
    originalLocation = window.location;
    delete window.location;
    window.location = { ...originalLocation, href: "" };
  });
  afterEach(() => {
    window.location = originalLocation;
  });

  it("서버 오류(5xx)면 로그인 화면으로 보내지 않고 토스트로 알린다", async () => {
    const err = new Error("서버에서 문제가 생겼습니다.");
    err.status = 500;
    apiMock.mockRejectedValueOnce(err);
    renderMenu();

    await openAndClickLogout();

    await waitFor(() => expect(screen.getByText(/서버에서 문제가 생겼습니다/)).toBeInTheDocument());
    expect(window.location.href, "세션이 살아 있을 수 있는데 /login 으로 이동했다").toBe("");
  });

  it("401(세션이 이미 없음)이면 그대로 로그인 화면으로 보낸다", async () => {
    const err = new Error("로그인이 필요합니다.");
    err.status = 401;
    apiMock.mockRejectedValueOnce(err);
    renderMenu();

    await openAndClickLogout();

    await waitFor(() => expect(window.location.href).toBe("/login"));
  });

  it("성공하면 로그인 화면으로 보낸다", async () => {
    apiMock.mockResolvedValueOnce({});
    renderMenu();

    await openAndClickLogout();

    await waitFor(() => expect(window.location.href).toBe("/login"));
  });
});
