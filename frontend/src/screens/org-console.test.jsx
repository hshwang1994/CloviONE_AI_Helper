import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 조직 관리가 관리 작업 공간이 됐다(O1 · D-533, D-510 을 뒤집는다). 대상 동작(주 동작 · 「더 보기」)은 페이지 머리에서 오른쪽 판 머리로, 「수정」은 「더 보기」 메뉴로 옮겼고, 늘 보이던 「정보」 구획(ID · 식별자 · 삭제 판정)은 「더 보기 › 상세 정보」 창과 누를 때 묻는 영향 확인 창으로 옮겼다. 트리는 아이콘 · 기본 접힘 · 검색 펼침이 있는 평탄한 줄(aria-level · aria-setsize · aria-posinset)이 됐고 연결선 · 중첩 group 을 걷었다. 「사용」 선택 칸은 「사용 중만」 토글이 되어 화면에서 조상을 남기며 거른다(서버 `?active=` 질의 없음). 부서 구성원의 기본은 하위 포함이다. 단언을 새 자리(판 머리 · 메뉴 · 토글 · 설명 붙은 수)로 옮기고, 걷은 구조(연결선 스타일 · 페이지 머리 동작 · 정보 구획 · 레일 sticky)를 단언하던 시험은 지웠다.
 *
 * 이 화면이 먼저 말하는 것: 「왼쪽에서 조직 · 부서 계층을 탐색하고, 오른쪽에서 고른 대상 하나와 그 구성원을 다룬다」.
 * 지키는 성질:
 *
 *   1) 트리에서 고른 것에 오른쪽 판이 반응하고, 선택이 주소에 남는다(부서 = /departments/:id, 조직 = /organizations?org=).
 *   2) 수는 한 곳에 하나다 — 가지 인원은 트리 줄의 설명, 지금 조건의 인원은 판의 「구성원 N명」.
 *   3) 검색과 「사용 중만」은 왼쪽 판 도구 줄에 있고 화면에서 거른다(조상은 남는다). 서버에 거르기 질의를 보내지 않는다.
 *   4) 대상 동작은 판 머리에 선다 — 조직이면 「부서 추가」, 부서면 「하위 부서 추가」가 이 화면의 채움 하나다.
 *   5) 평소 화면에 기술 정보(ID · 식별자 · 삭제 판정)가 없다 — 「더 보기 › 상세 정보」가 든다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1", management: { kind: "global" } } }),
}));

import { OrgConsole } from "./OrgConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";

/* 값이 실제로 달라지는 표본 — 부서마다 인원 · 사용 여부 · 깊이가 다르다. 가지 인원(subtree)과 직접 인원(user_count)도 다르다. */
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", slug: "clovirone", depth: 0, path: "클로비원",
    parent_id: null, active: true, user_count: 0, organization_direct_count: 0,
    unassigned_count: 1, child_count: 2, subtree_user_count: 9, cycle: false, created_at: AT },
  { id: "dep-sales", kind: "department", name: "영업팀", depth: 1, path: "클로비원 › 영업팀",
    parent_id: null, org_id: "org-1", active: true, user_count: 4, child_count: 1, subtree_user_count: 6, cycle: false, created_at: AT },
  { id: "dep-sales-kr", kind: "department", name: "국내영업", depth: 2, path: "클로비원 › 영업팀 › 국내영업",
    parent_id: "dep-sales", org_id: "org-1", active: false, user_count: 2, child_count: 0, subtree_user_count: 2, cycle: false, created_at: AT },
  { id: "dep-dev", kind: "department", name: "개발팀", depth: 1, path: "클로비원 › 개발팀",
    parent_id: null, org_id: "org-1", active: true, user_count: 3, child_count: 0, subtree_user_count: 3, cycle: false, created_at: AT },
];

const ORGS = [
  { id: "org-1", name: "클로비원", slug: "clovirone", status: "active", department_count: 3, user_count: 9, created_at: AT },
  { id: "org-2", name: "묵은회사", slug: "old-co", status: "suspended", department_count: 0, user_count: 0, created_at: AT },
];

