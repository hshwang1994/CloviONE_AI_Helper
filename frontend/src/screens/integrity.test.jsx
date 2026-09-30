import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 조직 정합성 화면 — 탭은 행을 가진 표로 나누고, 목록은 전량 페이지로 받는다 (계획 3.2 · D-508).
 *
 * 못박는 것:
 *   ① 탭 라벨 옆 칩이 그 탭의 건수다. 주소에 탭이 없으면 건수가 있는 첫 탭이 켜진다.
 *   ② 목록은 검사 목록 API 에서 온다(요약의 표본이 아니다). 선택 수가 적용 단추에 그대로 간다.
 *   ③ 적용은 서버의 작업 API 로 가고, 건너뛴 항목은 사유와 함께 말한다.
 *   ④ 0건 탭은 한 줄 안내와 검사 줄이다. 표도 체크박스도 없다.
 *   ⑤ 고치기는 전역 관리자만 한다 — 운영자와 부서 범위 관리자에게는 선택 열도 부서 후보 요청도 없다.
 *   ⑥ 관리자 범위 탭의 역할은 관리 콘솔의 역할 이름으로 선다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
let authUser = { role: "system_admin", admin_scope: "global" };
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: authUser }) }));

import { Integrity } from "./Integrity.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function finding(key, tab, kind, title, count, fixes = []) {
  return {
    key, tab, kind, title, why: `${title}는 닫혀 있습니다.`, remedy: `${title}를 고치세요.`,
    count, fixes, fixable_here: fixes.length > 0, items: [],
  };
}

const PEOPLE = finding("users_without_membership", "people", "user", "소속이 지정되지 않은 사용자", 2, ["membership"]);
const PEOPLE_DEAD = finding("users_on_inactive_department", "people", "user", "비활성 부서에 속한 사용자", 0, ["membership"]);
const TICKETS = finding("tickets_without_one_project", "tickets", "ticket", "프로젝트가 정확히 하나가 아닌 티켓", 0, ["ticket_project"]);
const TICKETS_UNMAPPED = finding("tickets_with_unmapped_assignees", "tickets", "ticket", "담당자를 포털 계정으로 연결하지 못한 티켓", 0);

const USERS = [
  { id: "u1", display_name: "홍길동", email: "hong@goodmit.co.kr", role: "user", reason: "부서도 조직 직속도 지정되지 않았습니다.", link: "#/users/u1" },
  { id: "u2", display_name: "김철수", email: "kim@goodmit.co.kr", role: "user", reason: "부서도 조직 직속도 지정되지 않았습니다.", link: "#/users/u2" },
];

const ADMIN_ROWS = [
  { id: "a1", display_name: "UI QA", email: "qa@goodmit.co.kr", role: "system_admin", admin_scope: "global", scope_path: [] },
  { id: "a2", display_name: "박민준", email: "park@goodmit.co.kr", role: "admin", admin_scope: "global", scope_path: [] },
];

function summary(findings, admins = { total: 2, by_scope: { global: 2, org: 0, dept: 0 } }) {
  const tabs = [["people", "사람"], ["tickets", "티켓"], ["resources", "프로젝트와 문서 공간"], ["sprints", "회차"]]
    .map(([key, label]) => ({ key, label, count: findings.filter((f) => f.tab === key).reduce((n, f) => n + f.count, 0) }));
  return {
    findings, tabs, notes: { closed_sprints_without_team: 0 },
    total_issues: findings.reduce((n, f) => n + f.count, 0), admins,
  };
}

