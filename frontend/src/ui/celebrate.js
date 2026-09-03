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

export function celebrate() {
  const now = Date.now();
  if (now - lastBurstAt < BURST_COOLDOWN_MS) return;
  lastBurstAt = now;
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
