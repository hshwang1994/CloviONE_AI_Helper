import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import BusinessRoundedIcon from "@mui/icons-material/BusinessRounded";
import GroupsRoundedIcon from "@mui/icons-material/GroupsRounded";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import { ListEmptyState, Skeleton, ErrorState } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, ICON, NAV_ANATOMY, NUMERIC, remPx } from "../ui/theme.js";
import {
  ancestorIndex, filterTree, flatten, forcedExpanded, initialExpanded, isOrgRow, matchRange, nestRows, tabStopId,
  typeaheadTarget,
} from "./org/orgTreeModel.js";

export { isOrgRow, nestRows } from "./org/orgTreeModel.js";

/* 조직도 트리 — 조직 관리 작업 공간의 왼쪽 판 몸 (O1 · D-533).
 *
 * IDE 파일 트리처럼 만들지 않는다: 연결선이 없고, 조직과 부서는 아이콘(건물 · 사람 묶음)과 글자 굵기로만 조용히 가른다. 줄은 높이
 * 36, 깊이마다 16 들여쓴다. 펼침 칸(20)은 마우스 전용이다(Tab 이 멈추지 않는다 — 키보드는 → · ← 로 편다). 오른쪽 끝의 수는 가지
 * 전체에서 지금 일하는 사람이다(`subtree_user_count`). 미사용은 이름을 옅게 하고 점 + 「미사용」, 상위 관계 오류는 위험 점이다 —
 * 줄 안에 배지를 쓰지 않는다. 선택은 옅은 보라 면 + 왼쪽 선택 레일(사이드바와 같은 굵기), 초점은 안쪽 2px 고리다.
 *
 * 무엇이 보이고 어디에 Tab 이 서는지는 `org/orgTreeModel.js` 가 정한다. 「사용 중만」은 화면에서 거르고 조상을 남긴다 — 서버
 * 거르기는 걸러진 부모의 자식을 맨 위로 올려 계층이 틀어졌다. 검색은 맞은 노드의 조상을 강제로 펴고, 검색을 지우면 검색 전
 * 펼침으로 돌아간다. 줄은 평탄하게 그린다(`aria-level` · `aria-setsize` · `aria-posinset` 이 계층을 알린다) — 키보드 이동과 화면이
 * 같은 목록을 쓴다.
 */

const ROW_H = remPx(36);
const INDENT = 1; // 깊이마다 16px(spacing 2 = 16px 의 절반 단위 — 아래 pl 계산)
const TOGGLE = remPx(20);

function NameText({ name, query }) {
  const range = matchRange(name, query);
  if (!range) return name;
  return (
    <>
      {name.slice(0, range[0])}
      <Box component="mark" sx={{ bgcolor: "transparent", color: "inherit", fontWeight: FONT_WEIGHT.extrabold }}>
        {name.slice(range[0], range[1])}
      </Box>
      {name.slice(range[1])}
    </>
  );
}

function StateDot({ tone, label, id }) {
  return (
    <Box component="span" id={id} sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, flexShrink: 0, color: "text.secondary", fontSize: FONT_SIZE.caption }}>
      <Box component="span" aria-hidden="true" sx={{ width: "0.375rem", height: "0.375rem", borderRadius: "50%", bgcolor: tone }} />
      {label}
    </Box>
  );
}

