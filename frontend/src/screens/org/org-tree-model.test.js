import { describe, it, expect } from "vitest";
import {
  ancestorIndex, filterTree, flatten, forcedExpanded, initialExpanded, matchRange, nestRows, tabStopId, typeaheadTarget,
} from "./orgTreeModel.js";

/* 조직도 트리 모델 (O1 · D-533) — 무엇이 보이고 어디에 Tab 이 서는가.
 *
 * 못박는 것:
 *   ① 평탄한 깊이 우선 목록을 중첩으로 되접는다(조직이 뿌리, 국내영업은 영업팀 아래).
 *   ② 「사용 중만」 · 검색은 맞는 노드와 그 **조상**만 남긴다 — 서버 거르기처럼 자식을 맨 위로 올리지 않는다.
 *   ③ 검색은 이름과 식별자만 맞춘다. 경로는 질의에 「›」가 있을 때만 — 조상 이름 하나에 자손 전부가 걸리지 않는다.
 *   ④ 처음 펼침은 조직과 고른 노드의 조상이다. 검색은 맞은 노드의 조상을 강제로 편다.
 *   ⑤ Tab 정지는 고른 노드가 보이면 그것, 숨었으면 가장 가까운 보이는 조상, 그것도 없으면 첫 줄이다.
 */

const TREE = [
  { id: "org-1", kind: "organization", name: "클로비원", slug: "clovirone", depth: 0, path: "클로비원", active: true },
  { id: "dep-sales", kind: "department", name: "영업팀", slug: "sales", depth: 1, path: "클로비원 › 영업팀", active: true },
  { id: "dep-sales-kr", kind: "department", name: "국내영업", depth: 2, path: "클로비원 › 영업팀 › 국내영업", active: false },
  { id: "dep-sales-kr-1", kind: "department", name: "서울영업", depth: 3, path: "클로비원 › 영업팀 › 국내영업 › 서울영업", active: true },
  { id: "dep-dev", kind: "department", name: "개발팀", depth: 1, path: "클로비원 › 개발팀", active: true },
  { id: "org-2", kind: "organization", name: "자회사", slug: "sub", depth: 0, path: "자회사", active: true },
];
const ids = (nodes) => nodes.flatMap((n) => [n.row.id, ...ids(n.children)]);

describe("nestRows", () => {
  it("깊이로 부모와 자식을 되살린다", () => {
    const roots = nestRows(TREE);
    expect(roots.map((r) => r.row.id)).toEqual(["org-1", "org-2"]);
    expect(roots[0].children.map((c) => c.row.id)).toEqual(["dep-sales", "dep-dev"]);
    expect(roots[0].children[0].children[0].children.map((c) => c.row.id)).toEqual(["dep-sales-kr-1"]);
  });

  it("조직 행이 없는 응답도 부서만으로 접는다", () => {
    const roots = nestRows([{ id: "a", depth: 0 }, { id: "b", depth: 1 }, { id: "c", depth: 0 }]);
    expect(roots.map((r) => r.row.id)).toEqual(["a", "c"]);
    expect(roots[0].children.map((r) => r.row.id)).toEqual(["b"]);
  });
});

describe("filterTree — 조상을 남기는 거르기", () => {
  it("「사용 중만」은 미사용 부서를 빼되, 그 아래 사용 중인 부서와 계층은 남긴다", () => {
    const out = filterTree(nestRows(TREE), { activeOnly: true });
    expect(ids(out)).toEqual(["org-1", "dep-sales", "dep-sales-kr", "dep-sales-kr-1", "dep-dev", "org-2"]);
    const kr = out[0].children[0].children[0];
    // 미사용 국내영업은 자식(서울영업) 때문에 남았지만 그 자신은 조건에 맞지 않는다 — 흐리게 그린다.
    expect(kr.row.id).toBe("dep-sales-kr");
    expect(kr.hit).toBe(false);
    expect(kr.children[0].hit).toBe(true);
    // 서울영업은 맨 위로 올라가지 않는다(서버 거르기의 고아 승격이 계층을 틀었던 자리).
    expect(out.map((n) => n.row.id)).toEqual(["org-1", "org-2"]);
  });

  it("미사용 말단 부서는 사라진다", () => {
    const rows = TREE.filter((r) => r.id !== "dep-sales-kr-1");
    expect(ids(filterTree(nestRows(rows), { activeOnly: true }))).not.toContain("dep-sales-kr");
  });

  it("검색은 이름과 식별자를 맞추고, 맞은 노드의 조상을 남긴다 — 공백 · 대소문자 · 전각을 가리지 않는다", () => {
    for (const q of ["서울영업", "서울 영업", " 서울  영업 "]) {
      expect(ids(filterTree(nestRows(TREE), { query: q })), q).toEqual(["org-1", "dep-sales", "dep-sales-kr", "dep-sales-kr-1"]);
    }
    for (const q of ["SALES", "Sales", "ｓａｌｅｓ"]) {
      expect(ids(filterTree(nestRows(TREE), { query: q })), q).toEqual(["org-1", "dep-sales"]);
    }
  });

  it("검색어가 조상 이름이어도 자손 전부가 걸리지 않는다 — 경로는 「›」가 든 질의만 본다", () => {
    expect(ids(filterTree(nestRows(TREE), { query: "영업팀" }))).toEqual(["org-1", "dep-sales"]);
    expect(ids(filterTree(nestRows(TREE), { query: "영업팀 › 국내" }))).toEqual(
      ["org-1", "dep-sales", "dep-sales-kr", "dep-sales-kr-1"],
    );
  });

  it("맞는 것이 없으면 빈 트리이고, 조건이 없으면 모두 hit 이다", () => {
    expect(filterTree(nestRows(TREE), { query: "없는부서" })).toEqual([]);
    const all = filterTree(nestRows(TREE), {});
    expect(ids(all)).toEqual(TREE.map((r) => r.id));
    expect(all.every((n) => n.hit)).toBe(true);
  });
});

