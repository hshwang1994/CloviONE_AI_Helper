import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Callout, Card, EmptyState, ErrorState, Skeleton } from "../ui/kit.jsx";
import { FilterToggle } from "../ui/FilterBar.jsx";
import { GroupedTickets, TicketEditModal, ticketColumns, ticketConnState, useInlineStatusEdit } from "./MyTickets.jsx";
import { useTicketSignals } from "../lib/ticketSignals.js";
import { useQueryState } from "../lib/useQueryState.js";
import { priorityKo } from "../lib/priority.js";
import { groupByAssignee } from "./TeamTickets.jsx";
import { TICKET_AUTO_MAX_ROWS, useAssigneeOptions, useTicketList, useTicketMeta } from "./ticket-options.js";
import {
  TICKET_LIST_EXTRA, TICKET_RANGE_KEYS, TicketEmptyState, TicketFilterBar, applyColumnFilter, clearTicketFilters,
  hasTicketFilter, nextTicketSort, ticketAssigneeOptions, ticketFilterSpec, ticketQueryParams, ticketSortOf,
} from "./TicketFilterBar.jsx";

/* 프로젝트에 걸린 티켓 — **기존 팀 티켓 목록을 그대로 재사용**한다.
 *
 * 여기서 새 목록 화면을 만들지 않는다. 티켓 한 줄이 어떤 열을 갖고 어떻게 묶이는지는 이미
 * 네 화면(내 티켓, 미할당, 팀 티켓, 스프린트)이 같은 부품으로 정해 두었다. 한 벌 더 만들면
 * 열 하나를 고칠 때 이 화면만 안 고쳐지고, 그러면 같은 티켓이 화면마다 달라 보인다.
 *
 * 같은 부품을 쓰면서 **배선이 빠져 있었다** — 열은 정렬 표지와 머리 필터를 선언하는데(`ticketColumns`) 이 탭만 그 둘을
 * 받지 않아 머리가 눌리지 않았고, 필터 바는 「완료, 취소 포함」 한 칸짜리 줄이었다. 이제 팀 티켓과 같은 배선이다: 조건 ·
 * 정렬은 주소에 두고(`useQueryState`), 필터 바 칸과 머리 필터가 같은 상태이며, 서버가 건다(`/api/tickets/team` 의
 * `TicketListQuery` 가 정렬 · 여러 값 조건 · 범위를 받는다).
 *
 * ## 조건은 서버가 건다
 *
 * `project_id` 로 **포털 프로젝트 id** 를 보낸다. 서버가 두 축으로 맞춘다(S14):
 * 해석된 `tickets.project_uid` 와, 이관해 온 티켓이 달고 있는 옛 relation 목록
 * `project_ids`(그쪽은 `projects.notion_page_id` 로 맞춘다) — `app/tickets/query.py`.
 *
 * 🔴 예전에는 여기서 `notion_page_id` 를 보냈고, 그 값이 없으면 **목록을 아예 안 불렀다.**
 * 이관 전에는 옳았다(짝이 없으면 걸린 작업이 있을 수 없었다). 지금은 반대다 — Cutover
 * 이후에 만드는 프로젝트에는 그 칸이 영원히 없으므로, 그대로 두면 **새 프로젝트의 티켓
 * 탭이 언제까지나 비어 있다.** 티켓은 멀쩡히 붙어 있는데 화면만 비고, 오류는 안 난다.
 *
 * 조건 없이 부르는 일은 여전히 없다. `project.id` 는 이 화면이 열려 있는 한 항상 있다.
 */

/* 이 탭의 조건 — 팀 티켓의 조건에서 프로젝트를 뺀 것이다. 프로젝트는 조건이 아니라 이 탭의 문맥이다(탭이 곧 그
 * 프로젝트다). 담당자 후보는 이 프로젝트에 닿는 사람으로 서버가 좁혀 준다. */
