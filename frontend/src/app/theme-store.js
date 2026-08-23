/* 테마 저장/적용 — 다크는 <html data-theme="dark">로만 켜진다.
 *
 * App.jsx에서 분리했다. 셸(UserMenu)과 부팅 코드가 같은 규칙을 봐야 하는데, 예전에는 두 곳이
 * 각자 localStorage를 만지며 키를 하나씩 빠뜨려 '선택한 테마가 새로고침마다 잘못된 색으로
 * 번쩍이는(FOUC)' 문제가 났다.
 *
 * 키가 두 벌인 이유:
 *   - 계정별 키(clovirassist_theme:<id>) — 공용/키오스크 PC에서 한 사람의 선택이 다음 사람에게
 *     넘어가지 않게 한다.
 *   - 부팅 키(clovirassist_theme) — 부팅 시점(모듈 로드, 아직 인증 전)에는 누가 로그인할지 모른다.
 *     첫 페인트 전에 테마를 정하려면 계정과 무관한 키가 하나 필요하다. 그래서 선택할 때마다
 *     양쪽에 함께 쓴다. 로그아웃 때는 부팅 키만 지운다.
 */

const THEME_KEY = "clovirassist_theme";

function accountKey(userId) {
  return userId ? THEME_KEY + ":" + userId : THEME_KEY;
}

export function applyTheme(t) {
  if (t === "dark" || t === "light") document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
}

/* 저장된 선호가 없으면 OS의 prefers-color-scheme를 따른다
 * (다크 OS 사용자가 매번 라이트로 시작하던 문제). */
function prefersDark() {
  try { return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches); }
  catch (e) { return false; }
}

export function readTheme(userId, opts) {
  const onlyAccount = opts && opts.onlyAccount;
  try {
    if (userId) {
      const perAccount = window.localStorage.getItem(accountKey(userId));
      if (perAccount) return perAccount;
      if (onlyAccount) return "";
    }
    if (onlyAccount) return "";
    const boot = window.localStorage.getItem(THEME_KEY);
    if (boot) return boot;
  } catch (e) { /* 시크릿 모드/저장소 차단 */ }
  return onlyAccount ? "" : (prefersDark() ? "dark" : "light");
}

export function storeTheme(theme, userId) {
  try {
    window.localStorage.setItem(accountKey(userId), theme);
    // 부팅 키에도 미러링 — 이게 빠지면 첫 페인트가 OS 설정을 따라가 잘못된 테마로 번쩍인다.
    window.localStorage.setItem(THEME_KEY, theme);
  } catch (e) { /* ignore */ }
}

export function clearBootTheme() {
  try { window.localStorage.removeItem(THEME_KEY); } catch (e) { /* ignore */ }
}

/* 첫 페인트 전(모듈 로드 시점, createRoot 이전)에 테마를 적용해 다크 사용자의 화이트 플래시를
 * 없앤다. CSP가 인라인 <script>를 막으므로 부팅 인라인 스크립트 대신 모듈 스코프에서 동기 적용. */
export function applyBootTheme() {
  applyTheme(readTheme());
}
