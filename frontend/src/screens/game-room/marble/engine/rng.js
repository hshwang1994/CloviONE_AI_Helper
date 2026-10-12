/* 구슬 레이스의 난수 — seed 로만 정해진다 (D-564).
 *
 * 경주의 모든 무작위(출발 순서 섞기 · 구슬 밀도 · 멈춘 구슬 흔들기)는 서버가 준 seed 에서 나온다. `Math.random` · 시각 ·
 * 기기 상태는 쓰지 않는다 — 같은 seed 면 모든 브라우저가 같은 경주를 계산한다. mulberry32 는 32비트 정수 연산과 한 번의
 * 나눗셈뿐이라 엔진 · OS 와 무관하게 같은 값을 낸다(초월 함수가 없다). */

/* 문자열 seed(서버의 16진수) → 32비트 정수. FNV-1a 는 짧은 글에도 고르게 퍼진다. */
export function seedToInt(seed) {
  const text = String(seed || "");
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export function createRng(seed) {
  let a = typeof seed === "number" ? seed >>> 0 : seedToInt(seed);
  /* [0, 1) 의 실수 하나. mulberry32 — 공개 도메인 (Tommy Ettinger). */
  const next = () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return {
    next,
    /* 0 이상 n 미만의 정수. */
    int(n) { return Math.floor(next() * n); },
    /* lo 이상 hi 미만의 실수. */
    range(lo, hi) { return lo + next() * (hi - lo); },
    /* 피셔-예이츠 — 제자리에서 섞고 그 배열을 돌려준다. */
    shuffle(list) {
      for (let i = list.length - 1; i > 0; i -= 1) {
        const j = Math.floor(next() * (i + 1));
        const tmp = list[i];
        list[i] = list[j];
        list[j] = tmp;
      }
      return list;
    },
  };
}
