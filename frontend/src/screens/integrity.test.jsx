import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 조직 정합성 화면 — 판은 정리할 것이 있는 항목에만 준다 (관리자 UI 정리 회차 · D-457).
 *
 * 못박는 것:
 *   ① 건수가 있는 항목은 판이고, 표와 공용 선택 열(체크박스 이름 = 대상 이름 + 「선택」)을 갖는다.
 *   ② 0건 항목은 판·표·체크박스 없이 이름·이유·「0건」 줄 하나다. 정리하는 법(remedy)은 거기 없다.
 *   ③ 선택 수가 지정 줄과 적용 버튼에 그대로 간다(전체 선택 포함).
 *   ④ 반례: 전부 0건이면 화면에 체크박스가 하나도 없고, 관리자 범위 표는 그대로 있다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
/* 역할은 시험마다 바꾼다 — 지정 폼과 부서 후보 요청은 전역 관리자에게만 있다(아래 describe). */
let authUser = { role: "system_admin", admin_scope: "global" };
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: authUser }) }));

import { Integrity } from "./Integrity.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function finding(key, title, items, extra = {}) {
  return {
    key, title, why: `${title} 는 닫혀 있습니다.`, remedy: `${title} 를 지정하세요.`,
    count: items.length, items, fixable_here: false, ...extra,
  };
}

const OPEN = finding("users_without_membership", "소속이 지정되지 않은 사용자", [
  { id: "u1", display_name: "홍길동", email: "hong@goodmit.co.kr" },
  { id: "u2", display_name: "김철수", email: "kim@goodmit.co.kr" },
], { fixable_here: true });
const CLEAR_A = finding("tickets_multi_project", "프로젝트가 정확히 하나가 아닌 티켓", []);
const CLEAR_B = finding("spaces_without_owner", "소속이 지정되지 않은 지식 공간", []);

const ADMINS = {
  by_scope: { global: 2, org: 0, dept: 0 }, total: 2,
  items: [
    { id: "a1", display_name: "UI QA", role: "system_admin", admin_scope: "global", scope_path: [] },
    { id: "a2", display_name: "박민준", role: "admin", admin_scope: "global", scope_path: [] },
  ],
};

function payload(findings) {
  return { findings, total_issues: findings.reduce((n, f) => n + f.count, 0), admins: ADMINS };
}

let data;
beforeEach(() => {
  data = payload([OPEN, CLEAR_A, CLEAR_B]);
  authUser = { role: "system_admin", admin_scope: "global" };
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path === "/api/admin/integrity") return Promise.resolve(data);
    if (path.startsWith("/api/admin/departments")) return Promise.resolve({ items: [{ id: "d1", name: "개발팀" }] });
    return Promise.resolve({});
  });
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Integrity />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("판은 정리할 것이 있는 항목에만 준다", () => {
  it("건수가 있는 항목은 h3 제목 + 표 + 공용 선택 열이다", async () => {
    renderScreen();
    expect(await screen.findByRole("heading", { level: 3, name: OPEN.title })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "홍길동 선택" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "전체 선택" })).toBeInTheDocument();
    expect(screen.getByText("2건")).toBeInTheDocument();
    expect(screen.getByText("0건 선택됨")).toBeInTheDocument();
    expect(screen.getByText(OPEN.remedy)).toBeInTheDocument();
  });

  it("0건 항목은 줄 하나다 — 제목 요소가 아니고 표도 체크박스도 없다", async () => {
    renderScreen();
    await screen.findByText(CLEAR_A.title);
    expect(screen.queryByRole("heading", { name: CLEAR_A.title })).toBeNull();
    expect(screen.getAllByText("0건").length).toBe(2);
    const row = screen.getByText(CLEAR_A.title).closest(".k-settingrow");
    expect(row).not.toBeNull();
    expect(within(row).queryByRole("checkbox")).toBeNull();
    expect(within(row).queryByRole("table")).toBeNull();
    // «왜 문제인가» 는 남는다 — 이름만 남기면 0건이 무엇을 뜻하는지 모른다.
    expect(within(row).getByText(CLEAR_A.why)).toBeInTheDocument();
    // 정리하는 법은 0건 줄에 없다 — 읽을 사람이 없는 안내다.
    expect(screen.queryByText(CLEAR_A.remedy)).toBeNull();
  });

  it("선택 수가 지정 줄과 적용 버튼에 그대로 간다 — 전체 선택 포함", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("checkbox", { name: "홍길동 선택" }));
    expect(screen.getByText("1건 선택됨")).toBeInTheDocument();
    // 소속을 아직 안 골랐으니 적용은 닫혀 있다.
    expect(screen.getByRole("button", { name: "선택한 1명에 적용" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "전체 선택" }));
    expect(screen.getByText("2건 선택됨")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "선택한 2명에 적용" })).toBeInTheDocument();
  });

  it("반례: 전부 0건이면 체크박스가 하나도 없고 관리자 범위 표는 그대로다", async () => {
    data = payload([{ ...OPEN, count: 0, items: [] }, CLEAR_A, CLEAR_B]);
    renderScreen();
    await screen.findByText(/정리할 것이 없습니다/);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getAllByText("0건").length).toBe(3);
    expect(screen.queryByRole("heading", { level: 3 })).toBeNull();
    expect(screen.getByRole("heading", { level: 2, name: "관리자 범위 현황" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "정리할 항목" })).toBeInTheDocument();
    expect(screen.getByText("박민준")).toBeInTheDocument();
  });
});

