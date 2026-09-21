import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 조직 관리 IA 재설계(P6)로 판 머리의 동작이 「주 동작(부서 추가 · 하위 부서 추가) · 수정 · 더 보기」 한 묶음이 됐다. 감사 로그 · 사용자 화면 링크와 활성/비활성 · 삭제는 「더 보기」 메뉴 항목으로 옮겼고, 화면의 채움은 페이지 머리 「부서 추가」에서 상세 판의 추가 단추로 옮겼다 — 단추를 찾던 단언을 메뉴 항목 단언으로 바꾸고 채움 단언을 새 자리로 옮겼다.
 *
 * qa-contract-change: 부서 삭제 가능 여부의 판정 근거가 화면의 자체 계산(user_count)에서 서버 응답의 delete_precheck 로 옮겨졌다(org-02·xc-01) — 표본에 그 필드를 실어 같은 성질을 새 계약으로 다시 잰다. 단언은 하나도 걷지 않았다.
 *
 * qa-contract-change: UI 3차 조합 계약 C-4 로 「상세 판의 채움은 「수정」 하나」가 「화면의 채움은 페이지 머리 「부서 추가」 하나이고 판 머리 동작(수정 · 링크 · 활성/비활성 · 삭제)은 30 보조」로 옮겨졌다. kit_measure primary_budget 이 「부서 추가」 + 「수정」 채움 둘을 잡았다. 판 안 채움 0 · 「수정」 보조 · 화면 채움 하나 · 판 머리 글자 단추 0 을 단언으로 더한다.
 *
 * 조직 콘솔의 **행동** — 확인 문구와 게이트 (admin-uiux 에서 이관 · 재설계 후 정본).
 *
 * 1) 조직 비활성화 확인 문구는 이 동작이 실제로 하는 일을 말한다: 몇 명이 **지금 즉시
 *    로그아웃**되고 다시 로그인할 수 없게 되는지, 그리고 되돌릴 수 있다는 사실.
 *    "기존 데이터는 그대로"라고만 적으면 아무 일도 안 일어나는 것처럼 읽힌다.
 * 2) 부서 비활성화도 인원수를 말한다 — 0명과 200명이 같은 경고를 받지 않는다.
 * 3) 서버가 막는 부서에는 삭제 항목 자체가 없다 — 눌러도 항상 409 인 동작을 세우지 않는다.
 *    그 판정은 상세 응답의 `delete_precheck` 다(app/org/service.py::delete_precheck).
 * 4) 파괴적 동작(비활성화 · 삭제)과 옮겨 가는 링크는 「더 보기」 메뉴에 든다. 화면의 채움(primary)은 상세 판의
 *    추가 단추 하나이고, 「수정」은 30 보조, 페이지 머리에는 채움이 없다(UI 3차 조합 계약 C-4).
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
/* 삭제 판정은 서버가 낸다 — 표본도 서버가 실제로 싣는 모양 그대로다
   (app/org/service.py::delete_precheck: deletable · blockers[] · detachables[] · reason). */
const DEPT_ITEMS = {
  "dep-sales": { id: "dep-sales", name: "영업팀", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 4, child_department_count: 0, created_at: AT,
    delete_precheck: {
      deletable: false,
      blockers: [{ kind: "users", label: "소속 사용자", count: 4, archived_count: 0 }],
      detachables: [],
      reason: "이 부서에 소속 사용자 4건이 연결되어 있어 삭제할 수 없습니다."
        + " 먼저 다른 부서로 옮기거나, '비활성'으로 두면 새로 고를 수는 없지만 기존 연결은"
        + " 그대로 유지됩니다.",
    } },
  "dep-empty": { id: "dep-empty", name: "빈부서", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 0, child_department_count: 0, created_at: AT,
    delete_precheck: { deletable: true, blockers: [], detachables: [], reason: null } },
};

