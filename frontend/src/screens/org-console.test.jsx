import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 조직 관리 IA 재설계(P6)로 페이지 요약 타일 넷과 상세 판 요약 타일 셋을 걷고 수를 한 곳에만 세웠다. 검색 · 사용 필터는 트리 판 안으로, 부서 추가는 상세 판의 동작 묶음으로 옮겼다 — 요약 타일 단언을 「수는 한 곳」 단언으로 바꾸고, 필터 · 생성 입구 단언을 새 자리(트리 판 · 상세 판)로 옮겨 적었다.
 *
 * qa-contract-change: 오른쪽 판이 전체 표(DataScreen)에서 선택 반응형 상세 판으로 재설계됐고 검색·사용 필터는 페이지 상단 탐색 줄로 올라갔다 — 조작기 이름과 자리가 전부 바뀌어 단언을 새 구조로 옮겨 적었다.
 *
 * 이 화면이 먼저 말하는 것: 「왼쪽에서 조직 · 부서 계층을 탐색하고, 오른쪽에서 고른 대상 하나를 관리한다」.
 * 지키는 성질:
 *
 *   1) 트리에서 고른 것에 오른쪽이 **상세로** 반응하고, 선택이 주소에 남는다(부서 = /departments/:id,
 *      조직 = /organizations?org=). 고른 항목이 눈에 보이게 강조된다(aria-selected).
 *   2) **수는 한 곳에만** 선다 — 가지 인원은 트리 줄, 직접 구성원은 부서 판의 「구성원 N명」, 부서 미지정은
 *      조직 판의 「부서 미지정 N명」. 페이지 요약 타일도, 상세 판 요약 타일도, 트리 부제도 없다.
 *   3) 검색과 「사용」은 트리 판 안에 있고 그대로 동작한다(검색 = 조상 보존, 사용 = 서버 필터).
 *   4) 부서 추가는 고른 자리에서 연다 — 조직을 다시 묻지 않고 상위 부서를 미리 채운다. 만들면 그리로 간다.
 *   5) 진짜 트리다(중첩 group + aria-level + 연결선). PageHeader 는 하나다.
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
import { nestRows, pruneTree } from "./OrgTree.jsx";
import { ancestorsOf } from "./org/DeptDetailPanel.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";

/* 값이 실제로 달라지는 표본을 쓴다 — 부서마다 인원, 사용 여부, 깊이가 다르고 조직도 둘이다.
 * 전부 같은 값이면 "바뀌었다"를 확인하는 검사가 우연히 통과한다. 가지 인원(subtree)과 직접 인원(user_count)도
 * 일부러 다르다 — 「수는 한 곳」 시험이 둘을 가를 수 있어야 한다. */
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", slug: "clovirone", depth: 0, path: "클로비원",
    parent_id: null, parent_name: null, active: true, user_count: 1, child_count: 2,
    subtree_user_count: 9, cycle: false, created_at: AT },
  { id: "dep-sales", kind: "department", name: "영업팀", depth: 1, path: "클로비원 › 영업팀",
    parent_id: null, parent_name: null, org_id: "org-1", active: true, user_count: 4,
    child_count: 1, subtree_user_count: 6, cycle: false, created_at: AT },
  { id: "dep-sales-kr", kind: "department", name: "국내영업", depth: 2,
    path: "클로비원 › 영업팀 › 국내영업", parent_id: "dep-sales", parent_name: "영업팀",
    org_id: "org-1", active: false, user_count: 2, child_count: 0, subtree_user_count: 2,
    cycle: false, created_at: AT },
  { id: "dep-dev", kind: "department", name: "개발팀", depth: 1, path: "클로비원 › 개발팀",
    parent_id: null, parent_name: null, org_id: "org-1", active: true, user_count: 3,
    child_count: 0, subtree_user_count: 3, cycle: false, created_at: AT },
];

const ORGS = [
  { id: "org-1", name: "클로비원", slug: "clovirone", status: "active",
    department_count: 3, user_count: 9, created_at: AT },
  { id: "org-2", name: "묵은회사", slug: "old-co", status: "suspended",
    department_count: 0, user_count: 0, created_at: AT },
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
  // 기록은 3명인데 목록(보관 계정 제외)은 2명이다 — 그 차이를 목록 아래 한 줄이 말해야 한다.
  "dep-dev": { id: "dep-dev", name: "개발팀", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 3, child_department_count: 0, created_at: AT },
  "dep-new": { id: "dep-new", name: "품질팀", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 0, child_department_count: 0, created_at: AT },
};

