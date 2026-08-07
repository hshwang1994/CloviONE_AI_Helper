import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 조직 콘솔 — 조직 관리, 부서 관리, 조직도를 한 화면으로 묶은 뒤에도 **아무것도 잃지
 * 않았는가**.
 *
 * 사용자 지적: "조직관리랑 부서관리랑 조직도 페이지는 하나로 묶을 수 있는거아님?
 * 조직도가 왼쪽 트리로 보이고 오른쪽에서 조직이랑 부서 관리할 수 있도록 하면 되는거아님?
 * 조직도 트리는 1/3 관리는 2/3 크기로."
 *
 * 그래서 이 파일이 지키는 것은 네 가지다.
 *   1) 트리에서 고른 **종류**(조직/부서)에 따라 오른쪽 관리 화면이 실제로 바뀐다.
 *   2) 고른 항목이 눈에 보이게 강조된다(aria-selected).
 *   3) 합치면서 **기존 기능이 사라지지 않는다** — 조직의 상태 필터, 부서의 생성 폼과
 *      상위 부서 선택, 조직도의 사용 여부 필터와 이름 검색.
 *   4) 1/3, 2/3 비율이 말뿐이 아니라 실제 스타일로 적용된다.
 *
 * 트리가 '들여쓴 목록'이 아니라 진짜 트리인지도 여기서 못박는다(중첩 group + aria-level).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import AdminRoutes from "../app/AdminRoutes.jsx";
import { OrgConsole } from "./OrgConsole.jsx";
import { nestRows } from "./OrgTree.jsx";
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

function mockApi() {
  apiMock.mockImplementation((url) => {
    const u = String(url);
    // /tree 를 먼저 본다 — /api/admin/departments 가 접두어라 순서가 뒤집히면 트리가 목록을 받는다.
    if (u.startsWith("/api/admin/departments/tree")) return Promise.resolve({ items: TREE });
    if (u.startsWith("/api/admin/organizations")) return Promise.resolve({ items: ORGS });
    if (u.startsWith("/api/admin/departments")) return Promise.resolve({ items: DEPTS });
    return Promise.resolve({ items: [] });
  });
}

function renderConsole(props) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <OrgConsole {...props} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/* MUI 화면 하나를 jsdom 에서 그리는 데 1초 가까이 걸린다(admin-uiux.test.jsx 와 같은 이유). */
const WAIT = { timeout: 8000 };
/* 기본 테스트 제한(5초)이 위 대기 상한보다 짧으면, 실패가 항상 "Test timed out" 으로 뭉개져
 * **무엇이 어긋났는지**가 보고서에 안 남는다(고장을 심어 확인할 때 특히 곤란하다). */
vi.setConfig({ testTimeout: 20000 });
const tree = () => screen.getByTestId("org-console-tree");
const panel = () => screen.getByTestId("org-console-panel");
const panelTitle = () => within(panel()).getByRole("heading", { level: 1 }).textContent;
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

/* ── 2. 왼쪽 트리에서 고르면 오른쪽 관리 화면이 바뀐다 ──────────────────── */

