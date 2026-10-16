import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 삭제 판정이 부서 상세 응답(`delete_precheck`)에서 열 때 묻는 `/impact` 로 옮겨 갔다(O1 · D-533). 판의 「정보 › 삭제」 줄과 「삭제가 없는 메뉴」를 걷고, 「삭제」는 늘 메뉴에 있으며 누르면 창이 서버 판정을 그린다 — 막히면 막는 항목만 한 줄씩(보관 수 포함) + 그 조건으로 걸러진 화면 링크, 지울 수 있으면 떼어 낼 것 한 줄씩과 확인. 단언을 판 · 메뉴에서 창으로 옮겼다. 「화면이 스스로 세지 않는다」는 성질은 그대로다.
 *
 * 부서 삭제 창이 **서버 판정과 같은 말을 하는가**(org-02 · xc-01 · xc-04).
 *
 * 실측(2026-09-06 · 자기 서버): 하위 부서 하나를 가진 부서의 상세 판이 「삭제하면 하위 부서 1개가 최상위 부서로 올라갑니다」라고
 * 적고 삭제 단추를 세웠다. 실제 응답은 409 «이 부서에 하위 부서 1건이(가) 연결되어 있어 삭제할 수 없습니다» 였다 — 화면이
 * 서버와 **정반대**를 약속했다. 그래서 지키는 성질은 「화면이 스스로 세지 않는다」다. 갈래 · 수 · 라벨은 `/impact` 의
 * `delete` 에서 오고(app/org/service.py::delete_precheck — 409 와 같은 함수), 창은 그것을 그리기만 한다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1", org_id: "org-1", management: { kind: "global" } } }),
}));

import { OrgConsole } from "./OrgConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";

const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, path: "클로비원", active: true, child_count: 5, subtree_user_count: 3, created_at: AT },
  { id: "dep-parent", kind: "department", name: "본부", depth: 1, path: "클로비원 › 본부", org_id: "org-1", active: true, child_count: 1, subtree_user_count: 0, created_at: AT },
  { id: "dep-child", kind: "department", name: "본부1팀", depth: 2, path: "클로비원 › 본부 › 본부1팀", org_id: "org-1", active: true, child_count: 0, subtree_user_count: 0, created_at: AT },
  { id: "dep-free", kind: "department", name: "빈부서", depth: 1, path: "클로비원 › 빈부서", org_id: "org-1", active: true, child_count: 0, subtree_user_count: 0, created_at: AT },
  { id: "dep-rooms", kind: "department", name: "방있는부서", depth: 1, path: "클로비원 › 방있는부서", org_id: "org-1", active: true, child_count: 0, subtree_user_count: 0, created_at: AT },
  { id: "dep-archived", kind: "department", name: "보관프로젝트부서", depth: 1, path: "클로비원 › 보관프로젝트부서", org_id: "org-1", active: true, child_count: 0, subtree_user_count: 0, created_at: AT },
  { id: "dep-people", kind: "department", name: "사람있는부서", depth: 1, path: "클로비원 › 사람있는부서", org_id: "org-1", active: true, child_count: 0, subtree_user_count: 3, created_at: AT },
];
const ORGS = [{ id: "org-1", name: "클로비원", slug: "clovirone", status: "active", department_count: 6, user_count: 3, created_at: AT }];