/* 사람 목록은 부서마다 다르다. `none` 은 부서 미지정 센티널이다(P-61). */
const PEOPLE = {
  "dep-sales": { items: [{ id: "u-1", display_name: "김영업", title: "과장", role: "user" }], total: 4 },
  "dep-dev": { items: [
    { id: "u-2", display_name: "이개발", title: "주임", role: "user" },
    { id: "u-3", display_name: "박개발", title: null, role: "admin" },
  ], total: 2 },
  "dep-sales-kr": { items: [], total: 0 },
  none: { items: [{ id: "u-9", display_name: "무소속", title: "사원", role: "user" }], total: 1 },
};

function mockApi({ tree = TREE } = {}) {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
    if (options && options.method === "POST" && u === "/api/admin/departments") {
      return Promise.resolve({ id: "dep-new", name: "품질팀" });
    }
    // /tree 를 먼저 본다 — /api/admin/departments 가 접두어라 순서가 뒤집히면 트리가 목록을 받는다.
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: tree });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    const single = u.match(/^\/api\/admin\/departments\/([a-z-]+)$/);
    if (single) return Promise.resolve({ department: DEPT_ITEMS[single[1]] || null });
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: DEPTS });
    if (u.startsWith("/api/admin/users")) {
      const dept = new URLSearchParams(u.split("?")[1] || "").get("department_id");
      return Promise.resolve(PEOPLE[dept] || { items: [], total: 0 });
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
const where = () => screen.getByTestId("location-probe").textContent;
const node = (name) => screen.findByRole("treeitem", { name }, WAIT);
const usersCalls = (dept) => apiMock.mock.calls.filter(([p]) =>
  String(p) === "/api/admin/users?department_id=" + dept);

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
});
afterEach(() => { window.location.hash = ""; });

/* ── 1. 평탄한 행 목록을 진짜 트리로 접는다 ──────────────────────────────── */

describe("트리 접기(nestRows)", () => {
  it("depth 로 부모, 자식을 되살린다", () => {
    const roots = nestRows(TREE);
    expect(roots).toHaveLength(1);
    expect(roots[0].row.id).toBe("org-1");
    expect(roots[0].children.map((c) => c.row.id)).toEqual(["dep-sales", "dep-dev"]);
    // 국내영업은 영업팀 아래다 — 개발팀 아래로 붙으면 트리가 거짓말을 한다.
    expect(roots[0].children[0].children.map((c) => c.row.id)).toEqual(["dep-sales-kr"]);
    expect(roots[0].children[1].children).toEqual([]);
  });

  it("조직 행이 없는 응답(초기화 전)도 부서만으로 접는다", () => {
    const roots = nestRows([
      { id: "a", name: "가", depth: 0 },
      { id: "b", name: "나", depth: 1 },
      { id: "c", name: "다", depth: 0 },
    ]);
    expect(roots.map((r) => r.row.id)).toEqual(["a", "c"]);
    expect(roots[0].children.map((r) => r.row.id)).toEqual(["b"]);
  });
});

/* 트리 검색(pruneTree)은 서버 검색과 같은 접기다(`lib/search.js`) — 공백 · 대소문자 · 전각 표기가 결과를 바꾸지 않고,
 * 맞는 노드의 조상은 그대로 남는다. */
