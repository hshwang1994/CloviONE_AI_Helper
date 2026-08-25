import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 머리의 이동 버튼이 **이동한다** (S21).
 *
 * 행 액션은 맨 앞에서 `navigate` 를 처리했는데 머리 액션은 그 가지가 없어, registry 가
 * `{ label: "백업 목록", navigate: () => "#/backup" }` 로 선언한 버튼이 쓰기 분기로 떨어져
 * `a.path()` 에서 예외가 났다. 예외를 삼키는 자리가 오류 처리기라 화면에는 아무 일도 안
 * 일어난 것처럼 보였다 — 브라우저 검증에서 «백업 목록» 을 눌러도 주소가 그대로였다.
 *
 * 여기서 고정하는 것:
 *   1) 머리의 이동 버튼을 누르면 주소가 그 화면으로 바뀐다.
 *   2) 그 버튼은 서버를 부르지 않는다(이동은 왕복이 아니다).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", email: "a@b.c" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROWS = [{ id: "1", name: "리허설 1" }];

const CONFIG = {
  key: "restore-drills", area: "운영", title: "복구 리허설",
  endpoint: "/api/admin/restore-drills",
  columns: [{ key: "name", label: "이름", identifier: true }],
  headerActions: [{ label: "백업 목록", navigate: () => "#/backup" }],
};

let hashBefore;

beforeEach(() => {
  hashBefore = window.location.hash;
  apiMock.mockReset();
  apiMock.mockImplementation(() => Promise.resolve({ items: ROWS, total: ROWS.length }));
});

afterEach(() => { window.location.hash = hashBefore; });

function renderScreen(cfg) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <DataScreen config={cfg} />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("머리의 이동 액션", () => {
  it("누르면 그 화면 주소로 옮긴다", async () => {
    const user = userEvent.setup();
    renderScreen(CONFIG);
    await screen.findByText("리허설 1");
    await user.click(screen.getByRole("button", { name: "백업 목록" }));
    expect(window.location.hash).toBe("#/backup");
  });

  it("이동은 서버 왕복이 아니다 — 목록 조회 말고는 아무것도 안 부른다", async () => {
    const user = userEvent.setup();
    renderScreen(CONFIG);
    await screen.findByText("리허설 1");
    const before = apiMock.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "백업 목록" }));
    expect(apiMock.mock.calls.length).toBe(before);
  });
});
