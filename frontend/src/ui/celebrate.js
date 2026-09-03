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
 * 🔴 그리고 **일이 끝났을 때만**이다. 「한 건 처리했다」가 아니라 「할 게 없어졌다」다 —
 * 매번 터지면 두 번째부터는 축하가 아니라 방해다. 그 판단은 부르는 쪽이 한다
 * (`celebrateIfCleared`).
 *
 * OS·브라우저의 동작 줄이기 설정은 보지 않는다 — 이 제품의 연출은 언제나 돈다
 * (제품 결정, `ui/motion.js` 머리말).
 */
export function celebrate() {
  const base = {
    spread: 74, startVelocity: 45, ticks: 200,
    origin: { y: 0.55 },
  };
  confetti({ ...base, particleCount: 90 });
  window.setTimeout(() => confetti({ ...base, particleCount: 55, angle: 60, origin: { x: 0, y: 0.62 } }), 140);
  window.setTimeout(() => confetti({ ...base, particleCount: 55, angle: 120, origin: { x: 1, y: 0.62 } }), 260);
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