describe("트리 검색(pruneTree) — 공백 · 대소문자 · 전각 표기를 가리지 않는다", () => {
  const ids = (nodes) => nodes.flatMap((n) => [n.row.id, ...ids(n.children)]);
  const SLUGGED = [
    { id: "org-9", kind: "organization", name: "클로비원", slug: "clovirone", depth: 0, path: "클로비원" },
    { id: "dep-pd", kind: "department", name: "플랫폼 개발팀", depth: 1, path: "클로비원 › 플랫폼 개발팀" },
    { id: "dep-qa", kind: "department", name: "품질팀", depth: 1, path: "클로비원 › 품질팀" },
  ];

  it("부서 이름을 붙여 치든 띄워 치든 같은 가지가 남고, 조상도 남는다", () => {
    for (const q of ["국내영업", "국내 영업", " 국내  영업 ", "국내\u{3000}영업"]) {
      expect(ids(pruneTree(nestRows(TREE), q)), q).toEqual(["org-1", "dep-sales", "dep-sales-kr"]);
    }
    for (const q of ["플랫폼개발", "플랫폼 개발팀"]) {
      expect(ids(pruneTree(nestRows(SLUGGED), q)), q).toEqual(["org-9", "dep-pd"]);
    }
  });

  it("식별자는 대소문자 · 전각 표기를 가리지 않는다", () => {
    for (const q of ["CLOVIRONE", "ClovirONE", "ｃｌｏｖｉｒｏｎｅ"]) {
      expect(ids(pruneTree(nestRows(SLUGGED), q)), q).toEqual(["org-9"]);
    }
  });

  it("맞는 것이 없으면 빈 트리이고, 공백만 친 검색어는 트리를 그대로 둔다", () => {
    expect(pruneTree(nestRows(TREE), "없는부서")).toEqual([]);
    const roots = nestRows(TREE);
    expect(pruneTree(roots, "   ")).toBe(roots);
    expect(pruneTree(roots, "\u{200B}")).toBe(roots);
  });
});

describe("부서 경로(ancestorsOf) — 판 머리 둘째 줄의 재료", () => {
  it("조상만 뿌리부터 순서대로 돌려주고, 고리에서는 한 바퀴 돌기 전에 멈춘다", () => {
    expect(ancestorsOf(TREE, "dep-sales-kr")).toEqual([{ id: "dep-sales", name: "영업팀" }]);
    expect(ancestorsOf(TREE, "dep-dev")).toEqual([]);
    const LOOP = [
      { id: "a", name: "가", parent_id: "b" },
      { id: "b", name: "나", parent_id: "a" },
    ];
    expect(ancestorsOf(LOOP, "a")).toEqual([{ id: "b", name: "나" }]);
  });
});

/* ── 2. 왼쪽 트리에서 고르면 오른쪽이 **상세로** 반응한다 ──────────────── */

