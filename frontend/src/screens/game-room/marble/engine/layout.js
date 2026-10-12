/* 출발 자리 — 원본 marble.ts 의 격자(한 줄 10개, 0.6 간격, 줄이 많으면 위로 올린다).
 *
 * 물리(`world.js`)와 그리기(대기 중 미리 보기)가 같은 함수를 쓴다. planck 를 들여오지 않는 모듈이라 화면이 이것만
 * 들여와도 물리 청크를 받지 않는다. 🔴 값을 바꾸면 지문이 바뀐다 — 모든 브라우저가 같은 자리에서 출발해야 한다. */
export function spawnPosition(order, total) {
  const maxLine = Math.ceil(total / 10);
  const line = Math.floor(order / 10);
  const lineDelta = -Math.max(0, Math.ceil(maxLine - 5));
  return { x: 10.25 + (order % 10) * 0.6, y: maxLine - line + lineDelta };
}
