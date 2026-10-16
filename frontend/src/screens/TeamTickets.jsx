import React from "react";
import { useNavigate } from "react-router-dom";
import { Card, Callout, ErrorState, PageHeader, Skeleton } from "../ui/kit.jsx";
import { useQueryState } from "../lib/useQueryState.js";
import { DepartmentFilter, unmatchedLabel } from "../ui/filters.jsx";
import { FilterToggle } from "../ui/FilterBar.jsx";
import { ticketColumns, GroupedTickets, TicketEditModal, ticketConnState, useInlineStatusEdit } from "./MyTickets.jsx";
import { useTicketSignals } from "../lib/ticketSignals.js";
import { useListMemory } from "../lib/listReturn.js";
import { TICKET_AUTO_MAX_ROWS, useAssigneeOptions, useTicketList, useTicketMeta } from "./ticket-options.js";
import {
  TicketEmptyState, TicketFilterBar, applyColumnFilter, clearTicketFilters, hasTicketFilter,
  nextTicketSort, ticketFilterSpec, ticketQueryParams, ticketSortOf, TICKET_LIST_EXTRA,
} from "./TicketFilterBar.jsx";
import { priorityKo } from "../lib/priority.js";

/* 팀 공간 > 팀 티켓 — 팀 전체 티켓을 담당자별로 묶어 본다(미할당 티켓이 프로젝트별로 묶이듯).
 * 제목을 누르면 상세로. 보이는 티켓은 담당자가 아니어도 고칠 수 있고, 고친 내용은 이력에 남는다.
 * 조건은 서버가 걸고, 그 조건은 주소에 남는다. */

const UNASSIGNED = "(미할당)";

/* 이 화면이 쓰는 조건. 담당자가 여기에만 있는 이유: 서버가 `assignee_user_id` 를 이 경로에서만
 * 받는다(내 티켓은 담당자가 언제나 나, 미할당은 정의상 담당자가 없다).
 *
 * 담당자는 **앱 user_id** 로 나간다(스펙 §12.3 — 브라우저는 소스 user id 를 주지도 받지도
 * 않는다). 그래서 후보는 앱에 연결된 사람뿐이고, 연결 안 된 Notion 계정만 담당자인 티켓은
 * 이름으로 거를 수 없다. 예전처럼 화면에 온 이름으로 거르면 **지금 페이지 안에서만** 걸러져
 * "총 40건인데 2건만 보인다"가 된다. */
const TEAM_FIELDS = ["q", "project_id", "status", "priority", "difficulty", "assignee_user_id", "due", "category"];
/* `active` 는 필터가 아니라 목록의 범위다 — 서버의 `/team?active=` 가 그대로 받는다.
 * 기본이 참(활성만)이라 꺼졌을 때만 주소에 실린다. */
/* `dept` 도 필터가 아니라 **목록의 범위**다(`active` 와 같은 자리) — 서버의
 * `/team?department_id=` 가 그대로 받는다. `TEAM_FIELDS` 에 넣지 않는 이유: 그 배열은
 * 주소 키와 API 키가 같은 것들만 담는 목록이고, 여기서 이름이 다르다. */
const TEAM_SPEC = ticketFilterSpec(TEAM_FIELDS, { ...TICKET_LIST_EXTRA, active: true, dept: "" });

/* 담당자별로 묶는다. 담당자가 여럿이면 각자 그룹에 들어간다(팀 부담을 한눈에). 없으면 '(미할당)' 맨 뒤.
 * export인 이유: 스프린트 회의 화면(Sprint.jsx)의 담당자별 티켓 목록이 같은 규칙을 써야 한다.
 * 예전엔 그 화면이 카운트 표라 이 함수가 필요 없었는데, 담당자별 목록으로 바꾸면서 같은 로직을
 * 한 벌 더 쓸 뻔했다 — 정렬(미할당을 맨 뒤로)이나 다중 담당 처리가 두 화면에서 어긋나면
 * "팀 티켓에선 두 사람 밑에 보이는 티켓이 스프린트에선 한 사람 밑에만 보이는" 식으로 갈라진다. */