describe("트리 선택 → 상세 판", () => {
  it("첫 진입에는 첫 조직의 상세를 보여준다(빈 오른쪽 판은 화면 절반이 죽은 상태다)", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    // 조직 상세 — 이름 · 식별자 · 부서 수가 실제로 그려진다(제목만이 아니다).
    expect(await within(panel()).findByRole("heading", { name: "클로비원" }, WAIT)).toBeInTheDocument();
    expect(within(panel()).getByText("clovirone")).toBeInTheDocument();
    expect(within(panel()).getByText("식별자")).toBeInTheDocument();
    expect(within(panel()).getByText("3개")).toBeInTheDocument();
    // 같은 수를 문장으로 되풀이하던 「포함 관계」 줄은 없다.
    expect(within(panel()).queryByText("포함 관계")).toBeNull();
    // 주소는 안 바뀌지만 첫 조직이 골라진 것으로 보인다.
    expect(await node("클로비원")).toHaveAttribute("aria-selected", "true");
  });

  it("부서 노드를 누르면 부서 상세가 서고, 주소가 /departments/:id 가 된다(D-104)", async () => {
    mockApi();
    renderConsole();
    await userEvent.click(await node("영업팀"));
    expect(await within(panel()).findByRole("heading", { name: "영업팀" }, WAIT)).toBeInTheDocument();
    expect(where()).toBe("/departments/dep-sales");
    // 단건 GET 이 실제로 나갔다 — 트리 행 재활용이 아니라 상세 자료다.
    expect(apiMock.mock.calls.some(([p]) => String(p) === "/api/admin/departments/dep-sales")).toBe(true);
    // 구성원이 상세 판 **안**에 있다 — 옛 셋째 판은 1920 미만에서 통째로 사라졌다.
    expect(await within(panel()).findByRole("heading", { name: "구성원 4명" }, WAIT)).toBeInTheDocument();
    expect(await within(panel()).findByText("김영업", {}, WAIT)).toBeInTheDocument();
    // 직급은 배지가 아니라 이름 뒤의 글자다.
    expect(within(panel()).getByText("과장").closest(".k-badge")).toBeNull();
    // 조직 · 전체 경로 · 상위 부서 세 줄 대신 판 머리 둘째 줄의 경로 하나다.
    expect(within(panel()).getByText("클로비원")).toBeInTheDocument();
    expect(within(panel()).queryByText("전체 경로")).toBeNull();
    expect(within(panel()).queryByText("상위 부서")).toBeNull();

    await userEvent.click(await node("클로비원"));
    expect(await within(panel()).findByRole("heading", { name: "클로비원" }, WAIT)).toBeInTheDocument();
    expect(where()).toBe("/organizations?org=org-1");
  });

  it("고른 항목만 강조된다(aria-selected)", async () => {
    mockApi();
    renderConsole();
    await userEvent.click(await node("국내영업"));
    await waitFor(async () => {
      expect(await node("국내영업")).toHaveAttribute("aria-selected", "true");
    }, WAIT);
    expect(await node("영업팀")).toHaveAttribute("aria-selected", "false");
  });

  it("딥링크 /departments/:id 로 들어오면 그 부서가 미리 골라진 채 열리고, 미사용 부서는 하위 부서 추가를 안 세운다", async () => {
    mockApi();
    renderConsole("/departments/dep-sales-kr");
    expect(await within(panel()).findByRole("heading", { name: "국내영업" }, WAIT)).toBeInTheDocument();
    expect(await node("국내영업")).toHaveAttribute("aria-selected", "true");
    // 미사용 부서라 상태 배지가 사실을 말한다. 경로는 조직 › 영업팀 이다.
    expect(within(panel()).getByText("미사용")).toBeInTheDocument();
    expect(within(panel()).getByText("클로비원 › 영업팀")).toBeInTheDocument();
    // 서버가 미사용 부서를 새 상위로 받지 않는다 — 단추 대신 이유와 푸는 길이 선다.
    expect(within(panel()).queryByRole("button", { name: "하위 부서 추가" })).toBeNull();
    expect(within(panel()).getByText("미사용 부서에는 하위 부서를 만들 수 없습니다. 먼저 활성화하세요."))
      .toBeInTheDocument();
  });

  it("없는 부서 id 딥링크는 판 안에서 말하고, 트리는 그대로 남는다(D-127)", async () => {
    mockApi();
    apiMock.mockImplementation((url) => {
      const u = String(url);
      if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
      if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
      if (u === "/api/admin/departments/dep-ghost") {
        const err = new Error("부서를 찾지 못했습니다.");
        err.status = 404;
        return Promise.reject(err);
      }
      if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: DEPTS });
      return Promise.resolve({ items: [], total: 0 });
    });
    renderConsole("/departments/dep-ghost");
    expect((await within(panel()).findAllByText(/찾을 수 없습니다/, {}, WAIT)).length).toBeGreaterThan(0);
    expect(await node("클로비원")).toBeInTheDocument();
  });
});

/* ── 3. 수는 한 곳에만 선다 ─────────────────────────────────────────────── */

