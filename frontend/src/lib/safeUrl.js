/* 외부 링크 스킴 검사 (SEC1).
 *
 * 예전에는 이 함수가 `screens/TeamDoc.jsx` 안에 있었다. 보안 원시함수가 화면 모듈에 숨어
 * 있으니 새 화면에서 아무도 찾아 쓰지 않았고, 실제로 `Banners.jsx`(전 사용자에게 뜨는
 * 공지 배너) · `Trash.jsx` · `DevReport.jsx` 세 곳이 그냥 `href={값}` 을 렌더했다.
 *
 * 왜 위험한가: react-dom 18.3.1 의 `sanitizeURL` 은 **개발 빌드 전용 `console.error`** 라
 * 운영 빌드에서는 아무 일도 하지 않는다. 그리고 CSP 의 `script-src` 에 `'unsafe-inline'` 이
 * 들어가면서 `javascript:` URI 가 실행 가능해졌다.
 *
 * **이것은 이중 방어다.** 진짜 경계는 서버(`app/core/safe_url.py`)이고, 화면 검사는 이미
 * 저장돼 있던 값이나 다른 경로로 들어온 값까지 덮는 역할이다. */

const ALLOWED = /^https?:\/\//i;

// `javascript:` 앞에 제어문자·공백을 붙여 스킴 검사를 우회하는 고전적 수법을 먼저 지운다 —
// 브라우저는 그런 값을 관대하게 해석한다. 서버(safe_url.py)와 같은 규칙이다.
const LEADING_JUNK = /^[\u0000-\u0020]+/;

export function safeExternal(url) {
  if (typeof url !== "string") return null;
  const cleaned = url.replace(LEADING_JUNK, "").trim();
  return ALLOWED.test(cleaned) ? cleaned : null;
}
