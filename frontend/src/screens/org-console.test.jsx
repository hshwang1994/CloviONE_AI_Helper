import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 오른쪽 판이 전체 표(DataScreen)에서 선택 반응형 상세 판으로 재설계됐고 검색·사용 필터는 페이지 상단 탐색 줄로 올라갔다 — 조작기 이름과 자리가 전부 바뀌어 단언을 새 구조로 옮겨 적었다.
 *
 * 계획서 지적: «우측 pane 이 트리 선택에 상세로 반응하지 않는다». 선택은 주소가 든다
 * (부서 = /departments/:id, 조직 = /organizations?org=). 지키는 성질은 그대로 옮긴다:
 *
 *   1) 트리에서 고른 것에 오른쪽이 **상세로** 반응하고, 선택이 주소에 남는다.
 *   2) 고른 항목이 눈에 보이게 강조된다(aria-selected).
 *   3) 합치면서 기존 기능이 사라지지 않는다 — 사용 여부 필터(서버), 이름 검색(조상 보존),
 *      부서 생성 폼(상위 부서 포함), 추가 후 트리 재조회.
 *   4) 진짜 트리다(중첩 group + aria-level + 연결선).
 *   5) PageHeader 는 화면에 하나다. 소속 인원은 모든 폭에서 상세 판 안에 보인다.
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
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const AT = "2026-01-02T03:04:05Z";

/* 값이 실제로 달라지는 표본을 쓴다 — 부서마다 인원, 사용 여부, 깊이가 다르고 조직도 둘이다.
 * 전부 같은 값이면 "바뀌었다"를 확인하는 검사가 우연히 통과한다. */
const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", depth: 0, path: "클로비원",
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
  "dep-dev": { id: "dep-dev", name: "개발팀", active: true, parent_id: null,
    org_id: "org-1", org_name: "클로비원", user_count: 0, child_department_count: 0, created_at: AT },
};

function mockApi() {
  apiMock.mockImplementation((url, options) => {
    const u = String(url);
    if (options && options.method === "POST" && u === "/api/admin/departments") {
      return Promise.resolve({ id: "dep-new", name: "품질팀" });
    }
    // /tree 를 먼저 본다 — /api/admin/departments 가 접두어라 순서가 뒤집히면 트리가 목록을 받는다.
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    const single = u.match(/^\/api\/admin\/departments\/([a-z-]+)$/);
    if (single) return Promise.resolve({ department: DEPT_ITEMS[single[1]] || null });
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: DEPTS });
    if (u.startsWith("/api/admin/users")) {
      return Promise.resolve({
        items: [{ id: "u-1", display_name: "김영업", title: "과장", role: "user" }],
        total: 4,
      });
    }
    return Promise.resolve({ items: [] });
  });
}

function renderConsole(path = "/org-tree") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
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
const node = (name) => screen.findByRole("treeitem", { name }, WAIT);

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

/* ── 2. 왼쪽 트리에서 고르면 오른쪽이 **상세로** 반응한다 ──────────────── */

describe("트리 선택 → 상세 판", () => {
  it("첫 진입에는 첫 조직의 상세를 보여준다(빈 오른쪽 판은 화면 절반이 죽은 상태다)", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    // 조직 상세 — 이름·식별자·부서 미지정이 실제로 그려진다(제목만이 아니다).
    expect(await within(panel()).findByRole("heading", { name: "클로비원" }, WAIT)).toBeInTheDocument();
    expect(within(panel()).getByText("clovirone")).toBeInTheDocument();
    // 「부서 미지정」은 요약 타일과 정보 행 양쪽에 선다 — 한 번 이상이면 된다.
    expect(within(panel()).getAllByText("부서 미지정").length).toBeGreaterThan(0);
  });

  it("부서 노드를 누르면 부서 상세가 서고, 주소가 /departments/:id 가 된다(D-104)", async () => {
    mockApi();
    renderConsole();
    await userEvent.click(await node("영업팀"));
    expect(await within(panel()).findByRole("heading", { name: "영업팀" }, WAIT)).toBeInTheDocument();
    // 단건 GET 이 실제로 나갔다 — 트리 행 재활용이 아니라 상세 자료다.
    expect(apiMock.mock.calls.some(([p]) => String(p) === "/api/admin/departments/dep-sales")).toBe(true);
    // 소속 인원이 상세 판 **안**에 있다 — 옛 셋째 판은 1920 미만에서 통째로 사라졌다.
    expect((await within(panel()).findAllByText(/소속 인원/, {}, WAIT)).length).toBeGreaterThan(0);
    expect(await within(panel()).findByText("김영업", {}, WAIT)).toBeInTheDocument();

    await userEvent.click(await node("클로비원"));
    expect(await within(panel()).findByRole("heading", { name: "클로비원" }, WAIT)).toBeInTheDocument();
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

  it("딥링크 /departments/:id 로 들어오면 그 부서가 미리 골라진 채 열린다", async () => {
    mockApi();
    renderConsole("/departments/dep-sales-kr");
    expect(await within(panel()).findByRole("heading", { name: "국내영업" }, WAIT)).toBeInTheDocument();
    expect(await node("국내영업")).toHaveAttribute("aria-selected", "true");
    // 미사용 부서라 활성화가 서고, 상태 배지가 사실을 말한다.
    expect(within(panel()).getByText("미사용")).toBeInTheDocument();
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
      return Promise.resolve({ items: [] });
    });
    renderConsole("/departments/dep-ghost");
    expect((await within(panel()).findAllByText(/찾을 수 없습니다/, {}, WAIT)).length).toBeGreaterThan(0);
    expect(await node("클로비원")).toBeInTheDocument();
  });
});

