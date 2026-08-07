import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { alpha } from "@mui/material/styles";
import { api } from "../../lib/api.js";
import { useConfirm, useToast } from "../../ui/kit.jsx";
import { celebrate, deriveCelebrateKey } from "./celebration.js";
import { useCountdown } from "./timeUtils.js";

/* 채팅 패널에 흘려보낼 이벤트: 대화 그 자체 + 사람이 읽을 수 있는 안내문이 달린 system 이벤트
 * (예: 방장이 나가 다른 참여자에게 위임될 때 app/games/service.py::leave_room 이 남기는
 * "○○님이 방장이 되었습니다." 문구). 방을 나가지 않고 이어지는 이 변화는 참여자 목록의
 * '방장' 배지가 다음 폴링(1.2초)에서 바뀌는 것 말고는 아무 안내가 없었다 — 방이 파해질 때
 * (disband)는 토스트+이동으로 안내하면서 정작 방이 이어질 때는 안내가 빠져 있었다.
 * 퀴즈 진행(revealed/next)·토너먼트 라운드 진행 system 이벤트는 payload에 text가 없다 —
 * 그런 진행 상황은 이미 무대(GameStage)가 상태로 보여주므로 채팅에 다시 끼워 넣지 않는다. */
function isChatFeedEvent(e) {
  return e.kind === "chat" || (e.kind === "system" && !!(e.payload && e.payload.text));
}

/* 게임방 진행 상태 관리 훅 — GameRoom.jsx 구조 분리(2026-08)로 옮겼다. 폴링(1.2초)으로 방
 * 상태·참여자·이벤트를 실시간처럼 흐르게 한다. 결과(당첨자)는 서버가 확정해 내려준다(§13.1) —
 * 클라이언트는 표현만 한다.
 *
 * 훅 규칙 유지: 모든 use* 호출은 조건 없이 매 렌더 같은 순서로 실행한다. state.isPending /
 * state.isError 에 따른 조기 반환은 훅 호출이 전부 끝난 "뒤"에 평범한 if 문으로 한다(원래
 * GameRoom() 함수 안에서도 같은 순서였다 — 로직만 옮겼다). phase가 "pending"/"error"이면
 * 그 외 필드는 없다 — 호출부(GameRoom.jsx)가 phase를 먼저 분기해서 쓴다. */
