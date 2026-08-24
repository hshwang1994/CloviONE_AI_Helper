import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { MascotPose } from "../../ui/Mascot.jsx";
import { EmptyState } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../../ui/theme.js";
import { fmtTime, ticketPageStart } from "../chat-helpers.js";
import { CardStack } from "./TicketCard.jsx";

/* 컨텍스트 레일(≥xxl) — 러너가 돌려준 구조화 결과. 예전엔 말풍선 안에 끼어 스레드를 밀어냈다.
 * 폭이 남을 때만 존재하고(railOpen), 그 아래에서는 지금까지처럼 말풍선 안에 그린다(같은 CardStack).
 *
 * 레일 자체의 스크롤(overflowY:auto, 아래)은 스레드 열(bodyRef)·사이드바 목록과 나란한 **형제**
 * 스크롤 영역이다 — 서로 안에 겹쳐 있지 않으므로 중첩 스크롤이 아니다(K-H3 대상 아님). */
export function ResultsRail({ railOpen, railMsg, railPayload, railIsLast, doSend, sending }) {
  if (!railOpen) return null;
  return (
    <Box
      component="aside" aria-label="결과"
      sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, borderLeft: 1, borderColor: "divider", bgcolor: "background.paper" }}
    >
      <Box sx={{ px: 3, py: 1.25, borderBottom: 1, borderColor: "divider", display: "flex", alignItems: "center", gap: 1, flexShrink: 0 }}>
        <Typography component="h2" sx={{ flex: 1, minWidth: 0, fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold }}>결과</Typography>
        {railMsg && railMsg.created_at ? (
          <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>{fmtTime(railMsg.created_at)}</Typography>
        ) : null}
      </Box>
      <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto", p: 3 }}>
        {railPayload ? (
          <>
            {/* 순번과 '상세' 원탭은 스레드와 정확히 같은 규칙으로 준다 — 마지막 어시스턴트
                메시지일 때만 살아 있다(옛 결과의 'N번 상세'는 지금 맥락의 엉뚱한 티켓을 가리킨다). */}
            <CardStack payload={railPayload} startNo={ticketPageStart(railMsg.structured, railMsg.content || "")}
              onChoose={railIsLast ? doSend : undefined} sending={sending} gap={1.5} />
            {!railIsLast ? (
              <Typography sx={{ mt: 2, fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
                대화가 이어져 이 결과는 지난 답변의 것입니다. 새 결과를 받으면 여기가 바뀝니다.
              </Typography>
            ) : null}
          </>
        ) : (
          <EmptyState
            size="compact"
            icon={<MascotPose mode="sleep" place="emptyCompact" decorative />}
            title="아직 표시할 결과가 없습니다"
            help="티켓, 프로젝트를 조회하면 그 결과 카드가 여기에 모입니다. 스레드는 대화만 남습니다."
          />
        )}
      </Box>
    </Box>
  );
}
