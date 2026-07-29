import React, { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import confetti from "canvas-confetti";
import { Badge, Button, ErrorState, PageHeader, Skeleton, useToast } from "../ui/kit.jsx";
import { GAME_LABELS } from "./Games.jsx";

/* 게임방(§5·§6·§13·§16.2). 폴링(1.2초)으로 방 상태·참여자·이벤트를 실시간처럼 흐르게 한다.
 * 결과(당첨자)는 서버가 확정해 내려준다(§13.1) — 클라이언트는 표현만 한다. 게임방 채팅은
 * 순수 내부 DB(n8n 안 거침, §13.2). 방에 들어오면 한 번 자동 입장(가득/진행 중이면 서버가 관전). */

const STATUS_LABELS = { waiting: "대기 중", playing: "진행 중", finished: "결과 확인 중" };
const STATUS_KIND = { waiting: "info", playing: "warn", finished: "ok" };
const ROLE_LABELS = { host: "방장", player: "참여", spectator: "관전" };

// 승자 공개 축포. canvas-confetti는 캔버스를 CSSOM 개별 속성으로 스타일링하고 기본은 워커 미사용이라
// CSP(style-src 'self', worker 미허용)에 안전하다. 동작 최소화 사용자는 라이브러리 옵션이 알아서 끈다.
function celebrate() {
  const base = { spread: 74, startVelocity: 45, ticks: 200, origin: { y: 0.55 }, disableForReducedMotion: true };
  confetti({ ...base, particleCount: 90 });
  window.setTimeout(() => confetti({ ...base, particleCount: 55, angle: 60, origin: { x: 0, y: 0.62 } }), 140);
  window.setTimeout(() => confetti({ ...base, particleCount: 55, angle: 120, origin: { x: 1, y: 0.62 } }), 260);
}

// 결과에 '승자'가 있으면 방별 고유 문자열(축포 트리거 키)을, 없으면 null. 값이 바뀔 때만 축포.
function deriveCelebrateKey(data) {
  if (!data || !data.room || data.room.status !== "finished") return null;
  const gt = data.room.game_type;
  const res = (data.state && data.state.result) || null;
  if (!res) return null;
  let sig = null;
  if (gt === "random_draw" && Array.isArray(res) && res.length) sig = "d:" + res.map((w) => w.user_id).join(",");
  else if (gt === "quick_vote" && (res.winners || []).length) sig = "v:" + res.winners.join(",");
  else if (gt === "number" && res.winner) sig = "n:" + res.winner.user_id;
  else if (gt === "rps" && res.outcome === "win") sig = "r:" + (res.winners || []).map((w) => w.user_id).join(",");
  else if (gt === "quiz" && (res.winners || []).length) sig = "q:" + res.winners.join(",");
  return sig ? data.room.id + sig : null;
}

export function GameRoom() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const joinedRef = useRef(false);
  const [draft, setDraft] = useState("");
  const [numDraft, setNumDraft] = useState("");

  const state = useQuery({
    queryKey: ["game-room", id],
    queryFn: () => api(`/api/games/rooms/${id}/state?since=0`),
    refetchInterval: 1200,
  });

  const join = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/join`, { method: "POST" }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "입장하지 못했습니다.", "error"),
  });
  // 방에 처음 들어오면 자동 입장. 서버가 대기 중·자리 있으면 참여자로, 아니면 관전자로 배정.
  useEffect(() => {
    if (!joinedRef.current && state.data && !state.data.you.in_room) {
      joinedRef.current = true;
      join.mutate();
    }
  }, [state.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const ready = useMutation({
    mutationFn: (v) => api(`/api/games/rooms/${id}/ready`, { method: "POST", body: { ready: v } }),
    onSuccess: () => state.refetch(),
  });
  const start = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/start`, { method: "POST" }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "게임을 시작하지 못했습니다.", "error"),
  });
  const vote = useMutation({
    mutationFn: (option) => api(`/api/games/rooms/${id}/vote`, { method: "POST", body: { option } }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "투표하지 못했습니다.", "error"),
  });
  const finish = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/finish`, { method: "POST" }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "게임을 종료하지 못했습니다.", "error"),
  });
  const pick = useMutation({
    mutationFn: (value) => api(`/api/games/rooms/${id}/pick`, { method: "POST", body: { value } }),
    onSuccess: () => { setNumDraft(""); state.refetch(); },
    onError: (e) => toast((e && e.message) || "숫자를 내지 못했습니다.", "error"),
  });
  const rps = useMutation({
    mutationFn: (option) => api(`/api/games/rooms/${id}/rps`, { method: "POST", body: { option } }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "내지 못했습니다.", "error"),
  });
  const quizAnswer = useMutation({
    mutationFn: (option) => api(`/api/games/rooms/${id}/quiz-answer`, { method: "POST", body: { option } }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "답을 내지 못했습니다.", "error"),
  });
  const reveal = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/reveal`, { method: "POST" }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "정답을 공개하지 못했습니다.", "error"),
  });
  const nextQ = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/next`, { method: "POST" }),
    onSuccess: () => state.refetch(),
    onError: (e) => toast((e && e.message) || "다음으로 넘어가지 못했습니다.", "error"),
  });
  const reset = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/reset`, { method: "POST" }),
    onSuccess: () => state.refetch(),
  });
  const leave = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/leave`, { method: "POST" }),
    onSettled: () => { qc.invalidateQueries({ queryKey: ["games-rooms"] }); nav("/games"); },
  });
  const chat = useMutation({
    mutationFn: (text) => api(`/api/games/rooms/${id}/chat`, { method: "POST", body: { text } }),
    onSuccess: () => { setDraft(""); state.refetch(); },
    onError: (e) => toast((e && e.message) || "메시지를 보내지 못했습니다.", "error"),
  });

  // 승자가 확정되면(폴링으로 결과가 처음 도착하는 순간) 축포를 한 번 터뜨린다. celebrateKey는
  // 결과 내용이 바뀔 때만 값이 달라지므로 폴링마다 재발화하지 않는다. 훅 순서 유지를 위해
  // 조기 return 위에 둔다(무승부·팀나누기·사다리처럼 '승자'가 없는 결과는 제외).
  const celebrateKey = deriveCelebrateKey(state.data);
  useEffect(() => { if (celebrateKey) celebrate(); }, [celebrateKey]);

  if (state.isError) return <div className="c-screen"><ErrorState error={state.error} onRetry={() => state.refetch()} /></div>;
  if (state.isPending) return <div className="c-screen"><Skeleton lines={6} /></div>;

  const { room, you, members } = state.data;
  const gstate = state.data.state || {};
  const chatMsgs = (state.data.events || []).filter((e) => e.kind === "chat");
  const isVote = room.game_type === "quick_vote";
  const isTeam = room.game_type === "team_split";
  const isDraw = room.game_type === "random_draw";
  const isNumber = room.game_type === "number";
  const isLadder = room.game_type === "ladder";
  const isRps = room.game_type === "rps";
  const isQuiz = room.game_type === "quiz";
  const isHost = you.is_host;
  const canReady = isDraw && you.in_room && you.role === "player" && room.status === "waiting";
  const canVote = isVote && room.status === "playing" && you.in_room && you.role !== "spectator";
  const canPick = isNumber && room.status === "playing" && you.in_room && you.role !== "spectator";
  const canRps = isRps && room.status === "playing" && you.in_room && you.role !== "spectator";

  // 랜덤 추첨 결과(당첨자 이름) / 팀 나누기 결과(팀별 명단) / 빠른 투표 결과(집계).
  const drawWinners = isDraw ? (gstate.result || []) : [];
  const teams = isTeam ? (gstate.result?.teams || []) : [];
  const ladderAssignments = isLadder ? (gstate.result?.assignments || []) : [];
  // 숫자 눈치: 진행 중엔 서버가 남의 선택을 감춘다(min/max/제출수/내 선택만). 종료 후 result 공개.
  const numResult = isNumber ? (gstate.result || null) : null;
  const rpsResult = isRps ? (gstate.result || null) : null;
  const RPS_LABELS = ["가위", "바위", "보"];
  const RPS_EMOJI = ["✌️", "✊", "✋"];
  const rpsEmoji = (label) => RPS_EMOJI[RPS_LABELS.indexOf(label)] || "";
  // 실시간 퀴즈: 진행 중엔 gstate가 라운드/문제/보기/내 답/점수(정답은 revealed에서만). 종료 후 result.
  const quizResult = isQuiz ? (gstate.result || null) : null;
  const quizPlaying = isQuiz && room.status === "playing" ? gstate : null;
  const canQuizAnswer = isQuiz && room.status === "playing" && gstate.phase === "answering" && you.in_room && you.role !== "spectator";
  const nameOf = {};
  members.forEach((m) => { nameOf[m.user_id] = m.name; });
  const liveScores = (quizPlaying?.scores || []).map((s) => ({ name: nameOf[s.user_id] || "?", score: s.score }));
  const voteResult = isVote ? (gstate.result || null) : null;
  // 빠른 투표 진행 중: state.votes(uid→선택지 index)로 라이브 집계 + 내 선택 표시.
  const voteOptions = isVote ? (gstate.options || voteResult?.options || []) : [];
  const votes = (isVote && gstate.votes) || {};
  const liveCounts = voteOptions.map((_, i) => Object.values(votes).filter((v) => v === i).length);
  const myVote = votes[you.user_id];
  const maxCount = voteResult ? Math.max(0, ...(voteResult.counts || [])) : Math.max(0, ...liveCounts);

  const sendChat = () => { const t = draft.trim(); if (t && !chat.isPending) chat.mutate(t); };

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="놀이" title={room.title}
        actions={<Button onClick={() => leave.mutate()} disabled={leave.isPending}>나가기</Button>} />

      <div className="game-room">
        <section className="game-main">
          <div className="game-status-bar">
            <Badge value={GAME_LABELS[room.game_type] || room.game_type} kind="neutral" />
            <Badge value={STATUS_LABELS[room.status] || room.status} kind={STATUS_KIND[room.status] || "neutral"} />
            <span className="game-count">참여 {room.player_count}/{room.max_players}</span>
            {you.role === "spectator" ? <span className="game-count">관전 중</span> : null}
          </div>

          {/* 무대: 게임 종류·상태별 화면 */}
          {isDraw && room.status === "finished" && drawWinners.length > 0 ? (
            <div className="game-result">
              <div className="game-result-label">당첨</div>
              <div className="game-result-winners">
                {drawWinners.map((w) => <span key={w.user_id} className="game-winner">{w.name}</span>)}
              </div>
            </div>
          ) : isTeam && room.status === "finished" && teams.length > 0 ? (
            <div className="game-teams">
              {teams.map((team, ti) => (
                <div key={ti} className="game-team">
                  <div className="game-team-title">{ti + 1}팀 <span className="game-team-size">{team.length}명</span></div>
                  <ul className="game-team-members">
                    {team.map((m) => <li key={m.user_id}>{m.name}</li>)}
                  </ul>
                </div>
              ))}
            </div>
          ) : isLadder && room.status === "finished" && ladderAssignments.length > 0 ? (
            <ul className="game-ladder">
              {ladderAssignments.map((a) => (
                <li key={a.user_id} className="game-ladder-row">
                  <span className="game-ladder-name">{a.name}</span>
                  <span className="game-ladder-arrow" aria-hidden="true">→</span>
                  <span className="game-ladder-outcome">{a.outcome}</span>
                </li>
              ))}
            </ul>
          ) : (isDraw || isTeam || isLadder) && room.status === "waiting" ? (
            <div className="game-stage-hint">
              {isTeam ? "참여자가 모이면 방장이 팀을 나눕니다."
                : isLadder ? "참여자가 모이면 방장이 사다리를 탑니다."
                  : "참여자가 모이면 방장이 추첨을 시작합니다."}
            </div>
          ) : isVote ? (
            <div className="game-vote">
              <div className="game-vote-q">{voteResult?.question || gstate.question || room.title}</div>
              {room.status === "finished" && voteResult ? (
                <>
                  <ul className="game-vote-bars">
                    {(voteResult.options || []).map((opt, i) => {
                      const c = (voteResult.counts || [])[i] || 0;
                      const win = (voteResult.winners || []).includes(opt);
                      return (
                        <li key={i} className={"game-bar" + (win ? " is-win" : "")}>
                          <span className="game-bar-label">{opt}</span>
                          <span className="game-bar-track"><span className="game-bar-fill" style={{ width: (maxCount ? (c / maxCount) * 100 : 0) + "%" }} /></span>
                          <span className="game-bar-count">{c}표</span>
                        </li>
                      );
                    })}
                  </ul>
                  {(voteResult.winners || []).length > 0 ? (
                    <div className="game-result-winners">
                      {voteResult.winners.map((w) => <span key={w} className="game-winner">{w}</span>)}
                    </div>
                  ) : <div className="game-stage-hint">투표한 사람이 없습니다.</div>}
                </>
              ) : room.status === "playing" ? (
                <ul className="game-vote-options">
                  {voteOptions.map((opt, i) => (
                    <li key={i}>
                      <button type="button" className={"game-vote-option" + (myVote === i ? " is-mine" : "")}
                        disabled={!canVote || vote.isPending} onClick={() => canVote && vote.mutate(i)}>
                        <span className="game-vote-option-label">{opt}</span>
                        <span className="game-vote-option-count">{liveCounts[i]}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <ul className="game-vote-options">
                  {voteOptions.map((opt, i) => (
                    <li key={i}><div className="game-vote-option is-preview">{opt}</div></li>
                  ))}
                </ul>
              )}
              {room.status === "playing" && !canVote && you.role === "spectator" ? (
                <div className="game-stage-hint">관전 중 — 투표는 참여자만 할 수 있습니다.</div>
              ) : null}
            </div>
          ) : isNumber ? (
            <div className="game-number">
              {room.status === "finished" && numResult ? (
                <>
                  <div className="game-result-label">가장 낮은 유일 숫자</div>
                  {numResult.winner ? (
                    <div className="game-result-winners">
                      <span className="game-winner">{numResult.winner.name} ({numResult.winner.number})</span>
                    </div>
                  ) : <div className="game-stage-hint">유일한 숫자가 없어 승자가 없습니다.</div>}
                  <ul className="game-picks">
                    {(numResult.picks || []).map((p) => {
                      const win = numResult.winner && numResult.winner.user_id === p.user_id;
                      return (
                        <li key={p.user_id} className={"game-pick" + (win ? " is-win" : "")}>
                          <span className="game-pick-num">{p.number}</span>
                          <span className="game-pick-name">{p.name}</span>
                        </li>
                      );
                    })}
                  </ul>
                </>
              ) : room.status === "playing" ? (
                <>
                  <div className="game-vote-q">1 ~ {gstate.max || 10} 중 하나를 몰래 내세요</div>
                  <div className="game-stage-hint">가장 낮은 ‘유일한’ 숫자를 낸 사람이 이깁니다. 지금 {gstate.submitted_count || 0}명 제출.</div>
                  {canPick ? (
                    <div className="game-num-input">
                      <input
                        className="k-input"
                        type="number"
                        min={gstate.min || 1}
                        max={gstate.max || 10}
                        value={numDraft}
                        placeholder={(gstate.min || 1) + "~" + (gstate.max || 10)}
                        onChange={(e) => setNumDraft(e.target.value)}
                      />
                      <Button variant="primary" disabled={pick.isPending || numDraft === ""}
                        onClick={() => { const v = Number(numDraft); if (Number.isInteger(v)) pick.mutate(v); }}>제출</Button>
                    </div>
                  ) : null}
                  {canPick && gstate.you_submitted ? (
                    <div className="game-stage-hint">내가 낸 숫자: {gstate.your_pick} (다시 내면 변경됩니다)</div>
                  ) : null}
                  {you.role === "spectator" ? (
                    <div className="game-stage-hint">관전 중 — 참여자만 숫자를 낼 수 있습니다.</div>
                  ) : null}
                </>
              ) : (
                <div className="game-stage-hint">참여자가 모이면 방장이 숫자 눈치를 시작합니다.</div>
              )}
            </div>
          ) : isRps ? (
            <div className="game-number">
              {room.status === "finished" && rpsResult ? (
                <>
                  {rpsResult.outcome === "win" ? (
                    <>
                      <div className="game-result-label">{rpsResult.win_choice} 승리</div>
                      <div className="game-result-winners">
                        {(rpsResult.winners || []).map((w) => <span key={w.user_id} className="game-winner">{w.name}</span>)}
                      </div>
                    </>
                  ) : <div className="game-result-label">무승부</div>}
                  <ul className="game-hands">
                    {(rpsResult.reveal || []).map((p) => {
                      const win = (rpsResult.winners || []).some((w) => w.user_id === p.user_id);
                      return (
                        <li key={p.user_id} className={"game-hand" + (win ? " is-win" : "")}>
                          <span className="game-hand-emoji" aria-hidden="true">{rpsEmoji(p.choice)}</span>
                          <span className="game-hand-choice">{p.choice}</span>
                          <span className="game-pick-name">{p.name}</span>
                        </li>
                      );
                    })}
                  </ul>
                </>
              ) : room.status === "playing" ? (
                <>
                  <div className="game-vote-q">가위, 바위, 보 중 하나를 몰래 내세요</div>
                  <div className="game-stage-hint">방장이 공개하면 판정합니다. 지금 {gstate.submitted_count || 0}명 제출.</div>
                  {canRps ? (
                    <div className="game-rps-choices">
                      {RPS_LABELS.map((label, i) => (
                        <button key={i} type="button"
                          className={"game-rps-choice" + (gstate.your_choice === i ? " is-mine" : "")}
                          disabled={rps.isPending} onClick={() => rps.mutate(i)}>
                          <span className="game-rps-emoji" aria-hidden="true">{RPS_EMOJI[i]}</span>
                          <span className="game-rps-label">{label}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {canRps && gstate.you_submitted ? (
                    <div className="game-stage-hint">낸 것: {RPS_LABELS[gstate.your_choice]} (다시 누르면 변경)</div>
                  ) : null}
                  {you.role === "spectator" ? (
                    <div className="game-stage-hint">관전 중 — 참여자만 낼 수 있습니다.</div>
                  ) : null}
                </>
              ) : (
                <div className="game-stage-hint">참여자가 모이면 방장이 가위바위보를 시작합니다.</div>
              )}
            </div>
          ) : isQuiz ? (
            <div className="game-quiz">
              {room.status === "finished" && quizResult ? (
                <>
                  <div className="game-result-label">최종 순위</div>
                  {(quizResult.winners || []).length > 0 ? (
                    <div className="game-result-winners">
                      {quizResult.winners.map((w) => <span key={w} className="game-winner">{w}</span>)}
                    </div>
                  ) : null}
                  <ol className="game-scoreboard">
                    {(quizResult.scoreboard || []).map((s) => (
                      <li key={s.user_id} className="game-score-row">
                        <span className="game-score-name">{s.name}</span>
                        <span className="game-score-val">{s.score} / {quizResult.total_rounds}</span>
                      </li>
                    ))}
                  </ol>
                </>
              ) : quizPlaying ? (
                <>
                  <div className="game-quiz-round">문제 {(quizPlaying.round || 0) + 1} / {quizPlaying.total}</div>
                  <div className="game-vote-q">{quizPlaying.question}</div>
                  <ul className="game-vote-options">
                    {(quizPlaying.options || []).map((opt, i) => {
                      const mine = quizPlaying.your_answer === i;
                      const isAnswer = quizPlaying.phase === "revealed" && quizPlaying.answer === i;
                      const cls = "game-vote-option" + (mine ? " is-mine" : "") + (isAnswer ? " is-correct" : "");
                      return (
                        <li key={i}>
                          <button type="button" className={cls}
                            disabled={!canQuizAnswer || quizAnswer.isPending}
                            onClick={() => canQuizAnswer && quizAnswer.mutate(i)}>
                            <span className="game-vote-option-label">{opt}</span>
                            {isAnswer ? <span className="game-vote-option-count">정답</span> : null}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                  {quizPlaying.phase === "answering" ? (
                    <div className="game-stage-hint">{quizPlaying.submitted_count || 0}명 응답. 방장이 정답을 공개하면 채점합니다.</div>
                  ) : (
                    <div className="game-stage-hint">{quizPlaying.your_answer == null ? "이번 문제에 응답하지 않았습니다." : quizPlaying.your_correct ? "정답입니다! 🎉" : "아쉽지만 오답이에요."}</div>
                  )}
                  {liveScores.length > 0 ? (
                    <ol className="game-scoreboard">
                      {liveScores.map((s, i) => (
                        <li key={i} className="game-score-row"><span className="game-score-name">{s.name}</span><span className="game-score-val">{s.score}</span></li>
                      ))}
                    </ol>
                  ) : null}
                </>
              ) : (
                <div className="game-stage-hint">참여자가 모이면 방장이 퀴즈를 시작합니다.</div>
              )}
            </div>
          ) : null}

          <div className="game-controls">
            {canReady ? (
              <Button variant={you.ready ? "default" : "primary"} onClick={() => ready.mutate(!you.ready)} disabled={ready.isPending}>
                {you.ready ? "준비 해제" : "준비"}
              </Button>
            ) : null}
            {isHost && room.status === "waiting" ? (
              <Button variant="primary" onClick={() => start.mutate()} disabled={start.isPending}>{isVote ? "투표 시작" : isTeam ? "팀 나누기" : isNumber ? "숫자 눈치 시작" : isLadder ? "사다리 타기" : isRps ? "가위바위보 시작" : isQuiz ? "퀴즈 시작" : "추첨 시작"}</Button>
            ) : null}
            {isHost && (isVote || isNumber || isRps) && room.status === "playing" ? (
              <Button variant="primary" onClick={() => finish.mutate()} disabled={finish.isPending}>{isVote ? "투표 종료" : "결과 공개"}</Button>
            ) : null}
            {isHost && isQuiz && room.status === "playing" && quizPlaying?.phase === "answering" ? (
              <Button variant="primary" onClick={() => reveal.mutate()} disabled={reveal.isPending}>정답 공개</Button>
            ) : null}
            {isHost && isQuiz && room.status === "playing" && quizPlaying?.phase === "revealed" ? (
              <Button variant="primary" onClick={() => nextQ.mutate()} disabled={nextQ.isPending}>
                {(quizPlaying.round || 0) + 1 >= quizPlaying.total ? "결과 보기" : "다음 문제"}
              </Button>
            ) : null}
            {isHost && room.status === "finished" ? (
              <Button variant="primary" onClick={() => reset.mutate()} disabled={reset.isPending}>다시 하기</Button>
            ) : null}
          </div>
        </section>

        <aside className="game-side">
          <div className="game-panel">
            <div className="game-side-title">참여자 ({members.length})</div>
            <ul className="game-member-list">
              {members.map((m) => (
                <li key={m.user_id} className="game-member">
                  <span className="game-member-name">{m.name}</span>
                  <span className="game-member-tags">
                    {m.user_id === room.host_user_id
                      ? <Badge value="방장" kind="info" />
                      : <Badge value={ROLE_LABELS[m.role] || m.role} kind="neutral" />}
                    {m.role === "player" && m.ready ? <Badge value="준비" kind="ok" /> : null}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="game-panel game-chat">
            <div className="game-side-title">채팅</div>
            <div className="game-chat-log">
              {chatMsgs.length === 0 ? (
                <div className="game-chat-empty">아직 메시지가 없습니다.</div>
              ) : chatMsgs.map((e) => (
                <div key={e.seq} className="game-chat-msg">
                  <span className="game-chat-who">{e.payload.name}</span>
                  <span className="game-chat-text">{e.payload.text}</span>
                </div>
              ))}
            </div>
            <div className="game-chat-input">
              <input className="k-input" maxLength={500} value={draft} placeholder="메시지 입력"
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); sendChat(); } }} />
              <Button variant="primary" onClick={sendChat} disabled={chat.isPending}>보내기</Button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
