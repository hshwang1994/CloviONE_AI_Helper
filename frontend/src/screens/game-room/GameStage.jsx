import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { Button } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, RADIUS } from "../../ui/theme.js";
import { rise, stageColumnSx, RPS_LABELS, RPS_EMOJI, rpsEmoji } from "./constants.js";
import { ResultStage, StageHint, WinnerName } from "./StageShared.jsx";
import { LadderBoard } from "./LadderBoard.jsx";
import { RpsChoices, RpsTournamentLive, RpsTournamentResult } from "./RpsViews.jsx";
import { Scoreboard } from "./Scoreboard.jsx";

/* 무대(왼쪽) — 게임 종류·상태별 실제 화면. GameRoom.jsx 구조 분리(2026-08)로 값 변경 없이 이
 * 파일로 옮겼다. 게임 종류(quick_vote/team_split/random_draw/number/ladder/rps/quiz)로 먼저
 * 가르고, 그 안에서 방 상태(waiting/playing/finished)로 다시 가른다. c는
 * useGameRoomController()가 반환한 값 전체다(원래 GameRoom() 함수 지역 변수였다). */
export function GameStage({ c }) {
  const {
    room, gstate, you,
    isVote, isTeam, isDraw, isNumber, isLadder, isRps, isQuiz, isTournament,
    canVote, canPick, canRps, canQuizAnswer,
    drawWinners, teams, ladderAssignments,
    numResult, rpsResult, quizResult, quizPlaying, liveScores,
    voteResult, voteOptions, liveCounts, myVote, maxCount,
    voteOptionSx, numDraft, setNumDraft,
    mutations,
  } = c;
  const { vote, pick, rps, quizAnswer } = mutations;

  return (
    <>
          {/* 무대: 게임 종류·상태별 화면 */}
          {isDraw && room.status === "finished" && drawWinners.length > 0 ? (
            <ResultStage label="당첨">
              <Stack direction="row" gap={1} flexWrap="wrap" justifyContent={{ xs: "center", md: "flex-start" }}>
                {drawWinners.map((w) => <WinnerName key={w.user_id}>{w.name}</WinnerName>)}
              </Stack>
            </ResultStage>
          ) : isTeam && room.status === "finished" && teams.length > 0 ? (
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
          ) : isLadder && room.status === "finished" && ladderAssignments.length > 0 ? (
            gstate.result && gstate.result.columns ? (
              // key=room.id: 방을 바꿔도 react-query 캐시에 새 방 데이터가 이미 있으면
              // "pending"(스켈레톤)을 거치지 않아 이 서브트리가 마운트 해제되지 않는다 - 그러면
              // LadderBoard가 같은 인스턴스로 재사용돼 내부 sel(고른 이름의 인덱스)이 이전
              // 방 것 그대로 남는다. 새 방 참여자 수가 더 적으면 그 인덱스가 배열 범위를 벗어나
              // cols[sel]이 undefined가 되어 화면이 크래시했다(gameroom-ladder-room-switch-
              // stale-selection.test.jsx). key를 room.id에 묶어 방이 바뀌면 항상 새로 마운트되게 한다.
              <LadderBoard key={room.id} result={gstate.result} highlightUserId={you.user_id} />
            ) : (
              <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
                {ladderAssignments.map((a) => (
                  <Paper component="li" key={a.user_id} variant="outlined" sx={{
                    display: "flex", alignItems: "center", gap: 1.5, px: 1.5, py: 1, animation: `${rise} .38s ease both`,
                  }}>
                    <Box component="span" sx={{ flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>{a.name}</Box>
                    <Box component="span" aria-hidden="true" sx={{ color: "text.secondary" }}>→</Box>
                    <Box component="span" sx={{ fontWeight: FONT_WEIGHT.bold, color: "primary.dark" }}>{a.outcome}</Box>
                  </Paper>
                ))}
              </Box>
            )
          ) : (isDraw || isTeam || isLadder) && room.status === "waiting" ? (
            <StageHint>
              {isTeam ? "참여자가 모이면 방장이 팀을 나눕니다."
                : isLadder ? "참여자가 모이면 방장이 사다리를 탑니다."
                  : "참여자가 모이면 방장이 추첨을 시작합니다."}
            </StageHint>
          ) : isVote ? (
            <Box sx={{ display: "grid", gap: 2 }}>
              <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle, textAlign: "center" }}>
                {voteResult?.question || gstate.question || room.title}
              </Typography>
              {room.status === "finished" && voteResult ? (
                <>
                  <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
                    {(voteResult.options || []).map((opt, i) => {
                      const c = (voteResult.counts || [])[i] || 0;
                      const win = (voteResult.winners || []).includes(opt);
                      return (
                        <Box component="li" key={i} sx={{
                          display: "grid", gridTemplateColumns: { xs: "minmax(0,1fr) auto", sm: "10rem minmax(0,1fr) auto" },
                          alignItems: "center", gap: 1.5,
                        }}>
                          <Box component="span" sx={{
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            fontWeight: win ? FONT_WEIGHT.bold : FONT_WEIGHT.regular,
                          }}>{opt}</Box>
                          <Box sx={{
                            display: { xs: "none", sm: "block" }, height: "0.875rem", borderRadius: RADIUS.full,
                            bgcolor: "action.hover", overflow: "hidden",
                          }}>
                            <Box sx={{
                              display: "block", height: "100%", borderRadius: RADIUS.full,
                              bgcolor: win ? "primary.main" : "primary.light",
                              width: (maxCount ? (c / maxCount) * 100 : 0) + "%",
                            }} />
                          </Box>
                          <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>{c}표</Typography>
                        </Box>
                      );
                    })}
                  </Box>
                  {(voteResult.winners || []).length > 0 ? (
                    <ResultStage label="결과">
                      <Stack direction="row" gap={1} flexWrap="wrap" justifyContent={{ xs: "center", md: "flex-start" }}>
                        {voteResult.winners.map((w) => <WinnerName key={w}>{w}</WinnerName>)}
                      </Stack>
                    </ResultStage>
                  ) : <StageHint>투표한 사람이 없습니다.</StageHint>}
                </>
              ) : room.status === "playing" ? (
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
          ) : isNumber ? (
            <Box sx={stageColumnSx}>
              {room.status === "finished" && numResult ? (
                <>
                  <ResultStage mood={numResult.winner ? "win" : "calm"} label="가장 낮은 유일 숫자">
                    {numResult.winner
                      ? <WinnerName>{numResult.winner.name} ({numResult.winner.number})</WinnerName>
                      : <Typography color="text.secondary">유일한 숫자가 없어 승자가 없습니다.</Typography>}
                  </ResultStage>
                  <Stack direction="row" gap={1.5} flexWrap="wrap" justifyContent="center">
                    {(numResult.picks || []).map((p) => {
                      const win = numResult.winner && numResult.winner.user_id === p.user_id;
                      return (
                        <Paper key={p.user_id} variant="outlined" sx={{
                          display: "grid", justifyItems: "center", gap: 0.25, px: 1.5, py: 1, minWidth: "5.25rem",
                          borderColor: win ? "primary.main" : "divider",
                          bgcolor: (t) => (win ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
                        }}>
                          {/* PA-RC-0001: 24px — ProjectWbs.jsx·charts/Donut.jsx의 큰 숫자와 정확히
                              같은 값+굵기 조합이라 우연이 아니라 이미 자리 잡은 관용으로 보인다.
                              statValue(30px)·pageTitle(20px) 사이 어느 쪽에도 억지로 안 맞춘다 —
                              세 곳이 이미 서로를 증거로 세우고 있어 임의로 바꾸면 그 일치가
                              깨진다. 전용 토큰 신설은 2026-08-16에 검토했으나 theme-baseline.
                              test.js가 FONT_SIZE를 정확히 6단계로 못박은 회귀 테스트라 보류
                              (DECISIONS.md D-78) — 이 값은 raw literal 예외로 유지한다. */}
                          <Box component="span" sx={{ fontSize: "1.5rem", fontWeight: FONT_WEIGHT.extrabold, fontVariantNumeric: "tabular-nums" }}>{p.number}</Box>
                          <Box component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>{p.name}</Box>
                        </Paper>
                      );
                    })}
                  </Stack>
                </>
              ) : room.status === "playing" ? (
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
                        size="small"
                        type="number"
                        value={numDraft}
                        placeholder={(gstate.min || 1) + "~" + (gstate.max || 10)}
                        inputProps={{ min: gstate.min || 1, max: gstate.max || 10, "aria-label": "낼 숫자" }}
                        onChange={(e) => setNumDraft(e.target.value)}
                        sx={{ width: "8rem", "& input": { textAlign: "center", fontVariantNumeric: "tabular-nums" } }}
                      />
                      <Button variant="primary" disabled={pick.isPending || numDraft === ""}
                        sx={{ flexShrink: 0, whiteSpace: "nowrap" }}
                        onClick={() => { const v = Number(numDraft); if (Number.isInteger(v)) pick.mutate(v); }}>제출</Button>
                    </Stack>
                  ) : null}
                  {canPick && gstate.you_submitted ? (
                    <Typography variant="body2" color="text.secondary">내가 낸 숫자: {gstate.your_pick} (다시 내면 수정됩니다)</Typography>
                  ) : null}
                  {you.role === "spectator" ? (
                    <StageHint>관전 중: 참여자만 숫자를 낼 수 있습니다.</StageHint>
                  ) : null}
                </>
              ) : (
                <StageHint>참여자가 모이면 방장이 숫자 눈치를 시작합니다.</StageHint>
              )}
            </Box>
          ) : isRps ? (
            <Box sx={stageColumnSx}>
              {room.status === "finished" && rpsResult && rpsResult.mode === "tournament" ? (
                <RpsTournamentResult result={rpsResult} />
              ) : room.status === "playing" && isTournament ? (
                <RpsTournamentLive gstate={gstate} onPick={(i) => rps.mutate(i)}
                  pending={rps.isPending} canPlay={you.in_room && you.role !== "spectator"} />
              ) : room.status === "finished" && rpsResult ? (
                <>
                  {rpsResult.outcome === "win" ? (
                    <ResultStage label={`${rpsResult.win_choice} 승리`}>
                      <Stack direction="row" gap={1} flexWrap="wrap" justifyContent={{ xs: "center", md: "flex-start" }}>
                        {(rpsResult.winners || []).map((w) => <WinnerName key={w.user_id}>{w.name}</WinnerName>)}
                      </Stack>
                    </ResultStage>
                  ) : (
                    <ResultStage mood="calm" label="무승부">
                      <Typography color="text.secondary">같은 손만 나왔거나 셋이 다 나왔습니다.</Typography>
                    </ResultStage>
                  )}
                  <Stack direction="row" gap={1.5} flexWrap="wrap" justifyContent="center">
                    {(rpsResult.reveal || []).map((p) => {
                      const win = (rpsResult.winners || []).some((w) => w.user_id === p.user_id);
                      return (
                        <Paper key={p.user_id} variant="outlined" sx={{
                          display: "grid", justifyItems: "center", gap: 0.25, px: 1.5, py: 1, minWidth: "5.25rem",
                          borderColor: win ? "primary.main" : "divider",
                          bgcolor: (t) => (win ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
                        }}>
                          <Box component="span" aria-hidden="true" sx={{ fontSize: "2.75rem", lineHeight: 1 }}>{rpsEmoji(p.choice)}</Box>
                          <Box component="span" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold }}>{p.choice}</Box>
                          <Box component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>{p.name}</Box>
                        </Paper>
                      );
                    })}
                  </Stack>
                </>
              ) : room.status === "playing" ? (
                <>
                  <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle, textAlign: "center" }}>가위, 바위, 보 중 하나를 몰래 내세요</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
                    방장이 공개하면 판정합니다. 지금 {gstate.submitted_count || 0}명 제출.
                  </Typography>
                  {canRps ? (
                    <RpsChoices labels={RPS_LABELS} emojis={RPS_EMOJI} chosen={gstate.your_choice}
                      disabled={rps.isPending} onPick={(i) => rps.mutate(i)} />
                  ) : null}
                  {canRps && gstate.you_submitted ? (
                    <Typography variant="body2" color="text.secondary">낸 것: {RPS_LABELS[gstate.your_choice]} (다시 누르면 수정)</Typography>
                  ) : null}
                  {you.role === "spectator" ? (
                    <StageHint>관전 중: 참여자만 낼 수 있습니다.</StageHint>
                  ) : null}
                </>
              ) : (
                <StageHint>참여자가 모이면 방장이 가위바위보를 시작합니다.</StageHint>
              )}
            </Box>
          ) : isQuiz ? (
            <Box sx={stageColumnSx}>
              {room.status === "finished" && quizResult ? (
                <>
                  <ResultStage mood={(quizResult.winners || []).length ? "win" : "calm"} label="최종 순위">
                    {(quizResult.winners || []).length > 0 ? (
                      <Stack direction="row" gap={1} flexWrap="wrap" justifyContent={{ xs: "center", md: "flex-start" }}>
                        {quizResult.winners.map((w) => <WinnerName key={w}>{w}</WinnerName>)}
                      </Stack>
                    ) : (
                      <Typography color="text.secondary">맞힌 사람이 없습니다.</Typography>
                    )}
                  </ResultStage>
                  <Scoreboard rows={(quizResult.scoreboard || []).map((s) => ({
                    key: s.user_id, name: s.name, value: `${s.score} / ${quizResult.total_rounds}`,
                  }))} />
                </>
              ) : quizPlaying ? (
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
                            {isAnswer ? (
                              <Box component="span" sx={{ flexShrink: 0, fontWeight: FONT_WEIGHT.bold, color: "success.strong" }}>정답</Box>
                            ) : null}
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
          ) : null}

    </>
  );
}