const item = (id, name, extra) => ({
  id, name, active: true, parent_id: null, org_id: "org-1", org_name: "클로비원", user_count: 0, child_department_count: 0, created_at: AT, ...extra,
});
const DEPT_ITEMS = {
  "dep-parent": item("dep-parent", "본부", { child_department_count: 1 }),
  "dep-free": item("dep-free", "빈부서"),
  "dep-rooms": item("dep-rooms", "방있는부서"),
  "dep-archived": item("dep-archived", "보관프로젝트부서"),
  "dep-people": item("dep-people", "사람있는부서", { user_count: 3 }),
};
const blocked = (blockers) => ({ deletable: false, blockers, detachables: [], summary: "막힘", reason: "막힘" });
/* 서버가 실제로 내는 다섯 가지 답(`department_impact`). */
const IMPACT = {
  // 하위 부서가 막는다 — 예전 화면이 「최상위로 올라갑니다」라고 약속하던 바로 그 경우다.
  "dep-parent": blocked([{ kind: "child_departments", label: "하위 부서", count: 1, unit: "개", archived_count: 0 }]),
  // 반례 — 아무것도 안 매달린 부서는 지울 수 있어야 한다.
  "dep-free": { deletable: true, blockers: [], detachables: [], summary: null, reason: null },
  // 막지 않고 연결만 끊는 갈래 — 지워지지는 않지만 부서 표시를 잃는다.
  "dep-rooms": {
    deletable: true, blockers: [], summary: null, reason: null,
    detachables: [
      { kind: "chat_rooms", label: "팀 채팅방", count: 1, unit: "개" },
      { kind: "closed_sprints", label: "닫힌 회차", count: 2, unit: "개" },
    ],
  },
  // 보관되어 **목록에 안 보이는** 프로젝트가 막는다(xc-04).
  "dep-archived": blocked([{ kind: "projects", label: "프로젝트", count: 1, unit: "개", archived_count: 1 }]),
  // 사람이 막는다 — 그중 한 명은 보관된 계정이라 사용자 목록 기본 화면에 안 보인다(org-08). 진행 회차도 막는다.
  "dep-people": blocked([
    { kind: "users", label: "소속 사용자", count: 3, unit: "명", archived_count: 1 },
    { kind: "open_sprints", label: "진행 중이거나 예정된 회차", count: 2, unit: "개", archived_count: 0 },
  ]),
};

function mockApi() {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    const impact = u.match(/^\/api\/admin\/departments\/([a-z-]+)\/impact$/);
    if (impact) {
      return Promise.resolve({ delete: IMPACT[impact[1]], deactivate: { members: 0, child_departments: 0, projects: 0, scoped_admins: 0, open_sprints: 0 } });
    }
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    const single = u.match(/^\/api\/admin\/departments\/([a-z-]+)$/);
    if (single && (!options || !options.method)) return Promise.resolve({ department: DEPT_ITEMS[single[1]] || null });
    if (single) return Promise.resolve({ ok: true });
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: [] });
    if (u.startsWith("/api/admin/users")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({ items: [] });
  });
}

function renderDept(id) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/departments/" + id]}>
          <Routes>
            <Route path="/departments/:id" element={<OrgConsole />} />
            <Route path="/organizations" element={<OrgConsole />} />
          </Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const WAIT = { timeout: 8000 };
vi.setConfig({ testTimeout: 20000 });
const panel = () => screen.getByTestId("org-console-panel");

/** 부서 판을 열고 「더 보기 › 삭제」로 창을 연다. */
async function openDelete(id, name) {
  mockApi();
  renderDept(id);
  await within(await screen.findByTestId("org-console-panel", {}, WAIT)).findByRole("heading", { level: 2, name }, WAIT);
  // 평소 판에는 삭제 판정이 없다 — 고르는 것만으로 `/impact` 를 묻지 않는다.
  expect(apiMock.mock.calls.some(([p]) => String(p).endsWith("/impact"))).toBe(false);
  expect(panel().textContent).not.toMatch(/삭제할 수/);
  await userEvent.click(within(panel().querySelector("[data-pane-head]")).getByRole("button", { name: `${name} 작업 더 보기` }));
  await userEvent.click(within(await screen.findByRole("menu", {}, WAIT)).getByRole("menuitem", { name: "삭제" }));
  const dialogs = await screen.findAllByRole("dialog", {}, WAIT);
  return dialogs[dialogs.length - 1];
}
const lines = (dlg) => within(dlg).getAllByRole("listitem").map((li) => li.textContent);

