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

  // localStorage가 막힌 브라우저에서도 화면이 죽으면 안 된다. 그럴 땐 라이트로 간다.
  var stored = "light";
  try { stored = localStorage.getItem(STORAGE_KEY) || "light"; } catch (e) {}
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