describe("수는 한 곳에만", () => {
  it("페이지 요약 타일도 상세 판 요약 타일도 없다 — 전체 합계는 어떤 결정에도 안 쓰인다", async () => {
    mockApi();
    renderConsole();
    await within(panel()).findByRole("heading", { name: "클로비원" }, WAIT);
    expect(screen.queryByRole("group", { name: "조직 요약" })).toBeNull();
    expect(screen.queryByRole("group", { name: /요약/ })).toBeNull();
    // 요약 타일이 쓰던 낱말(「구성원」 타일)이 트리 밖에 따로 서지 않는다 — 트리 줄의 「구성원 N명」 설명
    // (스크린리더 전용 머리말)만 남는다.
    const outsideTree = screen.queryAllByText("구성원").filter((el) => !tree().contains(el));
    expect(outsideTree).toEqual([]);
    expect(within(panel()).queryByText("사용자")).toBeNull();
  });

  it("가지 인원은 그 트리 줄에만 선다 — 상세 판은 같은 수를 되풀이하지 않는다", async () => {
    mockApi();
    renderConsole();
    const org = await node("클로비원");
    await within(panel()).findByRole("heading", { name: "클로비원" }, WAIT);
    // 수는 이름이 아니라 설명으로 붙는다 — 스크린리더는 「구성원 9명」으로 읽는다.
    expect(org).toHaveAccessibleName("클로비원");
    expect(org).toHaveAccessibleDescription(/구성원 9명/);
    expect(within(tree()).getByText("9명")).toBeInTheDocument();
    expect(panel().textContent).not.toMatch(/9명/);

    const sales = await node("영업팀");
    expect(sales).toHaveAccessibleDescription("구성원 6명");
    await userEvent.click(sales);
    // 부서 판의 수는 **직접** 구성원이다(4) — 가지 인원(6)은 트리 줄에만 있다.
    expect(await within(panel()).findByRole("heading", { name: "구성원 4명" }, WAIT)).toBeInTheDocument();
    expect(panel().textContent).not.toMatch(/6명/);
  });

  it("「부서 미지정」은 판에 한 번 — 수를 단 절 제목이고, 트리에는 수 없는 경고 배지로만 선다", async () => {
    mockApi();
    renderConsole("/organizations");
    await within(panel()).findByRole("heading", { name: "클로비원" }, WAIT);
    const inPanel = within(panel()).getAllByText(/부서 미지정/);
    expect(inPanel).toHaveLength(1);
    expect(inPanel[0]).toHaveTextContent("부서 미지정 1명");
    expect(within(panel()).getByRole("heading", { name: "부서 미지정 1명" })).toBeInTheDocument();
    // 트리에서는 그 조직 줄의 배지 하나다 — 수를 달지 않는다.
    const inTree = within(tree()).getAllByText(/부서 미지정/);
    expect(inTree).toHaveLength(1);
    expect(inTree[0].textContent).toBe("부서 미지정");
  });

  it("트리 줄에 부제가 없다 — 소속 · 하위 부서 · 하위 포함 · 부서 수를 적지 않는다", async () => {
    mockApi();
    renderConsole();
    await node("국내영업");
    expect(tree().textContent).not.toMatch(/소속|하위 부서|하위 포함|부서 \d+개|구성원 \d+명, /);
    // 수는 줄마다 하나다 — 네 줄에 넷이다.
    expect(within(tree()).getAllByText(/^\d+명$/)).toHaveLength(4);
  });

  it("기록된 인원이 목록보다 많으면 보관된 계정의 차이를 목록 아래 한 줄이 말한다", async () => {
    mockApi();
    renderConsole("/departments/dep-dev");
    expect(await within(panel()).findByRole("heading", { name: "구성원 2명" }, WAIT)).toBeInTheDocument();
    expect(await within(panel()).findByText("보관된 계정 1명은 이 목록에 없습니다.", {}, WAIT)).toBeInTheDocument();
    // 직급이 없는 사람은 역할 키를 대신 적지 않는다.
    expect(within(panel()).getByText("박개발")).toBeInTheDocument();
    expect(within(panel()).queryByText("admin")).toBeNull();
  });

  it("보이는 조직이 하나면 부서 미지정 사람들을 보여 주고, 링크는 그 사람들만 거른 사용자 화면으로 간다 (P-61)", async () => {
    /* 조직 마디의 `user_count` 가 곧 부서 없는 인원이다(클로비원: 1). 링크가 필터 없는
       `#/users` 로 가면 숫자만 말하고 그 사람들을 못 찾는다 — 서버 센티널 `none` 을 싣는다. */
    mockApi();
    renderConsole("/organizations");
    const section = (await within(panel()).findByRole("heading", { name: "부서 미지정 1명" }, WAIT))
      .closest("section");
    expect(await within(section).findByText("무소속", {}, WAIT)).toBeInTheDocument();
    expect(usersCalls("none").length).toBeGreaterThan(0);
    const link = within(section).getByRole("link", { name: "사용자 화면에서 보기" });
    expect(link.getAttribute("href")).toBe("#/users?department_id=none");
  });

  it("보이는 조직이 둘 이상이면 명단을 받지 않는다 — 부서 미지정 명단은 조직으로 안 좁혀진다", async () => {
    mockApi({
      tree: TREE.concat([
        { id: "org-2", kind: "organization", name: "묵은회사", slug: "old-co", depth: 0, path: "묵은회사",
          active: false, user_count: 0, child_count: 0, subtree_user_count: 0, created_at: AT },
      ]),
    });
    renderConsole("/organizations?org=org-1");
    const section = (await within(panel()).findByRole("heading", { name: "부서 미지정 1명" }, WAIT))
      .closest("section");
    expect(section.textContent).toContain("사용자 화면은 다른 조직에서 부서가 없는 사람도 함께 보여 줍니다.");
    expect(within(section).getByRole("link", { name: "사용자 화면에서 보기" }).getAttribute("href"))
      .toBe("#/users?department_id=none");
    expect(usersCalls("none")).toHaveLength(0);
    expect(within(section).queryByText("무소속")).toBeNull();
  });
});

