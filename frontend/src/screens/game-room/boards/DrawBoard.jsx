import Box from "@mui/material/Box";
import { Badge, FlatBadgeSurface } from "../../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../../ui/theme.js";
import { BoardFrame } from "../BoardFrame.jsx";
import { personOf } from "../people.js";
import { ANNOUNCE_MS } from "../revealMachine.js";
import { PeopleGrid, PersonTile, usePeopleTileSize } from "./PersonTile.jsx";

/* 추첨 판 (D-576) — 누구 중에서 누가 뽑혔는가.
 *
 * 추첨 대상(`state.pool` — 그 순간 방에 있던 참여자)의 얼굴 격자다. 발표 중(`announcing`)에는 하이라이트가 칸을 차례로 훑고, 공개되면
 * 당첨자가 브랜드 테두리 + 「당첨」을 받고 나머지는 흐려진다. 대화 상자를 닫아도 이 장면이 남는다(마지막 장면). 옛 상태 행(대상이 없는
 * 결과)은 지금 구성원으로 대신한다. */

export function drawPool(c) {
  const pool = Array.isArray(c.gstate.pool) && c.gstate.pool.length ? c.gstate.pool : null;
  if (pool) return pool;
  const seen = new Set();
  const out = [];
  for (const m of (c.members || []).filter((x) => x.role !== "spectator")) { seen.add(m.user_id); out.push({ user_id: m.user_id, name: m.name }); }
  for (const w of c.drawWinners || []) if (!seen.has(w.user_id)) out.push({ user_id: w.user_id, name: w.name });
  return out;
}

export function DrawBoard({ c }) {
  const pool = drawPool(c);
  const winners = new Set((c.drawWinners || []).map((w) => w.user_id));
  const announcing = c.reveal && c.reveal.phase === "announcing";
  const step = pool.length ? Math.max(60, Math.floor(ANNOUNCE_MS / pool.length)) : 0;
  const size = usePeopleTileSize(pool.length);
  return (
    <BoardFrame.Centered data-draw-board={announcing ? "announcing" : "revealed"}>
      <FlatBadgeSurface>
        <PeopleGrid count={pool.length} size={size} label="추첨 대상">
          {pool.map((p, i) => {
            const won = winners.has(p.user_id);
            const state = announcing ? "sweep" : won ? "winner" : "dim";
            return (
              <PersonTile size={size}
                key={p.user_id}
                person={personOf(c.people, p.user_id) || p}
                name={p.name}
                me={p.user_id === c.you.user_id}
                state={state}
                delayMs={i * step}
                badge={!announcing && won ? <Badge value="당첨" kind="info" emphasis="strong" /> : null}
              />
            );
          })}
        </PeopleGrid>
      </FlatBadgeSurface>
      <Box component="p" aria-live="polite" sx={{ m: 0, fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.semibold, textAlign: "center", ...KO_WORD_BREAK }}>
        {announcing ? "추첨하는 중입니다." : `${pool.length}명 중 ${winners.size}명을 뽑았습니다.`}
      </Box>
    </BoardFrame.Centered>
  );
}
