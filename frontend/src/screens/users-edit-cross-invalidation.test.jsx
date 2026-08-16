import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 회귀: 사용자 수정/대량 지정이 부서·직책·조직·조직도 캐시를 낡게 뒀다.
 *
 * registry/org.js의 부서·직책·조직 화면은 ["departments"]/["job-titles"]/["organizations"]를
 * 캐시 키로 쓰고(DataScreen.jsx cacheRoot=[config.key]), 조직도(OrgTree.jsx)는 ["org-tree"]를
 * 쓴다. 이 화면(Users.jsx)도 useNameOptions로 정확히 같은 키를 읽어 부서/직책/조직 드롭다운을
 * 채운다 — 그런데 사용자 수정(PATCH)이 성공해도 저 캐시들을 무효화하지 않았다. 부서/직책/조직
 * 화면의 소속·보유 인원(user_count) 열과 삭제 버튼 게이팅(when: (r) => !r.user_count)이 최신
 * 인원 수를 못 보는 결함이었다.
 *
 * 부서/직책/조직 캐시는 이 화면 자신도 useNameOptions로 늘 마운트해 쓰고 있어(활성 쿼리),
 * invalidateQueries가 곧바로 백그라운드 재조회를 트리거하고 그 재조회가 빨리 끝나면
 * isInvalidated가 금방 다시 false로 돌아온다 — 그래서 그 셋은 "저장 후 GET이 한 번 더
 * 나갔는가"(재조회가 실제로 일어났는가)로 확인한다. 조직도(org-tree)는 이 화면에 마운트되어
 * 있지 않은 비활성 쿼리라 자동 재조회가 없으므로, cross-screen-invalidation.test.jsx와 같은
 * 방식으로 isInvalidated를 그대로 본다.
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
  id: "u-1", email: "user@goodmit.co.kr", display_name: "홍길동", role: "user",
  admin_scope: "global", scope_org_id: null, scope_dept_id: null,
  active: true, locked: false, must_change_password: false, notion_mapping_status: "unmapped",
  department: null, department_id: null, title: null, title_id: null,
  last_login_at: null, created_at: "2026-07-01T00:00:00.000000", archived_at: null,
  active_session_count: 0,
};

function commonApi() {
  return (path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items: [USER], total: 1, page_size: 20 });
    if (path === "/api/admin/departments") return Promise.resolve({ items: [] });
    if (path === "/api/admin/job-titles") return Promise.resolve({ items: [] });
    if (path === "/api/admin/organizations") return Promise.resolve({ items: [], total: 0 });
    if (path === "/api/admin/settings") {
      return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
    }
    if (path === "/api/admin/users/" + USER.id && method === "GET") return Promise.resolve(USER);
    if (path.endsWith("/sessions")) return Promise.resolve({ items: [] });
    if (method === "PATCH") return Promise.resolve({ status: "ok" });
    return Promise.resolve({});
  };
}

function renderUsers(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Users />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function getCallCount(path) {
  return apiMock.mock.calls.filter((c) => c[0] === path && (!c[1] || !c[1].method || c[1].method === "GET")).length;
}

describe("사용자 수정 — 화면 밖 값 갱신", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(commonApi());
  });

  it("사용자 정보를 저장하면 부서/직책/조직/조직도 캐시까지 함께 무효화한다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 상세 드로어 열기 -> 수정 폼 열기 -> 텍스트 지우고 다시 타이핑 -> 저장까지 실제 사용자
    // 상호작용을 여러 단계 거치므로 vitest 기본 테스트 타임아웃(5초)보다 넉넉히 잡는다.
    // 네 캐시가 이미 값을 들고 있는 상태를 만든다 — 그래야 '무효화됐다'가 뜻을 가진다.
    // 조직도는 이 화면에 마운트돼 있지 않으므로 값을 미리 심어 두고 '무효화됐다'가 뜻을 갖게 한다.
    qc.setQueryData(["org-tree"], { items: [] });
    expect(qc.getQueryState(["org-tree"]).isInvalidated).toBe(false);

    const user = userEvent.setup();
    renderUsers(qc);

    const rowEmail = await screen.findByText("user@goodmit.co.kr");
    // 부서/직책/조직은 이 화면 자신이 마운트 시 이미 한 번씩 읽는다 — 그 기준 호출 수를
    // 저장 '후' 재조회가 실제로 일어났는지 비교할 기준선으로 잡는다.
    await waitFor(() => {
      expect(getCallCount("/api/admin/departments")).toBeGreaterThan(0);
      expect(getCallCount("/api/admin/job-titles")).toBeGreaterThan(0);
      expect(getCallCount("/api/admin/organizations")).toBeGreaterThan(0);
    });
    const deptBefore = getCallCount("/api/admin/departments");
    const titleBefore = getCallCount("/api/admin/job-titles");
    const orgBefore = getCallCount("/api/admin/organizations");

    const row = rowEmail.closest("tr");
    await user.click(row);
    const drawer = await screen.findByRole("dialog");
    await user.click(within(drawer).getByRole("button", { name: "수정" }));
    const dialogs = await screen.findAllByRole("dialog");
    const editDialog = dialogs[dialogs.length - 1];

    // 필수 필드는 라벨에 접근성 트리에서 숨긴(aria-hidden) '*' 표시가 붙어 textContent가
    // "이름 *"가 된다 — 정확히 "이름"과 일치하지 않으므로 부분 일치로 찾는다.
    const nameInput = within(editDialog).getByLabelText(/이름/);
    await user.clear(nameInput);
    await user.type(nameInput, "홍길동2");
    await user.click(within(editDialog).getByRole("button", { name: "저장" }));

    await waitFor(() => {
      const patchCall = apiMock.mock.calls.find((c) => c[0] === "/api/admin/users/" + USER.id && c[1] && c[1].method === "PATCH");
      expect(patchCall).toBeTruthy();
    });

    // 활성 쿼리(부서/직책/조직)는 무효화가 실제 재조회로 이어졌는가로 확인한다.
    await waitFor(() => {
      expect(getCallCount("/api/admin/departments"), "부서 재조회").toBeGreaterThan(deptBefore);
      expect(getCallCount("/api/admin/job-titles"), "직책 재조회").toBeGreaterThan(titleBefore);
      expect(getCallCount("/api/admin/organizations"), "조직 재조회").toBeGreaterThan(orgBefore);
    }, { timeout: 3000 });
    // 비활성 쿼리(조직도)는 재조회 없이 invalidated 표시만 남는다.
    await waitFor(() => {
      expect(qc.getQueryState(["org-tree"]).isInvalidated, "조직도").toBe(true);
    }, { timeout: 3000 });
  }, 15000);
});
