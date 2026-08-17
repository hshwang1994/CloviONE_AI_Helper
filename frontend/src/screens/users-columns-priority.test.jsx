import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* PA-RC-0029: /users의 유일한 고유 식별자인 이메일이 20/20행 잘렸다(131px, 필요 198px)
 * 반면 '역할'(295px)·'최근 로그인'(287px)은 내용량과 무관하게 더 넓었다. 이메일 열에
 * identifier:true(kit.jsx DataTable의 최소 폭 12.5rem)를 붙여 고쳤다 — 이 테스트는 그
 * 열 정의가 나중에 조용히 되돌아가지 않게 고정한다(required_tests (3)). 실제 렌더
 * 픽셀(clippedRows=0)은 jsdom이 계산하지 않으므로 TEST SERVER pa2_cols.py 재실행으로
 * 별도 확인한다.
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

const USER = {
  id: "u-1", email: "ui-qa-user@goodmit.co.kr", display_name: "서윤경", role: "admin",
  active: true, locked: false, must_change_password: false, notion_mapping_status: "unmapped",
  department: null, department_id: null, title: null, title_id: null,
  last_login_at: "2026-08-15T01:00:00.000000", created_at: "2026-07-01T00:00:00.000000", archived_at: null,
  active_session_count: 0,
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/admin/users?")) {
      return Promise.resolve({ items: [USER], total: 1, page_size: 20 });
    }
    if (path === "/api/admin/departments") return Promise.resolve({ items: [] });
    if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
    if (path === "/api/admin/settings") {
      return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
    }
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

describe("Users 목록 — 이메일 열의 최소 폭 (PA-RC-0029)", () => {
  it("이메일 열 머리글이 기본 바닥 폭(4.5rem)이 아니라 식별자 바닥 폭(12.5rem)을 받는다", async () => {
    renderUsers();
    const header = await screen.findByRole("columnheader", { name: "이메일" });
    expect(header).toHaveStyle({ minWidth: "12.5rem" });
  });

  it("역할 열은 좁힌 폭 힌트(9rem)를 받는다 — 배지 1~2개만 담는데 내용량과 무관하게 넓던 것을 회수", async () => {
    renderUsers();
    const header = await screen.findByRole("columnheader", { name: "역할" });
    expect(header).toHaveStyle({ width: "9rem" });
  });
});
