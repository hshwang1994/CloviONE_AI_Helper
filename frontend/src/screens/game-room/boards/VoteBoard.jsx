import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, NUMERIC, RADIUS } from "../../../ui/theme.js";
import { BoardFrame } from "../BoardFrame.jsx";
import { StageHint } from "../StageShared.jsx";

/* 빠른 투표 판 (D-576) — 질문 하나와 보기들. 대기 중엔 보기 미리 보기, 진행 중엔 누르는 보기(실시간 표 수), 끝나면 득표 막대가 남는다.
 * 결과 대화 상자의 「전체 집계」도 같은 막대(`VoteBars`)다. 선택지는 **번호(id)** 로 가른다(옛 상태 행만 라벨로). */

export function voteWinnerIndexes(voteResult) {
  const options = voteResult.options || [];
  return Array.isArray(voteResult.winner_indexes)
    ? voteResult.winner_indexes
    : options.map((opt, i) => ((voteResult.winners || []).includes(opt) ? i : -1)).filter((i) => i >= 0);
}

export function VoteBars({ voteResult, maxCount }) {
  const options = voteResult.options || [];
  const counts = voteResult.counts || [];
  const winnerIdx = voteWinnerIndexes(voteResult);
  const top = maxCount != null ? maxCount : Math.max(0, ...counts);
  return (
    <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1, width: "100%" }}>
      {options.map((opt, i) => {
        const cnt = counts[i] || 0;
        const win = winnerIdx.includes(i);
        return (
          <Box component="li" key={i} data-vote-option={win ? "winner" : ""} sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0,1fr) auto", sm: "minmax(6rem, 12rem) minmax(0,1fr) auto" }, alignItems: "center", gap: 1.5 }}>
            <Box component="span" title={opt} sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: win ? FONT_WEIGHT.bold : FONT_WEIGHT.regular }}>{opt}</Box>
            <Box sx={{ display: { xs: "none", sm: "block" }, height: "0.875rem", borderRadius: `${RADIUS.full}px`, bgcolor: "action.hover", overflow: "hidden" }}>
              <Box sx={{ display: "block", height: "100%", borderRadius: `${RADIUS.full}px`, bgcolor: win ? "primary.main" : "primary.light", width: (top ? (cnt / top) * 100 : 0) + "%", transition: "width .4s ease" }} />
            </Box>
            <Typography component="span" variant="body2" color={win ? "text.primary" : "text.secondary"} sx={{ ...NUMERIC, fontWeight: win ? FONT_WEIGHT.bold : FONT_WEIGHT.regular }}>{cnt}표</Typography>
          </Box>
        );
      })}
    </Box>
  );
}

export function VoteBoard({ c }) {
  const { room, gstate, you, voteResult, voteOptions, liveCounts, myVote, maxCount, canVote, voteOptionSx, mutations } = c;
  const { vote } = mutations;
  const finished = room.status === "finished";
  const question = voteResult?.question || gstate.question || room.title;
  return (
    <BoardFrame.Centered data-vote-board={room.status}>
      <Typography component="p" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.title, textAlign: "center", ...KO_WORD_BREAK }}>{question}</Typography>
      <Box sx={{ width: "100%", maxWidth: "40rem" }}>
        {finished && voteResult ? (
          <VoteBars voteResult={voteResult} maxCount={maxCount} />
        ) : room.status === "playing" ? (
          <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
            {voteOptions.map((opt, i) => (
              <li key={i}>
                <Box component="button" type="button" sx={voteOptionSx(myVote === i, false, false)}
                  aria-pressed={myVote === i}
                  disabled={!canVote || vote.isPending} onClick={() => canVote && vote.mutate(i)}>
                  <Box component="span" sx={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{opt}</Box>
                  <Box component="span" sx={{ flexShrink: 0, minWidth: "1.75rem", textAlign: "center", fontWeight: FONT_WEIGHT.bold, color: "primary.dark", ...NUMERIC }}>
                    {liveCounts[i]}
                  </Box>
                </Box>
              </li>
            ))}
          </Box>
        ) : finished ? (
          <StageHint>투표한 사람이 없습니다.</StageHint>
        ) : (
          <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
            {voteOptions.map((opt, i) => (
              <li key={i}><Box sx={voteOptionSx(false, false, true)}>{opt}</Box></li>
            ))}
          </Box>
        )}
      </Box>
      {room.status === "waiting" ? <StageHint>참여자가 모이면 방장이 투표를 엽니다.</StageHint> : null}
      {room.status === "playing" && !canVote && you.role === "spectator" ? <StageHint>관전 중입니다. 투표는 참여자만 할 수 있습니다.</StageHint> : null}
    </BoardFrame.Centered>
  );
}
