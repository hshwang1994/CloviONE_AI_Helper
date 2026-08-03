import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Card, Callout, ErrorState, PageHeader, Skeleton } from "../ui/kit.jsx";
import { EMPTYABLE_SELECT, ticketColumns, GroupedTickets, StatusFilter, TicketEditModal, TicketToolbar, ticketConnState } from "./MyTickets.jsx";

/* 팀 공간 > 팀 티켓 — 팀 전체 티켓을 담당자별로 묶어 본다(미할당 티켓이 프로젝트별로 묶이듯).
 * 제목을 누르면 상세로. 편집은 담당자/운영자만. 상태·담당자로 거를 수 있다. */

const UNASSIGNED = "(미할당)";

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
  const [status, setStatus] = React.useState("active");
  const [who, setWho] = React.useState("");
  const [editing, setEditing] = React.useState(null);
  const wantAll = status !== "active";
  const q = useQuery({
    queryKey: ["tickets", "team", wantAll],
    queryFn: () => api("/api/tickets/team?active=" + (wantAll ? "false" : "true")),
    retry: false,
  });

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="팀 티켓" title="팀 티켓" spot="teamspace" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5, maxWidth: "70ch" }}>
        팀 전체 티켓을 담당자별로 묶어서 봅니다. 제목을 누르면 상세 내용이 열립니다. 편집은 담당자와 운영자만 할 수 있습니다.
      </Typography>
      {q.isLoading ? <Card><Skeleton lines={6} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const data = q.data || {};
          // 연동 미설정/실패 안내는 내 티켓 화면과 같은 함수를 쓴다(문구가 화면마다 갈라지지 않게).
          const conn = ticketConnState(data);
          if (conn) return conn;
          if (data.ok === false) return <Callout tone="danger">{data.error || "티켓을 불러오지 못했습니다."}</Callout>;
          const all = Array.isArray(data.tickets) ? data.tickets : [];
          const byStatus = (status === "active" || status === "all") ? all : all.filter((t) => t.status === status);
          const whoOptions = [...new Set(all.flatMap((t) => ((t.assignee_names || []).length ? t.assignee_names : [UNASSIGNED])))].sort((a, b) => a.localeCompare(b));
          const rows = who
            ? byStatus.filter((t) => (who === UNASSIGNED ? !(t.assignee_names || []).length : (t.assignee_names || []).includes(who)))
            : byStatus;
          const cols = ticketColumns({ onEdit: setEditing, onOpen: (t) => nav("/tickets/" + t.id) });
          return (
            <Card>
              <TicketToolbar count={rows.length}>
                <StatusFilter value={status} onChange={setStatus} />
                <TextField select size="small" label="담당자" {...EMPTYABLE_SELECT} value={who} onChange={(e) => setWho(e.target.value)} sx={{ minWidth: "11rem" }}>
                  <MenuItem value="">전체</MenuItem>
                  {whoOptions.map((n) => <MenuItem key={n} value={n}>{n}</MenuItem>)}
                </TextField>
              </TicketToolbar>
              <GroupedTickets rows={rows} columns={cols} groupBy={groupByAssignee} empty="조건에 맞는 티켓이 없습니다." />
            </Card>
          );
        })()}
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </div>
  );
}