describe("펼침", () => {
  it("처음 펼침은 자식이 있는 조직과 고른 노드의 조상이다", () => {
    const nodes = nestRows(TREE);
    expect([...initialExpanded(nodes, null)]).toEqual(["org-1"]);
    expect([...initialExpanded(nodes, "dep-sales-kr-1")].sort()).toEqual(["dep-sales", "dep-sales-kr", "org-1"]);
  });

  it("검색이 강제로 펴는 것은 맞은 노드의 조상뿐이다", () => {
    const filtered = filterTree(nestRows(TREE), { query: "서울" });
    expect([...forcedExpanded(filtered)].sort()).toEqual(["dep-sales", "dep-sales-kr", "org-1"]);
  });

  it("flatten 은 펼친 가지만 줄로 내고, 깊이 · 형제 수 · 순번 · 부모를 단다", () => {
    const nodes = nestRows(TREE);
    const rows = flatten(nodes, new Set(["org-1"]));
    expect(rows.map((r) => r.row.id)).toEqual(["org-1", "dep-sales", "dep-dev", "org-2"]);
    const sales = rows[1];
    expect(sales).toMatchObject({ depth: 1, hasKids: true, expanded: false, parentId: "org-1", setSize: 2, posInSet: 1 });
    expect(rows[3]).toMatchObject({ depth: 0, setSize: 2, posInSet: 2, parentId: null, hasKids: false });
  });
});

describe("Tab 정지", () => {
  const nodes = nestRows(TREE);
  const anc = ancestorIndex(nodes);

  it("고른 노드가 보이면 그것이다", () => {
    const visible = flatten(nodes, new Set(["org-1", "dep-sales"]));
    expect(tabStopId(visible, "dep-sales-kr", anc)).toBe("dep-sales-kr");
  });

  it("고른 노드가 접혀 숨으면 가장 가까운 보이는 조상이다", () => {
    const visible = flatten(nodes, new Set(["org-1"]));
    expect(tabStopId(visible, "dep-sales-kr-1", anc)).toBe("dep-sales");
  });

  it("거르기로 조상까지 사라지면 첫 줄이고, 고른 것이 없어도 첫 줄이다", () => {
    const visible = flatten(filterTree(nodes, { query: "자회사" }), new Set());
    expect(tabStopId(visible, "dep-dev", anc)).toBe("org-2");
    expect(tabStopId(flatten(nodes, new Set()), null, anc)).toBe("org-1");
    expect(tabStopId([], "x", anc)).toBeNull();
  });
});

describe("검색 강조 · 글자 이동", () => {
  it("matchRange 는 이름 안에서 맞은 자리를 돌려주고, 경로 질의 · 빈 질의는 null 이다", () => {
    expect(matchRange("국내영업", "영업")).toEqual([2, 4]);
    expect(matchRange("Sales Team", "team")).toEqual([6, 10]);
    expect(matchRange("국내영업", "")).toBeNull();
    expect(matchRange("국내영업", "영업팀 › 국내")).toBeNull();
  });

  it("typeaheadTarget 은 지금 줄 다음부터 이름이 그 글자로 시작하는 줄이고, 끝에서 처음으로 돈다", () => {
    const visible = flatten(nestRows(TREE), new Set(["org-1"]));
    expect(typeaheadTarget(visible, "org-1", "개")).toBe("dep-dev");
    expect(typeaheadTarget(visible, "org-2", "클")).toBe("org-1");
    expect(typeaheadTarget(visible, "org-1", "없")).toBeNull();
  });
});
