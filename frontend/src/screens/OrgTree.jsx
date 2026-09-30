import React, { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import { Badge, Card, ErrorState, FlatBadgeSurface, ListEmptyState, Skeleton } from "../ui/kit.jsx";
import { useOrgTreeQuery } from "./org/orgQueries.js";
import { foldText, includesFolded } from "../lib/search.js";
import {
  APPBAR_HEIGHT, BREAKPOINTS, FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, NUMERIC, STICKY_TOP_VAR, stickyTopSx,
} from "../ui/theme.js";

/* 조직도 트리 — 조직 콘솔(OrgConsole.jsx)의 왼쪽 레일. **탐색하는 자리**다.
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
 * ## 줄마다 수는 하나다 (D-500)
 *
 * 예전 줄은 부제 한 줄에 수를 셋까지 적었다(조직: 구성원 · 부서 · 부서 미지정, 부서: 소속 · 하위 부서 ·
 * 하위 포함). 같은 수가 페이지 요약 타일과 상세 판 타일에 또 서서, 한 화면이 같은 사실을 세 번 말했다.
 * 지금 줄의 수는 **가지 전체의 구성원**(`subtree_user_count`) 하나다 — 가지를 따라 더하면 맞는 수이고,
 * 이 수의 자리는 여기뿐이다. 직접 구성원은 상세 판의 절 제목이, 하위 부서 수는 상세 판의 정보 줄이
 * 말한다. 부서 미지정 인원은 수 없이 경고 배지로만 선다(수는 조직 상세의 「부서 미지정 N명」 절이 든다).
 *
 * ## 검색과 「사용」은 이 판 머리가 든다
 *
 * 둘 다 트리만 거르는 조건이라 트리 판 안에 선다(`header` 슬롯 — 채팅방 목록 판과 같은 자리 규칙).
 * 상태 자체는 화면(OrgConsole)이 주소에 들고, 이 판은 prop 으로 받아 그리기만 한다. 질의는
 * `org/orgQueries.js` 한 벌이다 — 옛 registry 조각(org-tree)은 걷혔고, 그 설정이 들던 사실 중 이 판이
 * 쓰는 것(검색 축·빈 상태 문구)은 여기가 정본이다.
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

/* 줄의 수 — **가지 전체의 구성원**이다(app/org/tree.py). 조직 줄은 그 조직의 모든 사람(부서 미지정
 * 포함), 부서 줄은 그 부서와 아래 부서 전부의 직접 소속 합이라, 가지를 따라 더하면 맞는다. 둘 다
 * 보관된 계정도 센다 — 상세 판의 사람 목록은 보관된 계정을 빼고 그 차이를 목록 아래에서 말한다.
 * 이 수를 모르는 옛 응답이면 직접 소속으로 떨어진다. */
function branchCount(row) {
  if (row.subtree_user_count != null) return row.subtree_user_count;
  return row.user_count || 0;
}

/* 상태 배지 — 조직 · 미사용 · 상위 관계 오류, 그리고 부서가 지정되지 않은 사람이 있는 조직의 경고.
 * 조직의 `user_count` 가 곧 부서 미지정 인원이다. 0 이 아니면 관리자가 알아야 할 사실이라 서지만
 * 수는 달지 않는다 — 그 수의 자리는 조직 상세의 「부서 미지정 N명」 절 하나다. */
function stateBadges(row, isOrg) {
  const out = [];
  if (isOrg) out.push(<Badge key="org" value="조직" kind="info" />);
  if (row.active === false) out.push(<Badge key="inactive" value="미사용" kind="warn" />);
  if (row.cycle) out.push(<Badge key="cycle" value="상위 관계 오류" kind="danger" />);
  /* 「부서 미지정」 배지는 걷었다(계획 3.6) — 조직 줄의 직접 인원은 조직 직속(정상인 자리)이라 그 배지가 정상을
     예외로 읽게 했다. 부서도 조직 직속도 아닌 사람은 조직 판의 예외 줄이 말한다. */
  return out;
}

function TreeNode({ node, level, selectedId, onSelect, collapsed, onToggle, tabbableId }) {
  const row = node.row;
  const isOrg = isOrgRow(row);
  const hasKids = node.children.length > 0;
  const open = hasKids && !collapsed[row.id];
  const selected = selectedId === row.id;
  const badges = stateBadges(row, isOrg);
  const baseId = React.useId();
  const countId = baseId + "-count";
  const stateId = baseId + "-state";
  return (
    <Box
      component="li"
      role="treeitem"
      /* 이름을 명시한다 — 이름을 내용에서 뽑게 두면 자식 노드의 이름과 인원수까지 딸려 들어와
         "영업팀 4명 국내영업 2명"이 이 노드의 이름이 된다(중첩 트리의 함정). 배지와 수는 이름이
         아니라 설명으로 붙는다(`aria-describedby`) — 자식 줄의 배지 · 수는 딸려 오지 않는다. */
      aria-label={row.name}
      aria-describedby={badges.length ? `${stateId} ${countId}` : countId}
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
        /* 한 줄이다 — 이름 · 배지가 왼쪽, 수가 오른쪽 끝. 부제 줄이 걷혀 가운데 맞춤이 꺾쇠 · 이름 · 수를
           한 눈높이에 세운다(배지가 넘쳐 줄이 둘이 되면 그 두 줄의 가운데에 선다). */
        sx={{
          display: "flex", alignItems: "center", gap: 0.5, cursor: "pointer",
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
            sx={{ p: 0.25 }}
          >
            {open ? <ExpandMoreRoundedIcon fontSize="small" /> : <ChevronRightRoundedIcon fontSize="small" />}
          </IconButton>
        ) : (
          // 꺾쇠가 없는 줄도 같은 자리에서 이름이 시작해야 세로로 줄이 맞는다.
          <Box aria-hidden="true" sx={{ width: "1.5rem", flexShrink: 0 }} />
        )}
        <Box sx={{ minWidth: 0, flex: 1, display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
          <Typography
            component="span"
            sx={{ fontWeight: isOrg ? FONT_WEIGHT.extrabold : FONT_WEIGHT.semibold, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}
          >
            {row.name}
          </Typography>
          {badges.length ? (
            <Box component="span" id={stateId} sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
              {badges}
            </Box>
          ) : null}
        </Box>
        {/* 수는 오른쪽 끝에 고정폭 숫자로 선다 — 위아래 줄의 자릿수가 한 세로줄에 맞는다. 화면에는 「6명」,
            스크린리더에는 「구성원 6명」이다(`aria-describedby`). */}
        <Typography
          component="span"
          id={countId}
          sx={{ ...NUMERIC, flexShrink: 0, whiteSpace: "nowrap", pl: 1, fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}
        >
          <span className="sr-only">구성원 </span>
          {branchCount(row)}명
        </Typography>
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

/* 레일 판의 붙박이 — **두 칸 배치(lg 이상)에서만** 뜻이 있다. 상세 판이 길어져 창을 굴려도 트리는
 * 고정 머리 바로 아래에 남는다.
 *
 * 🔴 예전에는 `top: 0` 이었다. 윈도가 굴러가는 화면에서 그 자리는 **고정 머리(AppBar) 뒤**라 판 윗부분이
 * 머리에 가려졌다 — 표의 고정 열 이름이 겪던 것과 같은 결함이고, 답도 같다(`theme.js::stickyTopSx`).
 * 판 높이는 창 높이에서 머리와 위아래 여백을 뺀 만큼이 상한이고, 넘치는 트리는 판 **안에서** 굴러간다 —
 * 판이 창보다 크면 붙박인 판의 아래쪽이 끝까지 안 보인다. 한 칸 배치에서는 레일이 상세 판 위에 먼저
 * 서므로 붙박이지 않는다(붙박이면 상세 판을 덮는다). */
const RAIL_GAP_PX = 16;
function railCardSx() {
  const top = stickyTopSx(RAIL_GAP_PX);
  const maxAt = (h) => `calc(100vh - var(${STICKY_TOP_VAR}, ${h}px) - ${RAIL_GAP_PX * 2}px)`;
  const xxl = `@media (min-width:${BREAKPOINTS.xxl}px)`;
  const uhd = `@media (min-width:${BREAKPOINTS.uhd}px)`;
  return {
    display: "flex", flexDirection: "column", minHeight: 0,
    position: { lg: "sticky" },
    top: top.top,
    maxHeight: maxAt(APPBAR_HEIGHT.xs),
    [xxl]: { ...top[xxl], maxHeight: maxAt(APPBAR_HEIGHT.xxl) },
    [uhd]: { ...top[uhd], maxHeight: maxAt(APPBAR_HEIGHT.uhd) },
  };
}

export function OrgTree({ selectedId, onSelect, search = "", active = "", onClearSearch, header = null }) {
  /* 검색과 사용 여부의 **상태**는 화면(OrgConsole)이 주소에 든다. 그 조작기는 이 판 머리(`header`)에
     선다 — 트리만 거르는 조건이라 트리 판 안이 제자리다. 이 판은 상태를 prop 으로 받아 그리기만 한다. */
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
    <Card sx={railCardSx()}>
      {/* 판 머리 — 검색 · 「사용」 · 조건 줄(OrgConsole 이 준다). 트리가 판 안에서 굴러가도 이 줄은 제자리다. */}
      {header}
      {query.isLoading ? (
        <Skeleton lines={5} />
      ) : query.isError ? (
        <ErrorState layout="region" error={query.error} onRetry={() => query.refetch()} />
      ) : nodes.length === 0 ? (
        /* 조건을 푸는 길을 함께 준다 (C1 · W5) — 조건은 바로 위 판 머리가 들지만, 0건의 이유와
           푸는 단추는 빈 자리 곁에 서야 한다. */
        <ListEmptyState
          filtered={!!search}
          onClear={onClearSearch}
          clearLabel="검색어 지우기"
          filteredTitle="검색 결과가 없습니다"
          filteredHelp="조직 또는 부서 이름의 일부로 다시 찾아보세요."
          title="추가된 부서가 없습니다"
          help="조직을 고른 뒤 ‘부서 추가’로 부서를 만들면 여기에 계층으로 표시됩니다."
        />
      ) : (
        <FlatBadgeSurface>
        <Box
          component="ul"
          role="tree"
          aria-label="조직도"
          /* 판 높이의 남는 만큼을 먹고 넘치면 **여기서** 굴러간다(위 `railCardSx`). 초점이 옮겨 간 줄은
             브라우저가 이 칸 안으로 굴려 보인다. */
          sx={{ listStyle: "none", m: 0, p: 0, flex: "1 1 auto", minHeight: 0, overflowY: "auto", overflowX: "hidden" }}
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
