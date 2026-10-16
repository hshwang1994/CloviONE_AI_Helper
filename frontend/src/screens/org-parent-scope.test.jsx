import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 조직 관리가 작업 공간이 되며(O1 · D-533, D-510 을 뒤집는다) 「부서 추가」 · 「하위 부서 추가」는 페이지 머리에서 오른쪽 판 머리로, 「수정」은 판 머리 단추에서 「더 보기」 메뉴 항목으로 옮겼다 — 단추를 찾는 자리만 옮겼고 요청 본문 · 후보 · 문구 단언은 그대로다.
 *
 * qa-contract-change: 조직 관리 개선(계획 3.6 · D-510)으로 고른 대상의 「더 보기」와 주 동작(부서 추가 · 하위 부서 추가)이 상세 판 머리에서 페이지 머리로 옮겨 갔다(판 안의 30px 주 동작이 머리의 34px 보조 단추보다 작아 위계가 거꾸로 읽혔다). 판 머리에는 「수정」 하나가 남는다 — 판 안에서 단추를 찾던 단언을 페이지 머리(`.k-page-actions`)로 옮겼다.
 *
 * qa-contract-change: 조직 관리 IA 재설계(P6)로 부서 추가 창의 조직 칸이 없어졌다 — 조직은 창을 연 자리(조직 판 · 부서 판)가 고정한다. 「조직 칸을 바꾸면 후보가 따라간다」 단언을 「A 조직에서 열면 A 의 부서만, B 조직의 부서에서 열면 B 의 부서만」으로 옮기고, 정지된 조직의 상태 표시(org-17)를 조직 후보 라벨에서 창의 안내로 옮겼다. 미사용 부서를 후보에서 빼는 단언(xb-08)을 더했다.
 *
 * 부서 폼의 **상위 부서 후보는 그 부서가 들어갈 조직의 부서뿐이다**(org-03), 그리고
 * **정지된 조직에 부서를 만들 때는 창이 그 상태를 말한다**(org-17).
 *
 * 실측(2026-09-06 · 자기 서버, 조직 넷): 「부서 추가」의 상위 후보에 다른 조직의 부서
 * (P11타조직부서)가 그대로 서 있었고, 그것을 고르고 조직을 굿모닝아이텍으로 두면
 * `POST /api/admin/departments` → 422 «알 수 없는 상위 부서입니다» 였다. 서버는 상위 부서가
 * 이 행과 같은 조직일 것을 요구한다(app/org/tree.py::validate_parent · service.py::create_item).
 * 같은 목록에 정지된 조직의 부서(P11정지부서)도, 정지된 조직 자체(P11조직)도 아무 표시 없이
 * 섞여 있었다.
 *
 * 반례를 함께 잰다: 같은 조직의 부서는 그대로 후보이고 고른 값이 그대로 실려 나간다.
 * 후보를 조건에 따라 좁히는 것과, **없는 조합을 권하지 않는 것**은 다른 일이다. 미사용 부서도 새 상위가 될 수
 * 없다(xb-08) — 다만 수정 창에서 **지금** 상위 부서가 미사용이면 그 값은 후보에 남는다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({
    data: { role: "system_admin", id: "actor-1", org_id: "org-1", management: { kind: "global" } },
  }),
}));

import { OrgConsole } from "./OrgConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, path: "클로비원",
    active: true, user_count: 0, child_count: 3, subtree_user_count: 7, created_at: AT },
  { id: "dep-sales", kind: "department", name: "영업팀", depth: 1, path: "클로비원 › 영업팀",
    org_id: "org-1", active: true, user_count: 4, child_count: 0, subtree_user_count: 4, created_at: AT },
  { id: "dep-dev", kind: "department", name: "개발팀", depth: 1, path: "클로비원 › 개발팀",
    org_id: "org-1", active: true, user_count: 3, child_count: 0, subtree_user_count: 3, created_at: AT },
  { id: "dep-old", kind: "department", name: "옛본부", depth: 1, path: "클로비원 › 옛본부",
    org_id: "org-1", active: false, user_count: 0, child_count: 1, subtree_user_count: 0, created_at: AT },
  { id: "dep-kid", kind: "department", name: "남은팀", depth: 2, path: "클로비원 › 옛본부 › 남은팀",
    parent_id: "dep-old", org_id: "org-1", active: true, user_count: 0, child_count: 0,
    subtree_user_count: 0, created_at: AT },
  { id: "org-2", kind: "organization", name: "자회사", depth: 0, path: "자회사",
    active: true, user_count: 0, child_count: 1, subtree_user_count: 1, created_at: AT },
  { id: "dep-sub", kind: "department", name: "자회사기획팀", depth: 1, path: "자회사 › 자회사기획팀",
    org_id: "org-2", active: true, user_count: 1, child_count: 0, subtree_user_count: 1, created_at: AT },
  { id: "org-3", kind: "organization", name: "묵은회사", depth: 0, path: "묵은회사",
    active: false, user_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT },
];
const ORGS = [
  { id: "org-1", name: "클로비원", slug: "clovirone", status: "active",
    department_count: 4, user_count: 7, created_at: AT },
  { id: "org-2", name: "자회사", slug: "subsidiary", status: "active",
    department_count: 1, user_count: 1, created_at: AT },
  { id: "org-3", name: "묵은회사", slug: "old-co", status: "suspended",
    department_count: 0, user_count: 0, created_at: AT },
];
/* 조직마다 부서가 있어야 「좁혀졌다」를 실제로 잴 수 있다 — 전부 한 조직이면 좁히는 코드가
   없어도 이 시험이 우연히 통과한다. 미사용 부서(옛본부)도 하나 둔다. */