const PROJECT_TICKET_FIELDS = ["q", "status", "priority", "difficulty", "assignee_user_id", "due", "category"];
/* `active` 는 조건이 아니라 목록의 범위다(팀 티켓의 `active` 와 같은 자리 · 같은 기본값) — 기본이 참(활성만)이라 꺼졌을 때만
 * 주소에 실린다. 주소 키는 프로젝트 상세의 탭 키(`tab` · `week`)와 겹치지 않는다. */
const PROJECT_TICKET_SPEC = ticketFilterSpec(PROJECT_TICKET_FIELDS, { ...TICKET_LIST_EXTRA, active: true });
/* 빈 목록이 「조건 때문」인지 가르는 키 — 칸의 조건에 머리 필터의 범위를 더한다. */
const PROJECT_TICKET_FILTER_KEYS = [...PROJECT_TICKET_FIELDS, ...TICKET_RANGE_KEYS];

/* 이 티켓을 열고 「목록」을 누르면 **여기로** 돌아온다 (지시 19 · `lib/listReturn.js`).
 *
 * 한때 `"/projects"` 를 넘겼다. 그 값은 목록 → 상세로 들어갈 때 목록이 자기를 가리키라고
 * 쓰는 것이고, 여기는 목록이 아니라 **상세 안의 탭**이다 — 그래서 프로젝트 안에서 티켓
 * 하나를 열어 본 사람이 「목록」을 누르면 읽던 프로젝트가 통째로 사라지고 프로젝트 목록
 * 으로 떨어졌다. 탭까지 실어 보낸다: 티켓 탭에서 나갔으면 티켓 탭으로 돌아온다. 걸어 둔 조건 ·
 * 정렬도 지금 주소 그대로 실어 보낸다 — 조건이 주소에 있으므로 주소가 곧 돌아올 자리다.
 * (`ProjectDocuments.jsx` 가 이미 이렇게 하고 있었다 — 세 탭 중 하나만 맞았다.) */
function backToProject(projectId, search) {
  const params = new URLSearchParams(search || "");
  params.set("tab", "tickets");
  return "/projects/" + encodeURIComponent(projectId) + "?" + params.toString();
}

