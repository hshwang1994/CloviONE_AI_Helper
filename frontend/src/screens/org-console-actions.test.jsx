import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 조직 관리 작업 공간(O1 · D-533)으로 대상 동작이 페이지 머리에서 판 머리로 옮겨 갔고(D-510 을 뒤집는다), 「수정」은 「더 보기」의 첫 항목이 됐다. 메뉴 순서는 수정 · 비활성화(다시 사용) · 삭제 · 구분선 · 감사 로그 · 사용자 화면 · 상세 정보다. 확인 창은 confirm 문장 대신 열 때 서버에 묻는 영향 확인 창(`/impact`)이다 — 조직 정지 인원은 로그아웃될 정확한 수(보관 · 비활성 · 시스템 관리자 제외), 부서 비활성화는 그대로 남는 것들의 수다. 삭제 항목은 늘 있고, 못 지우는 부서면 창이 막는 항목만 말한다. 단언을 판 머리 · 메뉴 · 영향 창으로 옮겼다.
 *
 * 조직 콘솔의 **행동** — 확인 창과 게이트.
 *
 * 1) 조직 비활성화 창은 이 동작이 실제로 하는 일을 말한다: 몇 명이 지금 바로 로그아웃되고 다시 로그인할 수 없는지,
 *    빠지는 시스템 관리자 수, 되돌릴 수 있다는 사실. 수는 서버의 `/impact` 가 센다.
 * 2) 부서 비활성화 창은 그대로 남는 것들의 수를 말한다 — 0명과 200명이 같은 경고를 받지 않는다.
 * 3) 지울 수 있는 부서는 확인 창(취소가 기본 초점, 채움 위험 「삭제」), 못 지우는 부서는 막는 항목과 그 화면 링크 + 「비활성화하기」.
 * 4) 화면의 채움(primary)은 판 머리의 추가 단추 하나이고, 그 단추가 동작 묶음의 오른쪽 끝이다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1", management: { kind: "global" } } }),
}));

import { OrgConsole } from "./OrgConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, path: "클로비원",
    active: true, user_count: 0, child_count: 2, subtree_user_count: 9, created_at: AT },
  { id: "dep-sales", kind: "department", name: "영업팀", depth: 1, path: "클로비원 › 영업팀",
    org_id: "org-1", active: true, user_count: 4, child_count: 0, subtree_user_count: 4, created_at: AT },
  { id: "dep-empty", kind: "department", name: "빈부서", depth: 1, path: "클로비원 › 빈부서",
    org_id: "org-1", active: true, user_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT },
];
const ORGS = [{ id: "org-1", name: "클로비원", slug: "clovirone", status: "active",
  department_count: 2, user_count: 9, can_edit: true, created_at: AT }];
const DEPT_ITEMS = {
  "dep-sales": { id: "dep-sales", name: "영업팀", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 4, child_department_count: 0, created_at: AT },
  "dep-empty": { id: "dep-empty", name: "빈부서", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 0, child_department_count: 0, created_at: AT },
};
/* 영향 판정은 서버가 낸다 — 표본도 서버가 실제로 싣는 모양 그대로다(app/org/service.py::department_impact). */
const IMPACT = {
  "dep-sales": {
    delete: {
      deletable: false,
      blockers: [{ kind: "users", label: "소속 사용자", count: 4, unit: "명", archived_count: 0 }],
      detachables: [],
      summary: "이 부서에 소속 사용자 4명이 연결되어 있어 삭제할 수 없습니다.",
      reason: "이 부서에 소속 사용자 4명이 연결되어 있어 삭제할 수 없습니다.",
    },
    deactivate: { members: 4, child_departments: 0, projects: 2, scoped_admins: 0, open_sprints: 1 },
  },
  "dep-empty": {
    delete: { deletable: true, blockers: [], detachables: [], summary: null, reason: null },
    deactivate: { members: 0, child_departments: 0, projects: 0, scoped_admins: 0, open_sprints: 0 },
  },
};
const ORG_IMPACT = { suspend: { signed_out_users: 7, exempt_system_admins: 1, inactive_users: 2, archived_users: 3 } };

