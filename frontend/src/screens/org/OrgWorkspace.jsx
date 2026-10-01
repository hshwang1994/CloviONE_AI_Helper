import React from "react";
import { useMutation } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import UnfoldLessRoundedIcon from "@mui/icons-material/UnfoldLessRounded";
import UnfoldMoreRoundedIcon from "@mui/icons-material/UnfoldMoreRounded";
import { api } from "../../lib/api.js";
import { useAuth } from "../../app/auth.jsx";
import { Button, Callout, EmptyState, ErrorState, PageHeader, Skeleton, useToast } from "../../ui/kit.jsx";
import { FilterToggle } from "../../ui/FilterBar.jsx";
import { SearchBox } from "../../ui/filters.jsx";
import { PaneToolbar, Workspace, WorkspacePane } from "../../ui/Workspace.jsx";
import { handleApiError } from "../data-screen/apiError.js";
import { BREAKPOINTS, RADIUS } from "../../ui/theme.js";
import { OrgTree } from "../OrgTree.jsx";
import { ancestorIndex, isOrgRow, nestRows } from "./orgTreeModel.js";
import { useDepartmentItem, useInvalidateOrgCaches, useOrgTreeQuery, useOrganizations } from "./orgQueries.js";
import { DeptCreateModal, DeptEditModal, OrgCreateModal, OrgEditModal } from "./orgModals.jsx";
import { OrgMembersPane } from "./OrgMembersPane.jsx";
import { OrgPaneHead } from "./OrgPaneHead.jsx";
import { DeptDeactivateDialog, DeptDeleteDialog, OrgDetailsDialog, OrgSuspendDialog } from "./orgImpact.jsx";

/* 조직 관리 — 관리 작업 공간 (O1 · D-533).
 *
 * 왼쪽 판은 조직도(검색 · 「사용 중만」 · 모두 접기/펼치기가 고정, 트리 줄만 굴러간다), 오른쪽 판은 고른 조직이나 부서(경로 · 이름 ·
 * 대상 동작 · 「구성원 N명」 · 필터 줄 · 표 머리 · 판 발이 고정, 구성원 줄만 굴러간다)다. 폭 1200 · 높이 600 이상에서 채움 모드라
 * 문서가 구성원 수와 상관없이 굴러가지 않고 두 판의 굴림은 서로 독립이다(`ui/Workspace.jsx`). 그보다 작은 창은 한 열이고 트리 몸만
 * 높이 상한이 있는 스크롤 상자다.
 *
 * 대상 동작은 판 머리에 선다(D-510 을 뒤집는다) — 페이지 머리는 「조직 추가」 하나다. 평소 화면에서 기술 정보(ID · 식별자 · 삭제
 * 판정)를 걷었다: 「더 보기 › 상세 정보」 창이 들고, 「삭제」 · 「비활성화」는 누를 때 서버에 영향을 묻는다(`orgImpact.jsx`). 할 수
 * 없는 동작은 메뉴에서 지우지 않고 까닭 한 줄과 함께 비활성으로 둔다 — 판에 「정보」 구획을 두고 그 까닭을 늘 보이던 자리다.
 *
 * ## 선택은 주소다(그대로)
 *
 * 부서 = `/departments/:id`, 조직 = `/organizations?org=<id>`. 아무것도 안 골랐으면 첫 조직을 암묵으로 보인다(주소 불변).
 * 검색은 `q`, 「사용 중만」은 `active=true`(옛 주소의 `active=false` 는 무시한다 — 미사용만 보는 조작은 없어졌다). 트리 질의는 하나다 —
 * 「사용 중만」을 화면에서 거르므로(조상을 남긴다) 표시용 질의를 따로 두지 않는다. */

const NARROW_QUERY = `(max-width:${BREAKPOINTS.lg - 0.05}px)`;
function isNarrowLayout() {
  try {
    return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(NARROW_QUERY).matches;
  } catch (e) {
    return false;
  }
}

const EDIT_DENIED = "조직 이름과 상태는 전체 관리자만 바꿀 수 있습니다.";
const SELF_SUSPEND_DENIED = "자기 조직 비활성화는 시스템 관리자만 할 수 있습니다.";
const ORG_DELETE_DENIED = "조직은 지울 수 없습니다. 비활성화하면 새 사용을 막을 수 있습니다.";

