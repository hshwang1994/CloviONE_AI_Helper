import React from "react";
import { CommentThread } from "./CommentThread.jsx";

/* 문서 댓글 (사용자 지적 #9).
 *
 * 타래는 티켓과 **같은 컴포넌트**다(CommentThread.jsx) — 서버가 두 자원에 같은 규약을
 * 지키므로 화면도 한 벌이면 된다. 여기 남는 것은 주소와 빈 목록 안내 문구뿐이다. */

export function DocComments({ pageId }) {
  return (
    <CommentThread
      queryKey={["doc-comments", pageId]}
      listUrl={"/api/team-docs/" + pageId + "/comments"}
      itemUrl={(id) => "/api/team-docs/comments/" + id}
      emptyHint="아직 댓글이 없습니다. 이 문서에 대한 논의를 여기에 남기세요."
    />
  );
}
