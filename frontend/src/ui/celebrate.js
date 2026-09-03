import React from "react";
import confetti from "canvas-confetti";

/* 축포 — **일을 끝낸 순간**에만 터진다.
 *
 * ## 왜 놀이 밖으로 나왔나
 *
 * 이 함수는 `screens/game-room/celebration.js` 안에 있었고, 그래서 축포가 이 제품에서
 * 일어날 수 있는 유일한 자리가 「게임방 승자 공개」였다. 사용자가 로그인 화면의 축하
 * 연출을 보고 「앱 안에서는 왜 안 터지느냐」고 물은 것이 이 상태다 — 연출이 없는 게
 * 아니라, 업무를 끝낸 자리에 아무도 연결하지 않았다.
 *
 * 옮기면서 값은 그대로 뒀다(퍼짐 74°, 초속 45, 200틱, 좌우 보조 두 발). 놀이의 축포와
 * 업무의 축포가 다른 모양이면 같은 제품이 두 가지 축하를 갖게 된다.
 *
 * ## 언제 부르면 안 되나
 *
 * 🔴 **렌더 중에 부르지 않는다.** 이 함수는 캔버스를 만들고 타이머를 건다 — 목록이 다시
 * 그려질 때마다 부르면 종잇조각이 화면을 덮는다. 부르는 자리는 언제나 **뮤테이션의
 * `onSuccess`** 이거나, 값이 실제로 바뀐 것을 확인한 effect 다.
 *
 * 🔴 **터질 자리는 둘이다.**
 *
 *   1. 「할 게 없어졌다」 — 목록이 비는 순간(`celebrateIfCleared` · `useCelebrateOnCleared`).
 *   2. 「이 티켓을 끝냈다」 — 티켓이 완료로 옮겨 가는 순간(`celebrateIfCompleted`).
 *
 * 2 는 사용자가 못박은 것이다(2026-09-03): "티켓이 완료됐을 때 폭죽이 터지기로 했는데
 * 수정을 눌러서 완료 누르고 저장했을 때는 안 터진다." 그전까지 이 파일이 붙어 있던 자리는
 * 놀이·승인함 비움·내 티켓 비움·회차 닫기 넷뿐이라, **티켓 한 건을 끝낸 자리에는 아무도
 * 연결하지 않았다.**
 *
 * OS·브라우저의 동작 줄이기 설정은 보지 않는다 — 이 제품의 연출은 언제나 돈다
 * (제품 결정, `ui/motion.js` 머리말).
 */

/* 🔴 **겹쳐 터지지 않는다.**
 *
 * 두 자리가 한 동작에서 같이 열린다: 내 마지막 열린 티켓을 완료로 옮기면 「이 티켓을
 * 끝냈다」와 「할 게 없어졌다」가 동시에 참이 된다. 그러면 종잇조각이 두 겹으로 쏟아지고,
 * 그건 축하가 두 배가 아니라 그냥 화면이 시끄러운 것이다.
 *
 * 한 번의 축포는 세 발(가운데 → 좌 → 우)이 140·260ms 뒤에 이어지는 한 벌이라, 그 한 벌이
 * 끝나기 전에 들어온 두 번째 요청만 접는다. 5초 뒤에 다음 티켓을 끝내면 그건 새 축하다. */
const BURST_COOLDOWN_MS = 1500;
let lastBurstAt = 0;

/* 축포는 앱 크롬 위에 떠야 한다. canvas-confetti 의 기본 캔버스는 `z-index: 100` 이라
   MUI 모달(1300)·상단바(1100) 뒤에서 터진다 — 편집 모달에서 완료로 저장하면 정확히 그
   자리다. 로그인 인계 판에서 같은 이유로 폭죽이 통째로 안 보이던 것을 이미 겪었다
   (`app/LoginHandoff.jsx` 의 CONFETTI_Z). */
const CONFETTI_Z = 1320;

/* 겹침 방지 관문 한 곳. 통과하면 지금 시각을 적는다 — 세 발짜리 축포도, 한 발짜리
   클로버도 같은 관문을 지나므로 문서를 만들자마자 티켓을 끝내도 두 겹이 안 된다. */
function takeBurstSlot() {
  const now = Date.now();
  if (now - lastBurstAt < BURST_COOLDOWN_MS) return false;
  lastBurstAt = now;
  return true;
}