/* ── 4. 진짜 트리인가(들여쓴 목록이 아니라) ──────────────────────────────── */

describe("트리 구조", () => {
  it("중첩 group 과 aria-level 로 계층을 드러낸다", async () => {
    mockApi();
    renderConsole();
    const org = await node("클로비원");
    const sales = await node("영업팀");
    const kr = await node("국내영업");
    expect(within(tree()).getByRole("tree")).toBeInTheDocument();
    expect(org).toHaveAttribute("aria-level", "1");
    expect(sales).toHaveAttribute("aria-level", "2");
    expect(kr).toHaveAttribute("aria-level", "3");
    // 자식은 부모 안에 들어 있다 — 같은 층에 나란히 놓고 왼쪽 여백만 준 목록이 아니다.
    expect(org.contains(sales)).toBe(true);
    expect(sales.contains(kr)).toBe(true);
    expect(within(sales).getByRole("group")).toContainElement(kr);
  });

  /* 계층이 왼쪽 여백과 '└ ' 글자로만 표현되면 트리처럼 보일 뿐 트리가 아니다.
   * 연결선은 소스에 적혀 있는 것으로는 부족하다 — 실제 스타일로 나오는지 본다. */
  it("연결선을 실제 스타일로 그린다", async () => {
    mockApi();
    renderConsole();
    const sales = await node("영업팀");
    const org = await node("클로비원");
    const child = cssOf(sales);
    expect(child).toMatch(/::before\{content:""/);   // 형제를 잇는 세로 줄기
    expect(child).toMatch(/::after\{content:""/);    // 줄기에서 이 노드로 뻗는 가로 갈래
    expect(child).toMatch(/padding-inline-start/);   // 들여쓰기
    // 마지막 형제 아래로 줄기가 흘러내리면 아직 뭔가 더 있는 것처럼 보인다.
    expect(child).toMatch(/:last-of-type::before\{bottom:auto/);
    // 뿌리(조직)에는 위로 이어질 줄기가 없다 — 모든 줄에 갈래를 그리면 그것도 거짓말이다.
    expect(cssOf(org)).not.toMatch(/::after\{content:""/);
  });

  it("자식이 있는 노드는 접었다 펼 수 있다", async () => {
    mockApi();
    renderConsole();
    const sales = await node("영업팀");
    expect(sales).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(within(sales).getByRole("button", { name: /접기|펼치기/ }));
    await waitFor(() => expect(sales).toHaveAttribute("aria-expanded", "false"), WAIT);
    expect(screen.queryByRole("treeitem", { name: "국내영업" })).toBeNull();
  });
});

/* emotion 이 만든 규칙 중 그 요소의 클래스에 걸린 것만 모은다(미디어 규칙 안의 것도 포함). */
function cssOf(el) {
  const sheets = Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("\n");
  return Array.from(el.classList).map((c) => {
    const re = new RegExp("\\." + c + "[^{]*\\{[^}]*\\}", "g");
    const out = [];
    let m;
    while ((m = re.exec(sheets))) out.push(m[0]);
    return out.join("\n");
  }).join("\n");
}

/* ── 5. 레일 = 탐색 — 검색과 「사용」은 트리 판 안에 있다 ─────────────────── */

describe("레일 판 머리의 검색과 「사용」", () => {
  it("검색 상자와 「사용」은 트리 판 안에 있고, 상세 판에는 검색이 없다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    expect(within(tree()).getByRole("searchbox", { name: "조직도 검색" })).toBeInTheDocument();
    expect(within(tree()).getByRole("combobox", { name: /사용/ })).toBeInTheDocument();
    expect(within(panel()).queryByRole("searchbox")).toBeNull();
    // 트리 판 밖(페이지 전폭)에 따로 선 필터 줄은 없다 — 화면의 필터 바는 판 안의 하나다.
    expect(document.querySelectorAll("[data-filter-bar]")).toHaveLength(1);
    expect(tree().querySelector("[data-filter-bar]")).not.toBeNull();
  });

  it("'사용' 필터는 그대로 서버로 간다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    await userEvent.click(within(tree()).getByRole("combobox", { name: /사용/ }));
    await userEvent.click(await screen.findByRole("option", { name: "미사용" }, WAIT));
    await waitFor(() => expect(apiMock.mock.calls.some(([p]) =>
      String(p).startsWith("/api/admin/departments/tree") && String(p).includes("active=false"))).toBe(true), WAIT);
    expect(where()).toContain("active=false");
  });

  it("이름 검색이 그대로 있고(맞지 않는 가지는 사라지고 조상은 남는다), 조건 줄이 판 안에서 결과를 센다", async () => {
    mockApi();
    renderConsole();
    await node("개발팀");
    await userEvent.type(within(tree()).getByRole("searchbox", { name: "조직도 검색" }), "개발");
    await waitFor(() => expect(screen.queryByRole("treeitem", { name: "영업팀" })).toBeNull(), WAIT);
    // 맞는 노드와 그 조상은 남는다 — 조상을 지우면 어디 소속인지 알 수 없게 된다.
    expect(await node("개발팀")).toBeInTheDocument();
    expect(await node("클로비원")).toBeInTheDocument();
    expect(await within(tree()).findByText("조건 1개, 결과 1개 부서", {}, WAIT)).toBeInTheDocument();
  });

  it("레일 판은 고정 머리 아래에 붙박인다 — `top: 0` 이면 판 윗부분이 머리 뒤로 들어간다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    const card = tree().querySelector(".MuiCard-root");
    const css = cssOf(card);
    expect(css).toMatch(/position:sticky/);
    expect(css).toMatch(/top:calc\(var\(--c-sticky-top/);
    expect(css).not.toMatch(/top:0[;}]/);
  });
});

/* ── 6. 부서는 고른 자리에서 만든다 ──────────────────────────────────────── */

describe("부서 추가 — 고른 조직 · 부서의 판에서", () => {
  it("페이지 머리에는 선택과 무관한 「조직 추가」 하나뿐이고, 「부서 추가」는 조직 판에 있다", async () => {
    mockApi();
    const { container } = renderConsole();
    await within(panel()).findByRole("heading", { name: "클로비원" }, WAIT);
    const head = container.querySelector(".k-page-actions");
    expect(within(head).getAllByRole("button").map((b) => b.textContent)).toEqual(["조직 추가"]);
    expect(within(head).queryByRole("button", { name: "부서 추가" })).toBeNull();
    expect(within(panel()).getByRole("button", { name: "부서 추가" })).toBeInTheDocument();
  });

  it("조직 판의 「부서 추가」는 그 조직을 고정해 열고 조직을 다시 묻지 않는다 — 만들면 새 부서로 간다", async () => {
    mockApi();
    renderConsole();
    await userEvent.click(await within(panel()).findByRole("button", { name: "부서 추가" }, WAIT));
    const dlg = await screen.findByRole("dialog", { name: "클로비원에 부서 추가" }, WAIT);
    expect(within(dlg).getByLabelText(/부서 이름/)).toBeInTheDocument();
    expect(within(dlg).getByLabelText(/상위 부서/)).toHaveTextContent("(최상위)");
    expect(within(dlg).queryByLabelText(/^조직/)).toBeNull();
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p, o]) =>
        String(p) === "/api/admin/departments" && o && o.method === "POST");
      expect(post, "부서 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body).toEqual({ name: "품질팀", parent_id: null, org_id: "org-1" });
    }, WAIT);
    await waitFor(() => expect(where()).toBe("/departments/dep-new"), WAIT);
    expect(await within(panel()).findByRole("heading", { name: "품질팀" }, WAIT)).toBeInTheDocument();
  });

  it("부서 판의 「하위 부서 추가」는 그 부서를 상위로 미리 채우고, 요청에 상위 부서와 조직이 함께 실린다", async () => {
    mockApi();
    renderConsole("/departments/dep-sales");
    await userEvent.click(await within(panel()).findByRole("button", { name: "하위 부서 추가" }, WAIT));
    const dlg = await screen.findByRole("dialog", { name: "영업팀에 하위 부서 추가" }, WAIT);
    await waitFor(() => expect(within(dlg).getByLabelText(/상위 부서/)).toHaveTextContent("영업팀"), WAIT);
    expect(within(dlg).queryByLabelText(/^조직/)).toBeNull();
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));
    await waitFor(() => {
      const post = apiMock.mock.calls.find(([p, o]) =>
        String(p) === "/api/admin/departments" && o && o.method === "POST");
      expect(post, "부서 생성 요청이 안 나갔다").toBeTruthy();
      expect(post[1].body).toEqual({ name: "품질팀", parent_id: "dep-sales", org_id: "org-1" });
    }, WAIT);
  });

  it("부서를 추가하면 왼쪽 트리도 다시 읽는다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    const treeCalls = () => apiMock.mock.calls.filter(([p]) =>
      String(p).startsWith("/api/admin/departments/tree")).length;
    const before = treeCalls();

    await userEvent.click(await within(panel()).findByRole("button", { name: "부서 추가" }, WAIT));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));

    // 트리와 목록은 캐시 주소가 다르다 — 목록만 갱신하면 방금 만든 부서가 왼쪽에 안 나타나고,
    // 사용자는 "추가했는데 조직도에 없다"로 읽는다.
    await waitFor(() => expect(treeCalls()).toBeGreaterThan(before), { timeout: 3000 });
  });
});