const DEPTS = [
  { id: "dep-sales", name: "영업팀", org_name: "클로비원", org_id: "org-1", active: true, user_count: 4, created_at: AT },
  { id: "dep-dev", name: "개발팀", org_name: "클로비원", org_id: "org-1", active: true, user_count: 3, created_at: AT },
  { id: "dep-sales-kr", name: "국내영업", org_name: "클로비원", org_id: "org-1", active: false, user_count: 2, created_at: AT },
];

const DEPT_ITEMS = {
  "dep-sales": { id: "dep-sales", name: "영업팀", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 4, child_department_count: 1, created_at: AT },
  "dep-sales-kr": { id: "dep-sales-kr", name: "국내영업", active: false, parent_id: "dep-sales",
    org_id: "org-1", org_name: "클로비원", user_count: 2, child_department_count: 0, created_at: AT },
  "dep-dev": { id: "dep-dev", name: "개발팀", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 3, child_department_count: 0, created_at: AT },
  "dep-new": { id: "dep-new", name: "품질팀", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 0, child_department_count: 0, created_at: AT },
};

const PEOPLE = {
  "dep-sales": { items: [{ id: "u-1", display_name: "김영업", email: "sales@example.com", title: "과장", role: "user", active: true }], total: 4 },
  "dep-dev": { items: [
    { id: "u-2", display_name: "이개발", email: "dev1@example.com", title: "주임", role: "user", active: true },
    { id: "u-3", display_name: "박개발", email: "dev2@example.com", title: null, role: "admin", active: true },
  ], total: 2 },
  "dep-sales-kr": { items: [], total: 0 },
  none: { items: [{ id: "u-9", display_name: "무소속", email: "none@example.com", title: "사원", role: "user", active: true }], total: 1 },
};

function mockApi({ tree = TREE } = {}) {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
    if (options && options.method === "POST" && u === "/api/admin/departments") {
      return Promise.resolve({ department: { id: "dep-new", name: "품질팀" } });
    }
    // /tree 를 먼저 본다 — /api/admin/departments 가 접두어라 순서가 뒤집히면 트리가 목록을 받는다.
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: tree });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    const single = u.match(/^\/api\/admin\/departments\/([a-z-]+)$/);
    if (single) return Promise.resolve({ department: DEPT_ITEMS[single[1]] || null });
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: DEPTS });
    if (u.startsWith("/api/admin/users")) {
      const q = new URLSearchParams(u.split("?")[1] || "");
      const dept = q.get("department_id");
      if (dept) return Promise.resolve(PEOPLE[dept] || { items: [], total: 0 });
      if (q.get("membership_kind") === "unassigned") return Promise.resolve(PEOPLE.none);
      const all = [].concat(PEOPLE["dep-sales"].items, PEOPLE["dep-dev"].items, PEOPLE.none.items);
      return Promise.resolve({ items: all, total: 9 });
    }
    return Promise.resolve({ items: [] });
  });
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{location.pathname + location.search}</div>;
}

function renderConsole(path = "/org-tree") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <LocationProbe />
              <Routes>
                <Route path="/org-tree" element={<OrgConsole />} />
                <Route path="/organizations" element={<OrgConsole />} />
                <Route path="/departments" element={<OrgConsole />} />
                <Route path="/departments/:id" element={<OrgConsole />} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/* MUI 화면 하나를 jsdom 에서 그리는 데 1초 가까이 걸린다(admin-uiux.test.jsx 와 같은 이유). */
const WAIT = { timeout: 8000 };
vi.setConfig({ testTimeout: 20000 });
const tree = () => screen.getByTestId("org-console-tree");
const panel = () => screen.getByTestId("org-console-panel");
const paneHead = () => panel().querySelector("[data-pane-head]");
const where = () => screen.getByTestId("location-probe").textContent;
const node = (name) => screen.findByRole("treeitem", { name }, WAIT);
const usersCalls = (dept) => apiMock.mock.calls
  .map(([p]) => String(p))
  .filter((p) => p.startsWith("/api/admin/users?"))
  .map((p) => new URLSearchParams(p.split("?")[1]))
  .filter((q) => !dept || q.get("department_id") === dept);
const treeCalls = () => apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith("/api/admin/departments/tree"));

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
});
afterEach(() => { window.location.hash = ""; });

