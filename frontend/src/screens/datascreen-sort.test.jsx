import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 지시 10 — 표가 정렬을 안다. **다만 거짓말하지 않는 범위에서만.**
 *
 * 서버가 페이지를 자르는 목록에서 보이는 20건만 정렬해 놓고 화살표를 그리면, 사용자는
 * "가장 오래된 것"을 봤다고 믿는다. 실제로는 그 페이지 안에서 가장 오래된 것이다.
 * `clientFilter` 는 결과가 줄어드는 게 눈에 보여 경고 한 줄로 막을 수 있었지만, 정렬은
 * 틀린 순서가 **맞아 보이기** 때문에 경고로 못 막는다. 그래서 정렬 UI 자체를 안 준다.
 *
 * 여기서 고정하는 것:
 *   1) 전체를 들고 있는 목록에는 정렬이 있다.
 *   2) 서버 페이지네이션 목록에는 정렬 컨트롤이 **아예 없다**.
 *   3) 세 번 누르면 원래(서버가 정한) 순서로 돌아온다.
 *   4) 스크린리더가 방향을 읽는다(aria-sort).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", email: "a@b.c" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { dateCol } from "./data-screen/columnHelpers.jsx";

const ROWS = [
  { id: "1", name: "나중", created_at: "2026-08-18T10:00:00" },
  { id: "2", name: "가장 먼저", created_at: "2026-01-02T10:00:00" },
  { id: "3", name: "중간", created_at: "2026-05-05T10:00:00" },
];

function config(extra) {
  return {
    key: "things", area: "운영", title: "물건", endpoint: "/api/admin/things",
    columns: [{ key: "name", label: "이름", identifier: true }, dateCol("created_at", "추가")],
    ...extra,
  };
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(() => Promise.resolve({ items: ROWS, total: ROWS.length }));
});

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

/** 표의 첫 열 값을 위에서 아래로. */
function nameOrder() {
  return Array.from(document.querySelectorAll("tbody tr")).map(
    (tr) => tr.querySelector("td").textContent.trim(),
  );
}

describe("표 정렬 — 전체를 들고 있는 목록", () => {
  it("날짜 열 머리를 누르면 오름차순으로 정렬된다", async () => {
    const user = userEvent.setup();
    renderScreen(config());
    await screen.findByText("가장 먼저");
    expect(nameOrder()).toEqual(["나중", "가장 먼저", "중간"]); // 서버가 준 순서

    await user.click(screen.getByRole("button", { name: /^추가/ }));
    expect(nameOrder()).toEqual(["가장 먼저", "중간", "나중"]);
  });

  it("다시 누르면 내림차순, 세 번째에 원래 순서로 돌아온다", async () => {
    const user = userEvent.setup();
    renderScreen(config());
    await screen.findByText("가장 먼저");
    const head = screen.getByRole("button", { name: /^추가/ });

    await user.click(head);
    await user.click(head);
    expect(nameOrder()).toEqual(["나중", "중간", "가장 먼저"]);

    // 되돌릴 길이 없으면 정렬은 되돌릴 수 없는 조작이 된다.
    await user.click(head);
    expect(nameOrder()).toEqual(["나중", "가장 먼저", "중간"]);
  });

  it("스크린리더가 정렬 방향을 읽는다", async () => {
    const user = userEvent.setup();
    renderScreen(config());
    await screen.findByText("가장 먼저");
    const cell = screen.getByRole("button", { name: /^추가/ }).closest("th");
    expect(cell).toHaveAttribute("aria-sort", "none");
    await user.click(screen.getByRole("button", { name: /^추가/ }));
    expect(cell).toHaveAttribute("aria-sort", "ascending");
  });
});

describe("표 정렬 — 서버가 페이지를 자르는 목록", () => {
  it("정렬 컨트롤을 아예 주지 않는다", async () => {
    renderScreen(config({ paginated: true }));
    await screen.findByText("가장 먼저");
    // 머리행이 그냥 글자여야 한다 — 누를 수 있으면 그 순간 거짓말이 시작된다.
    expect(screen.queryByRole("button", { name: /^추가/ })).toBeNull();
    const head = screen.getByText("추가").closest("th");
    expect(head).not.toHaveAttribute("aria-sort");
  });
});
