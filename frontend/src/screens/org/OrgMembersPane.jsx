import React from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { ROLE_LABELS, roleLabel } from "../../lib/roles.js";
import { useInfiniteList } from "../../lib/useInfiniteList.js";
import { Badge, Button, Callout, DataTable } from "../../ui/kit.jsx";
import { FilterBar, FilterToggle } from "../../ui/FilterBar.jsx";
import { FilterSelect, SearchBox } from "../../ui/filters.jsx";
import { ListStateView } from "../../ui/ListStateView.jsx";
import { LIST_STATE_COPY, isFailureState, resolveListState } from "../../ui/listState.js";
import { PaneToolbar, WorkspacePane } from "../../ui/Workspace.jsx";
import { PersonLine, personLineLead } from "../../ui/UserAvatar.jsx";
import { FONT_WEIGHT } from "../../ui/theme.js";

/* 구성원 판 (O1 · D-533) — 고른 조직이나 부서의 사람. 판 머리 · 도구 줄 · 표 머리 · 판 발은 고정이고 표 몸만 굴러간다.
 *
 * 도구 줄: 「구성원 N명」(지금 조건의 서버 total) + 필터 줄(검색 · 상태 기본 활성 · 조직이면 소속 · 부서면 「직속만」). 부서의 기본은
 * **하위 포함**이다 — 트리 줄의 수(가지 전체)와 목록의 수가 같다. 예전에는 상위 부서가 트리에 12명인데 목록이 직속 0명이었다.
 * 모든 조건이 칩과 「필터 초기화」에 든다. 조직이면 부서도 조직 직속도 아닌 사람이 있을 때만 그 사실을 한 줄 메시지 상자로 말한다.
 *
 * 표(F3 열 배분): 이름 · 직책 · 이메일 · 부서 · 상태 · 역할. 이름 · 이메일 · 상태 · 역할은 필수 열이라 어떤 폭에서도 숨지 않고, 좁으면
 * 직책 → 부서 순서로 숨긴다 — 부서 열은 여러 부서가 섞이는 보기에만 서므로 문맥이 아니라 보조 열이고 직책보다 오래 남는다. 말단 부서의
 * 직속 보기에서는 부서 열을 처음부터 그리지 않는다. 동명이인은 이메일 열이 가른다
 * (이름 칸 둘째 줄의 이메일은 걷었다 — 두 번 보였다). */

const STATE_OPTIONS = [
  { value: "active", label: "활성" },
  { value: "inactive", label: "비활성" },
  { value: "archived", label: "보관" },
];

export const MEMBERSHIP_OPTIONS = [
  { value: "department", label: "부서 소속" },
  { value: "organization", label: "조직 직속" },
  { value: "unassigned", label: "미지정" },
];

function stateOf(user) {
  if (user.archived_at) return { label: "보관", kind: "neutral" };
  if (user.active === false) return { label: "비활성", kind: "warn" };
  return { label: "활성", kind: "ok" };
}

export function memberColumns({ showDepartment }) {
  return [
    {
      key: "display_name", label: "이름", type: "name", rowLink: true,
      rowName: (u) => u.display_name || u.email,
      /* 칸에 그려지는 글과 그 앞 아바타 폭 — 열 배분이 값 폭을 알아야 이름이 짧을 때 그 차이를 이메일 열에 내준다(D-529). */
      value: (u) => u.display_name || "알 수 없음",
      lead: personLineLead("xs"),
      render: (u) => <PersonLine person={u} name={u.display_name} size="xs" />,
    },
    { key: "title", label: "직책", type: "enum", tier: "secondary", priority: 0, render: (u) => u.title || "-" },
    { key: "email", label: "이메일", type: "identifier" },
    /* 그리는 함수를 두지 않는다 — 글 값 열이라 칸 폭 안에서 말줄임 + 전체 값 툴팁이다. 그리는 함수가 있으면 말줄임 판정에서
       빠져 아주 긴 부서 이름이 열두 줄로 접혀 행 하나가 250px 가 됐다(P17V 긴 값 상태 캡처). */
    showDepartment ? { key: "department", label: "부서", type: "path", tier: "secondary", priority: 1, value: (u) => u.department || "-" } : null,
    {
      key: "state", label: "상태", type: "status", values: STATE_OPTIONS.map((o) => o.label),
      hint: (u) => stateOf(u).label,
      render: (u) => { const s = stateOf(u); return <Badge value={s.label} kind={s.kind} />; },
    },
    { key: "role", label: "역할", type: "enum", values: Object.values(ROLE_LABELS), hint: (u) => roleLabel(u.role), render: (u) => roleLabel(u.role) },
  ].filter(Boolean);
}

/**
 * `scope` — `{ kind: "org", orgId, unassigned }` 또는 `{ kind: "dept", deptId, hasChildren }`.
 * `head` — 판 머리(`OrgPaneHead`). `emptyText` — 조건 없이 0명일 때의 문장.
 * `notice` — 그 대상에 예외가 있을 때만 서는 한 줄 메시지 상자(예: 상위 관계 오류). 도구 줄 맨 아래에 선다.
 */
