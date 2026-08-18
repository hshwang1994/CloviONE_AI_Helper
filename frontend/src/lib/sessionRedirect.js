/* 세션이 끊겼을 때 로그인 화면으로 보내는 단 하나의 자리 (지시 19).
 *
 * ## 왜 한 곳인가
 *
 * 처음에는 **아무도 보내지 않았다.** 401 을 맞으면 `["me"]` 를 다시 물어보고, 그것도 401 이면
 * 셸이 `minimal` 로 축소될 뿐이었다 — 사이드바가 사라진 화면에 직전 데이터가 그대로 남아
 * "로그인이 풀렸다"인지 "권한이 없다"인지 "화면이 고장났다"인지 구분되지 않았다.
 *
 * 그것을 고친 뒤에도 절반이 남아 있었다. 화면 열한 곳이 각자 `window.location.href = "/login"`
 * 을 하고 있었고, 그 경로들은 전부:
 *   - **되돌아올 곳(`next`)을 잃었다** — 재로그인하면 서버가 `/` 로 떨어뜨린다.
 *   - **만료였다는 사실(`expired=1`)을 안 알렸다** — 로그인 화면이 문맥 없는 첫 방문처럼 뜬다.
 *   - `setTimeout` 으로 1.2초 뒤 이동하는 곳들은 그 사이 다른 이동을 **덮어썼다**.
 * 그래서 이 모듈은 "만들었다"가 아니라 **소비처를 다 옮겨야** 뜻이 있다.
 *
 * 서버 렌더 경로는 이미 `303 /login?next=<path>` 규약을 갖고 있다(`app/main.py`) — SPA 도
 * 같은 규약을 쓴다.
 *
 * ## 지키는 것
 *
 * - **401 만.** 403(권한 없음)은 로그아웃이 아니다 — 그 화면은 이유를 보여 주고 남는다.
 * - **한 번만.** 이동 중에 또 부르면 로그인 화면이 자기 자신으로 계속 튕긴다.
 * - **되돌아올 곳.** 현재 SPA 주소(경로 + 쿼리 + 해시)를 `next` 로 싣는다. 서버의
 *   `safe_next_path()` 가 same-origin 상대 경로만 통과시킨다(open-redirect 방지).
 * - **로그인 화면에서는 안 한다.**
 */

let redirected = false;
let pendingTimer = null;

/** 테스트가 다음 경우를 독립적으로 재현할 수 있게 한다(프로덕션에서는 부르지 않는다). */
export function resetSessionRedirect() {
  redirected = false;
  if (pendingTimer) { clearTimeout(pendingTimer); pendingTimer = null; }
}

function onLoginPage(path) {
  return path === "/login" || path.startsWith("/login/");
}

/** 지금 화면으로 되돌아오는 로그인 주소. 링크·버튼의 `href` 로 쓴다.
 *
 * 이동을 실제로 하지는 않으므로 1회 가드를 건드리지 않는다 — 사용자가 누르기 전까지는
 * 아무 일도 일어나지 않아야 한다. */
export function loginUrl({ expired = true } = {}) {
  if (typeof window === "undefined" || !window.location) return "/login";
  const path = window.location.pathname || "/";
  if (onLoginPage(path)) return "/login";
  const here = path + (window.location.search || "") + (window.location.hash || "");
  const params = new URLSearchParams({ next: here });
  if (expired) params.set("expired", "1");
  return "/login?" + params.toString();
}

/** 지금 세션이 끊겼다 — 로그인 화면으로 보낸다. 이미 보냈으면 아무 일도 하지 않는다.
 *
 * `delayMs` 는 토스트를 잠깐 보여 준 뒤 떠나야 하는 자리를 위한 것이다. 예약한 순간부터
 * 1회 가드가 걸리므로, 그 사이 다른 곳이 또 불러도 이동이 두 번 예약되지 않는다 — 예전에
 * 화면 세 곳이 각자 `setTimeout` 을 걸어 좋은 주소를 덮어쓰던 문제가 그것이다.
 */
export function redirectToLogin({ delayMs = 0 } = {}) {
  if (redirected) return false;
  if (typeof window === "undefined" || !window.location) return false;
  if (onLoginPage(window.location.pathname || "/")) return false;

  redirected = true;
  const url = loginUrl();
  // `replace` 다 — 뒤로가기로 죽은 세션의 화면에 돌아가지 않는다.
  const go = () => { pendingTimer = null; window.location.replace(url); };
  if (delayMs > 0) pendingTimer = setTimeout(go, delayMs);
  else go();
  return true;
}