/* ── 1. 왼쪽 트리에서 고르면 오른쪽 판이 반응한다 ──────────────────────── */

describe("트리 선택 → 오른쪽 판", () => {
  it("첫 진입에는 첫 조직의 판이 선다 — 빈 오른쪽 판은 화면 절반이 죽은 상태다", async () => {
    mockApi();
    renderConsole();
    expect(await within(panel()).findByRole("heading", { level: 2, name: "클로비원" }, WAIT)).toBeInTheDocument();
    expect(await node("클로비원")).toHaveAttribute("aria-selected", "true");
    // 평소 화면에는 기술 정보가 없다 — 식별자 · ID · 「정보」 구획은 「더 보기 › 상세 정보」 안에만 있다.
    expect(within(panel()).queryByText("clovirone")).toBeNull();
    expect(within(panel()).queryByText(/조직 ID/)).toBeNull();
    expect(within(panel()).queryByRole("heading", { name: "정보" })).toBeNull();
  });

  it("부서 노드를 누르면 부서 판이 서고, 주소가 /departments/:id 가 된다(D-104)", async () => {
    mockApi();
    renderConsole();
    await userEvent.click(await node("영업팀"));
    expect(await within(panel()).findByRole("heading", { level: 2, name: "영업팀" }, WAIT)).toBeInTheDocument();
    expect(where()).toBe("/departments/dep-sales");
    expect(apiMock.mock.calls.some(([p]) => String(p) === "/api/admin/departments/dep-sales")).toBe(true);
    expect(await within(panel()).findByText("김영업", {}, WAIT)).toBeInTheDocument();
    // 판 머리 첫 줄은 이 부서가 어디에 있는가다 — 조상을 누르면 그 노드로 간다.
    const path = within(paneHead()).getByRole("navigation", { name: "위치" });
    await userEvent.click(within(path).getByRole("button", { name: "클로비원" }));
    expect(await within(panel()).findByRole("heading", { level: 2, name: "클로비원" }, WAIT)).toBeInTheDocument();
    expect(where()).toBe("/organizations?org=org-1");
  });

  it("고른 항목만 강조된다(aria-selected)", async () => {
    mockApi();
    renderConsole("/departments/dep-dev");
    await waitFor(async () => expect(await node("개발팀")).toHaveAttribute("aria-selected", "true"), WAIT);
    expect(await node("영업팀")).toHaveAttribute("aria-selected", "false");
  });

  it("딥링크로 접힌 가지 안의 부서에 들어오면 조상이 펴지고, 미사용 부서는 상태 낱말이 서고 「하위 부서 추가」가 없다", async () => {
    mockApi();
    renderConsole("/departments/dep-sales-kr");
    expect(await within(panel()).findByRole("heading", { level: 2, name: "국내영업" }, WAIT)).toBeInTheDocument();
    expect(await node("국내영업")).toHaveAttribute("aria-selected", "true");
    expect(await node("영업팀")).toHaveAttribute("aria-expanded", "true");
    expect(within(paneHead()).getByText("미사용")).toBeInTheDocument();
    expect(within(paneHead()).getByRole("navigation", { name: "위치" })).toHaveTextContent("클로비원›영업팀");
    expect(within(panel()).queryByRole("button", { name: "하위 부서 추가" })).toBeNull();
  });

  it("없는 부서 id 딥링크는 판 안에서 말하고, 트리는 그대로 남는다(D-127)", async () => {
    apiMock.mockImplementation((url) => {
      const u = String(url);
      if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
      if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
      if (u === "/api/admin/departments/dep-ghost") {
        return Promise.reject(Object.assign(new Error("부서를 찾지 못했습니다."), { status: 404 }));
      }
      if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: DEPTS });
      return Promise.resolve({ items: [], total: 0 });
    });
    renderConsole("/departments/dep-ghost");
    expect((await within(panel()).findAllByText(/찾을 수 없습니다/, {}, WAIT)).length).toBeGreaterThan(0);
    expect(await node("클로비원")).toBeInTheDocument();
  });
});

/* ── 2. 수는 한 곳에 하나다 ─────────────────────────────────────────────── */

