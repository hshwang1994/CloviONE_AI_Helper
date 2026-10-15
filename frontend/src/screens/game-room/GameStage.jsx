import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { rise } from "./constants.js";
import { BoardFrame, useBoardSize } from "./BoardFrame.jsx";
import { LadderBoard } from "./LadderBoard.jsx";
import { MarbleStage } from "./marble/MarbleStage.jsx";
import { WaitingBoard } from "./boards/WaitingBoard.jsx";
import { DrawBoard } from "./boards/DrawBoard.jsx";
import { TeamBoard } from "./boards/TeamBoard.jsx";
import { VoteBoard } from "./boards/VoteBoard.jsx";
import { NumberBoard } from "./boards/NumberBoard.jsx";
import { RpsBoard } from "./boards/RpsBoard.jsx";
import { QuizBoard } from "./boards/QuizBoard.jsx";

/* 판(왼쪽) — 게임 종류 · 상태별 판 하나 (D-575 · D-576). c 는 useGameRoomController() 가 반환한 값 전체다.
 *
 * 판은 **판만** 그린다: 결과의 발표 · 당첨자 · 복사 · 다시 하기는 결과 대화 상자(`ResultDialog.jsx`)의 일이고, 상태 · 동작은
 * 툴바(`RoomToolbar.jsx`)의 일이다. 모든 상태가 같은 틀(`BoardFrame`) 안의 온전한 판이라 대기 → 진행 → 종료 동안 판의 자리가
 * 그대로다 — 예전에는 대기 판이 점선 한 줄로 접혔다가 시작하면 튀어나왔다. 끝난 판은 대화 상자를 닫아도 마지막 장면으로 남는다. */

/* 사다리 판 — 판 높이를 사다리가 채운다(열 머리 · 도착지 · 안내 줄을 뺀 나머지). */
function LadderStage({ c }) {
  const size = useBoardSize();
  const { room, gstate, you, ladderAssignments, people } = c;
  if (gstate.result && gstate.result.columns) {
    const height = size.height ? size.height - 230 : null;
    return (
      <BoardFrame.Centered data-ladder-stage="">
        {/* key=room.id: 방을 바꿔도 캐시된 새 방 데이터로 "pending" 을 안 거치면 이 서브트리가 마운트 해제되지 않아 LadderBoard 의
            내부 선택(sel)이 이전 방 것으로 남는다(gameroom-ladder-room-switch-stale-selection.test.jsx). */}
        <Box sx={{ width: "100%", maxWidth: "64rem" }}>
          <LadderBoard key={room.id} result={gstate.result} highlightUserId={you.user_id} people={people} height={height} />
        </Box>
      </BoardFrame.Centered>
    );
  }
  return (
    <BoardFrame.Centered data-ladder-stage="list">
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5, width: "100%", maxWidth: "32rem" }}>
        {ladderAssignments.map((a) => (
          <Paper component="li" key={a.user_id} variant="outlined" sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 1.5, py: 1, animation: `${rise} .38s ease both` }}>
            <Box component="span" sx={{ flex: 1, minWidth: 0, ...KO_WORD_BREAK }}>{a.name}</Box>
            <Box component="span" aria-hidden="true" sx={{ color: "text.secondary" }}>→</Box>
            <Box component="span" sx={{ fontWeight: FONT_WEIGHT.bold, color: "primary.dark" }}>{a.outcome}</Box>
          </Paper>
        ))}
      </Box>
    </BoardFrame.Centered>
  );
}

export function GameStage({ c }) {
  const { room, isMarble, isDraw, isTeam, isLadder, isVote, isNumber, isRps, isQuiz, drawWinners, teams, ladderAssignments } = c;
  const finished = room.status === "finished";
  if (isMarble) return <MarbleStage c={c} />;
  if (isDraw) return finished && drawWinners.length > 0 ? <DrawBoard c={c} /> : <WaitingBoard c={c} />;
  if (isTeam) return finished && teams.length > 0 ? <TeamBoard c={c} /> : <WaitingBoard c={c} />;
  if (isLadder) return finished && ladderAssignments.length > 0 ? <LadderStage c={c} /> : <WaitingBoard c={c} />;
  if (isVote) return <VoteBoard c={c} />;
  if (isNumber) return <NumberBoard c={c} />;
  if (isRps) return <RpsBoard c={c} />;
  if (isQuiz) return <QuizBoard c={c} />;
  return null;
}