/* ── 7. 세 주소가 모두 살아 있는가 ──────────────────────────────────────── */

describe("라우팅", () => {
  /* 세 주소를 모두 남긴다. 하나라도 없애면 즐겨찾기와 딥링크가 대시보드로 튕긴다.
   * 미선택 기본은 어느 주소로 들어와도 **첫 조직의 상세**다 — 트리의 뿌리가 조직이라
   * 방향(위→아래)이 맞고, 빈 오른쪽 판은 화면 절반이 죽은 상태다. */
  it.each([["/org-tree"], ["/organizations"], ["/departments"]])(
    "%s 는 콘솔을 열고 첫 조직의 상세를 보여준다",
    async (path) => {
      mockApi();
      const { unmount } = renderConsole(path);
      expect(await screen.findByTestId("org-console-tree", {}, WAIT)).toBeInTheDocument();
      expect(await within(panel()).findByRole("heading", { name: "클로비원" }, WAIT)).toBeInTheDocument();
      unmount();
    },
  );
});

/* ── 8. 골격 — PageHeader 하나, [트리 | 상세], 한 칸 배치의 초점 ───────────── */

describe("화면 골격", () => {
  it("PageHeader 가 화면에 하나다 — 오른쪽 판은 페이지가 아니라 상세다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("조직 관리");
    expect(screen.getByText("조직도에서 조직이나 부서를 고르고 그 자리에서 관리합니다.")).toBeInTheDocument();
  });

  it("본문은 [트리 | 상세] 2칸 격자다 — 셋째 판은 없다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    const box = window.getComputedStyle(tree().parentElement);
    expect(box.display).toBe("grid");
    expect(screen.queryByTestId("org-console-people")).toBeNull();
  });

  describe("한 칸 배치(lg 미만)", () => {
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
      const heading = await within(panel()).findByRole("heading", { name: "영업팀" }, WAIT);
      await waitFor(() => expect(document.activeElement).toBe(heading), WAIT);
      expect(heading).toHaveAttribute("tabindex", "-1");
    });
  });

  it("두 칸 배치에서는 초점을 옮기지 않는다 — 트리에서 이어서 고를 수 있다", async () => {
    mockApi();
    renderConsole();
    await userEvent.click(await node("영업팀"));
    const heading = await within(panel()).findByRole("heading", { name: "영업팀" }, WAIT);
    await new Promise((resolve) => { setTimeout(resolve, 30); });
    expect(document.activeElement).not.toBe(heading);
  });
});