function mockApi(overrides) {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
    if (overrides) {
      const hit = overrides(u, options);
      if (hit !== undefined) return hit;
    }
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    const deptImpact = u.match(/^\/api\/admin\/departments\/([a-z-]+)\/impact$/);
    if (deptImpact) return Promise.resolve(IMPACT[deptImpact[1]]);
    if (u === "/api/admin/organizations/org-1/impact") return Promise.resolve(ORG_IMPACT);
    if (u.startsWith("/api/admin/organizations") && (!options || !options.method)) return Promise.resolve({ items: ORGS });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ ok: true });
    const single = u.match(/^\/api\/admin\/departments\/([a-z-]+)$/);
    if (single && (!options || !options.method)) return Promise.resolve({ department: DEPT_ITEMS[single[1]] || null });
    if (single) return Promise.resolve({ ok: true });
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: [] });
    if (u.startsWith("/api/admin/users")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({ items: [] });
  });
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{location.pathname + location.search}</div>;
}

function renderAt(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[path]}>
          <LocationProbe />
          <Routes>
            <Route path="/organizations" element={<OrgConsole />} />
            <Route path="/departments/:id" element={<OrgConsole />} />
          </Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const WAIT = { timeout: 8000 };
vi.setConfig({ testTimeout: 20000 });
const panel = () => screen.getByTestId("org-console-panel");
const paneHead = () => panel().querySelector("[data-pane-head]");
const isContained = (el) => [...el.classList].some((c) => /^MuiButton-contained[A-Z]/.test(c));
const itemName = (m) => m.getAttribute("aria-label") || m.textContent;

/** 판이 선 뒤 「더 보기」를 열고 메뉴를 돌려준다. 메뉴 단추의 이름은 「<대상> 작업 더 보기」다. */
async function openMenu(name) {
  await within(await screen.findByTestId("org-console-panel", {}, WAIT)).findByRole("heading", { level: 2, name }, WAIT);
  await userEvent.click(within(paneHead()).getByRole("button", { name: `${name} 작업 더 보기` }));
  return screen.findByRole("menu", {}, WAIT);
}

beforeEach(() => { apiMock.mockReset(); });

describe("조직 비활성화", () => {
  it("🔴 영향 창이 로그아웃될 정확한 인원 · 빠지는 시스템 관리자 · 되돌리는 길을 말하고, 확정하면 PATCH 가 나간다", async () => {
    mockApi();
    renderAt("/organizations");
    const menu = await openMenu("클로비원");
    await userEvent.click(within(menu).getByRole("menuitem", { name: "비활성화" }));
    const dlg = await screen.findByRole("dialog", { name: "클로비원을 비활성화하시겠습니까?" }, WAIT);
    await waitFor(() => expect(dlg.textContent).toContain("7명"), WAIT);
    expect(dlg.textContent).toContain("지금 바로 로그아웃되고 다시 로그인할 수 없습니다");
    expect(dlg.textContent).toContain("시스템 관리자 1명은 로그아웃되지 않습니다");
    expect(dlg.textContent).toContain("되돌릴 수 있습니다");
    // 조직의 기록 인원(9명 — 보관 · 비활성 포함)을 「로그아웃될 사람」으로 말하지 않는다.
    expect(dlg.textContent).not.toContain("9명");
    expect(apiMock.mock.calls.some(([p]) => String(p) === "/api/admin/organizations/org-1/impact")).toBe(true);
    // 취소가 기본 초점이다.
    expect(within(dlg).getByRole("button", { name: "취소" })).toHaveFocus();
    await userEvent.click(within(dlg).getByRole("button", { name: "비활성화" }));
    await waitFor(() => {
      const patch = apiMock.mock.calls.find(([p, o]) => String(p) === "/api/admin/organizations/org-1" && o && o.method === "PATCH");
      expect(patch, "비활성화 요청이 안 나갔다").toBeTruthy();
      expect(patch[1].body.status).toBe("suspended");
    }, WAIT);
  });

  it("영향은 창을 열 때만 묻는다 — 판을 고르는 것만으로는 `/impact` 가 나가지 않는다", async () => {
    mockApi();
    renderAt("/organizations");
    await within(await screen.findByTestId("org-console-panel", {}, WAIT)).findByRole("heading", { level: 2, name: "클로비원" }, WAIT);
    expect(apiMock.mock.calls.some(([p]) => String(p).endsWith("/impact"))).toBe(false);
  });
});

