import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

/* '보관된 계정 보기'가 켜졌을 때 배너가 서버가 실제로 하는 일을 말한다.
 *
 * 2026-09-06 배포 환경 실측: 조직 콘솔의 「부서 미지정 11」 타일을 눌러
 * `#/users?department_id=none` 으로 간 뒤 이 상자를 켜면 목록이 2건에서 9건으로 바뀌는데,
 * 사라진 것은 방금 보던 사용 중인 계정 2건이고 새로 온 것은 보관된 계정 9건이다.
 * 서버의 `archived=true` 는 보관함을 여는 문이라 사용 중인 계정을 **빼고** 답한다
 * (`app/users/router.py` 의 `User.archived_at.is_not(None) if archived else ...`).
 * 그런데 배너는 「보관된 계정을 포함해 보고 있습니다」라고 했다 — 그러면 관리자는
 * 목록에서 없어진 2건을 사고로 읽는다.
 *
 * 반례를 함께 잰다: 상자가 꺼져 있으면 배너 자체가 없어야 한다. 하나만 재면
 * 「항상 띄운다」도 통과한다.
 *
 * qa-contract-change: 필터 바의 켬/끔 스위치 · 체크박스를 34 중립 단추(FilterToggle, aria-pressed)로 옮겼다(핸드오프 RULES §3, 계획 P-14). 스위치 · 체크박스 역할로 찾던 단언을 같은 이름의 단추로 옮기고, 눌림 상태(aria-pressed)를 더 단언한다.
 */

beforeEach(() => { window.location.hash = ""; });
afterEach(() => { window.location.hash = ""; });

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { Users } from "./Users.jsx";

const LIVE = { id: "u-live", email: "live@example.com", display_name: "리브계정", role: "user", active: true };
const GONE = {
  id: "u-gone", email: "gone@example.com", display_name: "보관계정", role: "user",
  active: false, archived_at: "2026-08-01T00:00:00",
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/admin/users?")) {
      // 서버 계약 그대로: archived=true 면 보관된 계정'만' 돌려준다.
      const archived = new URL("http://x" + path).searchParams.get("archived") === "true";
      const items = archived ? [GONE] : [LIVE];
      return Promise.resolve({ items, total: items.length, page_size: 20 });
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
      <MemoryRouter initialEntries={["/users"]}>
        <Routes><Route path="/users" element={<Users />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("사용자 목록 — 보관함 배너는 '만'이라고 말한다", () => {
  it("상자를 켜면 '보관된 계정만 보고 있습니다'가 뜬다", async () => {
    const user = userEvent.setup();
    renderUsers();
    await screen.findByText("리브계정");

    const archivedToggle = screen.getByRole("button", { name: /보관된 계정 보기/ });
    expect(archivedToggle).toHaveAttribute("aria-pressed", "false");
    await user.click(archivedToggle);
    await waitFor(() => expect(archivedToggle).toHaveAttribute("aria-pressed", "true"));

    await waitFor(() => expect(screen.getByText(/보관된 계정만 보고 있습니다/)).toBeInTheDocument());
    // 옛 문구가 되살아나면 관리자는 사라진 계정을 사고로 읽는다.
    expect(screen.queryByText(/포함해 보고 있습니다/)).toBeNull();
    // 배너가 말한 대로 사용 중인 계정은 목록에 없다.
    await waitFor(() => expect(screen.queryByText("리브계정")).toBeNull());
    expect(screen.getByText("보관계정")).toBeInTheDocument();
  });

  it("상자가 꺼져 있으면 배너가 없다 — 반례", async () => {
    renderUsers();
    await screen.findByText("리브계정");
    expect(screen.queryByText(/보관된 계정만 보고 있습니다/)).toBeNull();
    expect(screen.queryByText(/포함해 보고 있습니다/)).toBeNull();
  });
});
