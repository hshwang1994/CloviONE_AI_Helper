import React, { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import { Badge, Card, ErrorState, FlatBadgeSurface, ListEmptyState, Skeleton } from "../ui/kit.jsx";
import { useOrgTreeQuery } from "./org/orgQueries.js";
import { foldText, includesFolded } from "../lib/search.js";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";

/* 조직도 트리 — 조직 콘솔(OrgConsole.jsx)의 왼쪽 1/3.
 *
 * ## 왜 표가 아니라 트리인가
 *
 * 사용자 지적: "조직도가 이쁘지도않음." 코드를 보면 그럴 만했다 — 조직도는 `DataScreen` 의
 * 표 한 장이었고, 계층은 이름 칸의 **왼쪽 여백과 '└ ' 글자**로만 표현됐다(registry/org.js
 * 의 org-tree columns). 들여쓴 목록은 트리처럼 보일 뿐 트리가 아니다: 어느 줄이 어느 줄의
 * 자식인지 눈으로 이어 주는 선이 없고, 접을 수도 없고, 스크린리더에는 그냥 표의 한 칸이다.
 *
 * 여기서는 실제 트리로 그린다. 중첩 `role="group"` + `aria-level` 로 계층을 알리고,
 * 세로 줄기와 가로 갈래(아래 CONNECTORS)로 눈에도 이어 준다.
 *
 * ## 상태는 위에서 온다
 *
 * 검색어와 사용 여부는 화면 상단 탐색 줄(OrgConsole)이 들고, 이 판은 prop 으로 받아
 * 그리기만 한다. 질의는 `org/orgQueries.js` 한 벌이다 — 옛 registry 조각(org-tree)은
 * 걷혔고, 그 설정이 들던 사실 중 이 판이 쓰는 것(검색 축·빈 상태 문구)은 여기가 정본이다.
 */

/* 검색이 보는 축 — 이름과 경로에 더해 **식별자(slug)** 까지다. 옛 registry 설정이 이 축을
 * 들고 있었고(S18: 오른쪽 판의 검색 상자를 내리면서 식별자 축을 트리 검색이 이어받았다),
 * registry 조각을 걷어낸 지금은 이 파일이 그 사실의 정본이다. */
const SEARCH_FIELDS = ["name", "path", "slug"];
// 트리는 조직 행과 부서 행을 섞어 받는다. 조직 행이 없는 응답(초기화 전)에는 kind 자체가
// 없으므로(app/org/tree.py 의 이른 반환), 없으면 부서로 읽는다.
export const isOrgRow = (row) => (row && row.kind) === "organization";

/**
 * 평탄한 행 목록(depth 순 깊이 우선)을 중첩 트리로 되접는다.
 *
 * 백엔드가 트리를 이미 깊이 우선으로 펴서 준다(app/org/tree.py). 그 순서 자체가 부모, 자식
 * 관계를 담고 있으므로 parent_id 로 다시 색인할 필요가 없다 — 조직 행에는 parent_id 라는
 * 개념이 아예 없고(자기가 뿌리다), 사이클 덩어리는 depth 0 으로 맨 뒤에 붙어 온다.
 * depth 만 보면 두 경우가 모두 자연스럽게 뿌리로 떨어진다.
 */
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

/** 검색어에 맞는 노드와 **그 조상**만 남긴다. 조상을 지우면 어디 소속인지 알 수 없게 된다.
 *
 * 대조는 검색 접기다(`lib/search.js`) — 「플랫폼 개발팀」과 「플랫폼개발팀」, 「ClovirONE」과 「clovirone」이 같은
 * 노드를 찾는다. 축(이름 · 경로 · 식별자)은 칸마다 따로 본다. */
export function pruneTree(nodes, term) {
  if (!foldText(term)) return nodes;
  const fields = SEARCH_FIELDS;
  const walk = (list) => list.reduce((out, node) => {
    const kids = walk(node.children);
    const hay = fields.map((k) => node.row[k]);
    if (includesFolded(hay, term) || kids.length) out.push({ ...node, children: kids });
    return out;
  }, []);
  return walk(nodes);
}

/* 연결선 — 트리를 '왼쪽 여백만 준 목록'과 가르는 것이 이 두 선이다.
 * ::before 는 형제들을 잇는 세로 줄기, ::after 는 그 줄기에서 이 노드로 뻗는 가로 갈래다.
 * 마지막 형제는 줄기를 갈래 높이까지만 그린다 — 안 그리면 마지막 노드 아래로 선이 흘러내려
 * 아직 뭔가 더 있는 것처럼 보인다. 길이는 전부 rem 이라 4K 루트 폰트 레버를 그대로 따라간다. */
const ELBOW_TOP = "1.15rem";
const CONNECTORS = {
  position: "relative",
  paddingInlineStart: "1.1rem",
  "&::before": {
    content: '""', position: "absolute", insetInlineStart: 0, top: 0, bottom: 0,
    width: "1px", bgcolor: "divider",
  },
  "&:last-of-type::before": { bottom: "auto", height: ELBOW_TOP },
  "&::after": {
    content: '""', position: "absolute", insetInlineStart: 0, top: ELBOW_TOP,
    width: "0.7rem", height: "1px", bgcolor: "divider",
  },
};

/* 노드 한 줄의 요약. 조직과 부서는 **세는 규칙이 다르다**(app/org/tree.py):
 * 조직의 user_count 는 '부서가 지정되지 않은 사람'이고 부서의 user_count 는 '직접 소속'이다.
 * 같은 라벨로 적으면 두 숫자가 같은 뜻으로 읽혀 오해가 된다. */
function summaryOf(row, isOrg) {
  const bits = [];
  if (isOrg) {
    bits.push("구성원 " + (row.subtree_user_count || 0) + "명");
    if (row.child_count) bits.push("부서 " + row.child_count + "개");
    // 0 이 아니면 그 자체가 관리자가 알아야 할 사실이다(어디에도 안 속한 계정).
    if (row.user_count) bits.push("부서 미지정 " + row.user_count + "명");
  } else {
    bits.push("소속 " + (row.user_count || 0) + "명");
    if (row.child_count) bits.push("하위 부서 " + row.child_count + "개");
    if (row.subtree_user_count != null && row.subtree_user_count !== row.user_count) {
      bits.push("하위 포함 " + row.subtree_user_count + "명");
    }
  }
  return bits.join(", ");
}

function TreeNode({ node, level, selectedId, onSelect, collapsed, onToggle, tabbableId }) {
  const row = node.row;
  const isOrg = isOrgRow(row);
  const hasKids = node.children.length > 0;
  const open = hasKids && !collapsed[row.id];
  const selected = selectedId === row.id;
  return (
    <Box
      component="li"
      role="treeitem"
      /* 이름을 명시한다 — 이름을 내용에서 뽑게 두면 자식 노드의 이름과 인원수까지 딸려 들어와
         "영업팀 소속 4명 국내영업 소속 2명"이 이 노드의 이름이 된다(중첩 트리의 함정). */
      aria-label={row.name}
      aria-level={level}
      aria-selected={selected}
      aria-expanded={hasKids ? open : undefined}
      /* Roving tabindex(WAI-ARIA APG treeview) — 노드마다 tabIndex=0을 주면 Tab이 트리
         전체를 한 칸씩 통과해야 해서(그것도 접기 버튼까지 있으면 둘씩) 화살표 키가
         있으나 마나가 된다. 트리 전체에서 딱 하나(선택된 노드, 없으면 첫 루트)만
         Tab 정지점이고 나머지는 -1 — 화살표 키 이동은 DOM에 직접 focus()하므로
         tabIndex=-1이어도 그대로 동작한다. */
      tabIndex={tabbableId === row.id ? 0 : -1}
      onClick={(e) => { e.stopPropagation(); onSelect(row); }}
      onKeyDown={(e) => {
        // ARIA 트리의 표준 조작 — 오른쪽/왼쪽으로 펴고 접는다. 그래서 아래 꺾쇠는 순수한
        // 장식(aria-hidden)이 아니라 마우스용 보조 버튼으로만 남는다.
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); onSelect(row); }
        else if (e.key === "ArrowRight" && hasKids && !open) { e.stopPropagation(); onToggle(row.id); }
        else if (e.key === "ArrowLeft" && hasKids && open) { e.stopPropagation(); onToggle(row.id); }
        else if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Home" || e.key === "End") {
          // 위/아래/Home/End로 "보이는" treeitem 사이를 옮긴다(WAI-ARIA treeview 패턴) — 접힌
          // 자식은 DOM에 아예 없으므로(위 open ? ... : null) querySelectorAll이 자동으로
          // 걸러 준다. 재귀 컴포넌트라 "다음 형제"가 부모가 다른 노드의 첫 자식일 수도 있어
          // prop으로 형제 목록을 끌고 다니는 것보다 DOM에서 직접 찾는 쪽이 더 단순하다.
          e.preventDefault(); e.stopPropagation();
          const root = e.currentTarget.closest('[role="tree"]');
          if (!root) return;
          const items = Array.from(root.querySelectorAll('[role="treeitem"]'));
          const idx = items.indexOf(e.currentTarget);
          if (idx < 0) return;
          const next = e.key === "ArrowDown" ? items[idx + 1]
            : e.key === "ArrowUp" ? items[idx - 1]
            : e.key === "Home" ? items[0]
            : items[items.length - 1];
          if (next) next.focus();
        }
      }}
      sx={{
        listStyle: "none",
        ...(level > 1 ? CONNECTORS : { position: "relative" }),
        "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2, borderRadius: 1 }),
      }}
    >
      <Box
        /* 선택을 나르는 것은 이 상자다(브랜드 테두리 + 워시) — `aria-selected` 는 바깥
           li(treeitem)에 있어서, 선언이 없으면 브랜드 검사가 잉크 없는 li 를 집는다
           (`scripts/ui_qa/brand.py` 의 selected_state 첫 선택자가 이 선언이다). */
        data-brand-role={selected ? "selected-state" : undefined}
        sx={{
          display: "flex", alignItems: "flex-start", gap: 0.5, cursor: "pointer",
          px: 1, py: 0.75, borderRadius: 1.5, minWidth: 0,
          border: 1,
          borderColor: selected ? "primary.main" : "transparent",
          /* 선택은 **브랜드 워시**다(`background.brandTint` — 잉크 대비 AA 실측 토큰).
             회색(action.selected)이면 이 화면의 selected_state 역할이 브랜드를 안 입는다 —
             콘솔이 첫 조직을 자동 선택하면서 이 상태가 첫 화면부터 보이게 됐다. */
          bgcolor: selected ? "background.brandTint" : "transparent",
          "&:hover": { bgcolor: selected ? "background.brandTint" : "action.hover" },
        }}
      >
        {hasKids ? (
          <IconButton
            size="small" edge={false}
            aria-label={(open ? "접기: " : "펼치기: ") + row.name}
            onClick={(e) => { e.stopPropagation(); onToggle(row.id); }}
            sx={{ p: 0.25, mt: "-0.125rem" }}
          >
            {open ? <ExpandMoreRoundedIcon fontSize="small" /> : <ChevronRightRoundedIcon fontSize="small" />}
          </IconButton>
        ) : (
          // 꺾쇠가 없는 줄도 같은 자리에서 이름이 시작해야 세로로 줄이 맞는다.
          <Box aria-hidden="true" sx={{ width: "1.5rem", flexShrink: 0 }} />
        )}
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
            <Typography
              component="span"
              sx={{ fontWeight: isOrg ? FONT_WEIGHT.extrabold : FONT_WEIGHT.semibold, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}
            >
              {row.name}
            </Typography>
            {isOrg ? <Badge value="조직" kind="info" /> : null}
            {row.active === false ? <Badge value="미사용" kind="warn" /> : null}
            {row.cycle ? <Badge value="상위 관계 오류" kind="danger" /> : null}
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            {summaryOf(row, isOrg)}
          </Typography>
        </Box>
      </Box>
      {open ? (
        <Box component="ul" role="group" sx={{ listStyle: "none", m: 0, p: 0, pl: "0.55rem" }}>
          {node.children.map((kid) => (
            <TreeNode
              key={kid.row.id}
              node={kid}
              level={level + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              collapsed={collapsed}
              onToggle={onToggle}
              tabbableId={tabbableId}
            />
          ))}
        </Box>
      ) : null}
    </Box>
  );
}

