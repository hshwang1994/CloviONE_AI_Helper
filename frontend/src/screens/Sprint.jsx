import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { Button, Callout, Card, DataTable, ErrorState, PageHeader, Skeleton, StatCard } from "../ui/kit.jsx";
import { ticketColumns, GroupedTickets, useClaim, TicketEditModal } from "./MyTickets.jsx";

/* 도우미 > 주간 스프린트 회의. 한 화면에서 (1) 지난주 완료 현황(담당자별), (2) 배분 대상(미할당),
 * (3) 계획 티켓을 본다. 배정/편집은 회의 중 바로 — 기존 티켓 API 재사용. 데이터는 조회 전용. */

function mondayOf(d) {
  const x = new Date(d);
  const back = (x.getDay() + 6) % 7; // 월요일 기준
  x.setDate(x.getDate() - back); x.setHours(0, 0, 0, 0);
  return x;
}
function isoDate(d) { const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }

export function Sprint() {
  const nav = useNavigate();
  const claim = useClaim();
  const [offset, setOffset] = React.useState(0); // 0=이번 주, -1=지난 주 …
  const [editing, setEditing] = React.useState(null);

  const monday = addDays(mondayOf(new Date()), offset * 7);
  const start = isoDate(monday);
  const end = isoDate(addDays(monday, 7));
  const sunday = isoDate(addDays(monday, 6));

  const q = useQuery({
    queryKey: ["sprint", start, end],
    queryFn: () => api(`/api/sprint/summary?start=${start}&end=${end}`),
    retry: false,
  });

  const weekLabel = offset === 0 ? "이번 주" : offset === -1 ? "지난 주" : offset === 1 ? "다음 주" : `${start} ~ ${sunday}`;
  const nudge = (
    <div className="k-row-actions">
      <Button size="sm" onClick={() => setOffset((o) => o - 1)}>◀ 이전 주</Button>
      <Button size="sm" disabled={offset === 0} onClick={() => setOffset(0)}>이번 주</Button>
      <Button size="sm" onClick={() => setOffset((o) => o + 1)}>다음 주 ▶</Button>
    </div>
  );

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="도우미" area="스프린트 회의" title="스프린트 회의" actions={nudge} />
      <p className="k-page-help">{weekLabel} ({start} ~ {sunday}) 기준입니다. 완료 현황을 함께 보고, 미할당 티켓을 배분하고, 계획을 논의하세요. 회의 중 바로 배정·수정할 수 있습니다.</p>

      {q.isLoading ? <Card><Skeleton lines={8} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const d = q.data || {};
          if (d.configured === false) return <Callout tone="warn">Notion 연동이 아직 설정되지 않았습니다. 관리자에게 문의하세요.</Callout>;
          if (d.ok === false) return <Callout tone="danger">{d.error || "불러오지 못했습니다."}</Callout>;
          const devs = (d.developers || []).filter((x) => x.has_tickets);
          const team = d.team || {};
          const unassigned = d.unassigned || [];
          const planned = d.planned || [];
          const onOpen = (t) => nav("/tickets/" + t.id);
          return (
            <>
              <section className="devrep-sec">
                <h2 className="devrep-sec-title">완료 현황 (담당자별)</h2>
                <div className="dash-grid">
                  <StatCard value={team.done || 0} label="완료(건)" />
                  <StatCard value={team.in_progress || 0} label="진행 중(건)" />
                  <StatCard value={team.est_done_total || 0} label="완료 업무량(인일)" />
                  <StatCard value={team.overdue || 0} label="지연(건)" kind={team.overdue ? "warn" : undefined} />
                </div>
                <Card>
                  <DataTable
                    columns={[
                      { key: "name", label: "개발자" },
                      { key: "done", label: "완료", align: "right", render: (r) => r.done },
                      { key: "prog", label: "진행", align: "right", render: (r) => r.prog },
                      { key: "verify", label: "검증", align: "right", render: (r) => r.verify },
                      { key: "plan", label: "계획", align: "right", render: (r) => r.plan },
                      { key: "est_done", label: "완료 업무량", align: "right", render: (r) => r.est_done },
                    ]}
                    rows={devs} rowKey={(r) => r.name}
                    empty="이 주에 완료·진행한 티켓이 있는 담당자가 없습니다." />
                </Card>
              </section>

              <section className="devrep-sec">
                <h2 className="devrep-sec-title">티켓 배분 (미할당 {unassigned.length}건)</h2>
                <Card>
                  <p className="k-field-help">담당자가 없는 활성 티켓입니다. ‘나에게 배정’ 또는 ‘편집’으로 담당자를 지정하세요.</p>
                  <GroupedTickets
                    rows={unassigned}
                    columns={ticketColumns({ onEdit: setEditing, onClaim: (t) => claim.mutate(t.id), onOpen })}
                    empty="미할당 티켓이 없습니다." />
                </Card>
              </section>

              <section className="devrep-sec">
                <h2 className="devrep-sec-title">계획 논의 (계획 {planned.length}건)</h2>
                <Card>
                  <GroupedTickets
                    rows={planned}
                    columns={ticketColumns({ showAssignee: true, onEdit: setEditing, onOpen })}
                    empty="계획 상태 티켓이 없습니다." />
                </Card>
              </section>

              <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
            </>
          );
        })()}
    </div>
  );
}
