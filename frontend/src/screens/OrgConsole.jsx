import React from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import { useAuth } from "../app/auth.jsx";
import { OrgTree, isOrgRow, nestRows, pruneTree } from "./OrgTree.jsx";
import {
  Button, Card, EmptyState, PageHeader, Skeleton,
} from "../ui/kit.jsx";
import { StatusKpiStrip } from "../ui/StatusKpi.jsx";
import { FilterBar } from "../ui/FilterBar.jsx";
import { FilterSelect, SearchBox } from "../ui/filters.jsx";
import { useOrgTreeQuery, useOrganizations } from "./org/orgQueries.js";
import { OrgDetailPanel } from "./org/OrgDetailPanel.jsx";
import { DeptDetailPanel } from "./org/DeptDetailPanel.jsx";
import { DeptCreateModal, OrgCreateModal } from "./org/orgModals.jsx";
import { LIST_RAIL_GRID } from "../ui/density.js";

/* 조직 콘솔 — 조직 관리, 부서 관리, 조직도가 **한 화면**이다.
 *
 * ## 무엇을 바꿨나
 *
 * 옛 화면은 3판(트리 | 전체 표 DataScreen | 인원)이었다. 트리를 눌러도 오른쪽에는 상세가
 * 아니라 같은 자료의 **전체 표**가 다시 섰고(계획서가 «우측 pane 이 트리 선택에 상세로
 * 반응하지 않는다»로 지목), PageHeader 가 화면에 둘, 검색은 왼쪽 판 안, 셋째 판(인원)은
 * 1920 미만에서 통째로 사라졌다. 가장 값진 숫자(부서 미지정 N명)는 12px 회색 부제였다.
 *
 * 지금은 다른 화면과 같은 골격이다:
 *
 *   PageHeader(하나) → 요약 타일(부서 미지정을 타일로) → 전폭 탐색 줄(검색·사용 여부)
 *   → 건수 줄 → [트리 | **선택 반응형 상세 판**]
 *
 * 상세 판이 조직/부서의 사실·조작·소속 인원을 전부 든다 — 인원 판이 따로 없으니 모든
 * 폭에서 보인다. 표는 없앴다: 트리가 이미 전체 목록이고, 같은 화면에 같은 자료의 표를
 * 한 벌 더 세우는 것이 옛 화면의 소음이었다.
 *
 * ## 선택은 주소다
 *
 * 부서 = `/departments/:id`(D-104 — 관리자 상세도 진짜 주소를 가진다), 조직 =
 * `/organizations?org=<id>`. 새로고침·공유에서 선택이 살아남는다. 아무것도 안 골랐으면
 * **첫 조직을 암묵으로** 보여 주되 주소는 안 바꾼다 — 빈 오른쪽 판은 화면 절반이 죽은
 * 상태고, 트리의 뿌리가 조직이라 방향(위→아래)이 맞다.
 *
 * ## 검색은 클라이언트, 사용 여부는 서버
 *
 * 트리 응답은 페이지네이션이 없는 전량이라 이름 검색은 받아 둔 것에서 걸러도 숨는 행이
 * 없다(조상 보존은 `pruneTree`). 사용 여부는 서버 필터다 — 걸러진 부모의 고아 처리를
 * 서버가 안다(app/org/tree.py). */