const DEPTS = [
  { id: "dep-sales", name: "영업팀", org_id: "org-1", active: true, user_count: 4, created_at: AT },
  { id: "dep-dev", name: "개발팀", org_id: "org-1", active: true, user_count: 3, created_at: AT },
  { id: "dep-old", name: "옛본부", org_id: "org-1", active: false, user_count: 0, created_at: AT },
  { id: "dep-kid", name: "남은팀", org_id: "org-1", active: true, user_count: 0, created_at: AT },
  { id: "dep-sub", name: "자회사기획팀", org_id: "org-2", active: true, user_count: 1, created_at: AT },
];
const item = (row, org, extra) => ({
  id: row.id, name: row.name, active: row.active, parent_id: null, org_id: row.org_id,
  org_name: org, user_count: row.user_count, child_department_count: 0, created_at: AT,
  delete_precheck: { deletable: true, blockers: [], detachables: [], reason: null }, ...extra,
});
const DEPT_ITEMS = {
  "dep-sales": item(DEPTS[0], "클로비원"),
  "dep-kid": item(DEPTS[3], "클로비원", { parent_id: "dep-old" }),
  "dep-sub": item(DEPTS[4], "자회사"),
};

function mockApi() {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
    if (options && options.method === "POST") return Promise.resolve({ department: { id: "made-1" } });
    if (options && options.method === "PATCH") return Promise.resolve({ ok: true });
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    const single = u.match(/^\/api\/admin\/departments\/([a-z0-9-]+)$/);
    if (single) return Promise.resolve({ department: DEPT_ITEMS[single[1]] || null });
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: DEPTS });
    if (u.startsWith("/api/admin/users")) return Promise.resolve({ items: [], total: 0 });
    return Promise.resolve({ items: [] });
  });
}

function renderAt(path = "/organizations") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[path]}>
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

/** 열린 대화상자에서 select 를 열고 후보 이름을 읽은 뒤 원래대로 닫는다. */
async function optionNames(dlg, label) {
  await userEvent.click(within(dlg).getByLabelText(label));
  const list = await screen.findByRole("listbox", {}, WAIT);
  const names = within(list).getAllByRole("option").map((o) => o.textContent);
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull(), WAIT);
  return names;
}

/** 고른 대상의 주 동작(조직이면 「부서 추가」, 부서면 「하위 부서 추가」)으로 부서 추가 창을 연다. 단추는 오른쪽 판
 * 머리에 선다(D-533). */
async function openCreate(path, heading, opener, title) {
  mockApi();
  renderAt(path);
  const panel = await screen.findByTestId("org-console-panel", {}, WAIT);
  await within(panel).findByRole("heading", { name: heading }, WAIT);
  await userEvent.click(within(panel.querySelector("[data-pane-head]")).getByRole("button", { name: opener }));
  return screen.findByRole("dialog", { name: title }, WAIT);
}

/** 「더 보기 › 수정」 — 수정은 판 머리 단추가 아니라 메뉴의 첫 항목이다(D-533). 「더 보기」는 화면에 하나다(판 머리). */
async function openEdit() {
  await userEvent.click(await screen.findByRole("button", { name: /작업 더 보기$/ }, WAIT));
  await userEvent.click(within(await screen.findByRole("menu", {}, WAIT)).getByRole("menuitem", { name: "수정" }));
}

function lastPost() {
  return apiMock.mock.calls.find(([p, o]) =>
    String(p) === "/api/admin/departments" && o && o.method === "POST");
}

beforeEach(() => { apiMock.mockReset(); });