describe("부서 동작", () => {
  it("메뉴는 수정 · 비활성화 · 삭제 · (구분선) · 감사 로그 · 사용자 화면 · 상세 정보 순서이고, 링크 항목은 그 부서를 가리킨다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const menu = await openMenu("영업팀");
    expect(within(menu).getAllByRole("menuitem").map(itemName))
      .toEqual(["수정", "비활성화", "삭제", "감사 로그에서 보기", "사용자 화면에서 보기", "상세 정보"]);
    expect(within(menu).getByRole("menuitem", { name: "감사 로그에서 보기" }).getAttribute("href"))
      .toBe("#/audit?object_type=department&object_id=dep-sales");
    expect(within(menu).getByRole("menuitem", { name: "사용자 화면에서 보기" }).getAttribute("href"))
      .toBe("#/users?department_id=dep-sales");
  });

  it("비활성화 창은 그대로 남는 것들의 수를 말한다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const menu = await openMenu("영업팀");
    await userEvent.click(within(menu).getByRole("menuitem", { name: "비활성화" }));
    const dlg = await screen.findByRole("dialog", { name: "영업팀을 비활성화하시겠습니까?" }, WAIT);
    await waitFor(() => expect(dlg.textContent).toContain("구성원 4명"), WAIT);
    // 0 인 갈래(하위 부서 · 관리 범위)는 줄을 세우지 않는다.
    expect(within(dlg).getAllByRole("listitem").map((li) => li.textContent))
      .toEqual(["구성원 4명", "프로젝트 2개", "진행 중이거나 예정된 회차 1개"]);
    await userEvent.click(within(dlg).getByRole("button", { name: "비활성화" }));
    await waitFor(() => {
      const patch = apiMock.mock.calls.find(([p, o]) => String(p) === "/api/admin/departments/dep-sales" && o && o.method === "PATCH");
      expect(patch).toBeTruthy();
      expect(patch[1].body).toEqual({ active: false });
    }, WAIT);
  });

  it("🔴 못 지우는 부서의 삭제 창은 막는 항목과 그 화면 링크만 말하고, 「비활성화하기」로 이어 준다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const menu = await openMenu("영업팀");
    await userEvent.click(within(menu).getByRole("menuitem", { name: "삭제" }));
    const dlg = await screen.findByRole("dialog", { name: "이 부서는 삭제할 수 없습니다." }, WAIT);
    expect(await within(dlg).findByText(/소속 사용자/, {}, WAIT)).toBeInTheDocument();
    expect(dlg.textContent).toContain("4명");
    expect(within(dlg).getByRole("link", { name: "사용자 보기" })).toHaveAttribute("href", "#/users?department_id=dep-sales");
    expect(within(dlg).queryByRole("button", { name: "삭제" })).toBeNull();
    await userEvent.click(within(dlg).getByRole("button", { name: "비활성화" }));
    expect(await screen.findByRole("dialog", { name: "영업팀을 비활성화하시겠습니까?" }, WAIT)).toBeInTheDocument();
    expect(apiMock.mock.calls.some(([p, o]) => o && o.method === "DELETE")).toBe(false);
  });

  it("빈 부서는 삭제 창에서 지울 수 있고, 확인 뒤 DELETE 가 나가며 그 부서가 있던 조직으로 옮겨 간다", async () => {
    mockApi();
    renderAt("/departments/dep-empty");
    const menu = await openMenu("빈부서");
    await userEvent.click(within(menu).getByRole("menuitem", { name: "삭제" }));
    const dlg = await screen.findByRole("dialog", { name: "빈부서를 삭제하시겠습니까?" }, WAIT);
    expect(await within(dlg).findByText("삭제한 부서는 되돌릴 수 없습니다.", {}, WAIT)).toBeInTheDocument();
    const confirmBtn = within(dlg).getByRole("button", { name: "삭제" });
    expect(isContained(confirmBtn)).toBe(true);
    expect(within(dlg).getByRole("button", { name: "취소" })).toHaveFocus();
    await userEvent.click(confirmBtn);
    await waitFor(() => {
      expect(apiMock.mock.calls.some(([p, o]) => String(p) === "/api/admin/departments/dep-empty" && o && o.method === "DELETE")).toBe(true);
    }, WAIT);
    await waitFor(() => expect(screen.getByTestId("location-probe").textContent).toBe("/organizations?org=org-1"), WAIT);
  });

  it("서버가 409 로 거절하면 그 문장이 그대로 보인다", async () => {
    mockApi((u, options) => {
      if (u === "/api/admin/departments/dep-empty" && options && options.method === "DELETE") {
        return Promise.reject(Object.assign(new Error("이 부서를 참조하는 프로젝트 2개가 있어 지울 수 없습니다."), { status: 409 }));
      }
      return undefined;
    });
    renderAt("/departments/dep-empty");
    const menu = await openMenu("빈부서");
    await userEvent.click(within(menu).getByRole("menuitem", { name: "삭제" }));
    const dlg = await screen.findByRole("dialog", { name: "빈부서를 삭제하시겠습니까?" }, WAIT);
    await userEvent.click(within(dlg).getByRole("button", { name: "삭제" }));
    expect(await screen.findByText(/참조하는 프로젝트 2개/, {}, WAIT)).toBeInTheDocument();
  });
});