/** 한 발만 쏜다. 층과 겹침 방지는 여기서 한 번에 챙긴다 — 부르는 쪽이 잊을 자리를
 *  안 만든다(축포가 모달 뒤에서 터지던 일이 그렇게 생겼다). */
function celebrateBurst(options) {
  if (!takeBurstSlot()) return;
  confetti({ zIndex: CONFETTI_Z, ...options });
}

export function celebrate() {
  if (!takeBurstSlot()) return;
  const base = {
    spread: 74, startVelocity: 45, ticks: 200,
    origin: { y: 0.55 },
    zIndex: CONFETTI_Z,
  };
  confetti({ ...base, particleCount: 90 });
  window.setTimeout(() => confetti({ ...base, particleCount: 55, angle: 60, origin: { x: 0, y: 0.62 } }), 140);
  window.setTimeout(() => confetti({ ...base, particleCount: 55, angle: 120, origin: { x: 1, y: 0.62 } }), 260);
}

/** 시험 전용 — 겹침 방지 기억을 비운다. 제품 코드에서는 부르지 않는다. */
export function resetBurstCooldown() {
  lastBurstAt = 0;
}

/** `/api/work/statuses` 응답 → **완료로 세는** 상태 key 집합.
 *
 * 🔴 `terminal` 이 아니라 `category === "DONE"` 이다. 취소도 종료 상태지만 축하할 일이
 * 아니다 — `terminal` 로 재면 티켓을 취소한 사람에게 종잇조각이 쏟아진다.
 *
 * 어휘가 아직 없으면 **빈 집합**이다(= 안 터진다). 여기에 "완료" 라고 적어 두면 어휘가
 * 바뀐 날 이 파일만 옛 이름으로 남고, 그 어긋남은 아무 오류도 안 낸다 —
 * `lib/ticketSignals.js::terminalKeys` 와 같은 규칙이다. */
export function doneStatusKeys(statusesBody) {
  const rows = statusesBody && Array.isArray(statusesBody.statuses) ? statusesBody.statuses : [];
  return new Set(rows.filter((s) => s && s.category === "DONE").map((s) => s.key));
}

/** 이번 쓰기가 티켓을 **완료로 옮겼으면** 터뜨린다.
 *
 * `nextStatus` 는 「이번에 실제로 바뀐 상태」다. 안 바뀌었으면 부르는 쪽이 빈 값을 넘긴다 —
 * 이미 완료인 티켓의 제목만 고쳐 저장한 것은 끝낸 것이 아니므로 축하하지 않는다. 그
 * 판단은 부르는 쪽에 이미 있다(편집 폼의 `buildChanges`, 판의 `fromColumn === toColumn`).
 *
 * 뮤테이션의 `onSuccess` 에서 부른다 — 서버가 받아 준 뒤에만 축하한다. */
export function celebrateIfCompleted(nextStatus, doneKeys) {
  if (!nextStatus || !doneKeys || !doneKeys.has(nextStatus)) return false;
  celebrate();
  return true;
}

/** 상태 갈래 어휘의 「끝났다」. 서버의 `app/work/workflow.py::CAT_DONE` 과 같은 값이다. */
export const DONE_CATEGORY = "DONE";

/** 서버가 돌려준 티켓이 **완료 갈래**면 터뜨린다.
 *
 * 판의 이동 응답(`/api/work/board/{id}/move`)은 티켓에 `status_category` 를 함께 싣는다
 * (`app/work/service.py::_card`). 그 자리에서는 상태 어휘를 따로 받아 올 이유가 없다 —
 * 서버가 이미 갈래를 말해 주는데 화면이 같은 판정을 두 번 하면 언젠가 둘이 갈린다.
 *
 * 「옮겼는가」는 여기서 못 본다. 같은 열 안에서 순서만 바꾼 것도 완료 티켓이면 참이 되므로,
 * **부르는 쪽이 열이 실제로 바뀐 경우에만** 부른다(판은 그때만 `to_status` 를 싣는다). */
export function celebrateIfCompletedCategory(ticket) {
  if (!ticket || ticket.status_category !== DONE_CATEGORY) return false;
  celebrate();
  return true;
}