export function OrgConsole() {
  const navigate = useNavigate();
  const routeParams = useParams();
  const [search, setSearchParams] = useSearchParams();
  const auth = useAuth();

  const q = search.get("q") || "";
  const active = search.get("active") || "";
  const orgParam = search.get("org") || "";
  const deptId = routeParams.id || "";

  /* 조건은 히스토리를 안 쌓는다(replace) — 뒤로 가기는 선택 사이를 오가는 길이다. */
  const setCondition = (patch) => {
    const next = new URLSearchParams(search);
    Object.entries(patch).forEach(([key, value]) => {
      if (value) next.set(key, value);
      else next.delete(key);
    });
    setSearchParams(next, { replace: true });
  };
  const commitSearch = React.useCallback(
    (next) => setCondition({ q: next || "" }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [search],
  );

  /* 표시용 트리는 사용 여부 조건을 따르고, 요약 타일은 **무필터** 트리로 센다 — 필터가
     걸린 트리로 합산하면 「미사용 포함」을 고르는 순간 조직의 구성원 수가 흔들린다.
     react-query 캐시가 같은 키를 물릴 때 왕복을 상쇄한다. */
  const displayTree = useOrgTreeQuery(active);
  const fullTree = useOrgTreeQuery("");
  const organizations = useOrganizations();

  const [orgForm, setOrgForm] = React.useState(false);
  const [deptForm, setDeptForm] = React.useState(false);

  const fullRows = (fullTree.data && fullTree.data.items) || [];
  const orgRows = fullRows.filter(isOrgRow);
  const metric = {
    orgs: orgRows.length,
    depts: fullRows.length - orgRows.length,
    members: orgRows.reduce((sum, r) => sum + (r.subtree_user_count || 0), 0),
    unassigned: orgRows.reduce((sum, r) => sum + (r.user_count || 0), 0),
  };

  /* 건수 줄 — 지금 조건으로 트리에 **보이는 부서 수**다(조직 행은 부서가 아니다).
     검색의 조상 보존 규칙(pruneTree)과 같은 판정을 쓴다. */
  const displayRows = (displayTree.data && displayTree.data.items) || [];
  const visibleDeptCount = React.useMemo(() => {
    const count = (nodes) => nodes.reduce(
      (sum, node) => sum + (isOrgRow(node.row) ? 0 : 1) + count(node.children), 0,
    );
    return count(pruneTree(nestRows(displayRows), q));
  }, [displayRows, q]);

  /* 선택 — 주소가 정본이다. 아무것도 없으면 첫 조직을 암묵으로 보여 준다(주소 불변). */
  const selectedDeptRow = deptId ? fullRows.find((r) => r.id === deptId) : null;
  const selectedOrgId = deptId ? "" : (orgParam || (orgRows[0] && orgRows[0].id) || "");
  const selectedOrg = selectedOrgId
    ? ((organizations.data && organizations.data.items) || []).find((o) => o.id === selectedOrgId)
    : null;
  const selectedTreeId = deptId || selectedOrgId || null;

  const selectRow = (row) => {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (active) qs.set("active", active);
    if (isOrgRow(row)) {
      qs.set("org", row.id);
      navigate({ pathname: "/organizations", search: "?" + qs.toString() });
    } else {
      const tail = qs.toString();
      navigate({ pathname: "/departments/" + row.id, search: tail ? "?" + tail : "" });
    }
  };

  const mgmt = (auth.data && auth.data.management) || {};
  /* 조직 생성은 서버가 전역 관리자만 허용한다(app/org/router.py 403). 여기서 감추는 것은
     방어가 아니라 안내다 — ScopeBar 와 같은 축(management.kind)을 읽는다. */
  const isGlobalAdmin = !mgmt.kind || mgmt.kind === "global";

  const hasFilter = Boolean(q || active);
  /* 조건 칩 — 조건마다 하나이고 조건 수는 칩 수다(조합 계약 C-1). */
  const conditionChips = [
    q ? { key: "q", label: `검색: ${q}`, onDelete: () => setCondition({ q: "" }) } : null,
    active ? { key: "active", label: `사용: ${active === "true" ? "사용 중" : "미사용"}`, onDelete: () => setCondition({ active: "" }) } : null,
  ].filter(Boolean);

  return (
    <div className="c-screen">
      <PageHeader
        area="사용자와 권한"
        title="조직 관리"
        description="조직도를 보면서 같은 화면에서 조직과 부서를 관리합니다."
        actions={(
          <>
            {isGlobalAdmin ? (
              <Button onClick={() => setOrgForm(true)}>조직 추가</Button>
            ) : null}
            <Button variant="primary" onClick={() => setDeptForm(true)}>부서 추가</Button>
          </>
        )}
      />

      <StatusKpiStrip
        ariaLabel="조직 요약"
        sx={{ mb: 2 }}
        items={[
          { key: "orgs", label: "조직", value: metric.orgs },
          { key: "depts", label: "부서", value: metric.depts },
          { key: "members", label: "구성원", value: metric.members },
          /* 계획서가 이 화면에서 가장 값진 숫자로 꼽은 값(E18) — 어디에도 안 속한 계정.
             12px 회색 부제로 눕던 것을 타일로 세운다. 0 이면 조용한 0 이다. */
          {
            key: "unassigned", label: "부서 미지정", value: metric.unassigned,
            primary: metric.unassigned > 0,
          },
        ]}
      />

      {/* 검색과 「사용」이 한 줄이다(조합 계약 C-1). 걸린 조건과 그 조건의 부서 수는 같은 면 안 조건 줄이 말한다 —
          조건이 없을 때의 전체 수는 바로 위 요약 줄(「부서」)이 이미 말하므로 단독 결과 줄을 두지 않는다. */}
      <FilterBar
        search={(
          <SearchBox
            value={q}
            onSearch={commitSearch}
            placeholder="조직 또는 부서를 이름이나 식별자로 검색"
            ariaLabel="조직도 검색"
          />
        )}
        conditions={{
          chips: conditionChips,
          total: visibleDeptCount,
          unit: "개 부서",
          onClearAll: hasFilter ? () => setCondition({ q: "", active: "" }) : null,
          clearLabel: "필터 지우기",
        }}
      >
        <FilterSelect
          label="사용"
          value={active}
          onChange={(v) => setCondition({ active: v || "" })}
          options={[
            { value: "true", label: "사용 중" },
            { value: "false", label: "미사용" },
          ]}
        />
      </FilterBar>

      {/* 좌측 레일 + 목록의 표준 트랙(density.js LIST_RAIL_GRID) — 문서 작업공간과 같은
          한 벌이다. 손으로 짠 값(20~26rem·gap20px)이 화면마다 달랐던 자리다. */}
      <Box sx={LIST_RAIL_GRID}>
        <Box data-testid="org-console-tree">
          <OrgTree
            selectedId={selectedTreeId}
            onSelect={selectRow}
            search={q}
            active={active}
            onClearSearch={() => setCondition({ q: "" })}
          />
        </Box>
        <Box data-testid="org-console-panel" sx={{ minWidth: 0 }}>
          {deptId ? (
            <DeptDetailPanel deptId={deptId} treeRow={selectedDeptRow} />
          ) : selectedOrgId ? (
            organizations.isPending || fullTree.isLoading ? (
              <Card><Skeleton lines={6} /></Card>
            ) : selectedOrg ? (
              <OrgDetailPanel
                org={selectedOrg}
                treeRow={orgRows.find((r) => r.id === selectedOrgId) || null}
                /* 이미 받아 둔 트리에서 이 조직의 부서만 걸러 넘긴다 — 상세 판이 스스로
                   또 묻지 않는다(같은 자료를 두 번 받으면 한쪽만 최신인 자리가 생긴다). */
                deptRows={fullRows.filter((r) => !isOrgRow(r) && r.org_id === selectedOrgId)}
                onOpenDept={selectRow}
              />
            ) : (
              <Card>
                <EmptyState
                  layout="card"
                  title="조직을 찾지 못했습니다."
                  help="주소가 가리키는 조직이 없습니다. 왼쪽 트리에서 다시 고를 수 있습니다."
                />
              </Card>
            )
          ) : (
            <Card>
              <EmptyState
                layout="card"
                title="왼쪽에서 조직이나 부서를 고릅니다."
                help="고른 항목의 정보와 소속 인원이 여기에 나타납니다."
              />
            </Card>
          )}
        </Box>
      </Box>

      <OrgCreateModal open={orgForm} onClose={() => setOrgForm(false)} />
      <DeptCreateModal
        open={deptForm}
        onClose={() => setDeptForm(false)}
        canPickOrg={isGlobalAdmin}
      />
    </div>
  );
}

export default OrgConsole;
