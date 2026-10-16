import React from "react";
import { EditableBody, hasUnsupportedBlocks, lineCount } from "../ui/EditableBody.jsx";
import { DocBody } from "../ui/DocBody.jsx";

/* 티켓 본문 읽기·편집 (계획 Phase 3 §E).
 *
 * 패널 자체는 `ui/EditableBody.jsx` 가 갖는다 — 문서 본문 편집(사용자 지적 #9)이 **같은
 * 상태**를 다뤄야 해서 그리 옮겼다. 복사해 두 벌로 뒀다면, 한쪽에서 고친 버그가 다른 쪽에
 * 남는다(이 저장소가 서버 쪽에서 반복해 적어 온 그 이유가 화면에도 똑같이 적용된다).
 *
 * 여기서 정하는 것은 티켓에만 해당하는 것들뿐이다: 어느 엔드포인트에 저장하는가, 어느 목록
 * 질의를 무효화하는가.
 *
 * 본문 폭은 담는 열(티켓 상세의 본문 트랙)이 정한다. 여기에 72ch 를 다시 걸면 카드는
 * 넓은데 글만 왼쪽에 붙는다.
 *
 * 헬퍼(lineCount/hasUnsupportedBlocks)는 이 경로로 계속 내보낸다 — 기존 테스트가 여기서
 * 가져오고, 옮겼다는 사실 때문에 그 계약을 깨뜨릴 이유는 없다. */

export { lineCount, hasUnsupportedBlocks };

export function TicketBody({ ticketId, blocks, blocksError, body, bodyMarkdown, bodyVersion, onSaved, onPickImage }) {
  return (
    <EditableBody
      editorId={"ticket-body-" + ticketId}
      endpoint={"/api/tickets/" + ticketId + "/body"}
      invalidateKeys={[["tickets"]]}
      blocks={blocks}
      bodyDoc={body}
      bodyMarkdown={bodyMarkdown}
      bodyVersion={bodyVersion}
      onSaved={onSaved}
      onPickImage={onPickImage}
      // VIS-135: 헤더의 '수정'(TicketEditModal)과 이 버튼이 다른 것을 편집한다는 것을
      // 밝힌다 — 상태·담당자 같은 속성은 여기서 못 고친다.
      editButtonHint="본문 텍스트만 수정합니다. 상태, 담당자 등 속성은 위 '수정' 버튼에서 수정합니다."
      sourceView={<DocBody blocks={blocks} blocksError={blocksError} />}
    />
  );
}
