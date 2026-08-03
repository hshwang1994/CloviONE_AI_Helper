import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { Badge, Button, Callout, ErrorState, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { DocBody, safeExternal } from "./TeamDoc.jsx";
import { TicketEditModal } from "./MyTickets.jsx";
import { priorityKo, priorityKind } from "../lib/priority.js";

/* 티켓 상세 — 문서처럼 우리 화면에서 내용을 읽고, '원본 열기'로 노션에 간다. 속성은 표로,
 * 본문 블록은 문서 상세와 같은 렌더러(DocBody)로 읽기 전용 표시. 편집·삭제(휴지통)도 여기서. */

function ticketId(t) { return t && t.tid != null ? "GIT-" + t.tid : "티켓"; }

export function Ticket() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(false);

  const detail = useQuery({
    queryKey: ["ticket", id],
    queryFn: () => api("/api/tickets/" + id),
    retry: false,
  });

  const trash = useMutation({
    mutationFn: () => api("/api/tickets/" + id + "/trash", { method: "POST" }),
    onSuccess: () => {
      toast("티켓을 휴지통으로 옮겼습니다.", "success");
      qc.invalidateQueries({ queryKey: ["tickets"], refetchType: "all" });
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      nav("/my-tickets");
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
  });

  if (detail.isError) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" actions={<Button onClick={() => nav("/my-tickets")}>목록</Button>} />
        <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
      </div>
    );
  }
  if (detail.isPending) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" />
        <Skeleton lines={8} />
      </div>
    );
  }

  const data = detail.data || {};
  if (data.configured === false) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" actions={<Button onClick={() => nav("/my-tickets")}>목록</Button>} />
        <Callout tone="warn">Notion 연동이 아직 설정되지 않았습니다. 관리자에게 문의하세요.</Callout>
      </div>
    );
  }
  if (data.ok === false) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" actions={<Button onClick={() => nav("/my-tickets")}>목록</Button>} />
        <Callout tone="danger">{data.error || "티켓을 불러오지 못했습니다."}</Callout>
      </div>
    );
  }

  const t = data.ticket || {};
  const original = safeExternal(t.url);
  const actions = (
    <div className="doc-actions">
      <Button variant="ghost" onClick={() => nav("/my-tickets")}>목록</Button>
      <Button onClick={() => setEditing(true)}>편집</Button>
      {original ? (
        <Button variant="primary" onClick={() => window.open(original, "_blank", "noopener,noreferrer")}>원본 열기</Button>
      ) : null}
      <Button variant="danger" disabled={trash.isPending}
        onClick={async () => {
          const ok = await confirm("이 티켓을 휴지통으로 옮깁니다. 보관기간이 지나면 원본이 삭제됩니다. 계속할까요?",
            { title: "티켓 삭제", confirmLabel: "휴지통으로", danger: true });
          if (ok) trash.mutate();
        }}>삭제</Button>
    </div>
  );

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="내 업무" area="티켓" title={ticketId(t)} actions={actions} />
      <article className="doc-detail">
        <div className="doc-head">
          {t.status ? <Badge value={t.status} /> : null}
          {t.priority ? <Badge value={priorityKo(t.priority)} kind={priorityKind(t.priority)} /> : null}
          <h1 className="doc-title">{t.title || "제목 없음"}</h1>
        </div>
        <dl className="doc-meta">
          {t.project ? <><dt>프로젝트</dt><dd>{t.project}</dd></> : null}
          {(t.assignee_names || []).length ? <><dt>담당자</dt><dd>{t.assignee_names.join(", ")}</dd></> : null}
          {t.difficulty ? <><dt>난이도</dt><dd>{t.difficulty}</dd></> : null}
          {t.est_wd != null ? <><dt>예상 WD</dt><dd>{t.est_wd}</dd></> : null}
          {t.act_wd != null ? <><dt>실제 WD</dt><dd>{t.act_wd}</dd></> : null}
          {t.due ? <><dt>마감</dt><dd>{t.due}</dd></> : null}
        </dl>
        <DocBody blocks={data.blocks} blocksError={data.blocks_error} originalUrl={original} />
      </article>
      <TicketEditModal ticket={t} open={editing} onClose={() => { setEditing(false); detail.refetch(); }} />
    </div>
  );
}