describe("부서 추가의 상위 부서 후보 — 창을 연 조직의 부서뿐이다", () => {
  it("조직 A 의 판에서 열면 A 의 사용 중인 부서만 후보다 — 남의 조직 부서 · 미사용 부서는 없다", async () => {
    const dlg = await openCreate("/organizations?org=org-1", "클로비원", "부서 추가", "클로비원에 부서 추가");
    const names = await optionNames(dlg, /상위 부서/);
    expect(names).toEqual(["(최상위)", "영업팀", "개발팀", "남은팀"]);
    expect(names).not.toContain("자회사기획팀");
    expect(names).not.toContain("옛본부");
    // 조직은 창을 연 자리가 정했다 — 다시 묻는 칸이 없다.
    expect(within(dlg).queryByLabelText(/^조직/)).toBeNull();
  });

  it("조직 B 의 판에서 열면 B 의 부서만 후보이고, 요청에 B 가 실린다(반례: 그 조직 부서는 남는다)", async () => {
    const dlg = await openCreate("/organizations?org=org-2", "자회사", "부서 추가", "자회사에 부서 추가");
    expect(await optionNames(dlg, /상위 부서/)).toEqual(["(최상위)", "자회사기획팀"]);
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = lastPost();
      expect(post, "부서 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body.parent_id).toBeNull();
      expect(post[1].body.org_id).toBe("org-2");
    }, WAIT);
  });

  it("조직 B 의 부서 판에서 「하위 부서 추가」를 열면 후보는 B 의 것이고 그 부서가 미리 골라져 있다", async () => {
    const dlg = await openCreate(
      "/departments/dep-sub", "자회사기획팀", "하위 부서 추가", "자회사기획팀에 하위 부서 추가",
    );
    await waitFor(() => expect(within(dlg).getByLabelText(/상위 부서/)).toHaveTextContent("자회사기획팀"), WAIT);
    expect(await optionNames(dlg, /상위 부서/)).toEqual(["(최상위)", "자회사기획팀"]);
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "기획1팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = lastPost();
      expect(post, "부서 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body).toEqual({ name: "기획1팀", parent_id: "dep-sub", org_id: "org-2" });
    }, WAIT);
  });

  it("같은 조직 안에서 고른 상위 부서는 그대로 실려 나간다(반례)", async () => {
    const dlg = await openCreate("/organizations?org=org-1", "클로비원", "부서 추가", "클로비원에 부서 추가");
    await userEvent.click(within(dlg).getByLabelText(/상위 부서/));
    await userEvent.click(await screen.findByRole("option", { name: "개발팀" }, WAIT));
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = lastPost();
      expect(post, "부서 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body.parent_id).toBe("dep-dev");
      expect(post[1].body.org_id).toBe("org-1");
    }, WAIT);
  });
});

describe("부서 수정의 상위 부서 후보", () => {
  it("이 부서가 속한 조직의 사용 중인 부서만 후보다(자기 자신은 여전히 빠진다)", async () => {
    mockApi();
    renderAt("/departments/dep-sales");
    await openEdit();
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    const names = await optionNames(dlg, /상위 부서/);
    expect(names).toEqual(["(최상위)", "개발팀", "남은팀"]);
    expect(names).not.toContain("옛본부");
  });

  it("지금 상위 부서가 미사용이면 그 값은 후보에 남는다 — 이름만 고치는 창이 지금 값을 잃지 않는다", async () => {
    mockApi();
    renderAt("/departments/dep-kid");
    await openEdit();
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    expect(within(dlg).getByLabelText(/상위 부서/)).toHaveTextContent("옛본부");
    expect(await optionNames(dlg, /상위 부서/)).toEqual(["(최상위)", "영업팀", "개발팀", "옛본부"]);
  });
});

describe("정지된 조직에 부서를 만들 때", () => {
  it("창이 그 조직의 미사용 상태를 말한다 — 활성 조직의 창은 평소 안내 그대로다(org-17)", async () => {
    const dlg = await openCreate("/organizations?org=org-3", "묵은회사", "부서 추가", "묵은회사에 부서 추가");
    expect(dlg.textContent).toContain("이 조직은 미사용 상태라 여기에 추가한 부서는 조직을 다시 활성화할 때까지 아무도 쓸 수 없습니다.");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull(), WAIT);
  });

  it("활성 조직의 창에는 미사용 안내가 없다(반례)", async () => {
    const dlg = await openCreate("/organizations?org=org-2", "자회사", "부서 추가", "자회사에 부서 추가");
    expect(dlg.textContent).not.toContain("미사용 상태");
    expect(dlg.textContent).toContain("사용자 폼의 '부서' 목록에 바로 나타납니다.");
  });
});