export function OrgWorkspace() {
  const navigate = useNavigate();
  const location = useLocation();
  const routeParams = useParams();
  const [search, setSearchParams] = useSearchParams();
  const auth = useAuth();
  const toast = useToast();
  const invalidate = useInvalidateOrgCaches();

  const q = search.get("q") || "";
  const activeOnly = search.get("active") === "true";
  const orgParam = search.get("org") || "";
  const deptId = routeParams.id || "";

  /* 조건은 히스토리를 쌓지 않는다(replace) — 뒤로 가기는 선택 사이를 오가는 길이다. */
  const setCondition = (patch) => {
    const next = new URLSearchParams(search);
    Object.entries(patch).forEach(([key, value]) => { if (value) next.set(key, value); else next.delete(key); });
    setSearchParams(next, { replace: true });
  };
  const commitSearch = React.useCallback(
    (next) => setCondition({ q: next || "" }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [search],
  );

  const tree = useOrgTreeQuery("");
  const organizations = useOrganizations();
  const rows = React.useMemo(() => (tree.data && tree.data.items) || [], [tree.data]);
  const orgRows = rows.filter(isOrgRow);
  const nodes = React.useMemo(() => nestRows(rows), [rows]);
  const ancestors = React.useMemo(() => ancestorIndex(nodes), [nodes]);
  const byId = React.useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows]);

  const selectedOrgId = deptId ? "" : (orgParam || (orgRows[0] && orgRows[0].id) || "");
  const selectedOrg = selectedOrgId
    ? ((organizations.data && organizations.data.items) || []).find((o) => o.id === selectedOrgId) : null;
  const selectedTreeId = deptId || selectedOrgId || null;
  const dept = useDepartmentItem(deptId);

  const [collapseSignal, setCollapseSignal] = React.useState(null);
  const [allOpen, setAllOpen] = React.useState(false);
  /* 열린 창 하나 — "org-create" · "org-edit" · "dept-create" · "dept-edit" · "delete" · "deactivate" · "suspend" · "details". */
  const [dialog, setDialog] = React.useState(null);
  const closeDialog = () => setDialog(null);

  const goTo = (target, { reveal = false } = {}) => {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (activeOnly) qs.set("active", "true");
    const state = reveal ? { orgPanelReveal: true } : undefined;
    if (target.kind === "organization") {
      qs.set("org", target.id);
      navigate({ pathname: "/organizations", search: "?" + qs.toString() }, { state });
    } else {
      const tail = qs.toString();
      navigate({ pathname: "/departments/" + target.id, search: tail ? "?" + tail : "" }, { state });
    }
  };
  const selectRow = (row) => goTo({ id: row.id, kind: isOrgRow(row) ? "organization" : "department" }, { reveal: isNarrowLayout() });
  /* 만든 뒤에는 그 항목으로 옮겨 간다 — 응답이 `{organization}` · `{department}` 봉투다. */
  const openCreated = (kind) => (made) => {
    const created = made && (made[kind] || made);
    if (created && created.id) goTo({ id: created.id, kind });
  };
  /* 지운 부서의 판에 남으면 곧바로 「찾을 수 없습니다」가 선다 — 그 부서가 있던 자리(상위 부서, 없으면 조직)로 옮겨 간다. */
  const leaveDeleted = (d) => {
    if (d.parent_id) goTo({ id: d.parent_id, kind: "department" });
    else if (d.org_id) goTo({ id: d.org_id, kind: "organization" });
    else navigate({ pathname: "/organizations" });
  };

  /* 한 열 배치에서 트리를 고르면 오른쪽 판을 화면 안으로 옮기고 제목에 초점을 둔다 — 안 그러면 고른 결과가 화면 밖에서 바뀐다.
     경로 이동의 초점 옮기기(`app/routeAnnounce.js`)가 같은 커밋의 뒤에서 돌므로 한 박자 늦춰 그 뒤에 둔다. */
  const wantsReveal = Boolean(location.state && location.state.orgPanelReveal);
  const revealedKey = React.useRef(null);
  const headingRef = React.useCallback((el) => {
    if (!el || !wantsReveal || revealedKey.current === location.key) return;
    revealedKey.current = location.key;
    window.setTimeout(() => {
      if (!el.isConnected) return;
      const pane = el.closest("[data-workspace-pane]") || el;
      if (typeof pane.scrollIntoView === "function") pane.scrollIntoView({ block: "start" });
      el.focus({ preventScroll: true });
    }, 0);
  }, [wantsReveal, location.key]);

  const actor = (auth && auth.data) || {};
  const mgmt = actor.management || {};
  /* 조직 생성은 서버가 전역 관리자만 허용한다(app/org/router.py 403). 여기서 감추는 것은 방어가 아니라 안내다. */
  const isGlobalAdmin = !mgmt.kind || mgmt.kind === "global";
  /* 부서 범위 관리자는 미지정 사람을 볼 수 없다(`apply_user_scope`) — 그 수는 언제나 0 이라 0 이 사실인지 말할 수 없다. */
  const seesUnassigned = !mgmt.kind || mgmt.kind === "global" || mgmt.kind === "org";

  const setDeptActive = useMutation({
    mutationFn: () => api("/api/admin/departments/" + deptId, { method: "PATCH", body: { active: true } }),
    onSuccess: () => { invalidate(); toast("다시 사용하도록 바꿨습니다."); },
    onError: (e) => handleApiError(e, toast),
  });
  const setOrgActive = useMutation({
    mutationFn: () => api("/api/admin/organizations/" + selectedOrgId, { method: "PATCH", body: { status: "active" } }),
    onSuccess: () => { invalidate(); toast("다시 사용하도록 바꿨습니다."); },
    onError: (e) => handleApiError(e, toast),
  });

  /* ── 왼쪽 판 ─────────────────────────────────────────────────────────── */
  const treePane = (
    <WorkspacePane
      label="조직도"
      bodyLabel="조직도 목록"
      flowMaxHeight="min(50vh, 28rem)"
      data-testid="org-console-tree"
      toolbar={(
        <Box sx={{ display: "grid", rowGap: 1, minWidth: 0 }}>
          <SearchBox value={q} onSearch={commitSearch} placeholder="조직, 부서 검색" ariaLabel="조직도 검색" layout="fill" />
          <PaneToolbar sx={{ justifyContent: "space-between" }}>
            <FilterToggle pressed={activeOnly} onClick={() => setCondition({ active: activeOnly ? "" : "true" })}>사용 중만</FilterToggle>
            <Tooltip title={allOpen ? "모두 접기" : "모두 펼치기"}>
              <IconButton
                aria-label={allOpen ? "모두 접기" : "모두 펼치기"}
                onClick={() => { setCollapseSignal({ kind: allOpen ? "collapse" : "expand", at: Date.now() }); setAllOpen((v) => !v); }}
                sx={{ border: 1, borderColor: "divider", borderRadius: `${RADIUS.sm}px`, color: "text.secondary" }}
              >
                {allOpen ? <UnfoldLessRoundedIcon fontSize="small" /> : <UnfoldMoreRoundedIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
          </PaneToolbar>
        </Box>
      )}
    >
      <OrgTree
        rows={rows}
        loading={tree.isLoading}
        error={tree.isError ? tree.error : null}
        onRetry={() => tree.refetch()}
        selectedId={selectedTreeId}
        onSelect={selectRow}
        query={q}
        activeOnly={activeOnly}
        onClearSearch={() => setCondition({ q: "", active: "" })}
        collapseSignal={collapseSignal}
      />
    </WorkspacePane>
  );

  /* ── 오른쪽 판 ───────────────────────────────────────────────────────── */
  const placeholderPane = (label, body) => <WorkspacePane label={label}>{body}</WorkspacePane>;
  let rightPane;
  const deptData = deptId && dept.data ? dept.data : null;
  if (deptId) {
    if (dept.isPending) {
      rightPane = placeholderPane("부서", <Box sx={{ p: 2.5 }}><Skeleton lines={6} /></Box>);
    } else if (dept.isError) {
      /* 없는 id 딥링크(D-127) — 판 안에서 말하고 트리는 그대로 산다. */
      rightPane = placeholderPane("부서", <ErrorState error={dept.error} onRetry={() => dept.refetch()} />);
    } else {
      const d = deptData || {};
      const row = byId.get(deptId) || {};
      let crumbs = (ancestors.get(deptId) || []).slice().reverse().map((id) => {
        const r = byId.get(id) || {};
        return { id, name: r.name, kind: isOrgRow(r) ? "organization" : "department" };
      }).filter((c) => c.name);
      /* 고리 덩어리는 트리의 맨 위에 서서 조상이 없다 — 그래도 어느 조직인지는 말한다. */
      if (!crumbs.length && d.org_name) crumbs = [{ id: d.org_id, name: d.org_name, kind: "organization" }];
      const childCount = d.child_department_count || 0;
      const menu = [
        { key: "edit", label: "수정", onClick: () => setDialog("dept-edit") },
        d.active
          ? { key: "deactivate", label: "비활성화", onClick: () => setDialog("deactivate") }
          : { key: "activate", label: "다시 사용", disabled: setDeptActive.isPending, onClick: () => setDeptActive.mutate() },
        { key: "delete", label: "삭제", tone: "danger", onClick: () => setDialog("delete") },
        { key: "audit", label: "감사 로그에서 보기", divider: true, href: "#/audit?object_type=department&object_id=" + encodeURIComponent(deptId) },
        { key: "users", label: "사용자 화면에서 보기", href: "#/users?department_id=" + encodeURIComponent(deptId) },
        { key: "details", label: "상세 정보", onClick: () => setDialog("details") },
      ];
      rightPane = (
        <OrgMembersPane
          key={deptId}
          label={d.name || "부서"}
          scope={{ kind: "dept", deptId, hasChildren: childCount > 0 }}
          emptyText="이 부서에 배치된 사람이 없습니다."
          notice={row.cycle ? (
            <Callout tone="danger" compact action={<Button size="sm" onClick={() => setDialog("dept-edit")}>수정</Button>}>
              상위 관계가 고리를 이루어 이 부서를 맨 위에 표시했습니다. 「수정」에서 상위 부서를 다시 지정하세요.
            </Callout>
          ) : null}
          head={(
            <OrgPaneHead
              kind="department"
              name={d.name}
              crumbs={crumbs}
              onPick={(c) => goTo({ id: c.id, kind: c.kind })}
              status={row.cycle ? { tone: "error.main", label: "상위 관계 오류" } : d.active === false ? { tone: "text.disabled", label: "미사용" } : null}
              /* 서버가 미사용 부서를 새 상위로 받지 않는다(xb-08) — 미사용이면 주 동작이 없고 상태 낱말이 그 까닭을 말한다. */
              primary={d.active ? { label: "하위 부서 추가", onClick: () => setDialog("dept-create") } : null}
              menu={menu}
              headingRef={headingRef}
            />
          )}
        />
      );
    }
  } else if (selectedOrgId) {
    if (organizations.isPending || tree.isLoading || (!selectedOrg && organizations.isFetching)) {
      /* 방금 만든 조직은 목록을 다시 받는 동안 아직 없다 — 그 사이 「찾지 못했습니다」를 세우지 않는다. */
      rightPane = placeholderPane("조직", <Box sx={{ p: 2.5 }}><Skeleton lines={6} /></Box>);
    } else if (!selectedOrg) {
      rightPane = placeholderPane("조직", (
        <EmptyState title="조직을 찾지 못했습니다." help="주소가 가리키는 조직이 없습니다. 왼쪽 조직도에서 다시 고르세요." />
      ));
    } else {
      const org = selectedOrg;
      const treeRow = byId.get(org.id) || {};
      const active = org.status === "active";
      /* 조직 이름 · 상태 PATCH 는 전체 관리자만 통과한다 — 서버가 그 답을 `can_edit` 로 싣는다. 모르는 옛 응답이면 전역 판정으로. */
      const canEdit = typeof org.can_edit === "boolean" ? org.can_edit : isGlobalAdmin;
      /* 자기 조직 정지는 시스템 관리자만 할 수 있다(org-09, `ensure_may_suspend_org`) — 역할과 조직 id 만 보는 조건이다. */
      const canSuspend = actor.role === "system_admin" || actor.org_id !== org.id;
      let statusItem = null;
      if (canEdit && active) {
        statusItem = canSuspend
          ? { key: "suspend", label: "비활성화", onClick: () => setDialog("suspend") }
          : { key: "suspend", label: "비활성화", disabled: true, help: SELF_SUSPEND_DENIED };
      } else if (canEdit) {
        statusItem = { key: "activate", label: "다시 사용", disabled: setOrgActive.isPending, onClick: () => setOrgActive.mutate() };
      }
      const menu = [
        canEdit
          ? { key: "edit", label: "수정", onClick: () => setDialog("org-edit") }
          : { key: "edit", label: "수정", disabled: true, help: EDIT_DENIED },
        statusItem,
        { key: "delete", label: "삭제", disabled: true, help: ORG_DELETE_DENIED },
        { key: "audit", label: "감사 로그에서 보기", divider: true, href: "#/audit?object_type=organization&object_id=" + encodeURIComponent(org.id) },
        { key: "details", label: "상세 정보", onClick: () => setDialog("details") },
      ];
      rightPane = (
        <OrgMembersPane
          key={org.id}
          label={org.name}
          scope={{ kind: "org", orgId: org.id, unassigned: seesUnassigned ? (treeRow.unassigned_count || 0) : 0 }}
          emptyText="이 조직에 속한 사람이 없습니다."
          head={(
            <OrgPaneHead
              kind="organization"
              name={org.name}
              crumbs={[]}
              status={active ? null : { tone: "text.disabled", label: "미사용" }}
              /* 부서를 만드는 것은 조직을 바꾸는 일이 아니다 — 미사용 조직에도 입구가 서고 창이 그 상태를 말한다(org-17). */
              primary={{ label: "부서 추가", onClick: () => setDialog("dept-create") }}
              menu={menu}
              headingRef={headingRef}
            />
          )}
        />
      );
    }
  } else {
    rightPane = placeholderPane("선택", (
      <EmptyState title="왼쪽에서 조직이나 부서를 고르세요." help="고른 조직이나 부서의 구성원이 여기에 나타납니다." />
    ));
  }

  return (
    <>
      <Workspace
        header={(
          <PageHeader
            area="사용자와 권한"
            title="조직 관리"
            help="왼쪽 조직도에서 조직이나 부서를 고르면 오른쪽에서 그 구성원과 동작을 봅니다. 조직도 줄의 수는 그 가지에서 지금 일하는 사람 수이고, 비활성 계정과 보관된 계정은 세지 않습니다."
            actions={isGlobalAdmin ? <Button onClick={() => setDialog("org-create")}>조직 추가</Button> : null}
          />
        )}
      >
        {treePane}
        {/* 오른쪽 자리 — 판은 고른 대상마다 새로 서지만(`key`, 필터 상태가 다른 대상으로 따라가지 않게) 이 자리는 그대로다.
            배치에는 끼지 않는다(`display: contents` — 판이 격자의 칸이다). 한 열 배치의 「판으로 옮기기」와 시험이 이 자리를 잡는다. */}
        <Box data-testid="org-console-panel" data-pane-slot="" sx={{ display: "contents" }}>{rightPane}</Box>
      </Workspace>

      <OrgCreateModal open={dialog === "org-create"} onClose={closeDialog} onCreated={openCreated("organization")} />
      {selectedOrg ? <OrgEditModal open={dialog === "org-edit"} org={selectedOrg} onClose={closeDialog} /> : null}
      {deptData ? <DeptEditModal open={dialog === "dept-edit"} dept={deptData} onClose={closeDialog} /> : null}
      {deptData || selectedOrg ? (
        <DeptCreateModal
          open={dialog === "dept-create"}
          onClose={closeDialog}
          fixedOrgId={deptData ? (deptData.org_id || "") : selectedOrg.id}
          defaultParentId={deptData ? deptData.id : undefined}
          defaultParentLabel={deptData ? deptData.name : undefined}
          title={deptData ? `${deptData.name}에 하위 부서 추가` : `${selectedOrg.name}에 부서 추가`}
          onCreated={openCreated("department")}
        />
      ) : null}
      {deptData ? (
        <>
          <DeptDeleteDialog
            dept={deptData} open={dialog === "delete"} onClose={closeDialog} onDeleted={leaveDeleted}
            onDeactivate={() => setDialog("deactivate")}
            onShowChildren={() => setCollapseSignal({ kind: "reveal", id: deptData.id, at: Date.now() })}
          />
          <DeptDeactivateDialog dept={deptData} open={dialog === "deactivate"} onClose={closeDialog} />
        </>
      ) : null}
      {selectedOrg ? <OrgSuspendDialog org={selectedOrg} open={dialog === "suspend"} onClose={closeDialog} /> : null}
      <OrgDetailsDialog
        open={dialog === "details"}
        onClose={closeDialog}
        kind={deptData ? "department" : "organization"}
        item={deptData || selectedOrg}
        childCount={deptData ? (deptData.child_department_count || 0) : ((selectedOrg && selectedOrg.department_count) || 0)}
      />
    </>
  );
}

export default OrgWorkspace;
