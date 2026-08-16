import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 회귀: 사용자 수정 폼의 '관리 범위' 필드 두 가지 문제.
 *
 * 1) SCOPE_OPTS는 '소속 조직'을 고를 수 있는 선택지로 보여주지만, 폼에는 실제로 어느 조직인지
 *    지정할 필드(scope_org_id)가 아예 없었다. 서버(app/users/service.py _apply_admin_scope)는
 *    admin_scope='org'인데 scope_org_id가 없으면 "조직 범위에는 대상 조직을 지정해야 합니다"로
 *    저장을 거부한다 — '조직관리자'를 만들려는 시도가 매번 이 검증 오류로 막혔다.
 * 2) app/core/scope.py build_scope는 role==='user'일 때 admin_scope 컬럼을 아예 읽지 않는다
 *    (부서 기반 자동 범위를 대신 쓴다). 그런데 '관리 범위' 필드는 role과 무관하게 항상 보여서,
 *    일반 사용자 계정에도 값을 저장할 수 있었다 — 저장되면 세션은 강제로 끊기지만 실제 효과는
 *    전혀 없는 죽은 설정이다.
 *
 * 두 테스트 모두 수정 전에는 FAIL(필드가 없거나, 있으면 안 되는 곳에 있음), 수정 후 PASS.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { Users } from "./Users.jsx";

const ADMIN_USER = {
  id: "u-admin", email: "admin@goodmit.co.kr", display_name: "관리자후보", role: "admin",
  admin_scope: "global", scope_org_id: null, scope_dept_id: null,
  active: true, locked: false, must_change_password: false, notion_mapping_status: "unmapped",
  department: null, department_id: null, title: null, title_id: null,
  last_login_at: null, created_at: "2026-07-01T00:00:00.000000", archived_at: null,
  active_session_count: 0,
};
const PLAIN_USER = {
  ...ADMIN_USER, id: "u-plain", email: "plain@goodmit.co.kr", display_name: "일반사용자후보",
  role: "user", admin_scope: "global", scope_org_id: null, scope_dept_id: null,
};

function commonApi(items) {
  return (path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items, total: items.length, page_size: 20 });
    if (path === "/api/admin/departments") return Promise.resolve({ items: [] });
    if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
    if (path === "/api/admin/organizations") return Promise.resolve({ items: [{ id: "org-1", name: "굿밋", active: true }], total: 1 });
    if (path === "/api/admin/settings") {
      return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
    }
    for (const it of items) {
      if (path === "/api/admin/users/" + it.id && method === "GET") return Promise.resolve(it);
    }
    if (path.endsWith("/sessions")) return Promise.resolve({ items: [] });
    if (method === "PATCH") return Promise.resolve({ status: "ok" });
    return Promise.resolve({});
  };
}

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

async function openEditForm(user, emailToClick) {
  renderUsers();
  const rowEmail = await screen.findByText(emailToClick);
  const row = rowEmail.closest("tr");
  await user.click(row);
  const drawer = await screen.findByRole("dialog");
  await user.click(within(drawer).getByRole("button", { name: "수정" }));
  return screen.findAllByRole("dialog").then((ds) => ds[ds.length - 1]);
}

describe("사용자 수정 폼 — 관리 범위(admin_scope)", () => {
  beforeEach(() => {
    apiMock.mockReset();
  });

  it("'소속 조직'을 고르면 대상 조직 칸이 나타나고, 고른 조직 id가 저장 요청에 실린다", async () => {
    apiMock.mockImplementation(commonApi([ADMIN_USER]));
    const user = userEvent.setup();
    const dialog = await openEditForm(user, "admin@goodmit.co.kr");

    // 지적 대상 1: 이 칸이 없으면 아래 클릭에서 combobox를 못 찾아 여기서 FAIL한다.
    await user.click(within(dialog).getByRole("combobox", { name: /관리 범위/ }));
    await user.click(await screen.findByRole("option", { name: "소속 조직(조직관리자)" }));

    const orgSelect = await within(dialog).findByRole("combobox", { name: /범위 대상 조직/ });
    await user.click(orgSelect);
    await user.click(await screen.findByRole("option", { name: "굿밋" }));

    await user.click(within(dialog).getByRole("button", { name: "저장" }));

    await waitFor(() => {
      const patchCall = apiMock.mock.calls.find((c) => c[0] === "/api/admin/users/u-admin" && c[1] && c[1].method === "PATCH");
      expect(patchCall).toBeTruthy();
      expect(patchCall[1].body.admin_scope).toBe("org");
      expect(patchCall[1].body.scope_org_id).toBe("org-1");
    });
  });

  it("역할이 '일반 사용자'면 관리 범위 필드 자체가 보이지 않는다(role=user는 admin_scope를 읽지 않는다)", async () => {
    apiMock.mockImplementation(commonApi([PLAIN_USER]));
    const user = userEvent.setup();
    const dialog = await openEditForm(user, "plain@goodmit.co.kr");

    // 지적 대상 2: 수정 전에는 이 필드가 항상 렌더돼 아래 단언이 FAIL한다.
    expect(within(dialog).queryByRole("combobox", { name: /관리 범위/ })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("combobox", { name: /범위 대상/ })).not.toBeInTheDocument();
  });
});
