/* **실제 화면**에서 확인한다 — 부서 범위 관리자에게 공지 배너의 쓰기 단추가 없다 (xa-07).
 *
 * `datascreen-admin-scope.test.jsx` 는 자기 손으로 만든 설정으로 셸의 장치만 쟀다. 그래서
 * 그 시험은 **배송되는 화면 어디에도 그 선언이 없어도** 초록이었다 — 부서 범위 관리자는
 * 여전히 「공지 추가」를 보고, 누르면 `POST /api/admin/announcements` 가 403 「공지는 전체
 * 범위 관리자만 만들고 바꿀 수 있습니다」로 돌아왔다(app/announcements/router.py). 여기서는
 * 실제 registry 설정(`PLATFORM_SCREENS.announcements`)을 그대로 그려서 그 간극을 못박는다.
 *
 * 반례는 같은 화면을 전역 범위 관리자로 여는 것이다 — 단추가 사라지면 안 된다.
 *
 * 범위 값은 두 자리에 함께 싣는다(`admin_scope` 와 `management.kind`). 셸이 둘 중 무엇을
 * 읽든 이 시험이 재는 사실("부서 범위 관리자에게는 안 보인다")은 같아야 한다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
let authData;
vi.mock("../../app/auth.jsx", () => ({ useAuth: () => ({ data: authData }) }));

import { DataScreen } from "../DataScreen.jsx";
import { PLATFORM_SCREENS } from "./platform.js";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const ROWS = [{
  id: "a1", title: "점검 예고", body: "토요일 02시부터 30분간 점검합니다.",
  level: "info", audience: "all", active: true,
  starts_at: null, ends_at: null, dismissible: true, created_at: "2026-08-24T00:00:00",
}];

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: ROWS, total: ROWS.length, page: 1, page_size: 20 });
  window.location.hash = "";
});

function renderAs(data) {
  authData = data;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <DataScreen config={PLATFORM_SCREENS.announcements} />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const DEPT_ADMIN = { role: "admin", id: "u-dept", admin_scope: "dept", management: { kind: "dept" } };
const GLOBAL_ADMIN = { role: "admin", id: "u-global", admin_scope: "global", management: { kind: "global" } };

/* 상세 판의 동작은 일부가 「작업 더 보기」 넘침 메뉴 안에 선다 — 단추든 메뉴 항목이든
   **사람이 지금 누를 수 있는가**가 재려는 사실이므로 둘을 함께 본다.
   메뉴를 연 뒤에는 그 뒤의 단추가 `aria-hidden` 이 되므로, 판 위에 바로 선 단추(「수정」)는
   메뉴를 열기 **전에** 본다. */
async function openRow(user) {
  await user.click(screen.getByText("점검 예고"));
  await screen.findByRole("dialog");
}
async function openOverflow(user) {
  const more = screen.queryByRole("button", { name: "공지 배너 작업 더 보기" });
  if (more) await user.click(more);
}
const clickable = (name) =>
  screen.queryByRole("button", { name }) || screen.queryByRole("menuitem", { name });

describe("공지 배너 — 부서 범위 관리자에게는 쓰기 단추가 없다", () => {
  it("「공지 추가」가 그려지지 않는다", async () => {
    renderAs(DEPT_ADMIN);
    await screen.findByText("점검 예고");

    expect(screen.queryByRole("button", { name: "공지 추가" })).toBeNull();
  });

  it("행을 열어도 「사용 안 함」·「삭제」·「수정」이 없다", async () => {
    const user = userEvent.setup();
    renderAs(DEPT_ADMIN);
    await screen.findByText("점검 예고");

    await openRow(user);
    expect(clickable("수정")).toBeNull();
    // 상세 판이 동작을 아예 안 그린 것이 아니다 — 읽기 성격의 딥링크는 그대로 있다.
    expect(clickable("감사 로그에서 보기")).not.toBeNull();
    await openOverflow(user);
    expect(clickable("사용 안 함")).toBeNull();
    expect(clickable("삭제")).toBeNull();
  });

  it("반례 — 전역 범위 관리자에게는 넷 다 그대로 있다", async () => {
    const user = userEvent.setup();
    renderAs(GLOBAL_ADMIN);
    await screen.findByText("점검 예고");

    expect(screen.getByRole("button", { name: "공지 추가" })).toBeInTheDocument();
    await openRow(user);
    expect(clickable("수정")).not.toBeNull();
    expect(clickable("감사 로그에서 보기")).not.toBeNull();
    await openOverflow(user);
    expect(clickable("사용 안 함")).not.toBeNull();
    expect(clickable("삭제")).not.toBeNull();
  });

  it("반례 — 범위를 안 싣는 계정은 전역으로 본다(옛 응답 호환)", async () => {
    renderAs({ role: "system_admin", id: "u-sys" });
    await screen.findByText("점검 예고");

    expect(screen.getByRole("button", { name: "공지 추가" })).toBeInTheDocument();
  });
});
