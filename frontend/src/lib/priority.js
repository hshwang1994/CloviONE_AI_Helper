/* 티켓 우선순위 어휘 — 원본값을 한국어 표시와 톤으로 옮긴다.
 *
 * 원래 Chat.jsx(1,205줄) 안에 있었는데, 내 티켓·티켓 상세 화면이 이 함수 두 개를 쓰려고
 * 채팅 화면 전체를 import했다. 그래서 채팅을 지연 로딩으로 빼도 초기 번들에 그대로
 * 끌려 들어왔다(순수 함수 두 개 때문에 1,205줄이 따라옴). 여기로 옮겨 끊는다.
 *
 * Badge에는 이미 번역된 한국어 문자열 + 명시적 kind를 넘긴다 — Badge는 kind가 오면 그것을
 * 그대로 쓰고, value는 매핑에 없으면 원문을 통과시키므로 번역된 문자열이 그대로 보인다.
 */

const PRIORITY_TEXT = {
  urgent: "긴급", critical: "긴급",
  high: "높음", medium: "보통", normal: "보통", low: "낮음",
  "1": "높음", "2": "보통", "3": "낮음",
  긴급: "긴급", 높음: "높음", 보통: "보통", 낮음: "낮음",
};

const PRIORITY_KIND = {
  urgent: "danger", critical: "danger", 긴급: "danger",
  high: "warn", 높음: "warn",
  medium: "info", normal: "info", 보통: "info",
  low: "neutral", 낮음: "neutral",
  "1": "danger", "2": "info", "3": "neutral",
};

export function priorityKo(p) {
  const key = String(p).trim().toLowerCase();
  if (PRIORITY_TEXT[key]) return PRIORITY_TEXT[key];
  const s = String(p).trim();
  // 매핑에 없는 값(러너가 보내는 커스텀 등급명 등) — kit.jsx의 statusText()와 같은 방식으로
  // 원시 snake_case/kebab-case를 사람이 읽는 형태로 다듬는다("p1_urgent" → "P1 Urgent").
  if (/^[a-z0-9]+([_-][a-z0-9]+)+$/i.test(s)) {
    return s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return s;
}

export function priorityKind(p) {
  const key = String(p).trim().toLowerCase();
  return PRIORITY_KIND[key]; // 매핑 없으면 undefined → Badge가 neutral로 폴백.
}
