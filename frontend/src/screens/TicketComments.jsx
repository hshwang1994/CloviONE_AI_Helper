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

export function TicketComments({ ticketId }) {
  return (
    <CommentThread
      queryKey={["ticket-comments", ticketId]}
      listUrl={"/api/tickets/" + ticketId + "/comments"}
      itemUrl={(id) => "/api/tickets/comments/" + id}
      emptyHint="아직 댓글이 없습니다. 이 티켓에 대한 논의를 여기에 남기세요."
    />
  );
}