export function groupByAssignee(rows) {
  const map = new Map();
  for (const t of rows) {
    const names = (t.assignee_names || []).length ? t.assignee_names : [UNASSIGNED];
    for (const n of names) {
      if (!map.has(n)) map.set(n, []);
      map.get(n).push(t);
    }
  }
  return [...map.entries()].sort((a, b) => {
    if (a[0] === UNASSIGNED) return 1;
    if (b[0] === UNASSIGNED) return -1;
    return a[0].localeCompare(b[0]);
  });
}

export function TeamTickets() {
  useListMemory("/team-tickets");
  const signalsOf = useTicketSignals();
  const statusEdit = useInlineStatusEdit();
  const nav = useNavigate();
  const [filters, setFilters] = useQueryState(TEAM_SPEC);
  const [editing, setEditing] = React.useState(null);
  const qs = ticketQueryParams(filters, TEAM_FIELDS, {
    active: filters.active ? "true" : "false",
    ...(filters.dept ? { department_id: filters.dept } : {}),
  }).toString();
  const q = useTicketList("/api/tickets/team", qs);
  const metaQ = useTicketMeta(true);
  const assigneesQ = useAssigneeOptions(true);
  const meta = metaQ.data || {};
  const colFilterOptions = {
    status: meta.statuses || [],
    priority: (meta.priorities || []).map((p) => ({ value: p, label: priorityKo(p) })),
    difficulty: meta.difficulties || [],
  };
  const colEntityOptions = {
    assignee_user_id: ((assigneesQ.data && assigneesQ.data.assignees) || []).map((c) => ({
      value: c.user_id, label: c.display_name,
    })),
  };
  /* 여기에 「지금 동기화」를 부르는 mutation 이 있었다. 그 버튼은 `POST /api/tickets/sync` 로
     노션을 읽어 이 서버의 `tickets` 표에 덮어썼는데, 지금은 그 표가 사본이 아니라 정본이라
     밖에서 덮어쓸 것이 없다. 엔드포인트 자체가 없어졌으므로 화면에서도 부르지 않는다. */

  // 완료·취소까지 볼지는 필터 줄 안에 둔다 — 조건과 떨어져 있으면 목록이 왜 이만큼인지 보이지 않는다.
  // 필터 바의 켬/끔은 스위치가 아니라 34 중립 단추다 — 켜져 있을 때만 눌린 면이다(핸드오프 RULES §3 · 계획 P-14).
  const activeToggle = (
    <FilterToggle pressed={!filters.active} onClick={() => setFilters({ active: !filters.active })}>
      완료, 취소 포함
    </FilterToggle>
  );

  /* 부서 후보는 **목록 응답이** 들고 온다(서버가 계산한 내 조회 범위). 별도 질의를 만들지
     않는 이유: 목록과 후보가 다른 시점의 범위를 말하면 고를 수는 있는데 결과가 비는 상자가
     생긴다. */
  /* 부서는 **scope** 다 — 줄의 맨 앞(C2 그룹 순서). 「완료, 취소 포함」은 조건이 아니라 보기
     방식이라 필터 바 오른쪽 끝(`end`)에 선다. 칸 폭은 줄 칸 표가 정한다 — 부서는 경로라 wide 칸이고(`DepartmentFilter` 기본),
     이 화면만의 폭을 두지 않는다. */
  const scopeControls = (
    <DepartmentFilter
      departments={q.first && q.first.departments}
      value={filters.dept}
      onChange={(v) => setFilters({ dept: v })}
    />
  );
  /* 부서 조건도 칩을 가진다 — 모든 조건은 칩이 있고 조건 수는 칩 수다(조합 계약 C-1). 이름은 칸과 같은 경로다. */
  const deptOption = ((q.first && q.first.departments && q.first.departments.options) || []).find((o) => o.id === filters.dept);
  const deptChips = filters.dept ? [{
    key: "dept",
    label: `부서: ${deptOption ? ((deptOption.path || []).map((n) => n.name).join(" › ") || deptOption.name) : unmatchedLabel(filters.dept, !q.first)}`,
    onDelete: () => setFilters({ dept: "" }),
  }] : [];

  return (
    <div className="c-screen">
      {/* 머리의 넘침 메뉴에는 「지금 동기화」 하나만 들어 있었다. 그 동작이 없어져 메뉴에
          담을 것이 남지 않았으므로 메뉴 자체를 뺀다 — 눌러도 빈 목록만 열리는 버튼은
          사용자에게 자기가 못 쓰는 기능이 있다고 말하는 셈이다. */}
      <PageHeader
        crumbRoot="팀 업무" area="팀 티켓" title="팀 티켓"
        description="팀 전체 티켓을 담당자별로 묶어서 봅니다. 보이는 티켓은 담당자가 아니어도 수정할 수 있고, 수정한 내용은 이력에 남습니다."
      />
      {q.isLoading ? <Card><Skeleton lines={6} /></Card>
        : q.isError ? <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          /* 목록 밖의 값(부서 후보·연결 상태)은 첫 묶음 원본이 들고 온다 — 묶음마다 같다. */
          const data = q.first || {};
          // 연동 미설정/실패 안내는 내 티켓 화면과 같은 함수를 쓴다(문구가 화면마다 갈라지지 않게).
          const conn = ticketConnState(data);
          if (conn) return conn;
          if (data.ok === false) return <Callout tone="danger">{data.error || "티켓을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}</Callout>;
          const rows = q.rows;
          const cols = ticketColumns({ onEdit: setEditing, filterAssignee: true, signalsOf, statusEdit, onOpen: (t) => nav("/tickets/" + t.id, { state: { from: "/team-tickets" } }) });
          return (
            <>
              {/* 여기 미러 신선도 안내가 있었다. 서버가 `sync` 블록을 더 이상 안 싣는다 —
                  티켓 표가 이 서버의 정본이라 낡을 것이 없다(S14). */}
              <TicketFilterBar
                fields={TEAM_FIELDS} value={filters} onChange={setFilters}
                total={q.total} scope={scopeControls} chips={deptChips} end={activeToggle}
                onClear={() => setFilters({ ...clearTicketFilters(TEAM_FIELDS), dept: "", ...TICKET_LIST_EXTRA, active: filters.active })}
              />
              <GroupedTickets
                placement="surface"
                rows={rows} columns={cols} groupBy={groupByAssignee}
                sort={ticketSortOf(filters)}
                onSort={(key) => setFilters(nextTicketSort(filters, key))}
                filters={filters}
                onFilter={(field, next) => setFilters(applyColumnFilter(field, next))}
                filterOptions={colFilterOptions}
                entityOptions={colEntityOptions}
                emptyState={
                  <TicketEmptyState
                    filtered={hasTicketFilter(filters, TEAM_FIELDS) || !!filters.dept}
                    onClear={() => setFilters({ ...clearTicketFilters(TEAM_FIELDS), dept: "", ...TICKET_LIST_EXTRA, active: true })}
                    title="팀 티켓이 없습니다."
                    help={filters.active
                      ? "미완료 팀 티켓이 없습니다. ‘완료, 취소 포함’을 누르면 끝난 티켓까지 봅니다."
                      : "이 팀에 티켓이 없습니다."}
                  />
                }
                list={{
                  total: q.total, loaded: q.loaded,
                  hasNext: q.hasNext, isFetchingNext: q.isFetchingNext, onMore: q.fetchNext,
                  moreLabel: "티켓 더 보기",
                  /* 담당자별로 묶은 이 표는 가상화가 없다(D-354 · D-361) — 자동 로딩에만
                     상한을 두고, 「더 보기」로는 계속 받는다. */
                  autoMaxRows: TICKET_AUTO_MAX_ROWS,
                }}
              />
            </>
          );
        })()}
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </div>
  );
}
