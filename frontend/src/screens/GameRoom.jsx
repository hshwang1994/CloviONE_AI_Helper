import React, { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import confetti from "canvas-confetti";
import { Badge, Button, ErrorState, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
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
  else if (gt === "rps" && res.mode === "tournament" && res.champion) sig = "t:" + res.champion.user_id;
  else if (gt === "rps" && res.outcome === "win") sig = "r:" + (res.winners || []).map((w) => w.user_id).join(",");
  else if (gt === "quiz" && (res.winners || []).length) sig = "q:" + res.winners.join(",");
  return sig ? data.room.id + sig : null;
}

// 백엔드는 UTC를 tz 표기 없는 isoformat으로 준다(예: "2026-07-29T05:30:00"). Z를 붙여 UTC로
// 파싱해야 브라우저가 로컬(KST)로 오해하지 않는다(lib/format.js와 같은 규칙). 이걸 빼먹으면
// 마감이 9시간 과거로 계산돼 카운트다운이 즉시 0이 되고 가위바위보가 바로 자동 처리되는 버그가 난다.
function toDate(iso) {
  if (!iso) return null;
  const s = String(iso);
  const norm = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(norm);
  return Number.isNaN(d.getTime()) ? null : d;
}

// 채팅 시각(HH:MM). created_at는 UTC — UTC로 파싱한 뒤 브라우저 로컬 시간으로 표시.
function fmtTime(iso) {
  const d = toDate(iso);
  if (!d) return "";
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

// 서버가 준 마감(UTC ISO)까지 남은 초. 없으면 null. 0.25초마다 다시 계산해 부드럽게 줄어든다.
function useCountdown(deadline) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    if (!deadline) return undefined;
    const t = window.setInterval(() => setNowMs(Date.now()), 250);
    return () => window.clearInterval(t);
  }, [deadline]);
  if (!deadline) return null;
  const d = toDate(deadline);
  if (!d) return null;
  return Math.max(0, Math.ceil((d.getTime() - nowMs) / 1000));
}

// 카운트다운 배지. 남은 시간이 적으면 경고색. 무제한(deadline 없음)이면 아무것도 안 그린다.
function Countdown({ remaining }) {
  if (remaining == null) return null;
  const urgent = remaining <= 5;
  return (
    <div className={"game-timer" + (urgent ? " is-urgent" : "")} aria-live="polite">
      <span className="game-timer-num">{remaining}</span>
      <span className="game-timer-unit">초</span>
    </div>
  );
}

/* 사다리(아미다쿠지) 시각화. 서버가 확정한 세로줄·가로줄·도착지를 정직하게 그리고,
 * 위쪽 이름을 누르면 그 사람의 경로를 따라 내려가는 선을 강조한다. 좌표는 열을 균등 분할한
 * 중심(그리드 1fr 칩과 정렬)으로 잡는다. 선은 non-scaling-stroke로 늘려도 굵기 유지. */
function LadderBoard({ result, highlightUserId }) {
  const cols = result.columns || [];
  const outcomes = result.outcomes || [];
  const rungs = result.rungs || [];
  const rows = result.rows || 8;
  const n = cols.length;
  const initial = highlightUserId ? cols.findIndex((c) => c.user_id === highlightUserId) : -1;
  const [sel, setSel] = useState(initial >= 0 ? initial : null);
  if (n < 2) return null;

  const colX = (c) => (c + 0.5) * (100 / n);
  const topY = 6, botY = 94;
  const rowY = (r) => topY + ((r + 1) * (botY - topY)) / (rows + 1);
  const rungSet = new Set(rungs.map((g) => g.row + ":" + g.col));

  function pathFor(start) {
    let col = start;
    const pts = [[colX(col), topY]];
    for (let r = 0; r < rows; r++) {
      pts.push([colX(col), rowY(r)]);
      if (rungSet.has(r + ":" + col)) { col += 1; pts.push([colX(col), rowY(r)]); }
      else if (col > 0 && rungSet.has(r + ":" + (col - 1))) { col -= 1; pts.push([colX(col), rowY(r)]); }
    }
    pts.push([colX(col), botY]);
    return { points: pts.map((p) => p[0].toFixed(2) + "," + p[1].toFixed(2)).join(" "), end: col };
  }
  const selPath = sel != null ? pathFor(sel) : null;
  const grid = { display: "grid", gridTemplateColumns: "repeat(" + n + ", 1fr)" };

  return (
    <div className="game-ladder-board">
      <div className="game-ladder-tops" style={grid}>
        {cols.map((c, i) => (
          <button type="button" key={c.user_id}
            className={"game-ladder-chip" + (sel === i ? " is-sel" : "")}
            onClick={() => setSel(sel === i ? null : i)}>{c.name}</button>
        ))}
      </div>
      <svg className="game-ladder-svg" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="사다리">
        {cols.map((_, i) => (
          <line key={"v" + i} x1={colX(i)} y1={topY} x2={colX(i)} y2={botY} className="game-ladder-vline" vectorEffect="non-scaling-stroke" />
        ))}
        {rungs.map((g, i) => (
          <line key={"r" + i} x1={colX(g.col)} y1={rowY(g.row)} x2={colX(g.col + 1)} y2={rowY(g.row)} className="game-ladder-rung" vectorEffect="non-scaling-stroke" />
        ))}
        {selPath ? (
          <polyline key={sel} className="game-ladder-path" points={selPath.points} pathLength="100" vectorEffect="non-scaling-stroke" fill="none" />
        ) : null}
      </svg>
      <div className="game-ladder-bots" style={grid}>
        {outcomes.map((o, i) => (
          <span key={i} className={"game-ladder-chip is-outcome" + (selPath && selPath.end === i ? " is-sel" : "")}>{o}</span>
        ))}
      </div>
      {sel != null && selPath ? (
        <div className="game-ladder-trace">{cols[sel].name} <span aria-hidden="true">→</span> <b>{outcomes[selPath.end]}</b></div>
      ) : (
        <div className="game-stage-hint">이름을 누르면 사다리 경로가 보입니다.</div>
      )}
    </div>
  );
}

