"use strict";

/* 테마 적용 — 로그인 이후 화면이 공유한다.
 *
 * 이 로직이 chat.js와 admin/app.js에 복붙돼 있었고, 비밀번호 변경 화면에만 빠져 있었다.
 * 그래서 다크로 쓰던 사용자가 '비밀번호 변경'을 누르면 흰 화면을 맞았다 — 로그인 이후
 * 화면인데 혼자 테마를 안 따라갔다. 첫 로그인한 신규 사용자가 반드시 거치는 화면이다.
 *
 * 로그인 화면은 이 파일을 읽지 않는다. 인증 전이고, 히어로가 라이트 고정으로 설계돼 있다.
 */
(function () {
  var STORAGE_KEY = "clovirone_theme";

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) {}
  }

  // 저장된 선호가 없으면 OS의 prefers-color-scheme를 따른다 — frontend/src/app/theme-store.js
  // 의 prefersDark()와 같은 규칙(PA-RC-0021). 이 파일이 그 규칙 없이 "light"로 고정한 채
  // localStorage에 그대로 써 버리면(아래 applyTheme), 이 화면(비밀번호 변경, 신규/재설정
  // 계정이 로그인 직후 반드시 거친다)이 SPA보다 먼저 부팅 키를 "light"로 오염시켜, 다크
  // OS 사용자도 이후 SPA 첫 로드까지 밝은 화면을 맞았다.
  function prefersDark() {
    try { return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches); }
    catch (e) { return false; }
  }

  // localStorage가 막힌 브라우저에서도 화면이 죽으면 안 된다. 그럴 땐 OS 선호(막혔으면 라이트)로 간다.
  var stored = prefersDark() ? "dark" : "light";
  try { stored = localStorage.getItem(STORAGE_KEY) || stored; } catch (e) {}
  applyTheme(stored);

  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });
  }

  // 다른 화면 스크립트가 쓸 수 있게 열어 둔다.
  window.ClovirTheme = { apply: applyTheme };
})();