describe("서버가 막는 부서", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("하위 부서가 막으면 창이 그 사실만 말하고, 삭제 단추가 없으며, 「트리에서 보기」가 가지를 편다", async () => {
    const dlg = await openDelete("dep-parent", "본부");
    expect(await within(dlg).findByRole("heading", { name: "이 부서는 삭제할 수 없습니다." }, WAIT)).toBeInTheDocument();
    expect(lines(dlg)).toEqual(["하위 부서 1개트리에서 보기"]);
    expect(within(dlg).queryByRole("button", { name: "삭제" })).toBeNull();
    // 🔴 서버와 정반대였던 약속은 어디에도 없다 — 이것이 이 시험의 핵심이다.
    expect(document.body.textContent).not.toContain("최상위 부서로 올라갑니다");
    expect(screen.queryByRole("treeitem", { name: "본부1팀" })).toBeNull();
    await userEvent.click(within(dlg).getByRole("button", { name: "트리에서 보기" }));
    expect(await screen.findByRole("treeitem", { name: "본부1팀" }, WAIT)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull(), WAIT);
  });

  it("보관되어 목록에 안 보이는 것이 막으면 보관 수를 함께 말하고, 링크가 보관까지 연다(xc-04)", async () => {
    const dlg = await openDelete("dep-archived", "보관프로젝트부서");
    await within(dlg).findByRole("link", { name: "프로젝트 보기" }, WAIT);
    expect(lines(dlg)[0]).toContain("프로젝트 1개 (보관 1개 포함)");
    expect(within(dlg).getByRole("link", { name: "프로젝트 보기" })).toHaveAttribute("href", "#/projects?dept=dep-archived&archived=true");
  });

  it("사람이 막으면 그 사람들 · 보관된 계정으로 가는 링크가 따로 서고, 진행 회차는 회차 화면으로 간다", async () => {
    const dlg = await openDelete("dep-people", "사람있는부서");
    await within(dlg).findByText(/소속 사용자/, {}, WAIT);
    expect(lines(dlg)[0]).toContain("소속 사용자 3명 (보관 1명 포함)");
    expect(within(dlg).getByRole("link", { name: "사용자 보기" })).toHaveAttribute("href", "#/users?department_id=dep-people");
    expect(within(dlg).getByRole("link", { name: "보관된 계정 보기" })).toHaveAttribute("href", "#/users?department_id=dep-people&archived=true");
    expect(lines(dlg)[1]).toContain("진행 중이거나 예정된 회차 2개");
    expect(within(dlg).getByRole("link", { name: "회차 보기" })).toHaveAttribute("href", "#/sprint?team=dep-people");
  });
});

describe("서버가 막지 않는 부서(반례)", () => {
  beforeEach(() => { apiMock.mockReset(); });

  it("아무것도 안 매달렸으면 확인 창이 서고, 확인 뒤 DELETE 가 나간다", async () => {
    const dlg = await openDelete("dep-free", "빈부서");
    expect(await within(dlg).findByText("삭제한 부서는 되돌릴 수 없습니다.", {}, WAIT)).toBeInTheDocument();
    expect(within(dlg).queryAllByRole("listitem")).toHaveLength(0);
    await userEvent.click(within(dlg).getByRole("button", { name: "삭제" }));
    await waitFor(() => {
      expect(apiMock.mock.calls.some(([p, o]) => String(p) === "/api/admin/departments/dep-free" && o && o.method === "DELETE")).toBe(true);
    }, WAIT);
  });

  it("연결만 끊는 갈래가 있으면 창이 그것을 미리 말한다 — 지운 뒤의 과거형이 아니다", async () => {
    const dlg = await openDelete("dep-rooms", "방있는부서");
    expect(await within(dlg).findByText("삭제하면 아래 항목은 이 부서와의 연결만 끊기고 그대로 남습니다.", {}, WAIT)).toBeInTheDocument();
    expect(lines(dlg)).toEqual(["팀 채팅방 1개", "닫힌 회차 2개"]);
    expect(dlg.textContent).not.toContain("그대로 두었습니다");
  });
});