export function OrgTree({ selectedId, onSelect, search = "", active = "", onClearSearch }) {
  /* 검색과 사용 여부는 이제 **화면 상단 탐색 줄**이 든다(OrgConsole) — 이 판은 그 상태를
     prop 으로 받아 그리기만 한다. 검색 상자가 판 안에 있으면 다른 목록 화면과 자리가
     달라지고, 같은 화면에 검색이 두 곳이던 옛 결함으로 돌아간다. */
  const [collapsed, setCollapsed] = useState({});
  const toggle = React.useCallback((id) => setCollapsed((s) => ({ ...s, [id]: !s[id] })), []);

  // 사용 여부는 예나 지금이나 **서버 필터**다(GET /api/admin/departments/tree 가 active 를 받는다).
  // 화면에서 거르면 걸러진 부모 아래 자식이 통째로 사라진다 — 백엔드는 그 경우 고아를 최상위로
  // 끌어올려 보여 준다(app/org/tree.py). 그 규칙을 여기서 두 번 구현하지 않는다.
  const query = useOrgTreeQuery(active);

  const rows = (query.data && query.data.items) || [];
  const nodes = useMemo(() => pruneTree(nestRows(rows), search), [rows, search]);
  // roving tabindex의 유일한 정지점 — 선택된 노드가 있으면 그 노드, 없으면(처음 진입) 첫
  // 루트 노드. nodes가 비어 있으면(로딩/빈 상태) undefined라 아무 노드와도 안 맞는다.
  const tabbableId = selectedId || (nodes[0] && nodes[0].row.id);

  return (
    <Card sx={{ position: "sticky", top: 0 }}>
      {/* 검색 상자는 이 판에 없다 — 상단 탐색 줄(OrgConsole)이 든다. 다른 목록 화면과
       * 같은 자리에 조건이 서고, 같은 화면에 검색이 두 곳이던 옛 결함으로 안 돌아간다. */}
      {query.isLoading ? (
        <Skeleton lines={5} />
      ) : query.isError ? (
        <ErrorState layout="region" error={query.error} onRetry={() => query.refetch()} />
      ) : nodes.length === 0 ? (
        /* 조건을 푸는 길을 함께 준다 (C1 · W5) — 조건은 위 탐색 줄이 들지만, 0건의 이유와
           푸는 단추는 빈 자리 곁에 서야 한다. */
        <ListEmptyState
          filtered={!!search}
          onClear={onClearSearch}
          clearLabel="검색어 지우기"
          filteredTitle="검색 결과가 없습니다"
          filteredHelp="조직 또는 부서 이름의 일부로 다시 찾아보세요."
          title="추가된 부서가 없습니다"
          help="‘부서 추가’로 부서를 추가하고 상위 부서를 지정하면 여기에 계층으로 표시됩니다."
        />
      ) : (
        <FlatBadgeSurface>
        <Box
          component="ul"
          role="tree"
          aria-label="조직도"
          sx={{ listStyle: "none", m: 0, p: 0, maxHeight: "70vh", overflowY: "auto", overflowX: "hidden" }}
        >
          {nodes.map((n) => (
            <TreeNode
              key={n.row.id}
              node={n}
              level={1}
              selectedId={selectedId}
              onSelect={onSelect}
              collapsed={collapsed}
              onToggle={toggle}
              tabbableId={tabbableId}
            />
          ))}
        </Box>
        </FlatBadgeSurface>
      )}
    </Card>
  );
}
