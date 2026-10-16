import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Badge, FlatBadgeSurface } from "../../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../../ui/theme.js";
import { BoardFrame } from "../BoardFrame.jsx";
import { StageHint } from "../StageShared.jsx";
import { RPS_EMOJI, RPS_LABELS, rpsEmoji } from "../constants.js";
import { RpsChoices, RpsTournamentLive, RpsTournamentResult } from "../RpsViews.jsx";
import { personOf } from "../people.js";
import { PeopleGrid, PersonTile, usePeopleTileSize } from "./PersonTile.jsx";
import { WaitingBoard } from "./WaitingBoard.jsx";

/* 가위바위보 판 (D-576) — 한 판은 낸 손이 얼굴과 함께 공개되고(이긴 손에 테두리), 토너먼트는 「얼굴 — vs — 얼굴」 대진표다.
 * 결과 대화 상자의 「낸 손」 · 「대진표」도 같은 부품이다. */

export function RpsHands({ rpsResult, people, youId }) {
  const winners = new Set((rpsResult.winners || []).map((w) => w.user_id));
  const count = (rpsResult.reveal || []).length;
  const size = usePeopleTileSize(count, "tall");
  return (
    <FlatBadgeSurface>
      <PeopleGrid count={count} size={size} label="낸 손">
        {(rpsResult.reveal || []).map((p) => {
          const won = winners.has(p.user_id);
          return (
            <PersonTile size={size}
              key={p.user_id}
              person={personOf(people, p.user_id) || p}
              name={p.name}
              me={p.user_id === youId}
              state={won ? "winner" : "idle"}
              sub={<Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                <Box component="span" aria-hidden="true" sx={{ fontSize: "2.125rem", lineHeight: 1 }}>{rpsEmoji(p.choice)}</Box>
                <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, color: "text.primary" }}>{p.choice}</Box>
              </Box>}
              badge={won ? <Badge value="승리" kind="info" emphasis="strong" /> : null}
            />
          );
        })}
      </PeopleGrid>
    </FlatBadgeSurface>
  );
}

export function RpsBoard({ c }) {
  const { room, gstate, you, rpsResult, isTournament, canRps, mutations, people } = c;
  const { rps } = mutations;
  if (room.status === "finished" && rpsResult) {
    if (rpsResult.mode === "tournament") {
      return (
        <BoardFrame.Centered data-rps-board="bracket">
          <RpsTournamentResult result={rpsResult} people={people} />
        </BoardFrame.Centered>
      );
    }
    const win = rpsResult.outcome === "win";
    return (
      <BoardFrame.Centered data-rps-board="hands">
        <RpsHands rpsResult={rpsResult} people={people} youId={you.user_id} />
        <Box component="p" sx={{ m: 0, fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.semibold, textAlign: "center", ...KO_WORD_BREAK }}>
          {win ? `${rpsResult.win_choice}를 낸 사람이 이겼습니다.` : "같은 손만 나왔거나 셋이 다 나와 비겼습니다."}
        </Box>
      </BoardFrame.Centered>
    );
  }
  if (room.status !== "playing") return <WaitingBoard c={c} />;
  if (isTournament) {
    return (
      <BoardFrame.Centered data-rps-board="live">
        <RpsTournamentLive gstate={gstate} people={people} onPick={(i) => rps.mutate(i)} pending={rps.isPending} canPlay={you.in_room && you.role !== "spectator"} />
      </BoardFrame.Centered>
    );
  }
  return (
    <BoardFrame.Centered data-rps-board="playing">
      <Typography component="p" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.title, textAlign: "center", ...KO_WORD_BREAK }}>가위, 바위, 보 중 하나를 몰래 내세요.</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", ...KO_WORD_BREAK }}>
        방장이 공개하면 판정합니다. 지금 {gstate.submitted_count || 0}명이 냈습니다.
      </Typography>
      {canRps ? (
        <RpsChoices labels={RPS_LABELS} emojis={RPS_EMOJI} chosen={gstate.your_choice} disabled={rps.isPending} onPick={(i) => rps.mutate(i)} />
      ) : null}
      {canRps && gstate.you_submitted ? (
        <Typography variant="body2" color="text.secondary">{RPS_LABELS[gstate.your_choice]}를 냈습니다. 다시 누르면 바뀝니다.</Typography>
      ) : null}
      {you.role === "spectator" ? <StageHint>관전 중입니다. 손은 참여자만 낼 수 있습니다.</StageHint> : null}
    </BoardFrame.Centered>
  );
}
