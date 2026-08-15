import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ChevronRightRoundedIcon from "@mui/icons-material/ChevronRightRounded";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import { api } from "../lib/api.js";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../ui/kit.jsx";
import { EMPTYABLE_SELECT, SearchBox } from "../ui/filters.jsx";
import { ORG_SCREENS } from "./registry/org.js";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";

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
 * ## 자료는 새로 만들지 않는다
 *
 * 엔드포인트, 사용 여부 필터, 검색 대상 필드, 빈 상태 문구까지 전부 기존 `org-tree` 화면
 * 설정(registry/org.js)에서 그대로 읽는다. 같은 값을 여기 한 벌 더 적으면 한쪽만 고쳐지는
 * 날이 오고, 그때 증상은 "조직도만 다르게 동작한다"라서 원인이 안 보인다.
 */

const TREE_CFG = ORG_SCREENS["org-tree"];
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

/** 검색어에 맞는 노드와 **그 조상**만 남긴다. 조상을 지우면 어디 소속인지 알 수 없게 된다. */
export function pruneTree(nodes, term) {
  const needle = String(term || "").trim().toLowerCase();
  if (!needle) return nodes;
  const fields = TREE_CFG.searchFields || ["name"];
  const walk = (list) => list.reduce((out, node) => {
    const kids = walk(node.children);
    const hay = fields.map((k) => (node.row[k] == null ? "" : String(node.row[k]))).join(" ").toLowerCase();
    if (hay.includes(needle) || kids.length) out.push({ ...node, children: kids });
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

function TreeNode({ node, level, selectedId, onSelect, collapsed, onToggle }) {
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
      tabIndex={0}
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
        "&:focus-visible": { outline: "2px solid", outlineColor: "primary.main", outlineOffset: 2, borderRadius: 1 },
      }}
    >
      <Box
        sx={{
          display: "flex", alignItems: "flex-start", gap: 0.5, cursor: "pointer",
          px: 1, py: 0.75, borderRadius: 1.5, minWidth: 0,
          border: 1,
          borderColor: selected ? "primary.main" : "transparent",
          bgcolor: selected ? "action.selected" : "transparent",
          "&:hover": { bgcolor: selected ? "action.selected" : "action.hover" },
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
              sx={{ fontWeight: isOrg ? FONT_WEIGHT.extrabold : FONT_WEIGHT.semibold, fontSize: isOrg ? "0.9375rem" : FONT_SIZE.body, overflowWrap: "anywhere" }}
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
            />
          ))}
        </Box>
      ) : null}
    </Box>
  );
}

export function OrgTree({ selectedId, onSelect }) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState("");
  const [collapsed, setCollapsed] = useState({});
  const commitSearch = React.useCallback((next) => setQ(next), []);
  const toggle = React.useCallback((id) => setCollapsed((s) => ({ ...s, [id]: !s[id] })), []);

  // 사용 여부는 예나 지금이나 **서버 필터**다(GET /api/admin/departments/tree 가 active 를 받는다).
  // 화면에서 거르면 걸러진 부모 아래 자식이 통째로 사라진다 — 백엔드는 그 경우 고아를 최상위로
  // 끌어올려 보여 준다(app/org/tree.py). 그 규칙을 여기서 두 번 구현하지 않는다.
  const url = TREE_CFG.endpoint + (active ? "?active=" + active : "");
  const query = useQuery({
    queryKey: [TREE_CFG.key, active],
    queryFn: () => api(url),
    retry: false,
  });

  const rows = (query.data && query.data.items) || [];
  const nodes = useMemo(() => pruneTree(nestRows(rows), q), [rows, q]);
  const activeFilter = (TREE_CFG.filters || [])[0];

  return (
    <Card sx={{ position: "sticky", top: 0 }}>
      {/* 조직 콘솔(OrgConsole.jsx)이 이미 같은 자리에 같은 문장으로 헤더를 그린다(PageHeader
       * title="조직도" + Callout). 이 카드는 OrgConsole 안에서만 쓰이므로(단독 사용처 없음,
       * grep -rn "OrgTree" frontend/src 로 확인) 여기서 제목·안내문을 다시 그리면 화면에
       * 완전히 같은 문장이 두 번 나온다. 트리가 무엇을 보여주는지는 role="tree" aria-label과
       * 아래 검색창 placeholder로 이미 드러나므로 별도 라벨 없이도 뜻이 통한다. */}
      <Box sx={{ display: "grid", gap: 1.5, mb: 2 }}>
        <SearchBox
          value={q}
          onSearch={commitSearch}
          placeholder={TREE_CFG.searchPlaceholder}
          ariaLabel={TREE_CFG.searchPlaceholder}
          /* 기본값은 목록 화면 툴바용(2칸 차지)이다. 여기 격자는 한 칸뿐이라 비워 넘긴다
             (undefined 를 넘기면 기본 인자가 되살아나 span 2 가 그대로 붙는다). */
          sx={{}}
        />
        {activeFilter ? (
          <TextField
            select size="small" label={activeFilter.label}
            value={active}
            onChange={(e) => setActive(e.target.value)}
            {...EMPTYABLE_SELECT}
          >
            <MenuItem value="">{activeFilter.label}: 전체</MenuItem>
            {(activeFilter.options || []).map((o) => (
              <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
            ))}
          </TextField>
        ) : null}
      </Box>
      {query.isLoading ? (
        <Skeleton lines={5} />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : nodes.length === 0 ? (
        q ? (
          <EmptyState title="검색 결과가 없습니다" help="조직 또는 부서 이름의 일부를 입력해 보세요." />
        ) : (
          <EmptyState title={TREE_CFG.emptyTitle} help={TREE_CFG.emptyHelp} />
        )
      ) : (
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
            />
          ))}
        </Box>
      )}
    </Card>
  );
}