describe("수", () => {
  it("가지 인원은 트리 줄의 설명이고, 판의 수는 「구성원 N명」(지금 조건의 서버 total)이다", async () => {
    mockApi();
    renderConsole();
    const org = await node("클로비원");
    expect(org).toHaveAccessibleName("클로비원");
    expect(org).toHaveAccessibleDescription("구성원 9명");
    await userEvent.click(await node("영업팀"));
    expect(await within(panel()).findByRole("heading", { level: 3, name: "구성원 4명" }, WAIT)).toBeInTheDocument();
  });

  it("부서 구성원은 하위 포함이 기본이다 — 트리 줄의 수와 목록의 수가 같은 범위를 센다", async () => {
    mockApi();
    renderConsole("/departments/dep-sales");
    await within(panel()).findByText("김영업", {}, WAIT);
    const q = usersCalls("dep-sales")[0];
    expect(q.get("include_descendants")).toBe("true");
    expect(q.get("state")).toBe("active");
  });

  it("부서도 조직 직속도 아닌 사람은 조직 판의 한 줄 메시지 상자로 서고, 「목록 보기」가 목록을 그 사람들로 바꾼다", async () => {
    mockApi();
    renderConsole("/organizations");
    const notice = await within(panel()).findByText("부서도 조직 직속도 아닌 사람이 1명 있습니다.", {}, WAIT);
    await userEvent.click(within(notice.closest(".k-callout")).getByRole("button", { name: "목록 보기" }));
    expect(await within(panel()).findByText("무소속", {}, WAIT)).toBeInTheDocument();
    const call = usersCalls().find((q) => q.get("membership_kind") === "unassigned");
    expect(call, "미지정 목록을 조직으로 좁혀 받지 않았다").toBeTruthy();
    expect(call.get("org_id")).toBe("org-1");
    expect(within(tree()).queryByText(/미지정/)).toBeNull();
  });

  it("조직이 둘이어도 명단은 고른 조직으로 좁혀 받는다", async () => {
    mockApi({
      tree: TREE.concat([{ id: "org-2", kind: "organization", name: "묵은회사", slug: "old-co", depth: 0, path: "묵은회사",
        active: false, user_count: 0, unassigned_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT }]),
    });
    renderConsole("/organizations?org=org-1");
    await within(panel()).findByRole("heading", { level: 2, name: "클로비원" }, WAIT);
    await waitFor(() => expect(usersCalls().some((q) => q.get("org_id") === "org-1")).toBe(true), WAIT);
    expect(usersCalls().every((q) => q.get("org_id") !== "org-2")).toBe(true);
  });
});

/* ── 3. 왼쪽 판 도구 줄 — 검색과 「사용 중만」 ───────────────────────────── */

describe("왼쪽 판의 검색과 「사용 중만」", () => {
  it("조직도 검색과 「사용 중만」은 왼쪽 판에 있고, 오른쪽 판의 검색은 구성원 검색 하나다", async () => {
    mockApi();
    renderConsole();
    await within(panel()).findByRole("heading", { level: 2, name: "클로비원" }, WAIT);
    expect(within(tree()).getByRole("searchbox", { name: "조직도 검색" })).toBeInTheDocument();
    expect(within(tree()).getByRole("button", { name: "사용 중만" })).toHaveAttribute("aria-pressed", "false");
    expect(within(panel()).getAllByRole("searchbox").map((b) => b.getAttribute("aria-label"))).toEqual(["구성원 검색"]);
  });

  it("검색은 화면에서 거른다 — 맞지 않는 가지는 사라지고 조상은 남으며, 트리를 다시 받지 않는다", async () => {
    mockApi();
    renderConsole();
    await node("개발팀");
    const before = treeCalls().length;
    await userEvent.type(within(tree()).getByRole("searchbox", { name: "조직도 검색" }), "개발");
    await waitFor(() => expect(screen.queryByRole("treeitem", { name: "영업팀" })).toBeNull(), WAIT);
    expect(await node("개발팀")).toBeInTheDocument();
    expect(await node("클로비원")).toBeInTheDocument();
    expect(where()).toContain("q=");
    expect(treeCalls().length).toBe(before);
  });

  it("「사용 중만」은 주소에 남고 화면에서 거른다 — 서버에 `active` 질의를 보내지 않는다", async () => {
    mockApi();
    renderConsole("/departments/dep-sales");
    await within(panel()).findByRole("heading", { level: 2, name: "영업팀" }, WAIT);
    await userEvent.click(within(tree()).getByRole("button", { name: "모두 펼치기" }));
    expect(await node("국내영업")).toBeInTheDocument();
    await userEvent.click(within(tree()).getByRole("button", { name: "사용 중만" }));
    await waitFor(() => expect(screen.queryByRole("treeitem", { name: "국내영업" })).toBeNull(), WAIT);
    expect(where()).toContain("active=true");
    expect(treeCalls().every((p) => !p.includes("active="))).toBe(true);
  });

  it("「모두 펼치기」 · 「모두 접기」가 트리 전체에 닿는다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    expect(screen.queryByRole("treeitem", { name: "국내영업" })).toBeNull();
    await userEvent.click(within(tree()).getByRole("button", { name: "모두 펼치기" }));
    expect(await node("국내영업")).toBeInTheDocument();
    await userEvent.click(within(tree()).getByRole("button", { name: "모두 접기" }));
    await waitFor(() => expect(screen.queryByRole("treeitem", { name: "영업팀" })).toBeNull(), WAIT);
  });
});

