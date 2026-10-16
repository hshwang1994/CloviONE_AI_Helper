import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { alpha } from "@mui/material/styles";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import { useGuardedMutation } from "../../lib/useGuardedMutation.js";
import { useConfirm, useToast } from "../../ui/kit.jsx";
import { RADIUS } from "../../ui/theme.js";
import { celebrate, deriveCelebrateKey, deriveResultKey } from "./celebration.js";
import { useCountdown } from "./timeUtils.js";
import { useRevealMachine } from "./revealMachine.js";
import { buildPeople } from "./people.js";
import { deriveRoomStatus, participantSummary } from "./roomStatus.js";
import { useMarbleRoom } from "./marble/useMarbleRoom.js";

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
/* 폴링 커서(P5 ②) — 두 번째부터는 `since=<마지막 seq>` 로 그 뒤 이벤트만 받아 앞 이벤트에 잇는다(seq 로 중복 제거).
 * 방 · 상태 · 참여자 · 결과 번호는 새 값으로 바꾼다. 첫 요청과 캐시가 없을 때는 `since=0` 이다. */
export function mergeEvents(prev, next) {
  const seen = new Set((prev || []).map((e) => e.seq));
  const out = (prev || []).slice();
  for (const e of next || []) {
    if (e && e.seq != null && seen.has(e.seq)) continue;
    if (e && e.seq != null) seen.add(e.seq);
    out.push(e);
  }
  return out;
}

