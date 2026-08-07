import React from "react";
import { CommentThread } from "./CommentThread.jsx";

/* 문서 댓글 (사용자 지적 #9).
 *
 * 타래는 티켓과 **같은 컴포넌트**다(CommentThread.jsx) — 서버가 두 자원에 같은 규약을
 * 지키므로 화면도 한 벌이면 된다. 여기 남는 것은 주소와 빈 목록 안내 문구뿐이다.
 *
 * `key={pageId}`가 필요하다. TeamDoc.jsx는 "/team-docs/:id" 라우트라, 알림 딥링크 등으로
 * id만 바뀌는 인앱 이동에서는 화면 컴포넌트가 리마운트되지 않는다(react-router가 같은
 * 자리의 같은 엘리먼트를 재사용) — DocComments도 pageId prop만 새로 받고 그대로 남는다.
 * key가 없으면 안의 CommentThread가 쓰던 댓글 초안(입력 중이던 문장)이 새 문서로 그대로
 * 넘어가, "등록"을 누르면 엉뚱한 문서에 댓글이 달린다. */
export function DocComments({ pageId }) {
  return (
    <CommentThread
      key={pageId}
      queryKey={["doc-comments", pageId]}
      listUrl={"/api/team-docs/" + pageId + "/comments"}
      itemUrl={(id) => "/api/team-docs/comments/" + id}
      emptyHint="아직 댓글이 없습니다. 이 문서에 대한 논의를 여기에 남기세요."
    />
  );
}
