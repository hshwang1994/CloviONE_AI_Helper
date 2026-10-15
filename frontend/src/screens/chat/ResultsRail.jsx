import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { MascotPose } from "../../ui/Mascot.jsx";
import { EmptyState } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../../ui/theme.js";
import { fmtTime } from "../chat-helpers.js";
import { SourceList, messageSources } from "./SourceList.jsx";

/* 「참고한 자료」 레일(≥xxl) — 마지막으로 출처를 든 도우미 답의 자료를 스레드 옆에 세운다(D-535).
 * 레일이 보이면 그 답의 말풍선 안 출처는 숨는다(같은 목록이 두 벌 서지 않는다). 폭이 남을 때만 존재한다(railOpen).
 * 레일은 서버가 싣는 출처 상한(서른 개, 답에 인용된 것이 먼저)까지 접지 않고 다 세운다(`RAIL_SOURCE_LIMIT`, D-569).
 *
 * 레일 자체의 스크롤은 스레드 열 · 사이드바 목록과 나란한 **형제** 스크롤 영역이다(중첩 스크롤이 아니다). */
export const RAIL_SOURCE_LIMIT = 30;

export function ResultsRail({ railOpen, railMsg, railIsLast }) {
  if (!railOpen) return null;
  const sources = railMsg ? messageSources(railMsg.structured) : [];
  return (
    <Box
      component="aside" aria-label="참고한 자료"
      sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, borderLeft: 1, borderColor: "divider", bgcolor: "background.paper" }}
    >
      <Box sx={{ px: 3, py: 1.25, borderBottom: 1, borderColor: "divider", display: "flex", alignItems: "center", gap: 1, flexShrink: 0 }}>
        <Typography component="h2" sx={{ flex: 1, minWidth: 0, fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold }}>참고한 자료</Typography>
        {railMsg && railMsg.created_at ? (
          <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>{fmtTime(railMsg.created_at)}</Typography>
        ) : null}
      </Box>
      <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto", p: 3 }}>
        {sources.length ? (
          <>
            <SourceList sources={sources} title={null} limit={RAIL_SOURCE_LIMIT} />
            {!railIsLast ? (
              <Typography sx={{ mt: 2, fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
                대화가 이어져 이 자료는 지난 답의 것입니다. 새 답이 자료를 찾으면 여기가 바뀝니다.
              </Typography>
            ) : null}
          </>
        ) : (
          <EmptyState
            size="compact"
            icon={<MascotPose mode="sleep" place="emptyCompact" decorative />}
            title="아직 참고한 자료가 없습니다"
            help="도우미가 찾아 본 문서와 티켓이 여기에 모입니다."
          />
        )}
      </Box>
    </Box>
  );
}