/* D-501 — 0건은 한 줄 · 한 사실은 한 곳 · 서버 값을 화면에 그대로 두지 않는다. */
describe("0건 줄 · 관리자 범위 (D-501)", () => {
  it("0건 항목은 촘촘한 줄이다 — 이름과 까닭이 각각 한 줄에 서고 까닭 전체는 title 이 든다", async () => {
    renderScreen();
    const row = (await screen.findByText(CLEAR_A.title)).closest(".k-settingrow");
    expect(row).toHaveClass("k-settingrow--compact");
    const why = within(row).getByText(CLEAR_A.why);
    expect(why).toHaveAttribute("title", CLEAR_A.why);
  });

  it("관리자 수는 구획 제목 옆 건수 하나다 — 표를 다시 세던 요약 카드는 없다", async () => {
    renderScreen();
    const heading = await screen.findByRole("heading", { level: 2, name: "관리자 범위 현황" });
    const titleRow = heading.parentElement.parentElement;
    expect(within(titleRow).getByText("2명")).toBeInTheDocument();
    expect(screen.queryByLabelText("관리자 범위 현황")).toBeNull();
    expect(document.querySelector("[data-summary-total]")).toBeNull();
  });

  it("전부 전체 관리자이면 범위 기능이 아직 쓰이지 않는다고 한 줄로 말한다", async () => {
    renderScreen();
    expect(await screen.findByText(/모든 관리자가 전체 관리자라서/)).toBeInTheDocument();
  });

  it("반례: 조직 · 부서 관리자가 하나라도 있으면 그 줄은 서지 않는다", async () => {
    data = {
      ...payload([OPEN, CLEAR_A, CLEAR_B]),
      admins: {
        by_scope: { global: 1, org: 0, dept: 1 }, total: 2,
        items: [
          ADMINS.items[0],
          { id: "a3", display_name: "이서연", role: "admin", admin_scope: "dept", scope_path: [{ id: "d1", name: "개발팀" }] },
        ],
      },
    };
    renderScreen();
    await screen.findByText("이서연");
    expect(screen.queryByText(/모든 관리자가 전체 관리자라서/)).toBeNull();
  });

  it("역할은 서버 값이 아니라 관리 콘솔의 역할 이름으로 선다", async () => {
    renderScreen();
    const table = (await screen.findByText("박민준")).closest("table");
    expect(within(table).getByText("시스템 관리자")).toBeInTheDocument();
    expect(within(table).getByText("관리자")).toBeInTheDocument();
    expect(within(table).queryByText("system_admin")).toBeNull();
    expect(within(table).queryByText("admin")).toBeNull();
    // 말줄임 힌트에도 서버 값이 새지 않는다.
    expect(table.querySelector("[title='system_admin']")).toBeNull();
  });
});

/* 지정은 전역 관리자만 한다 — 서버(`POST /api/admin/integrity/membership`)가 CONSOLE_WRITE +
 * 전역 범위로 막는다. 예전에는 운영자·감사자에게도 지정 폼이 그려졌고(누르면 403), 부서
 * 후보 요청(`/api/admin/departments` 는 admin 이상)이 화면을 열 때마다 403 으로 실패했다. */
describe("지정 폼과 부서 후보는 지정할 수 있는 사람에게만 있다", () => {
  const deptCalls = () => apiMock.mock.calls.map((c) => String(c[0])).filter((u) => u.startsWith("/api/admin/departments"));

  it("전역 관리자는 부서 후보를 받는다 — 페이지 인자 없이 정확히 그 주소로(P-76)", async () => {
    renderScreen();
    await screen.findByRole("checkbox", { name: "홍길동 선택" });
    await screen.findByRole("button", { name: "선택한 0명에 적용" });
    expect(deptCalls()).toEqual(["/api/admin/departments?active=true"]);
  });

  it("운영자는 진단은 보지만 지정 폼도 부서 후보 요청도 없다", async () => {
    authUser = { role: "operator", admin_scope: "global" };
    renderScreen();
    expect(await screen.findByRole("heading", { level: 3, name: OPEN.title })).toBeInTheDocument();
    expect(screen.getByText("홍길동")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /명에 적용/ })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "지정할 소속" })).toBeNull();
    expect(deptCalls()).toEqual([]);
  });

  it("부서 범위 관리자도 지정하지 못한다 — 서버가 전역 범위만 받는다", async () => {
    authUser = { role: "admin", admin_scope: "dept" };
    renderScreen();
    await screen.findByRole("heading", { level: 3, name: OPEN.title });
    expect(screen.queryByRole("button", { name: /명에 적용/ })).toBeNull();
    expect(deptCalls()).toEqual([]);
  });
});
