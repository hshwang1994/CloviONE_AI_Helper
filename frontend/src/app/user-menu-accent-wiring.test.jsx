/* UserMenu가 실제로 ThemeModeProvider에 계정을 알려 주는가 (배선 증명).
 *
 * `ThemeModeProvider`는 `AuthProvider`보다 바깥에 마운트돼 있어 userId를 prop으로 받을 수
 * 없다 - 계정을 아는 첫 지점인 UserMenu.jsx가 `identifyAccentUser(userId)`를 불러야
 * 강조색의 계정별 복원이 실제로 동작한다. 함수 하나가 올바르게 동작하는 것과, 그 함수에
 * 실제 값이 도달하는 것은 다른 사건이다(auth-wiring.test.jsx와 같은 이유) - 이 테스트는
 * 후자를 본다: 진짜 ThemeModeProvider 아래에 진짜 UserMenu를 마운트하고, userId 계정에
 * 저장돼 있던 강조색이 실제로 화면(테마)에 반영되는지 끝까지 확인한다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a) }));

import { UserMenu } from "./UserMenu.jsx";
import { ThemeModeProvider, useThemeMode } from "../ui/ThemeModeProvider.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";

function AccentReadout() {
  const { accent } = useThemeMode();
  return <div data-testid="accent">{accent}</div>;
}

describe("UserMenu → ThemeModeProvider 강조색 배선", () => {
  beforeEach(() => {
    window.localStorage.clear();
    apiMock.mockReset();
  });

  it("userId로 저장된 강조색이 UserMenu 마운트만으로 실제로 적용된다", async () => {
    window.localStorage.setItem("clovirassist_accent:acct-1", "#327C98");

    render(
      <MemoryRouter>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <AccentReadout />
              <UserMenu name="테스트" userId="acct-1" avatarUrl={null} />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(screen.getByTestId("accent")).toHaveTextContent("#327C98")
    );
  });
});