function ProjectTicketList({ pageId }) {
  const nav = useNavigate();
  const loc = useLocation();
  const signalsOf = useTicketSignals();
  const statusEdit = useInlineStatusEdit();
  const [editing, setEditing] = React.useState(null);
  const [filters, setFilters] = useQueryState(PROJECT_TICKET_SPEC);

  // 팀 티켓 화면과 같은 기본값(활성만) — 다른 이유는 팀 티켓의 activeToggle 주석과 같다:
  // 완료·취소까지 항상 섞으면 "지금 할 일"을 찾는 화면이 끝난 일로 덮인다.
  //
  // 🔴 서버 기본값(active=true)에 기대지 않고 **항상 명시적으로 보낸다.** 예전에는 이 값을
  // 아예 안 보냈다 — 그러면 완료·취소 티켓은 이 탭에서 영영 볼 방법이 없는데도 "총 N건"이
  // 마치 이 프로젝트의 전체 티켓 수인 것처럼 보였다(팀 티켓엔 있는 '완료, 취소 포함' 스위치가
  // 여기만 없었다 — 같은 목록 부품을 재사용한다고 적어 놓고 실제로는 그 기능만 빠져 있었다).
  const qs = ticketQueryParams(filters, PROJECT_TICKET_FIELDS, {
    project_id: pageId,
    active: filters.active ? "true" : "false",
  }).toString();
  /* 범위(완료·취소 포함)나 조건을 바꾸면 받아 둔 묶음은 질의 키가 바뀌며 함께 버려진다 —
     되돌릴 쪽 번호가 없다. */
  const q = useTicketList("/api/tickets/team", qs);
  const metaQ = useTicketMeta(true);
  const assigneesQ = useAssigneeOptions(true, pageId);
  const meta = metaQ.data || {};
  const colFilterOptions = {
    status: meta.statuses || [],
    priority: (meta.priorities || []).map((p) => ({ value: p, label: priorityKo(p) })),
    difficulty: meta.difficulties || [],
  };
  // 담당자 후보는 이 프로젝트에 닿는 사람이다 — 필터 바가 따로 받는 조직 전체 후보 대신 이 목록을 쓴다.
  const assigneeCandidates = {
    assignee_user_id: {
      items: ticketAssigneeOptions(assigneesQ.data && assigneesQ.data.assignees),
      loading: assigneesQ.isLoading,
    },
  };
  const clearFilters = () => setFilters({ ...clearTicketFilters(PROJECT_TICKET_FIELDS), ...TICKET_LIST_EXTRA, active: filters.active });

  // 필터 바의 켬/끔은 스위치가 아니라 34 중립 단추다 — 켜져 있을 때만 눌린 면이다(핸드오프 RULES §3 · 계획 P-14).
  const activeToggle = (
    <FilterToggle pressed={!filters.active} onClick={() => setFilters({ active: !filters.active })}>
      완료, 취소 포함
    </FilterToggle>
  );

  if (q.isLoading) return <Card><Skeleton lines={6} /></Card>;
  if (q.isError) return <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} />;

  /* 목록 밖의 값(연결 상태)은 첫 묶음 원본이 들고 온다 — 묶음마다 같다. */
  const data = q.first || {};
  // 연동 미설정, 조회 실패 안내는 티켓 화면들과 같은 함수를 쓴다(문구가 갈라지지 않게).
  const conn = ticketConnState(data);
  if (conn) return conn;
  if (data.ok === false) {
    return <Callout tone="danger">{data.error || "티켓을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}</Callout>;
  }

  const rows = q.rows;
  const cols = ticketColumns({
    onEdit: setEditing,
    onOpen: (t) => nav("/tickets/" + t.id, { state: { from: backToProject(pageId, loc.search) } }),
    signalsOf,
    statusEdit,
  });

  return (
    <>
    {/* 팀 티켓과 같은 필터 바다 — 검색 → 조건 칸 → 오른쪽 끝 「완료, 취소 포함」(보기 방식이라 칸 흐름 끝이 아니라 `end`,
        조합 계약 C-1). 조건이 있으면 같은 면 안 둘째 줄이 조건 칩 · 결과 수 · 「필터 지우기」다. */}
    <TicketFilterBar
      fields={PROJECT_TICKET_FIELDS} value={filters} onChange={setFilters}
      total={q.total} end={activeToggle}
      options={assigneeCandidates}
      onClear={clearFilters}
    />
    <GroupedTickets
      placement="surface"
      rows={rows} columns={cols} groupBy={groupByAssignee}
      sort={ticketSortOf(filters)}
      onSort={(key) => setFilters(nextTicketSort(filters, key))}
      filters={filters}
      onFilter={(field, next) => setFilters(applyColumnFilter(field, next))}
      filterOptions={colFilterOptions}
      emptyState={
        <TicketEmptyState
          filtered={hasTicketFilter(filters, PROJECT_TICKET_FILTER_KEYS)}
          onClear={clearFilters}
          title="이 프로젝트에 등록된 티켓이 없습니다."
          help="티켓을 추가할 때 이 프로젝트를 고르면 여기에 모입니다."
        />
      }
      list={{
        total: q.total, loaded: q.loaded,
        hasNext: q.hasNext, isFetchingNext: q.isFetchingNext, onMore: q.fetchNext,
        moreLabel: "티켓 더 보기",
        autoMaxRows: TICKET_AUTO_MAX_ROWS,
      }}
    />
    <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </>
  );
}

export function ProjectTickets({ project }) {
  const projectId = (project && project.id) || "";
  if (!projectId) {
    // 프로젝트를 아직 못 읽은 순간뿐이다. 조건 없이 부르면 회사의 모든 티켓이 이
    // 프로젝트의 목록으로 뜬다(서버가 진행률에서 같은 함정을 피한 이유와 같다).
    return (
      <Card>
        <EmptyState
          art="tickets"
          title="이 프로젝트에 등록된 티켓이 없습니다."
          situation="아직 이 프로젝트로 추가한 티켓이 하나도 없습니다."
          help="티켓을 추가할 때 이 프로젝트를 고르면 여기에 모입니다."
        />
      </Card>
    );
  }
  return <ProjectTicketList pageId={projectId} />;
}