export async function fetchRoomState(qc, id) {
  const prev = qc ? qc.getQueryData(["game-room", id]) : null;
  const since = prev && Number.isInteger(prev.seq) && prev.seq > 0 && Array.isArray(prev.events) ? prev.seq : 0;
  const fresh = await api(`/api/games/rooms/${id}/state?since=${since}`);
  if (!since || !fresh || !Array.isArray(fresh.events)) return fresh;
  return { ...fresh, events: mergeEvents(prev.events, fresh.events) };
}

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
    queryFn: () => fetchRoomState(qc, id),
    refetchInterval: 1200,
  });

  const join = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/join`, { method: "POST" }),
    onSuccess: () => state.refetch(),
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
  });
  const start = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/start`, { method: "POST" }),
    onSuccess: () => state.refetch(),
  });
  const vote = useMutation({
    mutationFn: (option) => api(`/api/games/rooms/${id}/vote`, { method: "POST", body: { option } }),
    onSuccess: () => state.refetch(),
  });
  const finish = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/finish`, { method: "POST" }),
    onSuccess: () => state.refetch(),
  });
  const pick = useMutation({
    mutationFn: (value) => api(`/api/games/rooms/${id}/pick`, { method: "POST", body: { value } }),
    onSuccess: () => { setNumDraft(""); state.refetch(); },
  });
  const rps = useMutation({
    mutationFn: (option) => api(`/api/games/rooms/${id}/rps`, { method: "POST", body: { option } }),
    onSuccess: () => state.refetch(),
  });
  const quizAnswer = useMutation({
    mutationFn: (option) => api(`/api/games/rooms/${id}/quiz-answer`, { method: "POST", body: { option } }),
    onSuccess: () => state.refetch(),
  });
  const reveal_ = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/reveal`, { method: "POST" }),
    onSuccess: () => state.refetch(),
  });
  const nextQ = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/next`, { method: "POST" }),
    onSuccess: () => state.refetch(),
  });
  /* 구슬 레이스(D-564) — 참가자 · 설정은 방장, 결과는 방장 finish · 나머지 attest(검증은 같다). */
  const marbleParticipants = useMutation({
    mutationFn: (body) => api(`/api/games/rooms/${id}/marble/participants`, { method: "PUT", body }),
    onSuccess: () => state.refetch(),
  });
  const marbleConfig = useMutation({
    mutationFn: (body) => api(`/api/games/rooms/${id}/marble/config`, { method: "PUT", body }),
    onSuccess: () => state.refetch(),
  });
  const marbleFinish = useMutation({
    mutationFn: (body) => api(`/api/games/rooms/${id}/marble/finish`, { method: "POST", body }),
    onSuccess: () => state.refetch(),
  });
  const marbleAttest = useMutation({
    mutationFn: (body) => api(`/api/games/rooms/${id}/marble/attest`, { method: "POST", body }),
    onSuccess: () => state.refetch(),
  });
  const reset = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/reset`, { method: "POST" }),
    onSuccess: () => state.refetch(),
  });
  const leave = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/leave`, { method: "POST" }),
    /* 성공했을 때만 떠난다 (E4). `onSettled` 는 **실패해도** 실행돼서, 실패한 '방 파하기' 가
       성공한 것과 똑같이 보였다 — 방은 그대로인데 사용자는 파했다고 믿는다. */
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["games-rooms"] }); nav("/games"); },
  });
  const disband = useMutation({
    mutationFn: () => api(`/api/games/rooms/${id}/disband`, { method: "POST" }),
    /* 성공했을 때만 떠난다 (E4). `onSettled` 는 **실패해도** 실행돼서, 실패한 '방 파하기' 가
       성공한 것과 똑같이 보였다 — 방은 그대로인데 사용자는 파했다고 믿는다. */
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["games-rooms"] }); nav("/games"); },
  });
  /* 채팅은 입력 칸의 Enter 로 나간다(`ChatPanel.jsx`). 그 처리기(`sendChat`)가 보는 `chat.isPending` 은 지난 렌더의
     값이라, 다시 그려지기 전에 온 둘째 Enter 가 같은 말을 한 번 더 보냈다. 같은 말은 끝나기 전에 한 번만 나간다. */
  const chat = useGuardedMutation({
    mutationFn: (text) => api(`/api/games/rooms/${id}/chat`, { method: "POST", body: { text } }),
    onSuccess: () => { setDraft(""); state.refetch(); },
  });

  /* 실패는 그 동작의 자리에 남는다 — 방 동작(입장 · 준비 · 시작 · 제출 · 공개 · 나가기 …)은 무대 위, 채팅은
     입력 칸 위. 가장 나중에 누른 동작 하나만 말하고 다음 동작에서 걷힌다(`lib/failure.js`). 문구는 토스트 때와 같다. */
  const actionFailure = failureText(
    [join, "입장하지 못했습니다. 다시 시도해 주세요."],
    [ready, "준비 상태를 바꾸지 못했습니다. 다시 시도해 주세요."],
    [start, "게임을 시작하지 못했습니다. 다시 시도해 주세요."],
    [vote, "투표하지 못했습니다. 다시 시도해 주세요."],
    [finish, "게임을 종료하지 못했습니다. 다시 시도해 주세요."],
    [pick, "숫자를 내지 못했습니다. 다시 시도해 주세요."],
    [rps, "내지 못했습니다. 다시 시도해 주세요."],
    [quizAnswer, "답을 내지 못했습니다. 다시 시도해 주세요."],
    [reveal_, "정답을 공개하지 못했습니다. 다시 시도해 주세요."],
    [nextQ, "다음으로 넘어가지 못했습니다. 다시 시도해 주세요."],
    [marbleFinish, "경주 결과를 올리지 못했습니다. 다시 시도해 주세요."],
    [marbleAttest, "경주 결과를 올리지 못했습니다. 다시 시도해 주세요."],
    [reset, "다시 시작하지 못했습니다. 다시 시도해 주세요."],
    [leave, "처리하지 못했습니다. 다시 시도해 주세요."],
    [disband, "처리하지 못했습니다. 다시 시도해 주세요."],
  );
  const chatFailure = failureText([chat, "메시지를 보내지 못했습니다. 다시 시도해 주세요."]);

  /* 발표 열쇠 — 방 id + 결과 번호(`result_seq`, D-563). 결과 대화 상자의 상태 기계(`revealMachine.js`, D-576)가 이 열쇠로
   * 「발표 → 당첨자 공개」를 한 번 돌리고, 공개되는 순간 축포를 한 번 쏜다(승자가 있는 결과만).
   *
   * 🔴 이 방을 **처음 열었을 때 본 열쇠**는 「지난 결과」다 — 이미 끝난 방에 늦게 들어오거나 새로고침한 사람은 발표를 본 것이
   * 아니므로 전환 없이 결과만 보이고 축포도 없다(`instant`). 그 뒤 값이 실제로 달라진 때만 발표한다. 훅 순서 유지를 위해
   * 조기 return 위에 둔다. */
  const resultKey = deriveResultKey(state.data);
  const roomKeyRef = useRef(null);
  const firstKeyRef = useRef(undefined);
  /* 렌더 중에 정한다 — 데이터가 온 그 렌더에 기계가 「처음 본 열쇠」를 알아야 늦게 들어온 사람에게 발표 전환을 시작하지 않는다.
     방이 바뀌면 그 방의 첫 열쇠를 새로 본다. */
  if (roomKeyRef.current !== id) { roomKeyRef.current = id; firstKeyRef.current = undefined; }
  if (state.data && firstKeyRef.current === undefined) firstKeyRef.current = resultKey;
  const hasWinners = deriveCelebrateKey(state.data) != null;
  /* 축포 캔버스 — 전체 화면일 때만 방의 루트 안에 선다(`GameRoom.jsx` 의 겹침 슬롯). 전체 화면인 요소는 그 밖의 캔버스를 가린다.
     없으면 `celebrate()` 가 문서의 기본 캔버스에 쏜다. */
  const celebrateCanvasRef = useRef(null);
  const reveal = useRevealMachine({
    key: resultKey,
    instant: resultKey != null && resultKey === firstKeyRef.current,
    hasWinners,
    fire: () => celebrate({ canvas: celebrateCanvasRef.current || undefined }),
  });
  /* 신원 지도(D-577) — 서버의 스냅샷(`people`) 위에 지금 구성원. 판 · 대화 상자 · 채팅의 모든 얼굴이 이것으로 풀린다. */
  const people = useMemo(() => buildPeople(state.data), [state.data]);
  /* 구슬 레이스(D-564 · D-578) — 경주 계산 · 참가자 · 확정 결과. 판(캔버스) · 순위 레일 · 툴바 · 결과 대화 상자가 함께 읽으므로
     방 단위로 한 번 돈다(판 안에 두면 레일이 판을 거쳐야 순위를 안다). 구슬 방이 아니면 아무것도 돌리지 않는다. */
  const marble = useMarbleRoom({ data: state.data, mutations: { marbleFinish, marbleAttest } });

  // 방이 사라지면(방장이 파함 → 404, 또는 closed 표시) 목록으로 돌려보낸다. 한 번만.
  const notFound = state.isError && state.error && state.error.status === 404;
  const closed = state.data && state.data.room && state.data.room.closed;
  useEffect(() => {
    if ((notFound || closed) && !goneRef.current) {
      goneRef.current = true;
      toast("게임방이 종료됐습니다.", "info");
      qc.invalidateQueries({ queryKey: ["games-rooms"] });
      nav("/games");
    }
  }, [notFound, closed]); // eslint-disable-line react-hooks/exhaustive-deps

  // 새 채팅이 오면 최신으로 따라 내려간다 — 단, 위로 올려 옛 대화를 읽는 중이면 끌어내리지 않는다
  // (첫 로드이거나 이미 맨 아래 근처에 있을 때만 스크롤). 상대·나 구분 없이 동작한다.
  // chatCount는 아래 chatMsgs(채팅+안내문)와 같은 집합을 세야 한다 — 방장 위임 같은 system
  // 이벤트만 새로 온 폴링에서는 채팅 개수가 그대로라 스크롤이 안 따라 내려가는 어긋남을 막는다.
  const chatCount = (state.data?.events || []).filter(isChatFeedEvent).length;
  // id도 의존성에 넣는다. HashRouter라 방을 바꿔도(위 [id] 이펙트) 이 컴포넌트는 마운트
  // 해제되지 않고, 바뀐 방이 이미 캐시돼 있으면(예: 전에 열어 본 방으로 되돌아감) "pending"
  // (스켈레톤)도 안 거쳐 채팅 로그 DOM이 그대로 살아있다 — 그 상태에서 두 방의 채팅 개수가
  // 우연히 같으면(예: 둘 다 4건) chatCount만 바라보는 이펙트는 "안 바뀌었다"고 보고 다시
  // 실행되지 않는다. 그러면 위 [id] 이펙트가 prevChatCountRef를 0으로 되돌려도 아무도 그 값을
  // 읽지 않아 새 방으로 넘어갔는데도 이전 방에서 위로 올려 두었던 스크롤 위치가 그대로
  // 남는다(gameroom-room-switch-same-chatcount.test.jsx). id를 의존성에 추가하면 방을 바꾼
  // 렌더마다 이 이펙트가 반드시 다시 돌아 [id] 이펙트가 되돌린 firstLoad 판정을 실제로 적용한다.
  useEffect(() => {
    const el = chatLogRef.current;
    if (!el) return;
    const firstLoad = prevChatCountRef.current === 0;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    if (firstLoad || nearBottom) el.scrollTop = el.scrollHeight;
    prevChatCountRef.current = chatCount;
  }, [chatCount, id]);

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
  const isMarble = room.game_type === "marble_race";
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
  /* 이름은 신원 지도에서 — 진행 중에 나간 사람의 점수 줄도 이름과 얼굴이 남는다(D-577). */
  const nameOf = {};
  Object.values(people).forEach((p) => { nameOf[p.user_id] = p.name; });
  members.forEach((m) => { nameOf[m.user_id] = m.name; });
  const liveScores = (quizPlaying?.scores || []).map((s) => ({ user_id: s.user_id, name: nameOf[s.user_id] || "?", score: s.score }));
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

  /* 상태의 정본 하나(G2) — 툴바가 이것만 그린다. 구슬 레이스는 서버의 단계 · 무결성이 방 상태보다 정확한 말이다. */
  const status = deriveRoomStatus({ room, gstate, you });
  const summary = participantSummary({ room, gstate, members, marble: marble.isMarble ? { finishedCount: marble.finishedCount } : null });
  /* 툴바의 동작 — 방장 · 참가자 · 관전자, 단계마다 다르다. 같은 판정이 판 아래 · 툴바 두 곳에 있으면 갈라진다(예전의 판 아래 동작 줄). */
  const startLabel = isMarble ? "경주 시작" : isVote ? "투표 시작" : isTeam ? "팀 나누기" : isNumber ? "숫자 눈치 시작"
    : isLadder ? "사다리 타기" : isRps ? "가위바위보 시작" : isQuiz ? "퀴즈 시작" : "추첨 시작";
  let primary = null;
  if (isHost && room.status === "waiting") {
    primary = { key: "start", label: startLabel, onClick: () => start.mutate(), pending: start.isPending };
  } else if (isHost && (isVote || isNumber || isRps) && room.status === "playing") {
    primary = { key: "finish", label: isVote ? "투표 종료" : isTournament ? "이 라운드 마감" : "결과 공개", onClick: () => finish.mutate(), pending: finish.isPending };
  } else if (isHost && isQuiz && room.status === "playing" && quizPlaying?.phase === "answering") {
    primary = { key: "reveal", label: "정답 공개", onClick: () => reveal_.mutate(), pending: reveal_.isPending };
  } else if (isHost && isQuiz && room.status === "playing" && quizPlaying?.phase === "revealed") {
    primary = { key: "next", label: (quizPlaying.round || 0) + 1 >= quizPlaying.total ? "결과 보기" : "다음 문제", onClick: () => nextQ.mutate(), pending: nextQ.isPending };
  } else if (isHost && room.status === "finished") {
    primary = { key: "reset", label: "다시 하기", onClick: () => reset.mutate(), pending: reset.isPending };
  }
  const actions = {
    primary,
    ready: canReady ? { key: "ready", label: you.ready ? "준비 해제" : "준비", on: !!you.ready, onClick: () => ready.mutate(!you.ready), pending: ready.isPending } : null,
    /* 끝난 결과가 있고 대화 상자가 닫혀 있으면 누구나 다시 연다(재발표 · 축포 없음). */
    showResult: room.status === "finished" && reveal.key != null && !reveal.open,
    settings: isMarble && isHost && marble.waiting,
    disband: isHost,
  };

  const voteOptionSx = (mine, correct, preview) => ({
    width: "100%", display: "flex", alignItems: "center", gap: 1.5, textAlign: "left",
    px: 2, py: 1.5, borderRadius: `${RADIUS.md}px`, cursor: preview ? "default" : "pointer",
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
    const ok = await confirm("게임방을 종료하면 모두 나가게 되고 방이 사라집니다. 계속할까요?",
      { title: "게임방 종료", confirmLabel: "게임방 종료", danger: true });
    if (ok) disband.mutate();
  };

  return {
    phase: "ready",
    room, you, members, gstate, chatMsgs,
    isVote, isTeam, isDraw, isNumber, isLadder, isRps, isQuiz, isMarble, isHost, isTournament,
    serverNow: state.data.now || null,
    people, reveal, marble, celebrateCanvasRef,
    status, summary, actions,
    canReady, canVote, canPick, canRps, canQuizAnswer,
    drawWinners, teams, ladderAssignments, numResult, rpsResult,
    quizResult, quizPlaying, liveScores,
    voteResult, voteOptions, liveCounts, myVote, maxCount,
    submittedSet, submissionActive, activePlayers, waitingNames, submittedCount,
    remaining,
    draft, setDraft, numDraft, setNumDraft, sendChat, voteOptionSx,
    chatLogRef,
    mutations: { join, ready, start, vote, finish, pick, rps, quizAnswer, reveal: reveal_, nextQ, reset, leave, disband, chat, marbleParticipants, marbleConfig, marbleFinish, marbleAttest },
    actionFailure, chatFailure,
    disbandWithConfirm,
  };
}
