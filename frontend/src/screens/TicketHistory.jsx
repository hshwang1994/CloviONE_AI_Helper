import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Card, EmptyState, ErrorState, SectionTitle, Skeleton } from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";
import { FONT_WEIGHT } from "../ui/theme.js";

/* 활동 이력 — 이 티켓이 **왜 지금 이 상태인가** (S18 · W8).
 *
 * 상태·담당자·마감이 바뀔 때마다 서버가 감사 기록을 남겨 왔는데 티켓 화면에는 그것이
 * 없었다. 「이거 언제 지연으로 바뀌었지」에 답하려면 관리자 콘솔의 감사 화면을 열어야
 * 했고 그 화면은 일반 사용자가 못 연다. 그 사이 상세 화면의 아래쪽은 비어 있었다
 * (2560 폭에서 하단 40%).
 *
 * 서버가 **바뀐 칸만** 준다(`app/tickets/service.py::ticket_history`). 저장 한 번에 아홉
 * 칸을 전부 나열하면 무엇이 바뀌었는지가 오히려 안 보이기 때문이다. 화면은 그것을 그대로
 * 그린다 — 여기서 다시 거르지 않는다(거르는 규칙이 두 곳에 있으면 언젠가 갈라진다).
 *
 * key={ticketId} 가 필요한 이유는 `TicketComments` 와 같다: 라우트가 같아 id 만 바뀌는
 * 이동에서는 이 컴포넌트가 리마운트되지 않는다.
 */
export function TicketHistory({ ticketId }) {
  const q = useQuery({
    queryKey: ["ticket-history", ticketId],
    queryFn: () => api("/api/tickets/" + ticketId + "/history"),
    retry: false,
  });

  const items = (q.data && q.data.items) || [];
  return (
    <Card>
      <SectionTitle component="h2" title="활동 이력" />
      {q.isPending ? <Skeleton lines={4} /> : null}
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
      {/* 값이 없으면 목록 껍데기를 남기지 않는다(D-296). 여기서 «아직 없다» 는 진짜
          없는 것이라 필터 얼굴이 아니라 데이터 없음 얼굴이다. */}
      {!q.isPending && !q.isError && items.length === 0 ? (
        <EmptyState
          layout="inline"
          title="아직 기록이 없습니다"
          help="상태, 담당자, 마감이 바뀌면 언제 누가 바꿨는지 여기에 쌓입니다."
        />
      ) : null}
      {items.length ? (
        <Box component="ol" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1.5 }}>
          {items.map((it) => (
            <Box
              component="li"
              key={it.id}
              sx={{
                minWidth: 0, pl: 2,
                /* 시간 순서를 **레일**로 말한다 — 사이드바의 활성 위치, 판독 줄의 선택과
                   같은 어휘다(D-289). 점·아이콘을 새로 만들지 않는다. */
                borderInlineStartStyle: "solid",
                borderInlineStartWidth: "2px",
                borderInlineStartColor: "divider",
              }}
            >
              <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, minWidth: 0 }}>
                {it.actor}님이 {it.summary}
              </Typography>
              <Typography variant="caption" color="text.secondary" component="div">
                {fmtDateTime(it.at)}
              </Typography>
              {(it.changes || []).length ? (
                <Box component="ul" sx={{ listStyle: "none", m: 0, mt: 0.5, p: 0, display: "grid", gap: 0.25 }}>
                  {it.changes.map((c) => (
                    <Typography component="li" variant="body2" key={c.field} sx={{ minWidth: 0 }}>
                      {c.label}: {c.from} → {c.to}
                    </Typography>
                  ))}
                </Box>
              ) : null}
            </Box>
          ))}
        </Box>
      ) : null}
    </Card>
  );
}

export default TicketHistory;
