import React from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Card, Callout, ErrorState, PageHeader, Skeleton, useToast } from "../ui/kit.jsx";
import { Pager } from "../ui/Pager.jsx";
import { useQueryState } from "../lib/useQueryState.js";
import { ticketColumns, GroupedTickets, TicketEditModal, ticketConnState, TicketSyncBanner } from "./MyTickets.jsx";
import { ticketRows, useTicketList } from "./ticket-options.js";
import { invalidateTicketViews } from "./ticket-views.js";
import {
  TicketEmptyState, TicketFilterBar, clearTicketFilters, hasTicketFilter,
  ticketFilterSpec, ticketQueryParams,
} from "./TicketFilterBar.jsx";

/* 팀 공간 > 팀 티켓 — 팀 전체 티켓을 담당자별로 묶어 본다(미할당 티켓이 프로젝트별로 묶이듯).
 * 제목을 누르면 상세로. 편집은 담당자/운영자만. 조건은 서버가 걸고, 그 조건은 주소에 남는다. */

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
const TEAM_SPEC = ticketFilterSpec(TEAM_FIELDS, { page: 1, active: true });
const PAGE_RESET = { reset: ["page"] };

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
  const nav = useNavigate();
  const [filters, setFilters] = useQueryState(TEAM_SPEC, PAGE_RESET);
  const [editing, setEditing] = React.useState(null);
  const qs = ticketQueryParams(filters, TEAM_FIELDS, { active: filters.active ? "true" : "false" }).toString();
  const q = useTicketList("/api/tickets/team", qs);
  const toast = useToast();
  const qc = useQueryClient();
  // 티켓 동기화(FN-03) — team_docs 화면과 같은 패턴, app/tickets/router.py trigger_sync의
  // 주석이 그 패턴을 그대로 따르라고 명시한다.
  const sync = useMutation({
    mutationFn: () => api("/api/tickets/sync", { method: "POST", body: {} }),
    onSuccess: (res) => {
      invalidateTicketViews(qc, { refetchType: "all" });
      const st = res && res.sync;
      if (st && st.status === "error") toast("동기화 실패: " + (st.error || "Notion 연결 확인 필요"), "error");
      else toast("동기화했습니다. 티켓 " + (st ? st.ticket_count : 0) + "개.", "success");
    },
    onError: (e) => toast((e && e.message) || "동기화하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error"),
  });

  // 완료·취소까지 볼지는 필터 줄 안에 둔다 — 조건과 떨어져 있으면 목록이 왜 이만큼인지 보이지 않는다.
  const activeToggle = (
    <FormControlLabel
      sx={{ m: 0 }}
      control={
        <Switch
          size="small"
          checked={!filters.active}
          onChange={(e) => setFilters({ active: !e.target.checked })}
        />
      }
      label={<Typography variant="body2">완료, 취소 포함</Typography>}
    />
  );

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="팀 티켓" title="팀 티켓" spot="teamspace" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5, maxWidth: "70ch" }}>
        팀 전체 티켓을 담당자별로 묶어서 봅니다. 제목을 누르면 상세 내용이 열립니다. 수정은 담당자와 운영자만 할 수 있습니다.
      </Typography>
      {q.isPending ? <Card><Skeleton lines={6} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const data = q.data || {};
          // 연동 미설정/실패 안내는 내 티켓 화면과 같은 함수를 쓴다(문구가 화면마다 갈라지지 않게).
          const conn = ticketConnState(data);
          if (conn) return conn;
          if (data.ok === false) return <Callout tone="danger">{data.error || "티켓을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}</Callout>;
          const rows = ticketRows(data);
          const cols = ticketColumns({ onEdit: setEditing, onOpen: (t) => nav("/tickets/" + t.id, { state: { from: "/team-tickets" } }) });
          return (
            <>
              <TicketSyncBanner
                sync={data.sync} canSync={data.can_sync}
                onSync={() => sync.mutate()} syncing={sync.isPending}
              />
              <TicketFilterBar
                fields={TEAM_FIELDS} value={filters} onChange={setFilters}
                total={data.total} extra={activeToggle}
                onClear={() => setFilters(clearTicketFilters(TEAM_FIELDS))}
              />
              <Card>
                <GroupedTickets
                  rows={rows} columns={cols} groupBy={groupByAssignee}
                  emptyState={
                    <TicketEmptyState
                      filtered={hasTicketFilter(filters, TEAM_FIELDS)}
                      onClear={() => setFilters(clearTicketFilters(TEAM_FIELDS))}
                      title="팀 티켓이 없습니다"
                      help={filters.active
                        ? "지금 진행 중인 팀 티켓이 없습니다. ‘완료, 취소 포함’을 켜면 끝난 티켓까지 봅니다."
                        : "이 팀에 티켓이 없습니다."}
                    />
                  }
                />
                <Pager page={data.page} pageSize={data.page_size} total={data.total}
                       onPage={(p) => setFilters({ page: p })} />
              </Card>
            </>
          );
        })()}
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </div>
  );
}
