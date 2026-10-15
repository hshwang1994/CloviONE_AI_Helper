import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, NUMERIC } from "../../../ui/theme.js";
import { BoardFrame } from "../BoardFrame.jsx";
import { StageHint } from "../StageShared.jsx";
import { Scoreboard } from "../Scoreboard.jsx";
import { personOf } from "../people.js";
import { WaitingBoard } from "./WaitingBoard.jsx";

/* 실시간 퀴즈 판 (D-576) — 진행 중엔 문제 · 보기 · 실시간 점수, 끝나면 최종 순위표가 남는다(얼굴과 함께, 우승 줄에 테두리).
 * 결과 대화 상자의 「최종 순위」도 같은 `Scoreboard` 다. */

export function quizWinnerIds(quizResult) {
  const board = quizResult.scoreboard || [];
  if (Array.isArray(quizResult.winner_ids)) return new Set(quizResult.winner_ids);
  return new Set(board.filter((s) => (quizResult.winners || []).includes(s.name)).map((s) => s.user_id));
}

export function quizRows(quizResult, people) {
  const ids = quizWinnerIds(quizResult);
  return (quizResult.scoreboard || []).map((s) => ({
    key: s.user_id, user_id: s.user_id, name: s.name, person: personOf(people, s.user_id),
    value: `${s.score} / ${quizResult.total_rounds}`, win: ids.has(s.user_id),
  }));
}

export function QuizBoard({ c }) {
  const { room, quizResult, quizPlaying, liveScores, canQuizAnswer, voteOptionSx, mutations, people, you } = c;
  const { quizAnswer } = mutations;
  if (room.status === "finished" && quizResult) {
    return (
      <BoardFrame.Centered data-quiz-board="finished">
        <Typography component="p" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.title, textAlign: "center" }}>최종 순위</Typography>
        <Scoreboard rows={quizRows(quizResult, people)} />
      </BoardFrame.Centered>
    );
  }
  if (!quizPlaying) return <WaitingBoard c={c} />;
  return (
    <BoardFrame.Centered data-quiz-board={quizPlaying.phase}>
      <Typography variant="body2" color="text.secondary" sx={NUMERIC}>
        문제 {(quizPlaying.round || 0) + 1} / {quizPlaying.total}
      </Typography>
      <Typography component="p" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.title, textAlign: "center", ...KO_WORD_BREAK }}>{quizPlaying.question}</Typography>
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1, width: "100%", maxWidth: "32rem" }}>
        {(quizPlaying.options || []).map((opt, i) => {
          const mine = quizPlaying.your_answer === i;
          const isAnswer = quizPlaying.phase === "revealed" && quizPlaying.answer === i;
          return (
            <li key={i}>
              <Box component="button" type="button" sx={voteOptionSx(mine, isAnswer, false)}
                aria-pressed={mine}
                disabled={!canQuizAnswer || quizAnswer.isPending}
                onClick={() => canQuizAnswer && quizAnswer.mutate(i)}>
                <Box component="span" sx={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{opt}</Box>
                {isAnswer ? <Box component="span" sx={{ flexShrink: 0, fontWeight: FONT_WEIGHT.bold, color: "success.strong" }}>정답</Box> : null}
              </Box>
            </li>
          );
        })}
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", ...KO_WORD_BREAK }}>
        {quizPlaying.phase === "answering"
          ? `${quizPlaying.submitted_count || 0}명이 답했습니다. 방장이 정답을 공개하면 채점합니다.`
          : quizPlaying.your_answer == null ? "이번 문제에 답하지 않았습니다."
            : quizPlaying.your_correct ? "정답입니다!" : "아쉽지만 오답입니다."}
      </Typography>
      {liveScores.length > 0 ? (
        <Scoreboard rows={liveScores.map((s, i) => ({ key: s.user_id || "s" + i, user_id: s.user_id, name: s.name, person: personOf(people, s.user_id), value: s.score }))} />
      ) : null}
      {you.role === "spectator" ? <StageHint>관전 중입니다. 답은 참여자만 낼 수 있습니다.</StageHint> : null}
    </BoardFrame.Centered>
  );
}