/* ── 4. 대상 동작은 판 머리에 ────────────────────────────────────────────── */

describe("판 머리의 동작", () => {
  it("페이지 머리에는 「조직 추가」 하나, 조직 판 머리에는 「더 보기」와 「부서 추가」(오른쪽 끝)가 선다", async () => {
    mockApi();
    const { container } = renderConsole();
    await within(panel()).findByRole("heading", { level: 2, name: "클로비원" }, WAIT);
    const head = container.querySelector(".k-page-actions");
    expect(within(head).getAllByRole("button").map((b) => b.textContent)).toEqual(["조직 추가"]);
    const group = within(paneHead()).getByRole("group", { name: "클로비원 작업" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent || b.getAttribute("aria-label")))
      .toEqual(["클로비원 작업 더 보기", "부서 추가"]);
  });

  it("조직 판의 「부서 추가」는 그 조직을 고정해 열고 조직을 다시 묻지 않는다 — 만들면 새 부서로 간다", async () => {
    mockApi();
    renderConsole();
    await within(panel()).findByRole("heading", { level: 2, name: "클로비원" }, WAIT);
    await userEvent.click(within(paneHead()).getByRole("button", { name: "부서 추가" }));
    const dlg = await screen.findByRole("dialog", { name: "클로비원에 부서 추가" }, WAIT);
    expect(within(dlg).getByLabelText(/상위 부서/)).toHaveTextContent("(최상위)");
    expect(within(dlg).queryByLabelText(/^조직/)).toBeNull();
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p, o]) => String(p) === "/api/admin/departments" && o && o.method === "POST");
      expect(post, "부서 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body).toEqual({ name: "품질팀", parent_id: null, org_id: "org-1" });
    }, WAIT);
    await waitFor(() => expect(where()).toBe("/departments/dep-new"), WAIT);
    expect(await within(panel()).findByRole("heading", { level: 2, name: "품질팀" }, WAIT)).toBeInTheDocument();
  });

  it("부서 판의 「하위 부서 추가」는 그 부서를 상위로 미리 채우고, 요청에 상위 부서와 조직이 함께 실린다", async () => {
    mockApi();
    renderConsole("/departments/dep-sales");
    await within(panel()).findByRole("heading", { level: 2, name: "영업팀" }, WAIT);
    await userEvent.click(within(paneHead()).getByRole("button", { name: "하위 부서 추가" }));
    const dlg = await screen.findByRole("dialog", { name: "영업팀에 하위 부서 추가" }, WAIT);
    await waitFor(() => expect(within(dlg).getByLabelText(/상위 부서/)).toHaveTextContent("영업팀"), WAIT);
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p, o]) => String(p) === "/api/admin/departments" && o && o.method === "POST");
      expect(post, "부서 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body).toEqual({ name: "품질팀", parent_id: "dep-sales", org_id: "org-1" });
    }, WAIT);
  });

  it("부서를 추가하면 왼쪽 트리도 다시 읽는다", async () => {
    mockApi();
    renderConsole();
    await within(panel()).findByRole("heading", { level: 2, name: "클로비원" }, WAIT);
    const before = treeCalls().length;
    await userEvent.click(within(paneHead()).getByRole("button", { name: "부서 추가" }));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => expect(treeCalls().length).toBeGreaterThan(before), WAIT);
  });

  it("「더 보기 › 상세 정보」가 ID · 식별자 · 하위 부서 수를 연다", async () => {
    mockApi();
    renderConsole();
    await within(panel()).findByRole("heading", { level: 2, name: "클로비원" }, WAIT);
    await userEvent.click(within(paneHead()).getByRole("button", { name: "클로비원 작업 더 보기" }));
    await userEvent.click(within(await screen.findByRole("menu", {}, WAIT)).getByRole("menuitem", { name: "상세 정보" }));
    const dlg = await screen.findByRole("dialog", { name: "상세 정보" }, WAIT);
    expect(within(dlg).getByText("org-1")).toBeInTheDocument();
    expect(within(dlg).getByText("clovirone")).toBeInTheDocument();
    expect(within(dlg).getByText("3개")).toBeInTheDocument();
    expect(within(dlg).getByRole("button", { name: "복사" })).toBeInTheDocument();
  });
});

