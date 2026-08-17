import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* PA-RC-0024 — 관리자 콘솔의 상세가 사용자 콘솔의 :id 라우트(/tickets/:id 등)와 같은
 * 방식으로 동작하는가.
 *
 * 예전엔 /users·/audit·/departments 모두 URL 없는 모달이라 딥링크·새로고침·뒤로가기가
 * 안 됐고, 등록되지 않은 관리자 경로는 설명 없이 /dashboard로(사용자 콘솔에서는 /me로)
 * 조용히 튕겼다. 여기서 못박는 것 네 가지:
 *   1) /users/:id 로 직접 들어가면 그 사용자 상세가 열린다(단건 GET).
 *   2) 행을 클릭하면 주소가 /users/:id 로 바뀐다(뒤로가기·새로고침의 전제).
 *   3) /departments/:id 도 같은 원리로 열린다(DataScreen 공용 배선, config.hasIdRoute).
 *   4) 모르는 관리자 경로는 대시보드로 안 튕기고 "찾을 수 없습니다"를 보여준다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("./auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import AdminRoutes from "./AdminRoutes.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";
const WAIT = { timeout: 8000 };
vi.setConfig({ testTimeout: 20000 });

const USER_ROW = {
  id: "u-detail-1", email: "detail@goodmit.co.kr", display_name: "상세대상", role: "user",
  active: true, locked: false, must_change_password: false, notion_mapping_status: "unmapped",
  department: null, department_id: null, title: null, title_id: null,
  last_login_at: null, created_at: AT, archived_at: null, active_session_count: 0,
};

const ORGS = [{ id: "org-1", name: "클로비원", slug: "clovirone", status: "active",
  department_count: 1, user_count: 1, created_at: AT }];
const DEPT_ROW = { id: "dep-1", name: "개발팀", org_name: "클로비원", org_id: "org-1",
  active: true, user_count: 1, created_at: AT };
const AUDIT_ROW = { id: "audit-1", created_at: AT, action: "user.update", object_type: "user",
  object_id: "u-detail-1", result: "success", user_id: "actor-1", actor_name: "감사대상행위자" };
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, path: "클로비원",
    parent_id: null, parent_name: null, active: true, user_count: 1, child_count: 1,
    subtree_user_count: 1, cycle: false, created_at: AT },
  { id: "dep-1", kind: "department", name: "개발팀", depth: 1, path: "클로비원 › 개발팀",
    parent_id: null, parent_name: null, org_id: "org-1", active: true, user_count: 1,
    child_count: 0, subtree_user_count: 1, cycle: false, created_at: AT },
];

function commonApi(extra) {
  return (url, opts) => {
    const u = String(url);
    const method = (opts && opts.method) || "GET";
    if (u.startsWith("/api/admin/users/u-detail-1")) return Promise.resolve(USER_ROW);
    // 실제 서버(app/org/router.py::get_org_item, body_key="department")는 단건 조회를
    // {"department": {...}}로 감싸서 준다 — 목이 감싸지 않은 응답을 흉내 내면 registry/org.js의
    // selectKey 배선이 빠져도 이 시험은 계속 통과한다(TEST SERVER 실측으로 실제로 놓쳤던 경우).
    if (u.startsWith("/api/admin/departments/dep-1")) return Promise.resolve({ department: DEPT_ROW });
    // audit의 단건 조회는 selectKey가 없다(governance.js) — 응답 자체가 그 행이다.
    if (u.startsWith("/api/admin/audit/audit-1")) return Promise.resolve(AUDIT_ROW);
    // 없는 id(예: does-not-exist)의 단건 조회를 여기서 가로챈다 — 아래 목록/트리 폴백이
    // prefix만 보고 더 넓게 걸려("/api/admin/audit"가 "/api/admin/audit/does-not-exist"에도
    // 걸린다) extra의 404 거부보다 먼저 응답해 버리는 것을 막는다.
    if (extra) { const hit = extra(u); if (hit !== undefined) return hit; }
    if (u.startsWith("/api/admin/users?")) return Promise.resolve({ items: [USER_ROW], total: 1, page_size: 20 });
    if (u === "/api/admin/departments/tree") return Promise.resolve({ items: TREE });
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: [DEPT_ROW] });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    if (u.startsWith("/api/admin/audit")) return Promise.resolve({ items: [], total: 0, page_size: 100 });
    if (u === "/api/admin/settings") {
      return Promise.resolve({ settings: { password_policy: { value: { min_length: 12, min_classes: 3 } } } });
    }
    if (method !== "GET") return Promise.resolve({ status: "ok" });
    return Promise.resolve({ items: [], total: 0 });
  };
}

// MemoryRouter(시험 전용)는 실제 HashRouter와 달리 navigate()가 window.location.hash를
// 건드리지 않는다 — 라우터 자신의 내부 스택만 바뀐다(datascreen.test.jsx 계열이 raw
// history.replaceState를 쓰는 다른 효과를 시험할 때 window.location.hash를 직접 보는 것과는
// 다른 경로). 같은 라우터 컨텍스트 안에서 useLocation()을 읽는 프로브로 실제 매치된 경로를 본다.
function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{location.pathname}</div>;
}