/** 「남은 게 0 이 됐을 때만」 터뜨린다.
 *
 * 처리할 때마다가 아니라 **비운 순간**이다. `remaining` 이 0 이 아니면 아무것도 안 한다.
 * 값을 못 셌으면(`null`/`undefined`) 역시 안 한다 — 모르는 것을 축하하지 않는다. */
export function celebrateIfCleared(remaining) {
  if (typeof remaining !== "number" || remaining !== 0) return false;
  celebrate();
  return true;
}

/** 목록이 **비워진 순간**에 한 번 축하한다 — 조건을 바꿔서 비는 것과 구별한다.
 *
 * 🔴 이 구별이 이 훅의 존재 이유다. 「보이는 건수가 0이 됐다」만 보면, 검색어를 쳐서
 * 결과가 0건이 된 사람에게도 종잇조각이 쏟아진다. 그것은 축하가 아니라 조롱이다.
 *
 * 그래서 **조건 지문**(`token`, 보통 질의 문자열)을 함께 받는다. 지문이 바뀌면 기억을
 * 조용히 새 값으로 옮기고 축포는 안 터뜨린다 — 같은 조건에서 숫자가 줄어 0이 됐을 때만
 * 「끝냈다」이다. 처음 본 값에도 안 터뜨린다(빈 채로 들어온 사람은 방금 끝낸 것이 아니다).
 */
export function useCelebrateOnCleared(total, token) {
  const seen = React.useRef({ token: null, total: null });
  React.useEffect(() => {
    if (typeof total !== "number") return;
    const prev = seen.current;
    seen.current = { token, total };
    if (prev.token !== token) return;      // 조건이 바뀌었다 — 끝낸 것이 아니다
    if (prev.total == null) return;        // 처음 본 값
    if (prev.total > 0 && total === 0) celebrate();
  }, [total, token]);
}

/* ── 네잎클로버 ─────────────────────────────────────────────────────────────
 *
 * 이 제품의 마크가 네잎클로버다(Clovi = clover). 그래서 「만들었다」·「움직였다」의 축하는
 * 무채색 종잇조각이 아니라 **브랜드 마크 그 자체**가 쏟아진다 — 다운로드도 새 자산도 없다.
 *
 * 🔴 `shapeFromPath` 는 경로를 **하나만** 받는다. 마크의 SVG 는 잎 하나를
 * `transform="rotate(90 64 64)"` 로 네 번 그리는데 path 데이터에는 회전이 없으므로,
 * 회전을 좌표에 구워 한 경로로 합쳤다. 90° 배수라 삼각함수 없이 정확하다:
 * (x,y) → (128-y, x). 원본은 `app/static/brand/logo/clovirassist-mark.svg` 이고,
 * 그 파일이 바뀌면 이 문자열도 다시 만들어야 한다(clover-shape.test.js 가 대조한다). */
export const CLOVER_PATH =
  "M64 64 C56 54 38 50 34 33 C30 17 42 7 54 11 C60 13 63 18 64 24 C65 18 68 13 74 11 C86 7 98 17 94 33 C90 50 72 54 64 64 ZM64 64 C74 56 78 38 95 34 C111 30 121 42 117 54 C115 60 110 63 104 64 C110 65 115 68 117 74 C121 86 111 98 95 94 C78 90 74 72 64 64 ZM64 64 C72 74 90 78 94 95 C98 111 86 121 74 117 C68 115 65 110 64 104 C63 110 60 115 54 117 C42 121 30 111 34 95 C38 78 56 74 64 64 ZM64 64 C54 72 50 90 33 94 C17 98 7 86 11 74 C13 68 18 65 24 64 C18 63 13 60 11 54 C7 42 17 30 33 34 C50 38 54 56 64 64 Z";

/** 마크의 네 잎이 쓰는 색 그대로. 잎마다 그라디언트지만 종잇조각은 단색이라 각 잎의
 *  대표색을 뽑았다 — 위(인디고)·오른쪽(보라)·아래(짙은 인디고)·왼쪽(청록). */
export const CLOVER_COLORS = ["#536CD6", "#8E75E1", "#435CBE", "#62C7BD"];