const T_RPS_LABELS = ["가위", "바위", "보"];
const T_RPS_EMOJI = ["✌️", "✊", "✋"];

function MatchTag({ done, winner, submitted, bye }) {
  if (bye) return <Badge value="부전승" kind="info" />;
  if (done) return winner ? <Badge value="승" kind="ok" /> : <Badge value="패" kind="neutral" />;
  return submitted ? <Badge value="제출" kind="ok" /> : <Badge value="대기" kind="warn" />;
}

/* 가위바위보 토너먼트 진행 화면: 라운드 대진표 + (내 대진이면) 선택 버튼. 상대 선택은 감춘다. */
function RpsTournamentLive({ gstate, onPick, pending, canPlay }) {
  const ym = gstate.your_match;
  return (
    <div className="game-tourney">
      <div className="game-quiz-round">라운드 {(gstate.round_idx || 0) + 1}</div>
      <ul className="game-bracket">
        {(gstate.matches || []).map((m, i) => (
          <li key={i} className={"game-bracket-match" + (m.done ? " is-done" : "")}>
            <span className={"game-bracket-side" + (m.done && m.winner_name === m.a_name ? " is-win" : "")}>
              <span className="game-bracket-name">{m.a_name}</span>
              <MatchTag done={m.done} winner={m.winner_name === m.a_name} submitted={m.a_submitted} />
            </span>
            <span className="game-bracket-vs">{m.bye ? "부전승" : "vs"}</span>
            <span className={"game-bracket-side" + (m.done && m.winner_name === m.b_name ? " is-win" : "")}>
              <span className="game-bracket-name">{m.b_name || "-"}</span>
              {!m.bye ? <MatchTag done={m.done} winner={m.winner_name === m.b_name} submitted={m.b_submitted} /> : null}
            </span>
          </li>
        ))}
      </ul>
      {ym ? (
        <div className="game-tourney-you">
          <div className="game-vote-q">내 상대: {ym.opponent}</div>
          {canPlay ? (
            <div className="game-rps-choices">
              {T_RPS_LABELS.map((label, i) => (
                <button key={i} type="button"
                  className={"game-rps-choice" + (ym.your_choice === i ? " is-mine" : "")}
                  disabled={pending} onClick={() => onPick(i)}>
                  <span className="game-rps-emoji" aria-hidden="true">{T_RPS_EMOJI[i]}</span>
                  <span className="game-rps-label">{label}</span>
                </button>
              ))}
            </div>
          ) : null}
          {ym.you_submitted
            ? <div className="game-stage-hint">낸 것 {T_RPS_LABELS[ym.your_choice]} (다시 누르면 변경). 상대가 내면 바로 판정됩니다.</div>
            : <div className="game-stage-hint">가위, 바위, 보 중 하나를 내세요.</div>}
        </div>
      ) : (
        <div className="game-stage-hint">이번 라운드 대진에 없습니다. 다음 라운드를 기다려 주세요.</div>
      )}
    </div>
  );
}

