import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* RBAC 발견성: role=admin + admin_scope 조합에 개념 이름이 없다.
 *
 * app/core/authz.py 의 ROLE_ORDER(user/operator/auditor/admin/system_admin) 와
 * app/users/models.py 의 admin_scope(global/org/dept) 는 **조합**된다 — role=admin +
 * admin_scope=org 가 "조직관리자", role=admin + admin_scope=dept 가 "부서관리자" 다.
 * 백엔드는 이미 이 조합으로 동작하지만(app/core/scope.py), 화면 어디에도 그 이름이
 * 없어 관리자가 이 개념을 찾을 수 없었다. adminConcept()가 그 이름을 붙이고, 목록·상세에
 * 실제로 렌더돼야 한다(pure 함수 테스트만으로는 화면에 반영됐는지 알 수 없다).
 */

import { adminConcept } from "./Users.jsx";

describe("adminConcept — role+admin_scope 조합에 이름 붙이기 (pure)", () => {
  it("admin이 아니면 개념이 없다", () => {
    expect(adminConcept({ role: "user", admin_scope: "org" })).toBeNull();
    expect(adminConcept({ role: "operator", admin_scope: "dept" })).toBeNull();
  });
  it("system_admin은 이 개념과 별개다(배지 없음)", () => {
    expect(adminConcept({ role: "system_admin", admin_scope: "global" })).toBeNull();
  });
  it("admin + org = 조직관리자", () => {
    expect(adminConcept({ role: "admin", admin_scope: "org" }).label).toBe("조직관리자");
  });
  it("admin + dept = 부서관리자", () => {
    expect(adminConcept({ role: "admin", admin_scope: "dept" }).label).toBe("부서관리자");
  });
  it("admin + global(또는 값 없음) = 전체 관리자", () => {
    expect(adminConcept({ role: "admin", admin_scope: "global" }).label).toBe("전체 관리자");
    expect(adminConcept({ role: "admin" }).label).toBe("전체 관리자");
  });
});

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { Users } from "./Users.jsx";

const ORG_ADMIN = {
  id: "u-org", email: "org-admin@goodmit.co.kr", display_name: "조직관리자후보", role: "admin",
  admin_scope: "org", scope_org_id: "org-1",
  active: true, locked: false, must_change_password: false, notion_mapping_status: "unmapped",
  department: null, department_id: null, title: null, title_id: null,
  last_login_at: null, created_at: "2026-07-01T00:00:00.000000", archived_at: null,
  active_session_count: 0,
};
const DEPT_ADMIN = {
  ...ORG_ADMIN, id: "u-dept", email: "dept-admin@goodmit.co.kr", display_name: "부서관리자후보",
  admin_scope: "dept", scope_org_id: null, scope_dept_id: "d-1",
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/admin/users?")) {
      return Promise.resolve({ items: [ORG_ADMIN, DEPT_ADMIN], total: 2, page_size: 20 });
    }
    if (path === "/api/admin/departments") return Promise.resolve({ items: [{ id: "d-1", name: "ClovirONE팀", active: true }] });
    if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
    if (path === "/api/admin/settings") {
      return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
    }
    if (path === "/api/admin/users/u-org") return Promise.resolve(ORG_ADMIN);
    if (path === "/api/admin/users/u-dept") return Promise.resolve(DEPT_ADMIN);
    if (path.endsWith("/sessions")) return Promise.resolve({ items: [] });
    return Promise.resolve({});
  });
});

function renderUsers() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Users />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Users 목록/상세 — 조직관리자·부서관리자 배지가 실제로 렌더된다", () => {
  it("목록의 '역할' 칸에 조직관리자/부서관리자 배지가 함께 보인다", async () => {
    renderUsers();
    expect(await screen.findByText("org-admin@goodmit.co.kr")).toBeInTheDocument();
    expect(screen.getByText("조직관리자")).toBeInTheDocument();
    expect(screen.getByText("부서관리자")).toBeInTheDocument();
  });

  it("상세 드로어의 '관리 범위' 줄에도 개념 배지가 붙는다", async () => {
    const user = userEvent.setup();
    renderUsers();
    const openRows = await screen.findAllByRole("row", { name: /상세 보기/ });
    await user.click(openRows[0]);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("조직관리자")).toBeInTheDocument();
  });
});
