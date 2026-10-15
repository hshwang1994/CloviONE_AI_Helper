import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Badge, Button, FlatBadgeSurface } from "../../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, NUMERIC } from "../../../ui/theme.js";
import { BoardFrame } from "../BoardFrame.jsx";
import { StageHint } from "../StageShared.jsx";
import { personOf } from "../people.js";
import { PeopleGrid, PersonTile, usePeopleTileSize } from "./PersonTile.jsx";
import { WaitingBoard } from "./WaitingBoard.jsx";

/* 숫자 눈치 판 (D-576) — 진행 중엔 몰래 내는 칸, 끝나면 낸 숫자가 얼굴과 함께 공개된다(가장 낮은 유일한 숫자에 테두리).
 * 결과 대화 상자의 「공개된 숫자」도 같은 격자(`NumberPicks`)다. */

export function NumberPicks({ numResult, people, youId }) {
  const w = numResult.winner;
  const count = (numResult.picks || []).length;
  const size = usePeopleTileSize(count, "tall");
  return (
    <FlatBadgeSurface>
      <PeopleGrid count={count} size={size} label="공개된 숫자">
        {(numResult.picks || []).map((p) => {
          const win = !!w && w.user_id === p.user_id;
          return (
            <PersonTile size={size}
              key={p.user_id}
              person={personOf(people, p.user_id) || p}
              name={p.name}
              me={p.user_id === youId}
              state={win ? "winner" : "idle"}
              sub={<Box component="span" sx={{ display: "block", fontSize: "1.5rem", lineHeight: 1.1, fontWeight: FONT_WEIGHT.extrabold, color: win ? "primary.dark" : "text.primary", ...NUMERIC }}>{p.number}</Box>}
              badge={win ? <Badge value="승리" kind="info" emphasis="strong" /> : null}
            />
          );
        })}
      </PeopleGrid>
    </FlatBadgeSurface>
  );
}

export function NumberBoard({ c }) {
  const { room, gstate, you, numResult, canPick, numDraft, setNumDraft, mutations, people } = c;
  const { pick } = mutations;
  if (room.status === "finished" && numResult) {
    const w = numResult.winner;
    return (
      <BoardFrame.Centered data-number-board="finished">
        <NumberPicks numResult={numResult} people={people} youId={you.user_id} />
        <Box component="p" sx={{ m: 0, fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.semibold, textAlign: "center", ...KO_WORD_BREAK }}>
          {w ? `가장 낮은 유일한 숫자는 ${w.number}입니다.` : "유일한 숫자가 없어 승자가 없습니다."}
        </Box>
      </BoardFrame.Centered>
    );
  }
  if (room.status !== "playing") return <WaitingBoard c={c} />;
  return (
    <BoardFrame.Centered data-number-board="playing">
      <Typography component="p" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.title, textAlign: "center", ...KO_WORD_BREAK }}>
        {gstate.min || 1} ~ {gstate.max || 10} 중 하나를 몰래 내세요
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", ...KO_WORD_BREAK }}>
        가장 낮은 유일한 숫자를 낸 사람이 이깁니다. 지금 {gstate.submitted_count || 0}명이 냈습니다.
      </Typography>
      {canPick ? (
        <Stack direction="row" gap={1} alignItems="center">
          <TextField
            size="small" type="number" value={numDraft}
            placeholder={(gstate.min || 1) + "~" + (gstate.max || 10)}
            inputProps={{ min: gstate.min || 1, max: gstate.max || 10, "aria-label": "낼 숫자" }}
            onChange={(e) => setNumDraft(e.target.value)}
            sx={{ width: "8rem", "& input": { textAlign: "center", ...NUMERIC } }}
          />
          <Button variant="primary" disabled={pick.isPending || numDraft === ""} sx={{ flexShrink: 0 }}
            onClick={() => { const v = Number(numDraft); if (Number.isInteger(v)) pick.mutate(v); }}>제출</Button>
        </Stack>
      ) : null}
      {canPick && gstate.you_submitted ? (
        <Typography variant="body2" color="text.secondary">내가 낸 숫자는 {gstate.your_pick}입니다. 다시 내면 바뀝니다.</Typography>
      ) : null}
      {you.role === "spectator" ? <StageHint>관전 중입니다. 숫자는 참여자만 낼 수 있습니다.</StageHint> : null}
    </BoardFrame.Centered>
  );
}