export function OrgTree({ rows = [], loading, error, onRetry, selectedId, onSelect, query = "", activeOnly = false, onClearSearch, collapseSignal }) {
  const nodes = React.useMemo(() => nestRows(rows), [rows]);
  const filtered = React.useMemo(() => filterTree(nodes, { query, activeOnly }), [nodes, query, activeOnly]);
  const ancestors = React.useMemo(() => ancestorIndex(nodes), [nodes]);

  /* 펼침 — 사용자가 연 것(`expanded`)과 검색이 강제로 연 것을 따로 든다. 검색을 지우면 사용자가 연 것만 남는다. */
  const [expanded, setExpanded] = React.useState(() => initialExpanded(nodes, selectedId));
  const seeded = React.useRef(nodes.length > 0);
  React.useEffect(() => {
    if (!seeded.current && nodes.length) {
      seeded.current = true;
      setExpanded(initialExpanded(nodes, selectedId));
    }
  }, [nodes, selectedId]);
  /* 고른 노드가 바뀌면 그 조상을 편다 — 주소로 들어온 부서가 접힌 가지 안에 있어도 보인다. */
  React.useEffect(() => {
    if (!selectedId) return;
    const chain = ancestors.get(selectedId) || [];
    if (!chain.length) return;
    setExpanded((s) => (chain.every((id) => s.has(id)) ? s : new Set([...s, ...chain])));
  }, [selectedId, ancestors]);
  /* 「모두 접기 · 펼치기」와 「트리에서 보기」 — 화면이 신호를 준다(`{ kind: "collapse" | "expand" | "reveal", id?, at }`).
     reveal 은 그 노드와 조상을 펴서 하위 부서를 보인다(삭제 창의 「하위 부서 N개 · 트리에서 보기」). */
  React.useEffect(() => {
    if (!collapseSignal) return;
    if (collapseSignal.kind === "collapse") setExpanded(new Set());
    else if (collapseSignal.kind === "reveal") {
      const chain = ancestors.get(collapseSignal.id) || [];
      setExpanded((s) => new Set([...s, collapseSignal.id, ...chain]));
    } else {
      const all = new Set();
      const walk = (list) => list.forEach((n) => { if (n.children.length) { all.add(n.row.id); walk(n.children); } });
      walk(nodes);
      setExpanded(all);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collapseSignal]);

  const searching = !!String(query || "").trim();
  const shownOpen = React.useMemo(
    () => (searching ? new Set([...expanded, ...forcedExpanded(filtered)]) : expanded),
    [searching, expanded, filtered],
  );
  const visible = React.useMemo(() => flatten(filtered, shownOpen), [filtered, shownOpen]);
  const stop = tabStopId(visible, selectedId, ancestors);

  const listRef = React.useRef(null);
  const typed = React.useRef({ text: "", at: 0 });
  const focusRow = (id) => {
    const el = listRef.current && listRef.current.querySelector(`[data-tree-id="${id}"]`);
    if (el) el.focus();
  };
  const toggle = (id) => setExpanded((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const onKeyDown = (e, item, index) => {
    const id = item.row.id;
    const move = (to) => { e.preventDefault(); const v = visible[to]; if (v) focusRow(v.row.id); };
    switch (e.key) {
      case "ArrowDown": return move(index + 1);
      case "ArrowUp": return move(index - 1);
      case "Home": return move(0);
      case "End": return move(visible.length - 1);
      case "ArrowRight":
        e.preventDefault();
        if (item.hasKids && !item.expanded) toggle(id);
        else if (item.hasKids) move(index + 1);
        return undefined;
      case "ArrowLeft":
        e.preventDefault();
        if (item.hasKids && item.expanded) toggle(id);
        else if (item.parentId) focusRow(item.parentId);
        return undefined;
      case "Enter":
      case " ":
        e.preventDefault();
        if (onSelect) onSelect(item.row);
        return undefined;
      default:
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
          const now = Date.now();
          typed.current = { text: (now - typed.current.at < 600 ? typed.current.text : "") + e.key, at: now };
          const target = typeaheadTarget(visible, id, typed.current.text);
          if (target) { e.preventDefault(); focusRow(target); }
        }
        return undefined;
    }
  };

  if (loading) return <Box sx={{ p: 1 }}><Skeleton lines={6} /></Box>;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!visible.length) {
    return (
      <ListEmptyState
        filtered={searching || activeOnly}
        onClear={onClearSearch}
        filteredTitle="조건에 맞는 조직이나 부서가 없습니다."
        filteredHelp="이름이나 식별자의 일부로 다시 찾아보세요."
        title="아직 부서가 없습니다."
        help="조직을 고른 뒤 「부서 추가」로 부서를 만들면 여기에 계층으로 나타납니다."
      />
    );
  }

  return (
    <Box component="ul" role="tree" aria-label="조직도" ref={listRef} data-org-tree="" sx={{ listStyle: "none", m: 0, p: 0.5 }}>
      {visible.map((item, index) => {
        const row = item.row;
        const isOrg = isOrgRow(row);
        const selected = selectedId === row.id;
        const inactive = row.active === false;
        const count = row.subtree_user_count != null ? row.subtree_user_count : (row.user_count || 0);
        const Icon = isOrg ? BusinessRoundedIcon : GroupsRoundedIcon;
        const stateId = `org-tree-state-${row.id}`;
        const countId = `org-tree-count-${row.id}`;
        return (
          <Box
            component="li"
            key={row.id}
            role="treeitem"
            data-tree-id={row.id}
            aria-level={item.depth + 1}
            aria-setsize={item.setSize}
            aria-posinset={item.posInSet}
            aria-selected={selected}
            aria-expanded={item.hasKids ? item.expanded : undefined}
            aria-label={row.name}
            /* 수는 이름이 아니라 설명이다 — 스크린리더는 「영업팀」 다음에 「구성원 6명」으로 읽는다. */
            aria-describedby={inactive || row.cycle ? `${countId} ${stateId}` : countId}
            tabIndex={stop === row.id ? 0 : -1}
            onClick={() => onSelect && onSelect(row)}
            onKeyDown={(e) => onKeyDown(e, item, index)}
            data-brand-role={selected ? "selected-state" : undefined}
            sx={(t) => ({
              position: "relative",
              display: "flex", alignItems: "center", gap: 0.75,
              height: ROW_H, pr: 1, pl: `calc(${INDENT * item.depth}rem + 0.25rem)`,
              borderRadius: 1, cursor: "pointer", minWidth: 0,
              color: item.hit ? "text.primary" : "text.secondary",
              bgcolor: selected ? "primary.soft" : "transparent",
              "&:hover": { bgcolor: selected ? "primary.soft" : "background.inset" },
              "&:focus-visible": { outline: `2px solid var(--clovir-focus-ring, ${t.palette.focusRing})`, outlineOffset: -2 },
              /* 선택 레일 — 사이드바의 활성 표지와 같은 굵기, 줄 왼쪽 가장자리. */
              "&::before": selected ? {
                content: '""', position: "absolute", insetInlineStart: 0, top: "0.375rem", bottom: "0.375rem",
                width: remPx(NAV_ANATOMY.rail), borderRadius: 1, bgcolor: "primary.main",
              } : undefined,
            })}
          >
            <Box
              component="span"
              aria-hidden="true"
              /* 마우스 전용 펼침 칸 — Tab 이 멈추지 않는다(키보드는 → · ←). 줄 클릭(선택)으로 번지지 않는다. */
              onClick={item.hasKids ? (e) => { e.stopPropagation(); toggle(row.id); } : undefined}
              sx={{ width: TOGGLE, height: TOGGLE, flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "text.secondary", borderRadius: 1, "&:hover": item.hasKids ? { bgcolor: "action.hover" } : undefined }}
            >
              {item.hasKids ? (item.expanded ? <ExpandMoreRoundedIcon sx={{ fontSize: remPx(ICON.mark) }} /> : <ChevronRightRoundedIcon sx={{ fontSize: remPx(ICON.mark) }} />) : null}
            </Box>
            <Icon aria-hidden="true" sx={{ fontSize: remPx(ICON.mark), flexShrink: 0, color: inactive ? "text.disabled" : "text.secondary" }} />
            <Typography
              component="span"
              title={row.name}
              sx={{
                flex: "1 1 auto", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                fontSize: FONT_SIZE.body, fontWeight: isOrg ? FONT_WEIGHT.bold : FONT_WEIGHT.medium,
                color: inactive ? "text.secondary" : "inherit",
              }}
            >
              <NameText name={row.name} query={query} />
            </Typography>
            {row.cycle ? <StateDot id={stateId} tone="error.main" label="상위 관계 오류" />
              : inactive ? <StateDot id={stateId} tone="text.disabled" label="미사용" /> : null}
            <Typography component="span" id={countId} sx={{ ...NUMERIC, flexShrink: 0, fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
              <span className="sr-only">구성원 </span>{count}명
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}

export default OrgTree;
