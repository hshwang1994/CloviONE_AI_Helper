import { useMemo } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { alpha, useTheme } from "@mui/material/styles";
import { Badge, FlatBadgeSurface, ScrollArea } from "../../../ui/kit.jsx";
import { UserAvatar } from "../../../ui/UserAvatar.jsx";
import { GAME_RAIL_BUDGET } from "../../../ui/density.js";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, NUMERIC, RADIUS } from "../../../ui/theme.js";
import { personOf } from "../people.js";
import { boardPalette, marbleColor } from "./render/theme.js";
import { finishedOf, rankOrder } from "./useMarbleRoom.js";

/* 구슬 순위 — 레일의 「순위」 칸 (D-578). 진행 중엔 실시간 순위(완주한 구슬 먼저, 나머지는 진행도 순), 확인 중엔 잠정, 확정 뒤엔
 * 서버 순위. 줄마다 구슬 색 점 · 얼굴(사람 참가자) · 이름 · 완주/당첨 표지. 레일이 판(Card)과 머리(전환)를 그리고 이것은 목록만이다.
 * 실시간 순위는 경주 훅의 `tick`(≈5Hz)에 맞춰 다시 그린다 — 프레임마다 DOM 을 바꾸지 않는다. */

export function RankRail({ c, maxHeight = GAME_RAIL_BUDGET.members }) {
  const theme = useTheme();
  const palette = useMemo(() => boardPalette(theme), [theme]);
  const m = c.marble;
  const snapshot = m.waiting ? null : m.race.snapshotRef.current;
  const finalRanking = m.announceable ? m.serverResult.ranking || [] : null;
  const order = rankOrder({ participants: m.participants, snapshot, finalRanking });
  return (
    <FlatBadgeSurface>
      {m.verifying ? (
        <Typography variant="caption" color="warning.strong" sx={{ display: "block", mb: 0.75, ...KO_WORD_BREAK }}>확정 전의 잠정 순위입니다.</Typography>
      ) : null}
      <ScrollArea maxHeight={maxHeight} ariaLabel="구슬 순위" sx={{ minHeight: 0 }}>
        <Box component="ol" data-marble-rail="" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.25 }}>
          {order.map((p, i) => {
            const person = p.user_id ? personOf(c.people, p.user_id) : null;
            const isMe = c.you && p.user_id && p.user_id === c.you.user_id;
            const won = m.winnerKeys.has(p.key);
            return (
              <Box component="li" key={p.key} sx={{
                display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.5, borderRadius: `${RADIUS.sm}px`, minWidth: 0,
                bgcolor: (t) => (won ? alpha(t.palette.primary.main, 0.12) : isMe ? alpha(t.palette.primary.main, 0.06) : "transparent"),
              }}>
                <Box component="span" sx={{ width: "1.5rem", flexShrink: 0, color: "text.secondary", ...NUMERIC, fontSize: FONT_SIZE.bodySm }}>{i + 1}</Box>
                <Box component="span" aria-hidden="true" sx={{ width: 10, height: 10, borderRadius: "50%", flexShrink: 0, bgcolor: marbleColor(p.hue, palette), boxShadow: (t) => `inset 0 0 0 1px ${alpha(t.palette.common.black, 0.25)}` }} />
                {person ? <UserAvatar person={person} name={p.name} size="sm" /> : null}
                <Box component="span" title={p.name} sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: won ? FONT_WEIGHT.bold : FONT_WEIGHT.regular }}>{p.name}</Box>
                {won ? <Badge value="당첨" kind="info" /> : finishedOf(p, snapshot, finalRanking) ? <Badge value="완주" kind="ok" /> : null}
              </Box>
            );
          })}
        </Box>
      </ScrollArea>
    </FlatBadgeSurface>
  );
}