describe("화면의 채움", () => {
  it("부서 판에서는 판 머리의 「하위 부서 추가」 하나이고, 동작 묶음의 오른쪽 끝이다", async () => {
    mockApi();
    const { container } = renderAt("/departments/dep-sales");
    await within(await screen.findByTestId("org-console-panel", {}, WAIT)).findByRole("heading", { level: 2, name: "영업팀" }, WAIT);
    const filled = Array.from(container.querySelectorAll("button, a.MuiButton-root")).filter(isContained);
    expect(filled.map((el) => el.textContent)).toEqual(["하위 부서 추가"]);
    expect(paneHead().contains(filled[0])).toBe(true);
    const group = within(paneHead()).getByRole("group", { name: "영업팀 작업" });
    const buttons = within(group).getAllByRole("button");
    expect(buttons[buttons.length - 1]).toBe(filled[0]);
    // 페이지 머리에는 채움이 없다 — 「조직 추가」는 보조다.
    const pageHead = container.querySelector(".k-page-actions");
    expect(isContained(within(pageHead).getByRole("button", { name: "조직 추가" }))).toBe(false);
  });

  it("조직 판에서는 「부서 추가」가 그 하나의 채움이다", async () => {
    mockApi();
    const { container } = renderAt("/organizations");
    await within(await screen.findByTestId("org-console-panel", {}, WAIT)).findByRole("heading", { level: 2, name: "클로비원" }, WAIT);
    const filled = Array.from(container.querySelectorAll("button")).filter(isContained);
    expect(filled.map((el) => el.textContent)).toEqual(["부서 추가"]);
  });

  it("판 머리에는 글자 단추가 없다 — 옮겨 가는 링크는 「더 보기」의 항목이다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    await within(await screen.findByTestId("org-console-panel", {}, WAIT)).findByRole("heading", { level: 2, name: "영업팀" }, WAIT);
    const isText = (el) => [...el.classList].some((c) => /^MuiButton-text/.test(c));
    expect(Array.from(paneHead().querySelectorAll("button, a")).filter(isText)).toHaveLength(0);
    expect(within(paneHead()).queryByRole("link", { name: "감사 로그에서 보기" })).toBeNull();
  });

  it("조직의 감사 로그 항목도 그 조직을 가리키고, 조직 삭제는 까닭과 함께 비활성이다", async () => {
    mockApi();
    renderAt("/organizations");
    const menu = await openMenu("클로비원");
    expect(within(menu).getByRole("menuitem", { name: "감사 로그에서 보기" }).getAttribute("href"))
      .toBe("#/audit?object_type=organization&object_id=org-1");
    const del = within(menu).getByRole("menuitem", { name: "삭제" });
    expect(del).toHaveAttribute("aria-disabled", "true");
    expect(del).toHaveAccessibleDescription("조직은 삭제할 수 없습니다. 대신 비활성화할 수 있습니다.");
  });
});
