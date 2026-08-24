import React from "react";
import { useNavigate } from "react-router-dom";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
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

function ProjectTicketList({ pageId, page, onPage }) {
  const nav = useNavigate();
  const [editing, setEditing] = React.useState(null);
  // 팀 티켓 화면과 같은 기본값(활성만) — 다른 이유는 팀 티켓의 activeToggle 주석과 같다:
  // 완료·취소까지 항상 섞으면 "지금 할 일"을 찾는 화면이 끝난 일로 덮인다.
  //
  // 🔴 서버 기본값(active=true)에 기대지 않고 **항상 명시적으로 보낸다.** 예전에는 이 값을
  // 아예 안 보냈다 — 그러면 완료·취소 티켓은 이 탭에서 영영 볼 방법이 없는데도 "총 N건"이
  // 마치 이 프로젝트의 전체 티켓 수인 것처럼 보였다(팀 티켓엔 있는 '완료, 취소 포함' 스위치가
  // 여기만 없었다 — 같은 목록 부품을 재사용한다고 적어 놓고 실제로는 그 기능만 빠져 있었다).
  const [includeDone, setIncludeDone] = React.useState(false);

  const params = new URLSearchParams();
  params.set("project_id", pageId);
  params.set("active", includeDone ? "false" : "true");
  if (page > 1) params.set("page", String(page));
  const q = useTicketList("/api/tickets/team", params.toString());

  // 범위(완료·취소 포함 여부)를 바꾸면 페이지는 처음으로 - 필터를 바꿨는데 3페이지에 남으면
  // 빈 목록을 "티켓이 없다"로 읽는다(다른 티켓 화면들과 같은 규약).
  const toggleIncludeDone = (checked) => { setIncludeDone(checked); onPage(1); };
  const activeToggle = (
    <FormControlLabel
      sx={{ m: 0 }}
      control={<Switch size="small" checked={includeDone} onChange={(e) => toggleIncludeDone(e.target.checked)} />}
      label={<Typography variant="body2">완료, 취소 포함</Typography>}
    />
  );

  if (q.isPending) return <Card><Skeleton lines={6} /></Card>;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  const data = q.data || {};
  // 연동 미설정, 조회 실패 안내는 티켓 화면들과 같은 함수를 쓴다(문구가 갈라지지 않게).
  const conn = ticketConnState(data);
  if (conn) return conn;
  if (data.ok === false) {
    return <Callout tone="danger">{data.error || "티켓을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}</Callout>;
  }

  const rows = ticketRows(data);
  const cols = ticketColumns({
    onEdit: setEditing,
    onOpen: (t) => nav("/tickets/" + t.id, { state: { from: "/projects" } }),
  });

  return (
    <Card>
      <Stack direction="row" gap={2} sx={{ flexWrap: "wrap", alignItems: "center", mb: 1.5 }}>
        <Typography variant="body2" color="text.secondary" aria-live="polite">
          총 {data.total != null ? data.total : rows.length}건
        </Typography>
        {activeToggle}
      </Stack>
      <GroupedTickets
        rows={rows} columns={cols} groupBy={groupByAssignee}
        emptyState={
          <EmptyState
            art="tickets"
            title="이 프로젝트에 걸린 티켓이 없습니다"
            help="티켓을 만들 때 이 프로젝트를 고르면 여기에 모입니다."
          />
        }
      />
      <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={onPage} />
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </Card>
  );
}

export function ProjectTickets({ project, page, onPage }) {
  const projectId = (project && project.id) || "";
  if (!projectId) {
    // 프로젝트를 아직 못 읽은 순간뿐이다. 조건 없이 부르면 회사의 모든 티켓이 이
    // 프로젝트의 목록으로 뜬다(서버가 진행률에서 같은 함정을 피한 이유와 같다).
    return (
      <Card>
        <EmptyState
          art="tickets"
          title="이 프로젝트의 티켓이 없습니다"
          situation="아직 이 프로젝트로 만든 티켓이 하나도 없습니다."
          help="티켓을 만들 때 이 프로젝트를 고르면 여기에 모입니다."
        />
      </Card>
    );
  }
  return <ProjectTicketList pageId={projectId} page={page} onPage={onPage} />;
}
