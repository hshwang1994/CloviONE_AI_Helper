import React from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import { useAuth } from "../app/auth.jsx";
import { OrgTree, isOrgRow, nestRows, pruneTree } from "./OrgTree.jsx";
import {
  Button, Card, EmptyState, PageHeader, Skeleton,
} from "../ui/kit.jsx";
import { FilterBar } from "../ui/FilterBar.jsx";
import { HeaderActionsHost, HeaderActionsProvider, useHeaderActionsSlot } from "../ui/HeaderSlot.jsx";
import { FilterSelect, SearchBox } from "../ui/filters.jsx";
import { useOrgTreeQuery, useOrganizations } from "./org/orgQueries.js";
import { OrgDetailPanel } from "./org/OrgDetailPanel.jsx";
import { DeptDetailPanel } from "./org/DeptDetailPanel.jsx";
import { OrgCreateModal } from "./org/orgModals.jsx";
import { LIST_RAIL_GRID } from "../ui/density.js";
import { APPBAR_HEIGHT, BREAKPOINTS, STICKY_TOP_VAR } from "../ui/theme.js";

/* 조직 콘솔 — 조직 관리, 부서 관리, 조직도가 **한 화면**이다.
 *
 * ## 이 화면이 먼저 말하는 것 (D-500)
 *
 * 「왼쪽에서 조직 · 부서 계층을 탐색하고, 오른쪽에서 고른 대상 하나를 관리한다.」 셋의 역할이 갈린다:
 *
 *   페이지 머리  제목 · 도움말 + 동작 셋: 「조직 추가」(전체 관리자만) · 고른 대상의 「더 보기」 · 주 동작
 *                (조직을 고르면 「부서 추가」, 부서를 고르면 「하위 부서 추가」)
 *   왼쪽 레일    탐색 — 판 머리에 검색 · 「사용」 · 조건 줄, 줄마다 이름 · 상태 배지 · 가지 인원 하나
 *   오른쪽 판    관리 — 고른 조직이나 부서의 이름 · 정체 · 「수정」, 그 아래 구성원 목록과 정보
 *
 * ## 무엇을 걷었나
 *
 * 예전에는 같은 수가 세 그릇에 되풀이됐다 — 페이지 요약 타일 넷(조직 · 부서 · 구성원 · 부서 미지정), 트리 줄
 * 부제(구성원 · 부서 · 부서 미지정 / 소속 · 하위 부서 · 하위 포함), 상세 판의 요약 타일 셋과 「포함 관계」 줄.
 * 화면은 넓은데 정보는 한 벌이었고, 둘은 세는 법이 달라 서로 어긋나기까지 했다. 전체 합계는 어떤 결정에도
 * 쓰이지 않는다(D-484 가 작업 보드 요약을 걷은 것과 같은 판단). 지금 수는 **한 곳에만** 선다: 가지 인원은
 * 트리 줄, 직접 구성원은 부서 판의 「구성원 N명」, 부서 미지정은 조직 판의 「부서 미지정 N명」, 하위 부서 ·
 * 부서 수는 정보 줄, 보관 계정은 사람 목록 아래 한 줄.
 *
 * 주 동작은 **고른 대상의 동작**이라 판이 그리지만, 자리는 페이지 머리다(`HeaderActions`, 계획 3.6 · D-510). 판 안에
 * 있던 동안 30px 주 동작이 머리의 34px 보조 단추(「조직 추가」)보다 작아 위계가 거꾸로 읽혔다. 무엇에 대한
 * 동작인지는 이름이 말한다 — 조직을 고르면 「부서 추가」, 부서를 고르면 「하위 부서 추가」이고, 창은 그 조직을
 * 고정하고 상위 부서를 미리 채운 채 열린다. 이 화면의 채움(주 동작)은 그 단추 하나다.
 *
 * ## 선택은 주소다
 *
 * 부서 = `/departments/:id`(D-104 — 관리자 상세도 진짜 주소를 가진다), 조직 =
 * `/organizations?org=<id>`. 새로고침·공유에서 선택이 살아남는다. 아무것도 안 골랐으면
 * **첫 조직을 암묵으로** 보여 주되 주소는 안 바꾼다 — 빈 오른쪽 판은 화면 절반이 죽은
 * 상태고, 트리의 뿌리가 조직이라 방향(위→아래)이 맞다. 만들고 나면 새 항목으로 옮겨 간다.
 *
 * 한 칸 배치(lg 미만)에서는 레일이 판 위에 먼저 선다. 거기서 트리를 고르면 판을 화면 안으로 옮기고
 * 초점을 판 제목에 둔다 — 안 그러면 고른 결과가 화면 밖에서 바뀐다. 이 의도는 주소 이동의 `state` 로
 * 넘긴다: 경로가 바뀌면 본문 경계가 화면을 새로 마운트하므로(App.jsx) 이 컴포넌트의 상태로는 못 넘긴다.
 *
 * ## 검색은 클라이언트, 사용 여부는 서버
 *
 * 트리 응답은 페이지네이션이 없는 전량이라 이름 검색은 받아 둔 것에서 걸러도 숨는 행이
 * 없다(조상 보존은 `pruneTree`). 사용 여부는 서버 필터다 — 걸러진 부모의 고아 처리를
 * 서버가 안다(app/org/tree.py). */

