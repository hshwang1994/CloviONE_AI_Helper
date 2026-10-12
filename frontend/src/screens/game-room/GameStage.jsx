import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { Button } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "../../ui/theme.js";
import { rise, stageColumnSx, RPS_LABELS, RPS_EMOJI, rpsEmoji } from "./constants.js";
import { StageHint } from "./StageShared.jsx";
import { LadderBoard } from "./LadderBoard.jsx";
import { RpsChoices, RpsTournamentLive, RpsTournamentResult } from "./RpsViews.jsx";
import { Scoreboard } from "./Scoreboard.jsx";
import { ResultPanel } from "./ResultPanel.jsx";
import { MarbleStage } from "./marble/MarbleStage.jsx";

/* 무대(왼쪽) — 게임 종류 · 상태별 실제 화면. 게임 종류로 먼저 가르고, 그 안에서 방 상태(waiting/playing/finished)로 다시 가른다.
 * c 는 useGameRoomController() 가 반환한 값 전체다.
 *
 * 결과는 공통 틀 하나(`ResultPanel`, D-563)에 게임마다 다른 결과 표현(`detail`)을 싣는다 — 당첨자 수 · 순위의 뜻 · 고유 정보
 * (사다리 경로 · 득표 · 점수 · 대진 · 완주 순위)는 게임마다 다르고, 승자가 없는 결과(팀 나누기 · 사다리 · 무승부)는 `calm` 이다.
 * 승자 · 선택지는 **id** 로 비교한다(옛 상태 행은 라벨만 있어 그때만 라벨로). 구슬 레이스는 자기 무대(`MarbleStage`)다. */

function personOf(members, userId) {
  return (members || []).find((m) => m.user_id === userId) || null;
}