let data;
let fixReply;
beforeEach(() => {
  data = summary([PEOPLE, PEOPLE_DEAD, TICKETS, TICKETS_UNMAPPED]);
  fixReply = { ok: true, changed: 2, skipped: [] };
  authUser = { role: "system_admin", admin_scope: "global" };
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/admin/integrity") return Promise.resolve(data);
    if (path.startsWith("/api/admin/integrity/checks/users_without_membership/fix")) return Promise.resolve(fixReply);
    if (path.startsWith("/api/admin/integrity/checks/users_without_membership?")) {
      return Promise.resolve({ items: USERS, total: 2, kind: "user", fixes: ["membership"], page: 1, page_size: 50 });
    }
    if (path.startsWith("/api/admin/integrity/checks/")) {
      return Promise.resolve({ items: [], total: 0, kind: "ticket", fixes: [], page: 1, page_size: 50 });
    }
    if (path.startsWith("/api/admin/integrity/admins")) {
      return Promise.resolve({ items: ADMIN_ROWS, total: ADMIN_ROWS.length, page: 1, page_size: 50 });
    }
    if (path.startsWith("/api/admin/departments")) return Promise.resolve({ items: [{ id: "d1", name: "개발팀" }] });
    if (path.startsWith("/api/projects")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({});
  });
});

function renderScreen(entry = "/integrity") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[entry]}>
              <Integrity />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const calls = (prefix) => apiMock.mock.calls.map((c) => String(c[0])).filter((u) => u.startsWith(prefix));

describe("탭과 전량 목록", () => {
  it("탭 옆 칩이 탭의 건수이고, 건수가 있는 첫 탭이 켜진다", async () => {
    renderScreen();
    const people = await screen.findByRole("tab", { name: /사람/ });
    expect(people).toHaveAttribute("aria-selected", "true");
    expect(within(people).getByText("2")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /관리자 범위/ })).toBeInTheDocument();
  });

  it("목록은 검사 목록 API 에서 온다 — 요약의 표본을 그리지 않는다", async () => {
    renderScreen();
    expect(await screen.findByText("홍길동")).toBeInTheDocument();
    expect(calls("/api/admin/integrity/checks/users_without_membership?")[0])
      .toBe("/api/admin/integrity/checks/users_without_membership?page=1&page_size=50");
    expect(screen.getByText(/소속이 지정되지 않은 사용자는 닫혀 있습니다/)).toBeInTheDocument();
  });

  it("선택 수가 적용 단추에 그대로 간다 — 전체 선택 포함", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("checkbox", { name: "홍길동 선택" }));
    // 소속을 아직 안 골랐으니 적용은 닫혀 있다.
    expect(screen.getByRole("button", { name: "선택한 1명에 적용" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "전체 선택" }));
    expect(screen.getByRole("button", { name: "선택한 2명에 적용" })).toBeInTheDocument();
  });

  it("적용은 작업 API 로 간다 — 고른 id 와 소속 하나만 싣는다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("checkbox", { name: "전체 선택" }));
    await user.click(screen.getByRole("combobox", { name: "지정할 소속" }));
    await user.click(await screen.findByRole("option", { name: "개발팀" }));
    await user.click(screen.getByRole("button", { name: "선택한 2명에 적용" }));
    await waitFor(() => expect(calls("/api/admin/integrity/checks/users_without_membership/fix")).toHaveLength(1));
    const post = apiMock.mock.calls.find((c) => String(c[0]).endsWith("/fix"));
    expect(post[1]).toEqual({ method: "POST", body: { fix: "membership", ids: ["u1", "u2"], department_id: "d1" } });
  });

  it("건너뛴 항목은 사유와 함께 말한다", async () => {
    fixReply = { ok: true, changed: 1, skipped: [{ id: "u2", title: "김철수", reason: "보관된 계정입니다." }] };
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("checkbox", { name: "전체 선택" }));
    await user.click(screen.getByRole("combobox", { name: "지정할 소속" }));
    await user.click(await screen.findByRole("option", { name: "조직 직속(부서 없음)" }));
    await user.click(screen.getByRole("button", { name: "선택한 2명에 적용" }));
    expect(await screen.findByText(/1명을 고쳤습니다\. 1명은 고치지 못했습니다\. 김철수: 보관된 계정입니다\./)).toBeInTheDocument();
    const post = apiMock.mock.calls.find((c) => String(c[0]).endsWith("/fix"));
    expect(post[1].body).toEqual({ fix: "membership", ids: ["u1", "u2"], organization_direct: true });
  });
});

