import React from "react";
import Box from "@mui/material/Box";
import { EditableBody, hasUnsupportedBlocks, lineCount } from "../ui/EditableBody.jsx";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { DocBody } from "./TeamDoc.jsx";

/* 티켓 본문 읽기·편집 (계획 Phase 3 §E).
 *
 * 패널 자체는 `ui/EditableBody.jsx` 가 갖는다 — 문서 본문 편집(사용자 지적 #9)이 **같은
 * 상태**를 다뤄야 해서 그리 옮겼다. 복사해 두 벌로 뒀다면, 한쪽에서 고친 버그가 다른 쪽에
 * 남는다(이 저장소가 서버 쪽에서 반복해 적어 온 그 이유가 화면에도 똑같이 적용된다).
 *
 * 여기서 정하는 것은 티켓에만 해당하는 것들뿐이다: 어느 엔드포인트에 저장하는가, 어느 목록
 * 질의를 무효화하는가, 소스 본문을 어떤 폭으로 그리는가.
 *
 * 헬퍼(lineCount/hasUnsupportedBlocks)는 이 경로로 계속 내보낸다 — 기존 테스트가 여기서
 * 가져오고, 옮겼다는 사실 때문에 그 계약을 깨뜨릴 이유는 없다. */

const PROSE_SX = {
  maxWidth: PROSE_MAX_WIDTH,
  "& .doc-body": { fontSize: "1rem" },
  "& .doc-h1": { fontSize: "1.25rem" },
  "& .doc-h2": { fontSize: "1.0625rem" },
  "& .doc-h3": { fontSize: "1rem" },
  "& .doc-code, & .doc-unsupported": { fontSize: "0.875rem" },
};

export { lineCount, hasUnsupportedBlocks };

export function TicketBody({ ticketId, blocks, blocksError, bodyMarkdown, bodyVersion, bodyIsLocal, bodySyncError, originalUrl, onSaved }) {
  return (
    <EditableBody
      editorId={"ticket-body-" + ticketId}
      endpoint={"/api/tickets/" + ticketId + "/body"}
      invalidateKeys={[["tickets"]]}
      blocks={blocks}
      bodyMarkdown={bodyMarkdown}
      bodyVersion={bodyVersion}
      bodyIsLocal={bodyIsLocal}
      bodySyncError={bodySyncError}
      onSaved={onSaved}
      sourceView={(
        <Box sx={PROSE_SX}>
          <DocBody blocks={blocks} blocksError={blocksError} originalUrl={originalUrl} />
        </Box>
      )}
    />
  );
}