export function GameStage({ c }) {
  const {
    room, gstate, you, members,
    isVote, isTeam, isDraw, isNumber, isLadder, isRps, isQuiz, isMarble, isTournament,
    canVote, canPick, canRps, canQuizAnswer,
    drawWinners, teams, ladderAssignments,
    numResult, rpsResult, quizResult, quizPlaying, liveScores,
    voteResult, voteOptions, liveCounts, myVote, maxCount,
    voteOptionSx, numDraft, setNumDraft,
    mutations, revealPlan, celebrateOnReveal,
  } = c;
  const { vote, pick, rps, quizAnswer } = mutations;
  const reveal = { revealKey: revealPlan ? revealPlan.key : null, instant: revealPlan ? revealPlan.instant : true, onReveal: celebrateOnReveal };
  const finished = room.status === "finished";

  if (isMarble) return <MarbleStage c={c} />;

  if (isDraw && finished && drawWinners.length > 0) {
    const winners = drawWinners.map((w) => ({ id: w.user_id, name: w.name, user_id: w.user_id, person: personOf(members, w.user_id) }));
    return (
      <ResultPanel game="랜덤 추첨" headline="당첨자를 발표합니다" lead={`${winners.length}명이 당첨됐습니다.`}
        winners={winners} winnerLabel="당첨" {...reveal}
        copyText={`랜덤 추첨 결과\n당첨: ${winners.map((w) => w.name).join(", ")}`} />
    );
  }
  if (isTeam && finished && teams.length > 0) {
    const detail = (
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "repeat(auto-fit, minmax(14rem, 1fr))" } }}>
        {teams.map((team, ti) => (
          <Paper key={ti} variant="outlined" sx={{ p: 2, animation: `${rise} .38s ease both` }}>
            <Typography sx={{ fontWeight: FONT_WEIGHT.bold, mb: 1 }}>
              {ti + 1}팀 <Box component="span" sx={{ color: "text.secondary", fontWeight: FONT_WEIGHT.regular, fontSize: FONT_SIZE.bodySm }}>{team.length}명</Box>
            </Typography>
            <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
              {team.map((m) => <li key={m.user_id}>{m.name}</li>)}
            </Box>
          </Paper>
        ))}
      </Box>
    );
    return (
      <ResultPanel game="랜덤 팀 나누기" headline="팀을 나눴습니다" lead={`${teams.length}팀으로 나눴습니다.`} mood="calm" {...reveal}
        detail={detail} detailLabel="팀 구성" detailDefaultOpen
        copyText={teams.map((team, ti) => `${ti + 1}팀: ${team.map((m) => m.name).join(", ")}`).join("\n")} />
    );
  }
  if (isLadder && finished && ladderAssignments.length > 0) {
    const detail = gstate.result && gstate.result.columns ? (
      // key=room.id: 방을 바꿔도 캐시된 새 방 데이터로 "pending" 을 안 거치면 이 서브트리가 마운트 해제되지 않아
      // LadderBoard 의 내부 선택(sel)이 이전 방 것으로 남는다(gameroom-ladder-room-switch-stale-selection.test.jsx).
      <LadderBoard key={room.id} result={gstate.result} highlightUserId={you.user_id} />
    ) : (
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
        {ladderAssignments.map((a) => (
          <Paper component="li" key={a.user_id} variant="outlined" sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 1.5, py: 1, animation: `${rise} .38s ease both` }}>
            <Box component="span" sx={{ flex: 1, minWidth: 0, ...KO_WORD_BREAK }}>{a.name}</Box>
            <Box component="span" aria-hidden="true" sx={{ color: "text.secondary" }}>→</Box>
            <Box component="span" sx={{ fontWeight: FONT_WEIGHT.bold, color: "primary.dark" }}>{a.outcome}</Box>
          </Paper>
        ))}
      </Box>
    );
    const mine = ladderAssignments.find((a) => a.user_id === you.user_id);
    return (
      <ResultPanel game="사다리타기" headline="사다리 결과" lead={mine ? `내 결과는 「${mine.outcome}」입니다.` : "참여자마다 도착한 결과입니다."} mood="calm" {...reveal}
        detail={detail} detailLabel="사다리" detailDefaultOpen
        copyText={ladderAssignments.map((a) => `${a.name} → ${a.outcome}`).join("\n")} />
    );
  }
  if ((isDraw || isTeam || isLadder) && room.status === "waiting") {
    return (
      <StageHint>
        {isTeam ? "참여자가 모이면 방장이 팀을 나눕니다."
          : isLadder ? "참여자가 모이면 방장이 사다리를 탑니다."
            : "참여자가 모이면 방장이 추첨을 시작합니다."}
      </StageHint>
    );
  }
  if (isVote) {
    const question = voteResult?.question || gstate.question || room.title;
    if (finished && voteResult) {
      const options = voteResult.options || [];
      const winnerIdx = Array.isArray(voteResult.winner_indexes)
        ? voteResult.winner_indexes
        : options.map((opt, i) => ((voteResult.winners || []).includes(opt) ? i : -1)).filter((i) => i >= 0);
      const winners = winnerIdx.map((i) => ({ id: `o${i}`, name: options[i], note: `${(voteResult.counts || [])[i] || 0}표` }));
      const detail = (
        <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
          {options.map((opt, i) => {
            const cnt = (voteResult.counts || [])[i] || 0;
            const win = winnerIdx.includes(i);
            return (
              <Box component="li" key={i} sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0,1fr) auto", sm: "10rem minmax(0,1fr) auto" }, alignItems: "center", gap: 1.5 }}>
                <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: win ? FONT_WEIGHT.bold : FONT_WEIGHT.regular }}>{opt}</Box>
                <Box sx={{ display: { xs: "none", sm: "block" }, height: "0.875rem", borderRadius: RADIUS.full, bgcolor: "action.hover", overflow: "hidden" }}>
                  <Box sx={{ display: "block", height: "100%", borderRadius: RADIUS.full, bgcolor: win ? "primary.main" : "primary.light", width: (maxCount ? (cnt / maxCount) * 100 : 0) + "%" }} />
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>{cnt}표</Typography>
              </Box>
            );
          })}
        </Box>
      );
      return (
        <ResultPanel game="빠른 투표" headline="투표 결과" lead={question}
          winners={winners} winnerLabel="선택됨" mood={winners.length ? "win" : "calm"} {...reveal}
          detail={detail} detailLabel="전체 집계" detailDefaultOpen
          copyText={[question, ...options.map((opt, i) => `${opt}: ${(voteResult.counts || [])[i] || 0}표`)].join("\n")} />
      );
    }
    return (
      <Box sx={{ display: "grid", gap: 2 }}>
        <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle, textAlign: "center" }}>{question}</Typography>
        {room.status === "playing" ? (
          <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
            {voteOptions.map((opt, i) => (
              <li key={i}>
                <Box component="button" type="button" sx={voteOptionSx(myVote === i, false, false)}
                  aria-pressed={myVote === i}
                  disabled={!canVote || vote.isPending} onClick={() => canVote && vote.mutate(i)}>
                  <Box component="span" sx={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{opt}</Box>
                  <Box component="span" sx={{ flexShrink: 0, minWidth: "1.75rem", textAlign: "center", fontWeight: FONT_WEIGHT.bold, color: "primary.dark", fontVariantNumeric: "tabular-nums" }}>
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
        {room.status === "playing" && !canVote && you.role === "spectator" ? (
          <StageHint>관전 중: 투표는 참여자만 할 수 있습니다.</StageHint>
        ) : null}
      </Box>
    );
  }
  if (isNumber) {
    if (finished && numResult) {
      const w = numResult.winner;
      const winners = w ? [{ id: w.user_id, name: w.name, user_id: w.user_id, person: personOf(members, w.user_id), note: `낸 숫자 ${w.number}` }] : [];
      const detail = (
        <Stack direction="row" gap={1.5} flexWrap="wrap" justifyContent="center">
          {(numResult.picks || []).map((p) => {
            const win = w && w.user_id === p.user_id;
            return (
              <Paper key={p.user_id} variant="outlined" sx={{
                display: "grid", justifyItems: "center", gap: 0.25, px: 1.5, py: 1, minWidth: "5.25rem",
                borderColor: win ? "primary.main" : "divider",
                bgcolor: (t) => (win ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
              }}>
                {/* PA-RC-0001: 24px — ProjectWbs.jsx·charts/Donut.jsx 의 큰 숫자와 같은 값+굵기 조합(의도된 예외, D-78). */}
                <Box component="span" sx={{ fontSize: "1.5rem", fontWeight: FONT_WEIGHT.extrabold, fontVariantNumeric: "tabular-nums" }}>{p.number}</Box>
                <Box component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>{p.name}</Box>
              </Paper>
            );
          })}
        </Stack>
      );
      return (
        <ResultPanel game="숫자 눈치" headline={w ? "가장 낮은 유일한 숫자" : "승자가 없습니다"}
          lead={w ? `가장 낮은 유일한 숫자는 ${w.number}입니다.` : "유일한 숫자가 없어 승자가 없습니다."}
          winners={winners} winnerLabel="승리" mood={w ? "win" : "calm"} {...reveal}
          detail={detail} detailLabel="공개된 숫자" detailDefaultOpen
          copyText={(numResult.picks || []).map((p) => `${p.name}: ${p.number}`).join("\n")} />
      );
    }
    return (
      <Box sx={stageColumnSx}>
        {room.status === "playing" ? (
          <>
            <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle, textAlign: "center" }}>
              {gstate.min || 1} ~ {gstate.max || 10} 중 하나를 몰래 내세요
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
              가장 낮은 ‘유일한’ 숫자를 낸 사람이 이깁니다. 지금 {gstate.submitted_count || 0}명 제출.
            </Typography>
            {canPick ? (
              <Stack direction="row" gap={1} alignItems="center">
                <TextField
                  size="small" type="number" value={numDraft}
                  placeholder={(gstate.min || 1) + "~" + (gstate.max || 10)}
                  inputProps={{ min: gstate.min || 1, max: gstate.max || 10, "aria-label": "낼 숫자" }}
                  onChange={(e) => setNumDraft(e.target.value)}
                  sx={{ width: "8rem", "& input": { textAlign: "center", fontVariantNumeric: "tabular-nums" } }}
                />
                <Button variant="primary" disabled={pick.isPending || numDraft === ""} sx={{ flexShrink: 0, whiteSpace: "nowrap" }}
                  onClick={() => { const v = Number(numDraft); if (Number.isInteger(v)) pick.mutate(v); }}>제출</Button>
              </Stack>
            ) : null}
            {canPick && gstate.you_submitted ? (
              <Typography variant="body2" color="text.secondary">내가 낸 숫자: {gstate.your_pick} (다시 내면 수정됩니다)</Typography>
            ) : null}
            {you.role === "spectator" ? <StageHint>관전 중: 참여자만 숫자를 낼 수 있습니다.</StageHint> : null}
          </>
        ) : (
          <StageHint>참여자가 모이면 방장이 숫자 눈치를 시작합니다.</StageHint>
        )}
      </Box>
    );
  }
  if (isRps) {
    if (finished && rpsResult && rpsResult.mode === "tournament") {
      const champ = rpsResult.champion;
      const winners = champ ? [{ id: champ.user_id, name: champ.name, user_id: champ.user_id, person: personOf(members, champ.user_id) }] : [];
      return (
        <ResultPanel game="가위바위보 토너먼트" headline={champ ? "우승자" : "우승자가 없습니다"}
          lead={champ ? `${(rpsResult.rounds || []).length}라운드를 이겨 올라왔습니다.` : "대진이 남지 않았습니다."}
          winners={winners} winnerLabel="우승" mood={champ ? "win" : "calm"} {...reveal}
          detail={<RpsTournamentResult result={rpsResult} />} detailLabel="대진표"
          copyText={champ ? `가위바위보 토너먼트 우승: ${champ.name}` : "우승자 없음"} />
      );
    }
    if (room.status === "playing" && isTournament) {
      return (
        <Box sx={stageColumnSx}>
          <RpsTournamentLive gstate={gstate} onPick={(i) => rps.mutate(i)} pending={rps.isPending} canPlay={you.in_room && you.role !== "spectator"} />
        </Box>
      );
    }
    if (finished && rpsResult) {
      const win = rpsResult.outcome === "win";
      const winners = win ? (rpsResult.winners || []).map((w) => ({ id: w.user_id, name: w.name, user_id: w.user_id, person: personOf(members, w.user_id) })) : [];
      const detail = (
        <Stack direction="row" gap={1.5} flexWrap="wrap" justifyContent="center">
          {(rpsResult.reveal || []).map((p) => {
            const won = (rpsResult.winners || []).some((w) => w.user_id === p.user_id);
            return (
              <Paper key={p.user_id} variant="outlined" sx={{
                display: "grid", justifyItems: "center", gap: 0.25, px: 1.5, py: 1, minWidth: "5.25rem",
                borderColor: won ? "primary.main" : "divider",
                bgcolor: (t) => (won ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
              }}>
                <Box component="span" aria-hidden="true" sx={{ fontSize: "2.75rem", lineHeight: 1 }}>{rpsEmoji(p.choice)}</Box>
                <Box component="span" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold }}>{p.choice}</Box>
                <Box component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>{p.name}</Box>
              </Paper>
            );
          })}
        </Stack>
      );
      return (
        <ResultPanel game="가위바위보" headline={win ? `${rpsResult.win_choice} 승리` : "무승부"}
          lead={win ? `${rpsResult.win_choice}를 낸 사람이 이겼습니다.` : "같은 손만 나왔거나 셋이 다 나왔습니다."}
          winners={winners} winnerLabel="승리" mood={win ? "win" : "calm"} {...reveal}
          detail={detail} detailLabel="낸 손" detailDefaultOpen
          copyText={(rpsResult.reveal || []).map((p) => `${p.name}: ${p.choice}`).join("\n")} />
      );
    }
    return (
      <Box sx={stageColumnSx}>
        {room.status === "playing" ? (
          <>
            <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle, textAlign: "center" }}>가위, 바위, 보 중 하나를 몰래 내세요</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
              방장이 공개하면 판정합니다. 지금 {gstate.submitted_count || 0}명 제출.
            </Typography>
            {canRps ? (
              <RpsChoices labels={RPS_LABELS} emojis={RPS_EMOJI} chosen={gstate.your_choice} disabled={rps.isPending} onPick={(i) => rps.mutate(i)} />
            ) : null}
            {canRps && gstate.you_submitted ? (
              <Typography variant="body2" color="text.secondary">낸 것: {RPS_LABELS[gstate.your_choice]} (다시 누르면 수정)</Typography>
            ) : null}
            {you.role === "spectator" ? <StageHint>관전 중: 참여자만 낼 수 있습니다.</StageHint> : null}
          </>
        ) : (
          <StageHint>참여자가 모이면 방장이 가위바위보를 시작합니다.</StageHint>
        )}
      </Box>
    );
  }
  if (isQuiz) {
    if (finished && quizResult) {
      const board = quizResult.scoreboard || [];
      const ids = Array.isArray(quizResult.winner_ids) ? quizResult.winner_ids : null;
      const winnerRows = ids ? board.filter((s) => ids.includes(s.user_id)) : board.filter((s) => (quizResult.winners || []).includes(s.name));
      const winners = winnerRows.map((s) => ({ id: s.user_id, name: s.name, user_id: s.user_id, person: personOf(members, s.user_id), note: `${s.score}점` }));
      return (
        <ResultPanel game="실시간 퀴즈" headline={winners.length ? "우승자" : "맞힌 사람이 없습니다"}
          lead={winners.length ? `${quizResult.total_rounds}문제 중 가장 많이 맞혔습니다.` : `${quizResult.total_rounds}문제를 냈습니다.`}
          winners={winners} winnerLabel="우승" mood={winners.length ? "win" : "calm"} {...reveal}
          detail={<Scoreboard rows={board.map((s) => ({ key: s.user_id, name: s.name, value: `${s.score} / ${quizResult.total_rounds}` }))} />}
          detailLabel="최종 순위" detailDefaultOpen
          copyText={board.map((s, i) => `${i + 1}. ${s.name} ${s.score}/${quizResult.total_rounds}`).join("\n")} />
      );
    }
    return (
      <Box sx={stageColumnSx}>
        {quizPlaying ? (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>
              문제 {(quizPlaying.round || 0) + 1} / {quizPlaying.total}
            </Typography>
            <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle, textAlign: "center" }}>{quizPlaying.question}</Typography>
            <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1, width: "100%", maxWidth: "30rem" }}>
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
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
              {quizPlaying.phase === "answering"
                ? `${quizPlaying.submitted_count || 0}명 응답. 방장이 정답을 공개하면 채점합니다.`
                : quizPlaying.your_answer == null ? "이번 문제에 응답하지 않았습니다."
                  : quizPlaying.your_correct ? "정답입니다! 🎉" : "아쉽지만 오답이에요."}
            </Typography>
            {liveScores.length > 0 ? (
              <Scoreboard rows={liveScores.map((s, i) => ({ key: "s" + i, name: s.name, value: s.score }))} />
            ) : null}
          </>
        ) : (
          <StageHint>참여자가 모이면 방장이 퀴즈를 시작합니다.</StageHint>
        )}
      </Box>
    );
  }
  return null;
}