function renderRoute(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <LocationProbe />
              <AdminRoutes />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const currentPath = () => screen.getByTestId("location-probe").textContent;

describe("관리자 상세 딥링크", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("/users/:id 로 직접 들어가면 단건 GET으로 그 사용자 상세가 열린다", async () => {
    apiMock.mockImplementation(commonApi());
    renderRoute("/users/u-detail-1");
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument(), WAIT);
    expect(within(screen.getByRole("dialog")).getByText("상세대상")).toBeInTheDocument();
    expect(apiMock).toHaveBeenCalledWith("/api/admin/users/u-detail-1");
  });

  it("목록에서 행을 클릭하면 주소가 /users/:id 로 바뀐다", async () => {
    apiMock.mockImplementation(commonApi());
    const user = userEvent.setup();
    renderRoute("/users");
    expect(currentPath()).toBe("/users");
    const row = await screen.findByText("상세대상", {}, WAIT);
    await user.click(row.closest("tr"));
    await waitFor(() => expect(currentPath()).toBe("/users/u-detail-1"), WAIT);
  });

  it("상세를 닫으면 주소가 /users 로 돌아간다", async () => {
    apiMock.mockImplementation(commonApi());
    const user = userEvent.setup();
    renderRoute("/users/u-detail-1");
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument(), WAIT);
    expect(currentPath()).toBe("/users/u-detail-1");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument(), WAIT);
    await waitFor(() => expect(currentPath()).toBe("/users"), WAIT);
  });

  // PA-RC-0033: 없는 id는 예전엔 토스트 하나만 뜨고 몇 초 뒤 사라지면 화면엔 흔적이 남지
  // 않았다(대상만 못 연다는 사실 자체를 알 길이 없었다) — 이제 목록 위 모달 자리에 기존
  // ErrorState(찾을 수 없습니다)가 계속 남는다. 목록은 뒤에 그대로 살아있다(PA-RC-0024 유지).
  it("없는 사용자 id로 들어가면 ErrorState로 명시하고 목록은 그대로 뒤에 남는다", async () => {
    apiMock.mockImplementation(commonApi((u) => {
      if (u.startsWith("/api/admin/users/does-not-exist")) return Promise.reject({ status: 404 });
      return undefined;
    }));
    renderRoute("/users/does-not-exist");
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument(), WAIT);
    // 사용자 콘솔 5개 라우트·RouteNotFound와 같은 컴포넌트·같은 문구(ErrorState, kit.jsx).
    expect(within(screen.getByRole("dialog")).getByText("찾을 수 없습니다")).toBeInTheDocument();
    expect(screen.getByText("상세대상")).toBeInTheDocument();
  });

  it("없는 사용자 id 모달을 닫으면 주소가 /users로 돌아간다(sel이 애초에 비어 반대 방향 효과가 못 걸린다)", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation(commonApi((u) => {
      if (u.startsWith("/api/admin/users/does-not-exist")) return Promise.reject({ status: 404 });
      return undefined;
    }));
    renderRoute("/users/does-not-exist");
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument(), WAIT);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument(), WAIT);
    await waitFor(() => expect(currentPath()).toBe("/users"), WAIT);
  });

  it("/departments/:id 로 직접 들어가면 단건 GET으로 그 부서 상세가 열린다(DataScreen 공용 배선)", async () => {
    apiMock.mockImplementation(commonApi());
    renderRoute("/departments/dep-1");
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument(), WAIT);
    expect(apiMock).toHaveBeenCalledWith("/api/admin/departments/dep-1");
  });

  // PA-RC-0033 Handoff는 부서 상세를 "오른쪽 패널 자리"로 적었지만, 실측(위 found-case 시험)은
  // /departments/:id도 /users·/audit과 같은 DataScreen 공용 Modal을 이미 쓰고 있다(OrgConsole은
  // 트리 클릭 시의 자동 오픈만 피할 뿐, :id 딥링크는 다른 두 라우트와 동일한 배선이다) — 그래서
  // not-found도 같은 Modal 자리에 같은 ErrorState로 통일한다(DECISIONS.md 기록).
  it("없는 부서 id로 들어가면 ErrorState로 명시하고 트리·목록은 그대로 뒤에 남는다", async () => {
    apiMock.mockImplementation(commonApi((u) => {
      if (u.startsWith("/api/admin/departments/does-not-exist")) return Promise.reject({ status: 404 });
      return undefined;
    }));
    renderRoute("/departments/does-not-exist");
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument(), WAIT);
    expect(within(screen.getByRole("dialog")).getByText("찾을 수 없습니다")).toBeInTheDocument();
    expect(screen.getByTestId("org-console-tree")).toBeInTheDocument();
  });

  it("/audit/:id 로 직접 들어가면 단건 GET으로 그 감사 기록 상세가 열린다(governance.js hasIdRoute)", async () => {
    apiMock.mockImplementation(commonApi());
    renderRoute("/audit/audit-1");
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument(), WAIT);
    expect(apiMock).toHaveBeenCalledWith("/api/admin/audit/audit-1");
  });

  it("없는 감사 기록 id로 들어가면 ErrorState로 명시한다(빈 목록이라도 조용히 침묵하지 않는다)", async () => {
    apiMock.mockImplementation(commonApi((u) => {
      if (u.startsWith("/api/admin/audit/does-not-exist")) return Promise.reject({ status: 404 });
      return undefined;
    }));
    renderRoute("/audit/does-not-exist");
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument(), WAIT);
    expect(within(screen.getByRole("dialog")).getByText("찾을 수 없습니다")).toBeInTheDocument();
  });
});

describe("모르는 관리자 경로 — 대시보드로 조용히 튕기지 않는다", () => {
  beforeEach(() => { apiMock.mockReset(); apiMock.mockImplementation(commonApi()); });

  it("등록되지 않은 경로는 '찾을 수 없습니다'를 보여준다(리다이렉트 아님)", async () => {
    renderRoute("/this-path-does-not-exist-anywhere");
    expect(await screen.findByText("찾을 수 없습니다", {}, WAIT)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "대시보드" })).not.toBeInTheDocument();
  });
});