export function useGameRoomController(id) {
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
  // HashRouter라 다른 방으로 가는 링크(예: 두 번째 초대 링크)를 이미 열린 게임방 탭에서 열면
  // 해시만 바뀌어 이 컴포넌트는 마운트 해제 없이 id만 바뀐다 — joinedRef를 id별로 리셋하지
  // 않으면 첫 방에서 이미 자동 입장을 한 번 시도한 뒤로는(joinedRef.current가 영구히 true라)
  // 새 방으로 넘어가도 다시는 자동 입장을 시도하지 않아, 참여자가 새 방에 "입장 안 한" 채로
  // 조용히 남는다(투표·준비 등 참여 동작이 전부 막힌다).
  // id가 바뀌어도 이 훅 인스턴스(와 그 안의 상태/ref)는 그대로 살아남는다(위 주석 참고) —
  // joinedRef뿐 아니라 "이 방 한정"인 다른 값도 새 방 것으로 다시 시작해야 한다.
  // - prevChatCountRef: 방 전환은 항상 "pending"(스켈레톤)을 거치는데, 그 순간 채팅 로그 DOM이
  //   통째로 마운트 해제돼 chatLogRef.current가 null이 된다 — 아래 자동 스크롤 effect가 el이
  //   없어 prevChatCountRef 갱신을 건너뛰므로 이전 방 값이 새 방까지 남는다. 남으면 "첫 로드"
  //   판정(prevChatCountRef.current === 0)이 거짓이 되어, 새로 연 방의 채팅인데도 오래된
  //   대화를 읽던 중인 것처럼 취급돼 맨 아래로 스크롤하지 않는다.
  // - draft/numDraft: 이전 방에 쓰다 만 채팅/숫자 초안이 새 방 입력창에 그대로 남아, 방이
  //   바뀐 줄 모르고 그대로 보내면 엉뚱한 방에 전송된다.
  useEffect(() => {
    joinedRef.current = false;
    prevChatCountRef.current = 0;
    setDraft("");
    setNumDraft("");
  }, [id]);
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
    onError: (e) => toast((e && e.message) || "준비 상태를 바꾸지 못했습니다.", "error"),
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
    onError: (e) => toast((e && e.message) || "다시 시작하지 못했습니다.", "error"),
  });
  const leave = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/leave`, { method: "POST" }),
    /* 성공했을 때만 떠난다 (E4). `onSettled` 는 **실패해도** 실행돼서, 실패한 '방 파하기' 가
       성공한 것과 똑같이 보였다 — 방은 그대로인데 사용자는 파했다고 믿는다. */
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["games-rooms"] }); nav("/games"); },
    onError: (e) => toast((e && e.message) || "처리하지 못했습니다.", "error"),
  });
  const disband = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/disband`, { method: "POST" }),
    /* 성공했을 때만 떠난다 (E4). `onSettled` 는 **실패해도** 실행돼서, 실패한 '방 파하기' 가
       성공한 것과 똑같이 보였다 — 방은 그대로인데 사용자는 파했다고 믿는다. */
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["games-rooms"] }); nav("/games"); },
    onError: (e) => toast((e && e.message) || "처리하지 못했습니다.", "error"),
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
  // chatCount는 아래 chatMsgs(채팅+안내문)와 같은 집합을 세야 한다 — 방장 위임 같은 system
  // 이벤트만 새로 온 폴링에서는 채팅 개수가 그대로라 스크롤이 안 따라 내려가는 어긋남을 막는다.
  const chatCount = (state.data?.events || []).filter(isChatFeedEvent).length;
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

  // 방이 사라진 뒤 공유된 옛 /games/<id> 링크로 처음 들어오면 state.data가 한 번도 성공적으로
  // 채워지지 않은 채 404만 온다 — notFound라서 위 줄은 "error"로 안 빠지고, isPending도 이미
  // false(react-query는 실패한 요청을 pending으로 보지 않는다)라 그대로 아래로 떨어져
  // `const { room } = state.data`가 undefined를 구조분해해 "Cannot destructure property
  // 'room' of 'state.data' as it is undefined"로 화면이 통째로 크래시했다. 134번째 줄 effect가
  // notFound를 이미 보고 토스트+이동을 발화하므로(훅 순서 유지를 위해 조기 return보다 위에 선언
  // 돼 있어 이 렌더에서도 그대로 실행된다), 여기서는 data가 없는 동안 destructure를 하지 않고
  // pending(스켈레톤)으로 넘겨 그 effect가 처리할 시간을 준다. 중간 폴링 404는 react-query가
  // 이전 성공 데이터를 그대로 들고 있어 이 분기를 안 타니(state.data가 채워진 채) 기존 정상
  // 흐름 그대로다.
  if (state.isError && !notFound) return { phase: "error", error: state.error, refetch: () => state.refetch() };
  if (state.isPending || !state.data) return { phase: "pending" };

  const { room, you, members } = state.data;
  const gstate = state.data.state || {};
  const chatMsgs = (state.data.events || []).filter(isChatFeedEvent);
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

  const voteOptionSx = (mine, correct, preview) => ({
    width: "100%", display: "flex", alignItems: "center", gap: 1.5, textAlign: "left",
    px: 2, py: 1.5, borderRadius: 2, cursor: preview ? "default" : "pointer",
    border: 1, borderColor: correct ? "success.main" : mine ? "primary.main" : "divider",
    bgcolor: (t) => (correct ? alpha(t.palette.success.main, 0.12)
      : mine ? alpha(t.palette.primary.main, 0.12) : t.palette.background.paper),
    color: preview ? "text.secondary" : "text.primary", font: "inherit",
    "&:hover:not(:disabled)": preview ? undefined : { borderColor: "primary.main" },
    "&:disabled": { cursor: "default" },
  });

  // 방 파하기 확인 다이얼로그 — 승인해야만 disband를 호출한다. 원래 GameRoom() 렌더의 disband
  // 버튼 onClick 안에 있던 로직을 그대로 옮겼다.
  const disbandWithConfirm = async () => {
    const ok = await confirm("방을 파하면 모두 나가지고 방이 사라집니다. 계속할까요?",
      { title: "방 파하기", confirmLabel: "방 파하기", danger: true });
    if (ok) disband.mutate();
  };

  return {
    phase: "ready",
    room, you, members, gstate, chatMsgs,
    isVote, isTeam, isDraw, isNumber, isLadder, isRps, isQuiz, isHost, isTournament,
    canReady, canVote, canPick, canRps, canQuizAnswer,
    drawWinners, teams, ladderAssignments, numResult, rpsResult,
    quizResult, quizPlaying, liveScores,
    voteResult, voteOptions, liveCounts, myVote, maxCount,
    submittedSet, submissionActive, activePlayers, waitingNames, submittedCount,
    remaining,
    draft, setDraft, numDraft, setNumDraft, sendChat, voteOptionSx,
    chatLogRef,
    mutations: { join, ready, start, vote, finish, pick, rps, quizAnswer, reveal, nextQ, reset, leave, disband, chat },
    disbandWithConfirm,
  };
}
