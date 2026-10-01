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
  it("이메일 열 머리글이 기본 바닥 폭(4.5rem)이 아니라 식별자 바닥 폭(11rem, D-529)을 받는다", async () => {
    renderUsers();
    const header = await screen.findByRole("columnheader", { name: "이메일" });
    expect(header).toHaveStyle({ minWidth: "11rem" });
  });

  it("역할 열은 폭 숫자를 적지 않는다 — 그린 이름(역할 · 관리 범위)의 길이가 폭을 정한다(D-529)", async () => {
    renderUsers();
    const header = await screen.findByRole("columnheader", { name: "역할" });
    // 칸을 재기 전 첫 그림은 닫힌 집합의 바닥(6.5rem)이다 — 예전 고정 힌트 9rem 이 아니다.
    expect(header).toHaveStyle({ width: "6.5rem" });
    expect(header).not.toHaveStyle({ width: "9rem" });
  });

  it("부서 · 직책은 보조 열이라 좁으면 숨는다 — 이름 · 이메일 · 상태 · 역할은 필수다", async () => {
    renderUsers();
    await screen.findByRole("columnheader", { name: "이메일" });
    for (const name of ["이메일", "이름", "역할", "상태"]) {
      expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
    }
  });
});