function mockApi(overrides) {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
    if (overrides) {
      const hit = overrides(u, options);
      if (hit !== undefined) return hit;
    }
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    const single = u.match(/^\/api\/admin\/departments\/([a-z-]+)$/);
    if (single && (!options || !options.method)) {
      return Promise.resolve({ department: DEPT_ITEMS[single[1]] || null });
    }
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
const isContained = (el) => [...el.classList].some((c) => /^MuiButton-contained[A-Z]/.test(c));
const isOutlined = (el) => [...el.classList].some((c) => /^MuiButton-outlined/.test(c));
const isText = (el) => [...el.classList].some((c) => /^MuiButton-text/.test(c));

/** 판이 선 뒤 「더 보기」를 열고 메뉴를 돌려준다. 메뉴 단추의 이름은 「<대상> 작업 더 보기」다. */
async function openMenu(name) {
  const p = await screen.findByTestId("org-console-panel", {}, WAIT);
  await within(p).findByRole("heading", { name }, WAIT);
  await userEvent.click(within(p).getByRole("button", { name: `${name} 작업 더 보기` }));
  return screen.findByRole("menu", {}, WAIT);
}

beforeEach(() => { apiMock.mockReset(); });

describe("조직 비활성화", () => {
  it("🔴 「더 보기」의 비활성화 — 확인 문구가 로그아웃 사실과 인원수, 되돌리는 길을 말한다", async () => {
    mockApi();
    renderAt("/organizations");
    const menu = await openMenu("클로비원");
    // 판 머리에 파괴적 단추가 따로 서지 않는다 — 메뉴 항목이다.
    expect(within(panel()).queryByRole("button", { name: "비활성화" })).toBeNull();
    await userEvent.click(within(menu).getByRole("menuitem", { name: "비활성화" }));

    const text = (await screen.findByText(/즉시 로그아웃/, {}, WAIT)).textContent;
    expect(text).toContain("9명");
    expect(text).toContain("다시 로그인할 수 없게");
    expect(text).toContain("되돌릴 수 있습니다");

    // 확인 대화상자의 확정 버튼도 「비활성화」라 대화상자 안에서 고른다.
    const dialogs = screen.getAllByRole("dialog");
    await userEvent.click(
      within(dialogs[dialogs.length - 1]).getByRole("button", { name: "비활성화" }),
    );
    await waitFor(() => {
      const patch = apiMock.mock.calls.find(([p, o]) =>
        String(p) === "/api/admin/organizations/org-1" && o && o.method === "PATCH");
      expect(patch, "비활성화 요청이 안 나갔다").toBeTruthy();
      expect(patch[1].body.status).toBe("suspended");
    }, WAIT);
  });
});

describe("부서 액션", () => {
  it("비활성화 확인 문구에 인원수가 실린다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const menu = await openMenu("영업팀");
    await userEvent.click(within(menu).getByRole("menuitem", { name: "비활성화" }));
    expect((await screen.findByText(/사용자 4명/, {}, WAIT))).toBeInTheDocument();
  });

  it("🔴 사용 중인 부서의 메뉴에는 삭제가 없고, 그 이유와 막는 것으로 가는 링크가 정보 절에 선다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const menu = await openMenu("영업팀");
    expect(within(menu).getAllByRole("menuitem").length).toBeGreaterThan(0);
    expect(within(menu).queryByRole("menuitem", { name: "삭제" })).toBeNull();
    // 메뉴가 열린 동안 판은 가려져 있다(aria-hidden) — 닫고 판을 읽는다.
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull(), WAIT);
    expect(within(panel()).queryByRole("button", { name: "삭제" })).toBeNull();
    // 이유는 사라진 항목 대신 정보의 「삭제」 줄이 말한다.
    expect(within(panel()).getByText(/삭제할 수 없습니다/)).toBeInTheDocument();
    expect(within(panel()).getByRole("link", { name: "소속 사용자 보기" }).getAttribute("href"))
      .toBe("#/users?department_id=dep-sales");
  });

  it("빈 부서는 메뉴에서 삭제할 수 있고, 확인 뒤 DELETE 가 나가며 그 부서가 있던 조직으로 옮겨 간다", async () => {
    mockApi();
    renderAt("/departments/dep-empty");
    const menu = await openMenu("빈부서");
    // 파괴적 항목 둘(비활성화 · 삭제)은 메뉴 끝에 있다 — 옮겨 가는 링크 둘 뒤다.
    expect(within(menu).getAllByRole("menuitem").map((m) => m.textContent))
      .toEqual(["감사 로그에서 보기", "사용자 화면에서 보기", "비활성화", "삭제"]);
    await userEvent.click(within(menu).getByRole("menuitem", { name: "삭제" }));
    expect(await screen.findByText(/되돌릴 수 없습니다/, {}, WAIT)).toBeInTheDocument();
    // 확인 대화상자의 확정 버튼(「삭제」) — 메뉴 항목과 이름이 같아 대화상자 안에서 고른다.
    const dialogs = screen.getAllByRole("dialog");
    const confirmDialog = dialogs[dialogs.length - 1];
    await userEvent.click(within(confirmDialog).getByRole("button", { name: "삭제" }));
    await waitFor(() => {
      expect(apiMock.mock.calls.some(([p, o]) =>
        String(p) === "/api/admin/departments/dep-empty" && o && o.method === "DELETE")).toBe(true);
    }, WAIT);
    // 지운 부서의 판에 남아 「찾을 수 없습니다」를 보지 않는다 — 상위 부서가 없으면 그 조직으로 간다.
    await waitFor(() => expect(screen.getByTestId("location-probe").textContent)
      .toBe("/organizations?org=org-1"), WAIT);
  });

  it("서버가 409 로 거절하면 그 문장이 그대로 보인다", async () => {
    mockApi((u, options) => {
      if (u === "/api/admin/departments/dep-empty" && options && options.method === "DELETE") {
        const err = new Error("이 부서를 참조하는 프로젝트 2건이 있어 지울 수 없습니다.");
        err.status = 409;
        return Promise.reject(err);
      }
      return undefined;
    });
    renderAt("/departments/dep-empty");
    const menu = await openMenu("빈부서");
    await userEvent.click(within(menu).getByRole("menuitem", { name: "삭제" }));
    const dialogs = await screen.findAllByRole("dialog", {}, WAIT);
    await userEvent.click(within(dialogs[dialogs.length - 1]).getByRole("button", { name: "삭제" }));
    expect(await screen.findByText(/참조하는 프로젝트 2건/, {}, WAIT)).toBeInTheDocument();
  });

  /* PA-RC-0023 이관(옛 admin-uiux) → UI 3차 조합 계약 C-4 — 화면의 채운(primary) 버튼은 정확히 하나다.
     예전에는 페이지 머리 「부서 추가」가 그 하나였고 판 머리 동작은 전부 30 보조였다. 지금 그 하나는 **고른 대상의**
     추가 단추다 — 부서 판에서는 「하위 부서 추가」, 조직 판에서는 「부서 추가」. 페이지 머리에는 채움이 없다. */
  it("화면의 채움은 부서 판의 「하위 부서 추가」 하나다 — 「수정」은 보조이고 페이지 머리에는 채움이 없다", async () => {
    mockApi();
    const { container } = renderAt("/departments/dep-sales");
    const p2 = await screen.findByTestId("org-console-panel", {}, WAIT);
    await within(p2).findByRole("heading", { name: "영업팀" }, WAIT);
    const screenFilled = Array.from(container.querySelectorAll("button, a.MuiButton-root")).filter(isContained);
    expect(screenFilled.map((el) => el.textContent)).toEqual(["하위 부서 추가"]);
    expect(p2.contains(screenFilled[0])).toBe(true);
    const edit = within(p2).getByRole("button", { name: "수정" });
    expect(isContained(edit)).toBe(false);
    expect(isOutlined(edit)).toBe(true);
    const head = container.querySelector(".k-page-actions");
    expect(Array.from(head.querySelectorAll("button")).filter(isContained)).toHaveLength(0);
    expect(within(head).getByRole("button", { name: "조직 추가" })).toBeInTheDocument();
  });

  it("조직 판에서는 「부서 추가」가 그 하나의 채움이다", async () => {
    mockApi();
    const { container } = renderAt("/organizations");
    const p2 = await screen.findByTestId("org-console-panel", {}, WAIT);
    await within(p2).findByRole("heading", { name: "클로비원" }, WAIT);
    const screenFilled = Array.from(container.querySelectorAll("button")).filter(isContained);
    expect(screenFilled.map((el) => el.textContent)).toEqual(["부서 추가"]);
    expect(isOutlined(within(p2).getByRole("button", { name: "수정" }))).toBe(true);
  });

  /* 판 머리의 동작 순서는 페이지 머리 규칙과 같다(D-501) — 보조 → 「더 보기」 → 채움이 오른쪽 끝이다. 화면마다 채움의 자리가
     다르면 사람은 매번 주 동작을 찾아야 한다. */
  it("판 머리의 채움은 동작 묶음의 오른쪽 끝이다 — 부서 판 · 조직 판 모두", async () => {
    mockApi();
    const orderIn = (panel) => {
      const group = within(panel).getByRole("group", { name: /작업$/ });
      return Array.from(group.querySelectorAll("button")).map((el) => (isContained(el) ? "채움" : el.getAttribute("aria-label") ? "더 보기" : el.textContent));
    };
    const first = renderAt("/departments/dep-sales");
    const dept = await screen.findByTestId("org-console-panel", {}, WAIT);
    await within(dept).findByRole("heading", { name: "영업팀" }, WAIT);
    expect(orderIn(dept)).toEqual(["수정", "더 보기", "채움"]);
    first.unmount();
    renderAt("/organizations");
    const org = await screen.findByTestId("org-console-panel", {}, WAIT);
    await within(org).findByRole("heading", { name: "클로비원" }, WAIT);
    expect(orderIn(org)).toEqual(["수정", "더 보기", "채움"]);
  });

  it("판 머리에는 글자 단추가 없다 — 옮겨 가는 링크는 「더 보기」의 항목이다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const p2 = await screen.findByTestId("org-console-panel", {}, WAIT);
    await within(p2).findByRole("heading", { name: "영업팀" }, WAIT);
    const head = p2.querySelector("[data-org-panel-head]");
    expect(Array.from(head.querySelectorAll("button, a")).filter(isText)).toHaveLength(0);
    expect(within(head).queryByRole("link", { name: "감사 로그에서 보기" })).toBeNull();
    // 동작 묶음은 하나이고 이름이 있다.
    expect(within(head).getByRole("group", { name: "영업팀 작업" })).toBeInTheDocument();
  });

  it("감사 로그 · 사용자 화면 항목은 그 부서를 가리키는 주소를 가진 메뉴 항목이다", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    const menu = await openMenu("영업팀");
    const audit = within(menu).getByRole("menuitem", { name: "감사 로그에서 보기" });
    expect(audit.getAttribute("href")).toBe("#/audit?object_type=department&object_id=dep-sales");
    expect(within(menu).getByRole("menuitem", { name: "사용자 화면에서 보기" }).getAttribute("href"))
      .toBe("#/users?department_id=dep-sales");
  });

  it("조직의 감사 로그 항목도 그 조직을 가리킨다", async () => {
    mockApi();
    renderAt("/organizations");
    const menu = await openMenu("클로비원");
    expect(within(menu).getByRole("menuitem", { name: "감사 로그에서 보기" }).getAttribute("href"))
      .toBe("#/audit?object_type=organization&object_id=org-1");
  });
});