/* ── 3. 진짜 트리인가(들여쓴 목록이 아니라) ──────────────────────────────── */

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
    const cssOf = (el) => {
      const sheets = Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("\n");
      return Array.from(el.classList).map((c) => {
        const re = new RegExp("\\." + c + "[^{]*\\{[^}]*\\}", "g");
        const out = [];
        let m;
        while ((m = re.exec(sheets))) out.push(m[0]);
        return out.join("\n");
      }).join("\n");
    };
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

/* ── 4. 합치면서 잃은 것이 없는가(회귀) ─────────────────────────────────── */

describe("기존 기능 회귀", () => {
  it("'사용' 필터는 그대로 서버로 간다 — 상단 탐색 줄에서", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    await userEvent.click(screen.getByRole("combobox", { name: /사용/ }));
    await userEvent.click(await screen.findByRole("option", { name: "미사용" }, WAIT));
    await waitFor(() => expect(apiMock.mock.calls.some(([p]) =>
      String(p).startsWith("/api/admin/departments/tree") && String(p).includes("active=false"))).toBe(true), WAIT);
  });

  it("이름 검색이 그대로 있다(맞지 않는 가지는 사라지고 조상은 남는다)", async () => {
    mockApi();
    renderConsole();
    await node("개발팀");
    await userEvent.type(screen.getByRole("searchbox", { name: "조직도 검색" }), "개발");
    await waitFor(() => expect(screen.queryByRole("treeitem", { name: "영업팀" })).toBeNull(), WAIT);
    // 맞는 노드와 그 조상은 남는다 — 조상을 지우면 어디 소속인지 알 수 없게 된다.
    expect(await node("개발팀")).toBeInTheDocument();
    expect(await node("클로비원")).toBeInTheDocument();
  });

  it("부서 생성 폼이 그대로 있다(상위 부서 선택 포함) — 입구는 페이지 헤더다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    await userEvent.click(screen.getByRole("button", { name: "부서 추가" }));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    expect(within(dlg).getByLabelText(/부서 이름/)).toBeInTheDocument();
    expect(within(dlg).getByLabelText(/상위 부서/)).toBeInTheDocument();
  });

  it("부서를 추가하면 왼쪽 트리도 다시 읽는다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    const treeCalls = () => apiMock.mock.calls.filter(([p]) =>
      String(p).startsWith("/api/admin/departments/tree")).length;
    const before = treeCalls();

    await userEvent.click(screen.getByRole("button", { name: "부서 추가" }));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "추가" }));

    // 트리와 목록은 캐시 주소가 다르다 — 목록만 갱신하면 방금 만든 부서가 왼쪽에 안 나타나고,
    // 사용자는 "추가했는데 조직도에 없다"로 읽는다.
    await waitFor(() => expect(treeCalls()).toBeGreaterThan(before), { timeout: 3000 });
  });
});

/* ── 5. 세 주소가 모두 살아 있는가 ──────────────────────────────────────── */

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

/* ── 6. 골격 — PageHeader 하나, 상단 탐색 줄, 요약 타일 ─────────────────── */

describe("화면 골격", () => {
  it("PageHeader 가 화면에 하나다 — 오른쪽 판은 페이지가 아니라 상세다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("조직 관리");
  });

  it("요약 타일이 부서 미지정 인원을 센다(무필터 트리의 조직 행 합)", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    const strip = screen.getByRole("group", { name: "조직 요약" });
    expect(within(strip).getByText("부서 미지정")).toBeInTheDocument();
    // TREE 의 조직 행 user_count 합 = 1(부서 미지정), 조직 수도 1 — "1" 이 두 타일에 선다.
    // 구성원은 subtree_user_count 합 = 9.
    expect(within(strip).getAllByText("1")).toHaveLength(2);
    expect(within(strip).getByText("9")).toBeInTheDocument();
  });

  it("본문은 [트리 | 상세] 2칸 격자다 — 셋째 판은 없다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    const box = window.getComputedStyle(tree().parentElement);
    expect(box.display).toBe("grid");
    expect(screen.queryByTestId("org-console-people")).toBeNull();
  });

  it("「부서 미지정」 링크는 그 사람들만 거른 사용자 화면으로 간다 (P-61)", async () => {
    /* 조직 마디의 `user_count` 가 곧 부서 없는 인원이다(클로비원: 1). 링크가 필터 없는
       `#/users` 로 가면 숫자만 말하고 그 사람들을 못 찾는다 — 서버 센티널 `none` 을 싣는다. */
    mockApi();
    renderConsole("/organizations");
    await node("클로비원");
    const link = await screen.findByRole("link", { name: /부서가 지정되지 않은 사용자 1명/ }, WAIT);
    expect(link.getAttribute("href")).toBe("#/users?department_id=none");
  });
});