describe("트리 선택 → 오른쪽 관리 패널", () => {
  it("첫 진입에는 조직 관리를 보여준다(트리의 뿌리가 조직이라 위에서 아래로 읽힌다)", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    await waitFor(() => expect(panelTitle()).toBe("조직 관리"), WAIT);
    // 조직 목록이 실제로 그려진다(제목만 바뀐 게 아니다).
    expect(await within(panel()).findByText("묵은회사", {}, WAIT)).toBeInTheDocument();
  });

  it("부서 노드를 누르면 부서 관리로, 다시 조직 노드를 누르면 조직 관리로 돌아온다", async () => {
    mockApi();
    renderConsole();
    await userEvent.click(await node("영업팀"));
    await waitFor(() => expect(panelTitle()).toBe("부서 관리"), WAIT);
    // 부서 목록 고유의 열('조직')이 실제로 그려진다.
    expect(await within(panel()).findByText("소속 인원(보관 포함)", {}, WAIT)).toBeInTheDocument();

    await userEvent.click(await node("클로비원"));
    await waitFor(() => expect(panelTitle()).toBe("조직 관리"), WAIT);
    expect(await within(panel()).findByText("식별자", {}, WAIT)).toBeInTheDocument();
  });

  it("고른 항목만 강조된다(aria-selected)", async () => {
    mockApi();
    renderConsole();
    await userEvent.click(await node("국내영업"));
    await waitFor(() => expect(panelTitle()).toBe("부서 관리"), WAIT);
    expect(await node("국내영업")).toHaveAttribute("aria-selected", "true");
    expect(await node("영업팀")).toHaveAttribute("aria-selected", "false");
    expect(await node("클로비원")).toHaveAttribute("aria-selected", "false");
  });

  it("딥링크로 들어온 종류가 미리 골라진 채 열린다(/departments)", async () => {
    mockApi();
    renderConsole({ defaultKind: "departments" });
    await node("클로비원");
    await waitFor(() => expect(panelTitle()).toBe("부서 관리"), WAIT);
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

  /* 사용자 지적은 "조직도가 이쁘지도않음" 이었고, 원인은 계층이 **왼쪽 여백과 '└ ' 글자**로만
   * 표현된 표였다는 것이다(registry/org.js 의 org-tree columns). 연결선은 소스에 적혀 있는
   * 것으로는 부족하다 — 실제 스타일로 나오는지 본다. */
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
  it("조직의 상태 필터가 그대로 동작한다(정지만 남는다)", async () => {
    mockApi();
    renderConsole();
    expect(await within(panel()).findByText("묵은회사", {}, WAIT)).toBeInTheDocument();
    await userEvent.click(within(panel()).getByRole("combobox", { name: /상태/ }));
    await userEvent.click(await screen.findByRole("option", { name: "정지" }, WAIT));
    await waitFor(() => expect(within(panel()).queryByText("클로비원")).toBeNull(), WAIT);
    expect(within(panel()).getByText("묵은회사")).toBeInTheDocument();
  });

  it("부서의 생성 폼이 그대로 있다(상위 부서 선택 포함)", async () => {
    mockApi();
    renderConsole({ defaultKind: "departments" });
    await waitFor(() => expect(panelTitle()).toBe("부서 관리"), WAIT);
    await userEvent.click(within(panel()).getByRole("button", { name: "+ 부서 추가" }));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    expect(within(dlg).getByLabelText(/부서 이름/)).toBeInTheDocument();
    expect(within(dlg).getByLabelText(/상위 부서/)).toBeInTheDocument();
  });

  it("조직도의 '사용' 필터는 그대로 서버로 간다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    await userEvent.click(within(tree()).getByRole("combobox", { name: /사용/ }));
    await userEvent.click(await screen.findByRole("option", { name: "미사용" }, WAIT));
    await waitFor(() => expect(apiMock.mock.calls.some(([p]) =>
      String(p).startsWith("/api/admin/departments/tree") && String(p).includes("active=false"))).toBe(true), WAIT);
  });

  it("오른쪽에서 부서를 추가하면 왼쪽 트리도 다시 읽는다", async () => {
    mockApi();
    renderConsole({ defaultKind: "departments" });
    await waitFor(() => expect(panelTitle()).toBe("부서 관리"), WAIT);
    const treeCalls = () => apiMock.mock.calls.filter(([p]) =>
      String(p).startsWith("/api/admin/departments/tree")).length;
    const before = treeCalls();

    await userEvent.click(within(panel()).getByRole("button", { name: "+ 부서 추가" }));
    const dlg = await screen.findByRole("dialog", {}, WAIT);
    await userEvent.type(within(dlg).getByLabelText(/부서 이름/), "품질팀");
    await userEvent.click(within(dlg).getByRole("button", { name: "만들기" }));

    // 트리와 목록은 캐시 주소가 다르다 — 목록만 갱신하면 방금 만든 부서가 왼쪽에 안 나타나고,
    // 사용자는 "추가했는데 조직도에 없다"로 읽는다(한 화면에 둘을 나란히 놓아 더 잘 보인다).
    await waitFor(() => expect(treeCalls()).toBeGreaterThan(before), { timeout: 3000 });
  });

  it("조직도의 이름 검색이 그대로 있다(맞지 않는 가지는 사라진다)", async () => {
    mockApi();
    renderConsole();
    await node("개발팀");
    await userEvent.type(within(tree()).getByRole("searchbox"), "개발");
    await waitFor(() => expect(screen.queryByRole("treeitem", { name: "영업팀" })).toBeNull(), WAIT);
    // 맞는 노드와 그 조상은 남는다 — 조상을 지우면 어디 소속인지 알 수 없게 된다.
    expect(await node("개발팀")).toBeInTheDocument();
    expect(await node("클로비원")).toBeInTheDocument();
  });
});