const NARROW_QUERY = `(max-width:${BREAKPOINTS.lg - 0.05}px)`;
function isNarrowLayout() {
  try {
    return typeof window !== "undefined" && typeof window.matchMedia === "function"
      && window.matchMedia(NARROW_QUERY).matches;
  } catch (e) {
    return false;
  }
}

/* 판을 화면 안으로 옮기고 제목에 초점을 둔다. 부드러운 굴림을 쓰지 않는다 — 움직임 없이 곧바로 옮기므로
   동작 줄이기 설정과 부딪히지 않는다(제품은 그 신호를 읽지 않는다, `ui/motion.js`). 판의 `scroll-margin-top`
   이 고정 머리만큼 비켜 선다. */
function revealPanel(heading) {
  const panel = heading.closest('[data-testid="org-console-panel"]') || heading;
  if (typeof panel.scrollIntoView === "function") panel.scrollIntoView({ block: "start" });
  heading.focus({ preventScroll: true });
}

const PANEL_SX = {
  minWidth: 0,
  scrollMarginTop: `calc(var(${STICKY_TOP_VAR}, ${APPBAR_HEIGHT.xs}px) + 16px)`,
};

export function OrgConsole() {
  return (
    <HeaderActionsProvider>
      <OrgConsoleBody />
    </HeaderActionsProvider>
  );
}

