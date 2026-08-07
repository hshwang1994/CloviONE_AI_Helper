import React from "react";
import { CommentThread, MAX_COMMENT_CHARS } from "./CommentThread.jsx";

/* 티켓 댓글 (계획 Phase 3 §E).
 *
 * 타래 자체는 CommentThread.jsx 로 옮겼다 — 문서 댓글(사용자 지적 #9)이 같은 서버 규약
 * (쓰기마다 목록 전체 + 툼스톤)을 쓰므로, 화면에서 그 규약을 두 번 구현하면 언젠가 갈라진다.
 * 여기 남는 것은 "티켓 댓글은 어느 주소에 있는가" 하나뿐이다.
 *
 * 이 파일이 계속 존재하는 이유: Ticket.jsx 와 ticket-detail.test.jsx 가 이 이름으로 가져온다. */

export { MAX_COMMENT_CHARS };

// key={ticketId}가 필요하다. Ticket.jsx는 "/tickets/:id" 라우트라, 알림 딥링크 등으로
// id만 바뀌는 인앱 이동에서는 화면 컴포넌트가 리마운트되지 않는다(react-router가 같은
// 자리의 같은 엘리먼트를 재사용) — key가 없으면 안의 CommentThread가 쓰던 댓글 초안이
// 새 티켓으로 그대로 넘어가, "등록"을 누르면 엉뚱한 티켓에 댓글이 달린다
// (DocComments.jsx와 같은 이유, comment-thread-stale-draft.test.jsx).
export function TicketComments({ ticketId }) {
  return (
    <CommentThread
      key={ticketId}
      queryKey={["ticket-comments", ticketId]}
      listUrl={"/api/tickets/" + ticketId + "/comments"}
      itemUrl={(id) => "/api/tickets/comments/" + id}
      emptyHint="아직 댓글이 없습니다. 이 티켓에 대한 논의를 여기에 남기세요."
    />
  );
}