export function OrgMembersPane({ label, head, scope, emptyText, notice = null }) {
  const nav = useNavigate();
  const isDept = scope.kind === "dept";
  const [q, setQ] = React.useState("");
  const [state, setState] = React.useState("active");
  const [directOnly, setDirectOnly] = React.useState(false);
  const [membership, setMembership] = React.useState("");

  const params = React.useMemo(() => {
    const out = {};
    if (isDept) {
      out.department_id = scope.deptId;
      if (!directOnly) out.include_descendants = "true";
    } else {
      out.org_id = scope.orgId;
      if (membership) out.membership_kind = membership;
    }
    if (q) out.q = q;
    if (state) out.state = state;
    return out;
  }, [isDept, scope.deptId, scope.orgId, directOnly, membership, q, state]);

  const list = useInfiniteList({
    key: ["users", "org-members", params],
    rowId: (u) => (u && u.id) || undefined,
    fetch: (page) => api("/api/admin/users?" + new URLSearchParams({
      ...params, page: String(page.page), page_size: String(page.page_size),
    }).toString()),
  });

  /* 기본 조건(상태 「활성」 · 하위 포함)은 칸 자체가 말한다 — 칩은 기본과 다른 조건만 만들고, 「필터 초기화」는 기본으로 되돌린다.
     고정 도구 줄에 늘 서는 칩 줄 하나가 1366 판에서 표 행 하나를 먹는다. */
  const clearAll = () => { setQ(""); setState("active"); setDirectOnly(false); setMembership(""); };
  const chips = [
    q ? { key: "q", label: `검색: ${q}`, onDelete: () => setQ("") } : null,
    state !== "active" ? {
      key: "state",
      label: `상태: ${state ? ((STATE_OPTIONS.find((o) => o.value === state) || {}).label || state) : "보관 제외 전체"}`,
      onDelete: () => setState("active"),
    } : null,
    !isDept && membership ? {
      key: "membership",
      label: `소속: ${(MEMBERSHIP_OPTIONS.find((o) => o.value === membership) || {}).label || membership}`,
      onDelete: () => setMembership(""),
    } : null,
    isDept && directOnly ? { key: "direct", label: "직속만", onDelete: () => setDirectOnly(false) } : null,
  ].filter(Boolean);

  /* 부서 열 — 조직 보기이거나, 하위가 있는 부서를 하위 포함으로 볼 때만 뜻이 있다(말단 부서 직속은 모두 같은 부서다). */
  const showDepartment = !isDept || (!directOnly && !!scope.hasChildren);
  const columns = React.useMemo(() => memberColumns({ showDepartment }), [showDepartment]);
  const hasCondition = !!q || state !== "active" || directOnly || !!membership;
  const listState = resolveListState({
    loading: list.isLoading, error: list.isError ? list.error : null, hasCondition, count: list.rows.length,
  });

  const toolbar = (
    <Box sx={{ display: "grid", rowGap: 1.25, minWidth: 0 }}>
      <PaneToolbar>
        <Typography component="h3" sx={{ fontWeight: FONT_WEIGHT.semibold }} data-members-total="">
          구성원 {list.total != null ? `${list.total.toLocaleString("ko-KR")}명` : ""}
        </Typography>
      </PaneToolbar>
      <FilterBar
        flush
        divider={false}
        search={<SearchBox value={q} onSearch={setQ} placeholder="이름, 이메일 검색" ariaLabel="구성원 검색" />}
        toggles={isDept ? (
          <FilterToggle pressed={directOnly} onClick={() => setDirectOnly((v) => !v)}>직속만</FilterToggle>
        ) : null}
        conditions={chips.length ? {
          chips, total: list.total, unit: "명", noun: "사람", onClearAll: clearAll, clearLabel: "필터 초기화",
        } : undefined}
      >
        <FilterSelect label="상태" value={state} onChange={(v) => setState(v || "")} options={STATE_OPTIONS} allLabel="보관 제외 전체" />
        {!isDept ? (
          <FilterSelect label="소속" value={membership} onChange={(v) => setMembership(v || "")} options={MEMBERSHIP_OPTIONS} />
        ) : null}
      </FilterBar>
      {!isDept && scope.unassigned > 0 && membership !== "unassigned" ? (
        <Callout tone="warn" compact action={<Button size="sm" onClick={() => setMembership("unassigned")}>목록 보기</Button>}>
          부서도 조직 직속도 아닌 사람이 {scope.unassigned.toLocaleString("ko-KR")}명 있습니다.
        </Callout>
      ) : null}
      {!isDept && membership === "unassigned" ? (
        <Callout tone="info" compact action={<Button size="sm" href="#/integrity?tab=people">조직 정합성 열기</Button>}>
          여러 사람의 소속을 한 번에 지정하려면 조직 정합성 화면의 사람 탭을 쓰세요.
        </Callout>
      ) : null}
      {notice}
    </Box>
  );

  return (
    <WorkspacePane label={label} head={head} toolbar={toolbar} body="table">
      {isFailureState(listState) ? (
        <ListStateView state={listState} error={list.error} onRetry={() => list.refetch()} />
      ) : (
        <DataTable
          /* 채움 작업 공간이면 표가 판 몸의 남은 높이를 받아 직접 굴리고, 흐름이면 문서와 함께 흐른다(`DataTable` 이 판정한다). */
          fill
          stickyHeader
          columns={columns}
          rows={list.rows}
          rowKey={(u) => u.id}
          loading={listState === "loading"}
          onRow={(u) => nav("/users/" + u.id)}
          rowHref={(u) => "#/users/" + u.id}
          empty={hasCondition ? LIST_STATE_COPY["filtered-empty"].title : (emptyText || "속한 사람이 없습니다.")}
          emptyAction={hasCondition
            ? <Button size="sm" onClick={clearAll}>필터 초기화</Button>
            : <Button size="sm" href="#/users">사용자 화면 열기</Button>}
          list={{
            total: list.total, loaded: list.loaded, hasNext: list.hasNext,
            isFetchingNext: list.isFetchingNext, onMore: list.fetchNext, unit: "명", moreLabel: "구성원 더 보기",
          }}
        />
      )}
    </WorkspacePane>
  );
}

export default OrgMembersPane;
