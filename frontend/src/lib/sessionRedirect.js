/* 세션이 끊겼을 때 로그인 화면으로 보내는 단 하나의 자리 (지시 19).
 *
 * ## 왜 한 곳인가
 *
 * 예전에는 **아무도 보내지 않았다.** 401 을 맞으면 `["me"]` 를 다시 물어보고, 그것도 401 이면
 * 셸이 `minimal` 로 축소될 뿐이었다 — 사이드바가 사라진 화면에 직전 데이터가 그대로 남아
 * 있어서 "로그인이 풀렸다"인지 "권한이 없다"인지 "화면이 고장났다"인지 구분되지 않았다.
 * 서버 렌더 경로는 이미 `303 /login?next=<path>` 규약을 갖고 있다(app/main.py) — SPA 도
 * 같은 규약을 쓴다.
 *
 * ## 지키는 것
 *
 * - **401 만.** 403(권한 없음)은 로그아웃이 아니다 — 그 화면은 이유를 보여 주고 남는다.
 * - **한 번만.** 이동 중에 또 부르면 로그인 화면이 자기 자신으로 계속 튕긴다.
 * - **되돌아올 곳.** 현재 SPA 주소(경로 + 해시)를 `next` 로 싣는다. 서버의
 *   `safe_next_path()` 가 same-origin 상대 경로만 통과시킨다(open-redirect 방지).
 * - **로그인 화면에서는 안 한다.** 그 페이지는 SPA 밖이지만, 테스트·임베드처럼 경로가
 *   `/login` 인 상태로 이 코드가 실행될 수 있다.
 */

let redirected = false;

/** 테스트가 다음 경우를 독립적으로 재현할 수 있게 한다(프로덕션에서는 부르지 않는다). */
export function resetSessionRedirect() {
  redirected = false;
}

/** 지금 세션이 끊겼다 — 로그인 화면으로 보낸다. 이미 보냈으면 아무 일도 하지 않는다. */
export function redirectToLogin() {
  if (redirected) return false;
  if (typeof window === "undefined" || !window.location) return false;
  const path = window.location.pathname || "/";
  if (path === "/login" || path.startsWith("/login/")) return false;

  redirected = true;
  const here = path + (window.location.search || "") + (window.location.hash || "");
  const params = new URLSearchParams({ next: here, expired: "1" });
  // `replace` 다 — 뒤로가기로 죽은 세션의 화면에 돌아가지 않는다.
  window.location.replace("/login?" + params.toString());
  return true;
}
