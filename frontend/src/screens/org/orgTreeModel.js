/* 조직도 트리 모델 (O1 · D-533) — 화면 부품(`OrgTree.jsx`)이 그리기만 하게, 무엇이 보이고 어디에 Tab 이 서는지를 여기서 정한다.
 *
 * 예전 트리는 전부 펼친 채 시작했고, 검색이 접힌 부모를 펴지 않았으며, 「사용」 거르기는 서버가 걸러진 부모의 자식을 맨 위로 올려
 * 계층이 틀어졌다. 고른 노드가 접힘 · 검색 · 거르기로 숨으면 Tab 으로 트리에 들어갈 자리가 없었다. 이 모듈이 정하는 것:
 *
 *   nestRows        서버의 깊이 우선 평탄 목록 → 중첩(조직 행이 뿌리, 고리 덩어리는 깊이 0 으로 맨 뒤)
 *   filterTree      「사용 중만」 · 검색 — 맞는 노드와 **그 조상**만 남긴다(조상은 흐리게 서도 계층이 남는다)
 *   initialExpanded 처음 펼침 — 조직(깊이 0)과 고른 노드의 조상
 *   flatten         지금 보이는 줄의 평탄 목록(깊이 · 펼침 · 형제 수 · 순번) — 키보드 · 화면이 같은 목록을 쓴다
 *   tabStopId       Tab 정지 — 고른 노드가 보이면 그것, 숨었으면 가장 가까운 보이는 조상, 그것도 없으면 첫 줄
 *   matchRange      검색어가 이름의 어디에 맞았는가(굵게 그릴 자리)
 */
import { foldText } from "../../lib/search.js";

export const isOrgRow = (row) => (row && row.kind) === "organization";

/** 평탄한 행 목록(depth 순 깊이 우선)을 중첩 트리로 되접는다. 서버가 이미 깊이 우선으로 펴서 준다(`app/org/tree.py`). */
export function nestRows(rows) {
  const roots = [];
  const stack = [];
  (rows || []).forEach((row) => {
    const node = { row, children: [] };
    const depth = row.depth || 0;
    while (stack.length && stack[stack.length - 1].depth >= depth) stack.pop();
    if (stack.length) stack[stack.length - 1].node.children.push(node);
    else roots.push(node);
    stack.push({ depth, node });
  });
  return roots;
}

/* 검색 축 — 이름과 식별자. 경로는 질의에 「›」가 있을 때만 본다 — 경로로 맞추면 조상 이름 하나에 자손 전부가 걸린다. */
function matches(row, term) {
  const t = foldText(term);
  if (!t) return true;
  const hay = [row.name, row.slug];
  if (String(term).includes("›")) hay.push(row.path);
  return hay.some((v) => v && foldText(v).includes(t));
}

/**
 * 「사용 중만」 · 검색을 건 트리 — 맞는 노드와 그 조상만 남긴다.
 * 노드에 `hit`(그 노드 자신이 조건에 맞는가)을 단다 — 조건 때문에 남은 조상은 `hit=false` 라 흐리게 그린다.
 */
export function filterTree(nodes, { query = "", activeOnly = false } = {}) {
  const searching = !!foldText(query);
  if (!searching && !activeOnly) return nodes.map(function mark(n) { return { ...n, hit: true, children: n.children.map(mark) }; });
  const walk = (list) => list.reduce((out, node) => {
    const kids = walk(node.children);
    const alive = !activeOnly || node.row.active !== false;
    const hit = alive && (!searching || matches(node.row, query));
    if (hit || kids.length) out.push({ ...node, hit, children: kids });
    return out;
  }, []);
  return walk(nodes);
}

/** id → 조상 id 목록(가까운 것부터). */
export function ancestorIndex(nodes) {
  const index = new Map();
  const walk = (list, chain) => {
    for (const n of list) {
      index.set(n.row.id, chain);
      walk(n.children, [n.row.id, ...chain]);
    }
  };
  walk(nodes, []);
  return index;
}

/** 처음 펼침 — 조직(깊이 0)과 고른 노드의 조상. */
export function initialExpanded(nodes, selectedId) {
  const open = new Set();
  for (const n of nodes) if (n.children.length) open.add(n.row.id);
  if (selectedId) {
    const chain = ancestorIndex(nodes).get(selectedId) || [];
    for (const id of chain) open.add(id);
  }
  return open;
}

/** 검색이 강제로 펴는 노드 — 맞은 노드의 조상 전부. */
export function forcedExpanded(nodes) {
  const open = new Set();
  const walk = (list) => {
    let any = false;
    for (const n of list) {
      const below = walk(n.children);
      if (below) open.add(n.row.id);
      if (n.hit || below) any = true;
    }
    return list.some((n) => n.hit) || any;
  };
  walk(nodes);
  return open;
}

/**
 * 지금 보이는 줄의 평탄 목록. `expanded` 는 펼친 노드 id 집합이다.
 * 줄마다 `{ row, depth, hasKids, expanded, hit, parentId, setSize, posInSet }` — 형제 수 · 순번은 평탄하게 그린 트리가
 * 보조 기술에 계층을 알리는 값이다(`aria-setsize` · `aria-posinset`).
 */
export function flatten(nodes, expanded) {
  const out = [];
  const walk = (list, depth, parentId) => {
    list.forEach((n, i) => {
      const hasKids = n.children.length > 0;
      const open = hasKids && expanded.has(n.row.id);
      out.push({
        row: n.row, depth, hasKids, expanded: open, hit: n.hit !== false, parentId,
        setSize: list.length, posInSet: i + 1,
      });
      if (open) walk(n.children, depth + 1, n.row.id);
    });
  };
  walk(nodes, 0, null);
  return out;
}

/** Tab 정지 — 고른 노드가 보이면 그것, 숨었으면 가장 가까운 보이는 조상, 그것도 없으면 첫 줄. */
export function tabStopId(visible, selectedId, ancestors) {
  if (!visible.length) return null;
  const shown = new Set(visible.map((v) => v.row.id));
  if (selectedId && shown.has(selectedId)) return selectedId;
  const chain = (selectedId && ancestors && ancestors.get(selectedId)) || [];
  for (const id of chain) if (shown.has(id)) return id;
  return visible[0].row.id;
}

/** 검색어가 이름의 어디에 맞았는가 — `[시작, 끝)` 또는 null. 접기(대소문자 · 전각)는 길이를 바꾸지 않는 범위에서만 맞춘다. */
export function matchRange(name, query) {
  const q = String(query || "").trim();
  if (!q || q.includes("›")) return null;
  const at = String(name || "").toLowerCase().indexOf(q.toLowerCase());
  return at < 0 ? null : [at, at + q.length];
}

/** 글자 입력 이동 — 지금 줄 다음부터 이름이 `prefix` 로 시작하는 첫 보이는 줄(끝까지 가면 처음부터). */
export function typeaheadTarget(visible, currentId, prefix) {
  const p = foldText(prefix);
  if (!p || !visible.length) return null;
  const start = Math.max(0, visible.findIndex((v) => v.row.id === currentId));
  for (let k = 1; k <= visible.length; k += 1) {
    const v = visible[(start + k) % visible.length];
    if (foldText(v.row.name).startsWith(p)) return v.row.id;
  }
  return null;
}
