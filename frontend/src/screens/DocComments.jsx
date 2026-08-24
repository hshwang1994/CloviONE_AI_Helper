import React from "react";
import { CommentThread } from "./CommentThread.jsx";

/* 문서 댓글.
 *
 * 타래는 티켓과 **같은 컴포넌트**다(CommentThread.jsx) — 서버가 두 자원에 같은 규약을
 * 지키므로 화면도 한 벌이면 된다. 여기 남는 것은 주소와 빈 목록 안내 문구뿐이다.
 *
 * 주소가 문서 id 다 (S14 · C2). 옛 미러의 page id 로 붙어 있던 축을 정본 문서로 옮겼다 —
 * 같은 문서의 논의가 주소마다 다른 곳에 쌓이면, 한쪽에 쓴 질문을 다른 쪽에서 못 본다.
 *
 * `key={documentId}`가 필요하다. KnowledgeDoc.jsx는 "/knowledge/:id" 라우트라, 알림 딥링크
 * 등으로 id만 바뀌는 인앱 이동에서는 화면 컴포넌트가 리마운트되지 않는다(react-router가
 * 같은 자리의 같은 엘리먼트를 재사용) — DocComments도 prop만 새로 받고 그대로 남는다.
 * key가 없으면 안의 CommentThread가 쓰던 댓글 초안(입력 중이던 문장)이 새 문서로 그대로
 * 넘어가, "등록"을 누르면 엉뚱한 문서에 댓글이 달린다. */
export function DocComments({ documentId }) {
  return (
    <CommentThread
      key={documentId}
      queryKey={["doc-comments", documentId]}
      listUrl={"/api/knowledge/documents/" + documentId + "/comments"}
      itemUrl={(id) => "/api/knowledge/comments/" + id}
      emptyHint="아직 댓글이 없습니다. 이 문서에 대한 논의를 여기에 남기세요."
    />
  );
}
