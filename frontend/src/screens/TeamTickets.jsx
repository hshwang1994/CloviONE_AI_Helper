import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { Card, ErrorState, PageHeader, Skeleton, Callout } from "../ui/kit.jsx";
import { ticketColumns, GroupedTickets, TicketEditModal } from "./MyTickets.jsx";

/* 팀 공간 > 팀 티켓 — 팀 전체 티켓을 담당자별로 묶어 본다(미할당 티켓이 프로젝트별로 묶이듯).
 * 제목을 누르면 상세로. 편집은 담당자/운영자만. 상태·담당자로 거를 수 있다. */

const UNASSIGNED = "(미할당)";

// 담당자별로 묶는다. 담당자가 여럿이면 각자 그룹에 들어간다(팀 부담을 한눈에). 없으면 '(미할당)' 맨 뒤.
function groupByAssignee(rows) {
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
      <PageHeader crumbRoot="팀 공간" area="팀 티켓" title="팀 티켓" />
      <p className="k-page-help">팀 전체 티켓을 담당자별로 묶어서 봅니다. 제목을 누르면 상세 내용이 열립니다. 편집은 담당자와 운영자만 할 수 있습니다.</p>
      {q.isLoading ? <Card><Skeleton lines={6} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const data = q.data || {};
          if (data.configured === false) return <Callout tone="warn">Notion 연동이 아직 설정되지 않았습니다. 관리자에게 문의하세요.</Callout>;
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
              <div className="c-toolbar-row">
                <label className="k-field-inline"><span className="k-field-label">상태</span>
                  <select className="c-filter" value={status} onChange={(e) => setStatus(e.target.value)}>
                    <option value="active">진행 중(완료, 취소 제외)</option>
                    <option value="진행">진행</option>
                    <option value="검증">검증</option>
                    <option value="계획">계획</option>
                    <option value="이슈">이슈</option>
                    <option value="완료">완료</option>
                    <option value="취소">취소</option>
                    <option value="all">전체</option>
                  </select>
                </label>
                <label className="k-field-inline"><span className="k-field-label">담당자</span>
                  <select className="c-filter" value={who} onChange={(e) => setWho(e.target.value)}>
                    <option value="">전체</option>
                    {whoOptions.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <span className="k-field-help">{rows.length}건</span>
              </div>
              <GroupedTickets rows={rows} columns={cols} groupBy={groupByAssignee} empty="조건에 맞는 티켓이 없습니다." />
            </Card>
          );
        })()}
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </div>
  );
}