/* ── 5. 세 주소가 모두 살아 있는가 ──────────────────────────────────────── */

describe("라우팅", () => {
  it.each([["/org-tree"], ["/organizations"], ["/departments"]])(
    "%s 는 작업 공간을 열고 첫 조직의 판을 보여 준다",
    async (path) => {
      mockApi();
      const { unmount } = renderConsole(path);
      expect(await screen.findByTestId("org-console-tree", {}, WAIT)).toBeInTheDocument();
      expect(await within(panel()).findByRole("heading", { level: 2, name: "클로비원" }, WAIT)).toBeInTheDocument();
      unmount();
    },
  );
});

/* ── 6. 골격 ─────────────────────────────────────────────────────────────── */

describe("화면 골격", () => {
  it("PageHeader 는 하나이고 설명 줄 없이 도움말만 든다 — 판 둘이 작업 공간 격자에 선다", async () => {
    mockApi();
    const { container } = renderConsole();
    await node("클로비원");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("조직 관리");
    expect(screen.queryByText("조직도에서 조직이나 부서를 고르고 그 자리에서 관리합니다.")).toBeNull();
    const grid = container.querySelector("[data-workspace-grid]");
    expect(grid.querySelectorAll("[data-workspace-pane]")).toHaveLength(2);
    // 오른쪽 자리는 배치에 끼지 않는다 — 판이 곧 격자의 칸이다.
    expect(window.getComputedStyle(panel()).display).toBe("contents");
    expect(tree()).toHaveAttribute("aria-label", "조직도");
  });

  describe("한 열 배치(lg 미만)", () => {
    const NARROW = "(max-width:1199.95px)";
    let original;
    beforeEach(() => {
      original = window.matchMedia;
      window.matchMedia = (query) => ({
        matches: query === NARROW,
        media: query,
        addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {}, onchange: null,
        dispatchEvent: () => false,
      });
    });
    afterEach(() => { window.matchMedia = original; });

    it("트리에서 고르면 초점이 판 제목으로 옮겨 간다 — 고른 결과가 화면 밖에서 바뀌지 않는다", async () => {
      mockApi();
      renderConsole();
      await userEvent.click(await node("영업팀"));
      const heading = await within(panel()).findByRole("heading", { level: 2, name: "영업팀" }, WAIT);
      await waitFor(() => expect(document.activeElement).toBe(heading), WAIT);
      expect(heading).toHaveAttribute("tabindex", "-1");
    });
  });

  it("두 판 배치에서는 초점을 옮기지 않는다 — 트리에서 이어서 고를 수 있다", async () => {
    mockApi();
    renderConsole();
    await userEvent.click(await node("영업팀"));
    const heading = await within(panel()).findByRole("heading", { level: 2, name: "영업팀" }, WAIT);
    await new Promise((resolve) => { setTimeout(resolve, 30); });
    expect(document.activeElement).not.toBe(heading);
  });
});
