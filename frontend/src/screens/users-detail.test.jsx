import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 회귀: 사용자 상세 팝업(UserDetail)의 Rules of Hooks 위반 크래시.
 *
 * UserDetail은 <Users/>에서 항상 마운트되고(user={sel}, sel 초기값 null), 예전엔 세 훅
 * (copiedId useState/useRef/useEffect)이 `if (!user) return null;` 아래에 있었다. 그래서
 * 목록 행의 '상세'를 눌러 sel이 null→비null로 바뀌는 순간 훅 개수가 12→15로 늘어 React가
 * "Rendered more hooks than during the previous render"를 렌더 중 던졌고, App.jsx의
 * ErrorBoundary가 상세 팝업을 통째로 "화면을 표시하는 중 문제가 발생했습니다"로 대체했다
 * (모든 사용자의 첫 상세 클릭마다 100% 발생). 이 테스트는 수정 전엔 클릭에서 throw로 FAIL,
 * 훅을 이른 return 위로 옮긴 뒤엔 드로어가 정상으로 열려 PASS 해야 한다. 네트워크·타이머 없음. */

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
  id: "u-1", email: "syk@goodmit.co.kr", display_name: "서윤경", role: "admin",
  active: true, locked: false, must_change_password: false, notion_mapping_status: "unmapped",
  department: null, department_id: null, title: null, title_id: null,
  last_login_at: null, created_at: "2026-07-01T00:00:00.000000", archived_at: null,
  active_session_count: 0,
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (path.startsWith("/api/admin/users?")) {
      return Promise.resolve({ items: [USER], total: 1, page_size: 20 });
    }
    if (path === "/api/admin/departments") return Promise.resolve({ items: [] });
    if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
    if (path === "/api/admin/settings") {
      return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
    }
    if (path === "/api/admin/users/u-1" && method === "GET") return Promise.resolve(USER);
    if (path === "/api/admin/users/u-1/sessions") return Promise.resolve({ items: [] });
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

describe("Users 상세 팝업 (Rules of Hooks 회귀)", () => {
  it("행을 눌러도 크래시 없이 상세 드로어가 열린다", async () => {
    const user = userEvent.setup();
    renderUsers();
    // 목록에 사용자가 렌더된 뒤 행(aria-label="상세 보기: <이메일>")을 누른다.
    const openRow = await screen.findByRole("row", { name: /상세 보기/ });
    await user.click(openRow); // 수정 전에는 여기서 훅 개수 변화로 throw → 테스트 실패
    // 드로어(role=dialog)가 열리고 그 안에 대상 사용자 정보가 보이면 크래시 없이 렌더된 것이다.
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("서윤경")).toBeInTheDocument();       // 드로어 제목
    expect(within(dialog).getByText("syk@goodmit.co.kr")).toBeInTheDocument(); // 이메일 Row
    // 상세 전용 작업 버튼도 함께 렌더된다(드로어가 온전히 그려졌음을 확인).
    expect(within(dialog).getByRole("button", { name: "비밀번호 재설정" })).toBeInTheDocument();
  });
});