/* 모양은 **한 번만** 만든다. `shapeFromPath` 는 Path2D 로 경로를 재고 캔버스에 굽는 일이라
 * 발사마다 부르면 그 값을 매번 다시 계산한다.
 *
 * 🔴 만들지 못하면 `null` 이고, 그때는 기본 모양으로 터진다. jsdom 에는 Path2D 가 없고
 * (시험이 이 경로를 지난다) 아주 오래된 브라우저도 없다 — 축하가 안 뜨는 것보다 모양이
 * 기본인 편이 낫다. */
let cloverShape;
function cloverShapes() {
  if (cloverShape === undefined) {
    try {
      // 이름 있는 export 가 아니라 기본 export 의 속성이다(canvas-confetti 1.9).
      // 시험의 대역은 맨 함수라 이 속성이 없다 — 그러면 아래 catch 가 받아 기본 모양이 된다.
      cloverShape = confetti.shapeFromPath({ path: CLOVER_PATH });
    } catch (e) {
      cloverShape = null;
    }
  }
  return cloverShape ? [cloverShape] : undefined;
}

/** 무언가를 **새로 만든 순간**. 끝낸 것이 아니라 시작한 것이라, 축포보다 가볍다.
 *
 * 값이 완료 축포와 다른 이유가 있다: 아래에서 위로 한 줌 피어오르고(startVelocity 낮음,
 * 좁은 퍼짐) 곧 걷힌다. 「끝냈다」의 세 발짜리 축포와 같은 무게로 터지면 문서를 열 장 만든
 * 사람에게는 그냥 소음이다. */
export function celebrateCreated() {
  celebrateBurst({
    particleCount: 46,
    spread: 52,
    startVelocity: 34,
    ticks: 140,
    gravity: 0.9,
    scalar: 1.1,
    origin: { y: 0.72 },
    colors: CLOVER_COLORS,
    shapes: cloverShapes(),
  });
}

/** 일이 **움직인 순간**(예: 진행 중으로 옮김). 만든 것보다도 가볍다 — 하루에 여러 번
 *  일어나는 일이라, 눈에 띄되 손을 멈추게 하지 않아야 한다. */
export function celebrateMoved() {
  celebrateBurst({
    particleCount: 18,
    spread: 34,
    startVelocity: 26,
    ticks: 90,
    gravity: 1.1,
    scalar: 0.9,
    origin: { y: 0.6 },
    colors: CLOVER_COLORS,
    shapes: cloverShapes(),
  });
}

/** 상태 갈래 어휘의 「하는 중」. 서버의 `app/work/workflow.py::CAT_IN_PROGRESS` 와 같다. */
export const IN_PROGRESS_CATEGORY = "IN_PROGRESS";

/** `/api/work/statuses` 응답 → **하는 중으로 세는** 상태 key 집합.
 *
 * 이 제품의 어휘에서는 '진행' 과 '검증' 둘이다. 화면이 "진행" 이라고 적지 않는 이유는
 * `doneStatusKeys` 와 같다 — 어휘가 바뀌면 이 파일만 옛 이름으로 남는다. */
export function inProgressStatusKeys(statusesBody) {
  const rows = statusesBody && Array.isArray(statusesBody.statuses) ? statusesBody.statuses : [];
  return new Set(
    rows.filter((s) => s && s.category === IN_PROGRESS_CATEGORY).map((s) => s.key)
  );
}

/** 이번 쓰기가 티켓을 **하는 중으로 옮겼으면** 가벼운 클로버 한 줌.
 *
 * `celebrateIfCompleted` 와 같은 계약이다: `nextStatus` 는 「이번에 실제로 바뀐 상태」이고,
 * 안 바뀌었으면 부르는 쪽이 빈 값을 넘긴다. 완료가 큰 축포인 것과 달리 여기는 작은 한 줌이다 —
 * 시작은 끝이 아니고, 하루에 여러 번 일어난다. */
export function celebrateIfStarted(nextStatus, inProgressKeys) {
  if (!nextStatus || !inProgressKeys || !inProgressKeys.has(nextStatus)) return false;
  celebrateMoved();
  return true;
}

/** 판의 이동 응답처럼 서버가 갈래를 실어 줄 때. `celebrateIfCompletedCategory` 의 짝이다. */
export function celebrateIfStartedCategory(ticket) {
  if (!ticket || ticket.status_category !== IN_PROGRESS_CATEGORY) return false;
  celebrateMoved();
  return true;
}
