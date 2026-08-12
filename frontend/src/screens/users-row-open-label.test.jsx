import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* SEM-01: `/users` 목록의 "상세 보기" 버튼(과 대량 작업 선택 체크박스)이 18명 전부
 * 똑같은 이름으로 읽혔다. 첫 열이 선택 체크박스(render 있음, rowName:false로 스스로
 * 제외)이고 그다음 "이메일" 열엔 표식이 없어 kit.jsx의 rowOpenLabel 이 옛 폴백(첫 열 —
 * 즉 체크박스)에 걸려 무조건 "상세 보기"로 뭉뚱그렸다. 이메일 열에 rowName 을 달아
 * 고쳤다 — 이 테스트는 실제로 2행을 렌더링해 두 "상세 보기" 버튼의 접근 이름이 서로
 * 다른지 확인한다(단일 행 픽스처인 users-detail.test.jsx는 이 결함을 드러낼 수 없었다).
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

const USERS = [
  {
    id: "u-1", email: "syk@goodmit.co.kr", display_name: "서윤경", role: "admin",
    active: true, locked: false, must_change_password: false, notion_mapping_status: "unmapped",
    department: null, department_id: null, title: null, title_id: null,
    last_login_at: null, created_at: "2026-07-01T00:00:00.000000", archived_at: null,
    active_session_count: 0,
  },
  {
    id: "u-2", email: "hgd@goodmit.co.kr", display_name: "홍길동", role: "member",
    active: true, locked: false, must_change_password: false, notion_mapping_status: "unmapped",
    department: null, department_id: null, title: null, title_id: null,
    last_login_at: null, created_at: "2026-07-02T00:00:00.000000", archived_at: null,
    active_session_count: 0,
  },
];

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/admin/users?")) {
      return Promise.resolve({ items: USERS, total: USERS.length, page_size: 20 });
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

describe("Users 목록의 행별 접근 이름 (SEM-01)", () => {
  it("두 사용자의 '상세 보기' 버튼이 서로 다른 이름으로 읽힌다", async () => {
    renderUsers();
    const openButtons = await screen.findAllByRole("button", { name: /상세 보기/ });
    expect(openButtons).toHaveLength(2);
    const names = openButtons.map((b) => b.getAttribute("aria-label"));
    expect(new Set(names).size).toBe(2);
    expect(names).toContain("상세 보기: 서윤경");
    expect(names).toContain("상세 보기: 홍길동");
  });

  it("대량 선택 체크박스도 서로 다른 이름으로 읽힌다(같은 열 표식을 공유)", async () => {
    renderUsers();
    await screen.findAllByRole("button", { name: /상세 보기/ });
    const boxes = screen.getAllByRole("checkbox").filter((b) => b.getAttribute("aria-label") !== "전체 선택");
    const names = boxes.map((b) => b.getAttribute("aria-label"));
    expect(new Set(names).size).toBe(names.length);
    expect(names).toContain("서윤경 선택");
    expect(names).toContain("홍길동 선택");
  });
});