/* 토너먼트 최종 결과: 우승자 + 라운드별 대진 히스토리. */
function RpsTournamentResult({ result }) {
  return (
    <>
      <div className="game-result-label">우승</div>
      {result.champion ? (
        <div className="game-result-winners">
          <span className="game-winner">🏆 {result.champion.name}</span>
        </div>
      ) : <div className="game-stage-hint">우승자가 없습니다.</div>}
      <div className="game-bracket-history">
        {(result.rounds || []).map((rnd, ri) => (
          <div key={ri} className="game-bracket-round">
            <div className="game-side-title">라운드 {ri + 1}</div>
            <ul className="game-bracket">
              {rnd.map((m, i) => (
                <li key={i} className="game-bracket-match is-done">
                  <span className={"game-bracket-side" + (m.winner_name === m.a_name ? " is-win" : "")}>
                    <span className="game-bracket-name">{m.a_name}</span>
                  </span>
                  <span className="game-bracket-vs">{m.b_name ? "vs" : "부전승"}</span>
                  <span className={"game-bracket-side" + (m.winner_name === m.b_name ? " is-win" : "")}>
                    <span className="game-bracket-name">{m.b_name || "-"}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </>
  );
}

export function GameRoom() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const joinedRef = useRef(false);
  const chatLogRef = useRef(null);
  const prevChatCountRef = useRef(0);    // 자동 스크롤 판단(첫 로드/맨아래 근처일 때만 따라감)
  const goneRef = useRef(false);
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
  const disband = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/disband`, { method: "POST" }),
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

  // 방이 사라지면(방장이 파함 → 404, 또는 closed 표시) 목록으로 돌려보낸다. 한 번만.
  const notFound = state.isError && state.error && state.error.status === 404;
  const closed = state.data && state.data.room && state.data.room.closed;
  useEffect(() => {
    if ((notFound || closed) && !goneRef.current) {
      goneRef.current = true;
      toast("방이 사라졌습니다.", "info");
      qc.invalidateQueries({ queryKey: ["games-rooms"] });
      nav("/games");
    }
  }, [notFound, closed]); // eslint-disable-line react-hooks/exhaustive-deps

  // 새 채팅이 오면 최신으로 따라 내려간다 — 단, 위로 올려 옛 대화를 읽는 중이면 끌어내리지 않는다
  // (첫 로드이거나 이미 맨 아래 근처에 있을 때만 스크롤). 상대·나 구분 없이 동작한다.
  const chatCount = (state.data?.events || []).filter((e) => e.kind === "chat").length;
  useEffect(() => {
    const el = chatLogRef.current;
    if (!el) return;
    const firstLoad = prevChatCountRef.current === 0;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    if (firstLoad || nearBottom) el.scrollTop = el.scrollHeight;
    prevChatCountRef.current = chatCount;
  }, [chatCount]);

  // 카운트다운(진행 중 타이머 게임). 훅 순서 유지를 위해 조기 return 위에서 계산한다.
  const liveDeadline = state.data && state.data.room && state.data.room.status === "playing"
    ? (state.data.state && state.data.state.deadline) || null
    : null;
  const remaining = useCountdown(liveDeadline);

  // 마감(deadline)은 이제 서버가 폴링 진입마다 강제한다(service.maybe_autoresolve) — 방장 브라우저에
  // 의존하지 않으므로 클라이언트 자동 진행은 두지 않는다. 카운트다운이 0이 되면 다음 폴링(1.2초)에서
  // 서버가 확정하고, 그 결과가 폴링으로 내려온다.

  if (state.isError && !notFound) return <div className="c-screen"><ErrorState error={state.error} onRetry={() => state.refetch()} /></div>;
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
  const isTournament = isRps && (gstate.mode === "tournament" || (rpsResult && rpsResult.mode === "tournament"));
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

  // 진행 중 제출 현황(누가 냈고 누가 안 냈는지). rps/number/quiz는 서버가 submitted(uid 목록)를,
  // 빠른 투표는 votes 키를 준다. 이걸로 참여자 목록에 제출/대기 배지를 달고 대기자를 안내한다.
  const submittedSet = new Set(
    room.status === "playing" ? (isVote ? Object.keys(votes) : (gstate.submitted || [])) : []
  );
  const submissionActive = room.status === "playing"
    && (isVote || isNumber || (isRps && !isTournament) || (isQuiz && gstate.phase === "answering"));
  const activePlayers = members.filter((m) => m.role !== "spectator");
  const waitingNames = submissionActive
    ? activePlayers.filter((m) => !submittedSet.has(m.user_id)).map((m) => m.name)
    : [];
  const submittedCount = submissionActive ? activePlayers.filter((m) => submittedSet.has(m.user_id)).length : 0;

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

          {/* 진행 현황: 카운트다운 + 제출/대기(모든 제출형 게임 공통) */}
          {submissionActive || remaining != null ? (
            <div className="game-progress-bar">
              <Countdown remaining={remaining} />
              {submissionActive ? (
                <div className="game-submit-status">
                  <span className="game-submit-count">제출 {submittedCount}/{activePlayers.length}</span>
                  {waitingNames.length > 0
                    ? <span className="game-submit-waiting">대기 {waitingNames.join(", ")}</span>
                    : <span className="game-submit-done">모두 제출했습니다</span>}
                </div>
              ) : null}
            </div>
          ) : null}

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
            gstate.result && gstate.result.columns ? (
              <LadderBoard result={gstate.result} highlightUserId={you.user_id} />
            ) : (
              <ul className="game-ladder">
                {ladderAssignments.map((a) => (
                  <li key={a.user_id} className="game-ladder-row">
                    <span className="game-ladder-name">{a.name}</span>
                    <span className="game-ladder-arrow" aria-hidden="true">→</span>
                    <span className="game-ladder-outcome">{a.outcome}</span>
                  </li>
                ))}
              </ul>
            )
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
                  <div className="game-vote-q">{gstate.min || 1} ~ {gstate.max || 10} 중 하나를 몰래 내세요</div>
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
              {room.status === "finished" && rpsResult && rpsResult.mode === "tournament" ? (
                <RpsTournamentResult result={rpsResult} />
              ) : room.status === "playing" && isTournament ? (
                <RpsTournamentLive gstate={gstate} onPick={(i) => rps.mutate(i)}
                  pending={rps.isPending} canPlay={you.in_room && you.role !== "spectator"} />
              ) : room.status === "finished" && rpsResult ? (
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
              <Button variant="primary" onClick={() => finish.mutate()} disabled={finish.isPending}>{isVote ? "투표 종료" : isTournament ? "이 라운드 마감" : "결과 공개"}</Button>
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
            {isHost ? (
              <Button variant="danger" disabled={disband.isPending}
                onClick={async () => {
                  const ok = await confirm("방을 파하면 모두 나가지고 방이 사라집니다. 계속할까요?",
                    { title: "방 파하기", confirmLabel: "방 파하기", danger: true });
                  if (ok) disband.mutate();
                }}>방 파하기</Button>
            ) : null}
          </div>
        </section>

        <aside className="game-side">
          <div className="game-panel game-panel-members">
            <div className="game-side-title">참여자 {members.length}명</div>
            <ul className="game-member-list">
              {members.map((m) => {
                const sub = [m.title, m.dept].filter(Boolean);
                const isHostRow = m.user_id === room.host_user_id;
                return (
                  <li key={m.user_id} className={"game-member" + (m.user_id === you.user_id ? " is-me" : "")}>
                    <span className={"game-member-avatar" + (isHostRow ? " is-host" : "")} aria-hidden="true">
                      {(m.name || "?").slice(0, 1)}
                    </span>
                    <span className="game-member-info">
                      <span className="game-member-name">
                        {m.name}{m.user_id === you.user_id ? <span className="game-member-you"> (나)</span> : null}
                      </span>
                      {sub.length ? (
                        <span className="game-member-sub">
                          {m.title ? <span className="game-member-title">{m.title}</span> : null}
                          {m.dept ? <span className="game-member-dept">{m.dept}</span> : null}
                        </span>
                      ) : null}
                    </span>
                    <span className="game-member-tags">
                      {isHostRow
                        ? <Badge value="방장" kind="info" />
                        : <Badge value={ROLE_LABELS[m.role] || m.role} kind="neutral" />}
                      {submissionActive && m.role !== "spectator"
                        ? (submittedSet.has(m.user_id)
                          ? <Badge value="제출" kind="ok" />
                          : <Badge value="대기" kind="warn" />)
                        : (m.role === "player" && m.ready ? <Badge value="준비" kind="ok" /> : null)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="game-panel game-chat">
            <div className="game-side-title">채팅</div>
            <div className="game-chat-log" ref={chatLogRef}>
              {chatMsgs.length === 0 ? (
                <div className="game-chat-empty">아직 메시지가 없습니다. 먼저 인사해 보세요.</div>
              ) : chatMsgs.map((e) => {
                const mine = e.actor_user_id === you.user_id;
                return (
                  <div key={e.seq} className={"game-chat-msg" + (mine ? " is-mine" : "")}>
                    {!mine ? <span className="game-chat-who">{e.payload.name}</span> : null}
                    <span className="game-chat-row">
                      <span className="game-chat-bubble">{e.payload.text}</span>
                      <span className="game-chat-time">{fmtTime(e.created_at)}</span>
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="game-chat-input">
              <input className="k-input" maxLength={500} value={draft} placeholder="메시지 입력"
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); sendChat(); } }} />
              <Button variant="primary" onClick={sendChat} disabled={chat.isPending}>보내기</Button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