/* ── 5. 세 주소가 모두 살아 있는가 ──────────────────────────────────────── */

describe("라우팅", () => {
  function renderRoute(path) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <MemoryRouter initialEntries={[path]}>
                <AdminRoutes />
              </MemoryRouter>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>,
    );
  }

  /* 세 주소를 모두 남긴다. 하나라도 없애면 즐겨찾기와 다른 화면의 딥링크(registry/org.js 의
   * '조직도에서 보기', '부서 관리에서 열기')가 대시보드로 튕긴다. 대신 들어온 주소에 맞는
   * 관리 화면이 미리 골라진 채 열린다. */
  it.each([
    ["/org-tree", "조직 관리"],
    ["/organizations", "조직 관리"],
    ["/departments", "부서 관리"],
  ])("%s 는 콘솔을 열고 오른쪽을 '%s'로 맞춘다", async (path, title) => {
    mockApi();
    const { unmount } = renderRoute(path);
    expect(await screen.findByTestId("org-console-tree", {}, WAIT)).toBeInTheDocument();
    await waitFor(() => expect(panelTitle()).toBe(title), WAIT);
    unmount();
  });
});

/* ── 6. 1/3, 2/3 비율 ───────────────────────────────────────────────────── */

describe("가로 비율", () => {
  it("왼쪽 1, 오른쪽 2 로 늘어나고 기준 폭도 1:2 다", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    const l = window.getComputedStyle(tree());
    const r = window.getComputedStyle(panel());
    expect(l.flexGrow).toBe("1");
    expect(r.flexGrow).toBe("2");
    // flex-grow 만 1:2 로 두면 기준 폭(flex-basis)이 남아 실제 비율이 1:2 가 아니게 된다.
    // 기준 폭까지 1:2 여야 어느 화면 폭에서도 정확히 1/3, 2/3 이 된다.
    const rem = (v) => parseFloat(String(v).replace("rem", ""));
    expect(rem(r.flexBasis)).toBe(rem(l.flexBasis) * 2);
    expect(rem(l.flexBasis)).toBeGreaterThan(0);
  });

  it("좁은 화면에서는 위아래로 쌓인다(가로 3분할을 강요하지 않는다)", async () => {
    mockApi();
    renderConsole();
    await node("클로비원");
    // 두 칸의 기준 폭 합이 컨테이너보다 넓어지면 줄바꿈으로 쌓인다 — 미디어 쿼리가 아니라
    // 실제로 남은 폭을 보고 접는 방식이라 좁은 컨테이너(사이드바가 넓은 경우)도 함께 산다.
    const box = window.getComputedStyle(tree().parentElement);
    expect(box.display).toBe("flex");
    expect(box.flexWrap).toBe("wrap");
  });
});
