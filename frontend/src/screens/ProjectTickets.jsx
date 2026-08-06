import React from "react";
import { useNavigate } from "react-router-dom";
import Typography from "@mui/material/Typography";
import { Callout, Card, EmptyState, ErrorState, Skeleton } from "../ui/kit.jsx";
import { Pager } from "../ui/Pager.jsx";
import { GroupedTickets, TicketEditModal, ticketColumns, ticketConnState } from "./MyTickets.jsx";
import { groupByAssignee } from "./TeamTickets.jsx";
import { ticketRows, useTicketList } from "./ticket-options.js";

/* 프로젝트에 걸린 티켓 — **기존 팀 티켓 목록을 그대로 재사용**한다.
 *
 * 여기서 새 목록 화면을 만들지 않는다. 티켓 한 줄이 어떤 열을 갖고 어떻게 묶이는지는 이미
 * 네 화면(내 티켓, 미할당, 팀 티켓, 스프린트)이 같은 부품으로 정해 두었다. 한 벌 더 만들면
 * 열 하나를 고칠 때 이 화면만 안 고쳐지고, 그러면 같은 티켓이 화면마다 달라 보인다.
 *
 * ## 조건은 서버가 건다
 *
 * `project_id` 는 **노션 프로젝트 page id** 다(app/tickets/repository.py 가 `project_ids`
 * 다중값과 맞춘다). 그래서 노션 짝이 없는 포털 전용 프로젝트는 걸린 작업이 있을 수 없고,
 * 그때는 목록을 아예 부르지 않는다 - 조건 없이 부르면 회사의 모든 티켓이 이 프로젝트의
 * 목록으로 뜬다(서버가 진행률에서 같은 함정을 피한 이유와 같다).
 *
 * 두 부품으로 나눈 이유는 훅이다. 목록 질의는 훅이라 조건부로 부를 수 없으므로, "부를지"를
 * 정하는 쪽과 "부르는" 쪽을 나눈다.
 */

function ProjectTicketList({ pageId, page, onPage }) {
  const nav = useNavigate();
  const [editing, setEditing] = React.useState(null);

  const params = new URLSearchParams();
  params.set("project_id", pageId);
  if (page > 1) params.set("page", String(page));
  const q = useTicketList("/api/tickets/team", params.toString());

  if (q.isPending) return <Card><Skeleton lines={6} /></Card>;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const data = q.data || {};
  // 연동 미설정, 조회 실패 안내는 티켓 화면들과 같은 함수를 쓴다(문구가 갈라지지 않게).
  const conn = ticketConnState(data);
  if (conn) return conn;
  if (data.ok === false) {
    return <Callout tone="danger">{data.error || "티켓을 불러오지 못했습니다."}</Callout>;
  }

  const rows = ticketRows(data);
  const cols = ticketColumns({
    onEdit: setEditing,
    onOpen: (t) => nav("/tickets/" + t.id, { state: { from: "/projects" } }),
  });

  return (
    <Card>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }} aria-live="polite">
        총 {data.total != null ? data.total : rows.length}건
      </Typography>
      <GroupedTickets
        rows={rows} columns={cols} groupBy={groupByAssignee}
        emptyState={
          <EmptyState
            art="tickets"
            title="이 프로젝트에 걸린 티켓이 없습니다"
            help="노션 작업의 프로젝트 속성에 이 프로젝트를 걸면 여기에 모입니다."
          />
        }
      />
      <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={onPage} />
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </Card>
  );
}

export function ProjectTickets({ project, page, onPage }) {
  const pageId = (project && project.notion_page_id) || "";
  if (!pageId) {
    return (
      <Card>
        <EmptyState
          art="tickets"
          title="연결된 노션 작업이 없습니다"
          situation="이 프로젝트는 포털에서만 관리하는 프로젝트라 노션 페이지 짝이 없습니다."
          help="노션 작업은 프로젝트가 노션 페이지와 연결돼 있을 때만 여기에 모입니다."
        />
      </Card>
    );
  }
  return <ProjectTicketList pageId={pageId} page={page} onPage={onPage} />;
}