describe("0건 탭과 딥링크", () => {
  it("0건 탭은 한 줄 안내와 검사 줄이다 — 표도 체크박스도 없다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("tab", { name: /티켓/ }));
    expect(await screen.findByText("이 탭에서 정리할 항목이 없습니다.")).toBeInTheDocument();
    const row = screen.getByText(TICKETS.title).closest(".k-settingrow");
    expect(row).toHaveClass("k-settingrow--compact");
    expect(within(row).getByText(TICKETS.why)).toHaveAttribute("title", TICKETS.why);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("주소가 고른 검사를 연다 — 0건이어도 목록 자리가 선다", async () => {
    data = summary([PEOPLE, PEOPLE_DEAD, { ...TICKETS, count: 3 }, TICKETS_UNMAPPED]);
    renderScreen("/integrity?tab=tickets&issue=tickets_with_unmapped_assignees");
    expect(await screen.findByText("정리할 항목이 없습니다.")).toBeInTheDocument();
    expect(calls("/api/admin/integrity/checks/tickets_with_unmapped_assignees?")).toHaveLength(1);
    expect(calls("/api/admin/integrity/checks/tickets_without_one_project?")).toHaveLength(0);
  });
});

describe("고치기는 전역 관리자만 한다", () => {
  it("전역 관리자는 행을 고른 뒤에 부서 후보를 받는다 — 페이지 인자 없이 정확히 그 주소로(P-76)", async () => {
    const user = userEvent.setup();
    renderScreen();
    const box = await screen.findByRole("checkbox", { name: "홍길동 선택" });
    // 작업 줄은 고른 행이 있을 때만 선다 - 고르기 전에는 후보를 받지 않는다.
    expect(calls("/api/admin/departments")).toEqual([]);
    await user.click(box);
    await waitFor(() => expect(calls("/api/admin/departments")).toEqual(["/api/admin/departments?active=true"]));
  });

  it("운영자는 목록은 보지만 선택 열도 적용 단추도 부서 후보 요청도 없다", async () => {
    authUser = { role: "operator", admin_scope: "global" };
    renderScreen();
    expect(await screen.findByText("홍길동")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: /적용/ })).toBeNull();
    expect(calls("/api/admin/departments")).toEqual([]);
  });

  it("부서 범위 관리자도 고치지 못한다 — 서버가 전역 범위만 받는다", async () => {
    authUser = { role: "admin", admin_scope: "dept" };
    renderScreen();
    expect(await screen.findByText("홍길동")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(calls("/api/admin/departments")).toEqual([]);
  });
});

describe("관리자 범위 탭", () => {
  it("역할은 서버 값이 아니라 관리 콘솔의 역할 이름으로 선다", async () => {
    renderScreen("/integrity?tab=admins");
    const table = (await screen.findByText("박민준")).closest("table");
    expect(within(table).getByText("시스템 관리자")).toBeInTheDocument();
    expect(within(table).getByText("관리자")).toBeInTheDocument();
    expect(within(table).queryByText("system_admin")).toBeNull();
    expect(table.querySelector("[title='system_admin']")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("전부 전체 관리자이면 범위 기능이 아직 쓰이지 않는다고 한 줄로 말한다", async () => {
    renderScreen("/integrity?tab=admins");
    expect(await screen.findByText(/모든 관리자가 전체 관리자라서/)).toBeInTheDocument();
  });

  it("반례: 부서 관리자가 하나라도 있으면 그 줄은 서지 않는다", async () => {
    data = summary([PEOPLE, PEOPLE_DEAD, TICKETS, TICKETS_UNMAPPED], { total: 2, by_scope: { global: 1, org: 0, dept: 1 } });
    renderScreen("/integrity?tab=admins");
    await screen.findByText("박민준");
    expect(screen.queryByText(/모든 관리자가 전체 관리자라서/)).toBeNull();
  });
});