function OrgConsoleBody() {
  const navigate = useNavigate();
  const slot = useHeaderActionsSlot();
  const location = useLocation();
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

  /* 표시용 트리는 사용 여부 조건을 따르고(레일이 그린다), 상세 판이 읽는 행 · 경로 · 첫 조직은 **무필터**
     트리에서 온다 — 「미사용」을 골라도 고른 부서의 경로와 조직이 흔들리지 않는다. react-query 캐시가 같은
     키를 물릴 때 왕복을 상쇄한다. */
  const displayTree = useOrgTreeQuery(active);
  const fullTree = useOrgTreeQuery("");
  const organizations = useOrganizations();

  const [orgForm, setOrgForm] = React.useState(false);

  const fullRows = (fullTree.data && fullTree.data.items) || [];
  const orgRows = fullRows.filter(isOrgRow);

  /* 조건 줄의 결과 수 — 지금 조건으로 트리에 **보이는 부서 수**다(조직 행은 부서가 아니다).
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
  /* 머리 동작 자리 — 고른 대상이 있으면 판이 그 자리에 「더 보기」와 주 동작을 그린다. 자리를 판이 붙은 **뒤에**
     내면(HeaderSlot 의 기본 순서, 수동 효과) 판 제목이 먼저 서고 단추는 한 박자 늦게 선다. 고른 대상이 곧 판이
     설 자리이므로 그때 미리 낸다 — 판이 서는 그 커밋에 단추가 함께 선다. */
  const panelActions = Boolean(selectedTreeId) || !!(slot && slot.count > 0);

  const goTo = (target, { reveal = false } = {}) => {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (active) qs.set("active", active);
    const state = reveal ? { orgPanelReveal: true } : undefined;
    if (target.kind === "organization") {
      qs.set("org", target.id);
      navigate({ pathname: "/organizations", search: "?" + qs.toString() }, { state });
    } else {
      const tail = qs.toString();
      navigate({ pathname: "/departments/" + target.id, search: tail ? "?" + tail : "" }, { state });
    }
  };
  const selectRow = (row) => goTo(
    { id: row.id, kind: isOrgRow(row) ? "organization" : "department" },
    { reveal: isNarrowLayout() },
  );
  /* 만든 뒤에는 그 항목으로 옮겨 간다 — 응답이 `{organization}` · `{department}` 봉투다. */
  const openCreated = (kind) => (made) => {
    const created = made && (made[kind] || made);
    if (created && created.id) goTo({ id: created.id, kind });
  };
  /* 부서를 지운 뒤에는 그 부서가 있던 자리 — 상위 부서, 없으면 그 조직 — 로 옮겨 간다. */
  const leaveDeleted = (dept) => {
    if (dept.parent_id) goTo({ id: dept.parent_id, kind: "department" });
    else if (dept.org_id) goTo({ id: dept.org_id, kind: "organization" });
    else navigate({ pathname: "/organizations" });
  };

  /* 한 칸 배치에서 고른 결과로 판을 옮긴다(위 머리 주석). 제목이 그려지는 순간 한 번 — 부서 판은 상세를
     받은 뒤에 제목이 선다. 경로 이동의 초점 옮기기(`app/routeAnnounce.js` — 본문으로 보낸다)가 같은 커밋의
     뒤에서 돌므로 한 박자 늦춰 그 뒤에 둔다. */
  const wantsReveal = Boolean(location.state && location.state.orgPanelReveal);
  const revealedKey = React.useRef(null);
  const headingRef = React.useCallback((el) => {
    if (!el || !wantsReveal || revealedKey.current === location.key) return;
    revealedKey.current = location.key;
    window.setTimeout(() => { if (el.isConnected) revealPanel(el); }, 0);
  }, [wantsReveal, location.key]);

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

  /* 레일 판 머리 — 검색과 「사용」이 트리만 거르므로 트리 판 안에 선다(조합 계약 C-1 의 필터 바 그대로).
     22rem 레일에서는 검색이 줄을 다 쓰고 「사용」이 다음 줄로 접힌다. 걸린 조건과 그 조건의 부서 수는 같은 면
     안 조건 줄이 말한다 — 조건이 없을 때의 전체 수는 어디에도 따로 세우지 않는다(결정에 안 쓰인다). */
  const filterBar = (
    <FilterBar
      /* 자리표시 글은 22rem 레일의 검색 칸 안에 다 들어가야 한다 — 무엇을 찾는지는 칸의 이름(「조직도 검색」)과
         바로 아래 트리가 말한다. */
      search={(
        <SearchBox
          value={q}
          onSearch={commitSearch}
          placeholder="이름이나 식별자로 검색"
          ariaLabel="조직도 검색"
        />
      )}
      conditions={{
        chips: conditionChips,
        total: visibleDeptCount,
        unit: "개",
        noun: "부서",
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
  );

  return (
    <div className="c-screen">
      <PageHeader
        area="사용자와 권한"
        title="조직 관리"
        description="조직도에서 조직이나 부서를 고르고 그 자리에서 관리합니다."
        help={(
          <>
            왼쪽 조직도에서 조직이나 부서를 고르면 오른쪽 판에서 그 대상을 관리합니다. 조직도 줄의 수는 그 조직이나
            부서에서 지금 일하는 사람을 하위 부서까지 모두 센 수이고, 비활성 계정과 보관된 계정은 세지 않습니다.
            부서는 고른 조직이나 부서에서 머리의 추가 단추로 만듭니다.
          </>
        )}
        actions={isGlobalAdmin || panelActions ? (
          <>
            {isGlobalAdmin ? <Button onClick={() => setOrgForm(true)}>조직 추가</Button> : null}
            {panelActions ? <HeaderActionsHost /> : null}
          </>
        ) : null}
      />

      {/* 좌측 레일 + 목록의 표준 트랙(density.js LIST_RAIL_GRID) — 문서 작업공간과 같은
          한 벌이다. 손으로 짠 값(20~26rem·gap20px)이 화면마다 달랐던 자리다.
          레일 칸은 두 칸 배치에서 줄 높이만큼 늘어난다 — 그래야 그 안의 판이 붙박인 채 따라온다(OrgTree
          `railCardSx`). 칸이 판 높이로 줄어 있으면 붙박이가 움직일 자리가 없다. */}
      <Box sx={LIST_RAIL_GRID}>
        <Box data-testid="org-console-tree" sx={{ minWidth: 0, alignSelf: { lg: "stretch" } }}>
          <OrgTree
            selectedId={selectedTreeId}
            onSelect={selectRow}
            search={q}
            active={active}
            onClearSearch={() => setCondition({ q: "" })}
            header={filterBar}
          />
        </Box>
        <Box data-testid="org-console-panel" sx={PANEL_SX}>
          {/* 판은 고른 대상마다 새로 선다(`key`) — 화면은 고를 때 다시 마운트되지 않으므로(`navEntry.jsx::screenKeyOf`), 판이
              든 순간 상태(수정 · 추가 대화상자가 열려 있는가)가 다른 대상으로 따라가지 않게 한다. */}
          {deptId ? (
            <DeptDetailPanel
              key={deptId}
              deptId={deptId}
              treeRow={selectedDeptRow}
              treeRows={fullRows}
              headingRef={headingRef}
              onCreated={openCreated("department")}
              onDeleted={leaveDeleted}
            />
          ) : selectedOrgId ? (
            /* 방금 만든 조직은 목록을 다시 받는 동안 아직 없다 — 그 사이 「찾지 못했습니다」를 세우지 않는다. */
            organizations.isPending || fullTree.isLoading || (!selectedOrg && organizations.isFetching) ? (
              <Card><Skeleton lines={6} /></Card>
            ) : selectedOrg ? (
              <OrgDetailPanel
                key={selectedOrgId}
                org={selectedOrg}
                treeRow={orgRows.find((r) => r.id === selectedOrgId) || null}
                headingRef={headingRef}
                onCreated={openCreated("department")}
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
                help="고른 항목의 정보와 구성원이 여기에 나타납니다."
              />
            </Card>
          )}
        </Box>
      </Box>

      <OrgCreateModal open={orgForm} onClose={() => setOrgForm(false)} onCreated={openCreated("organization")} />
    </div>
  );
}

export default OrgConsole;
