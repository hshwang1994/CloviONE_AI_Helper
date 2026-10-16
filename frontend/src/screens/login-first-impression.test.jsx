import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/* 로그인 첫인상 계약 (12단계).
 *
 * ── 이 파일이 왜 두 층을 함께 보는가 ─────────────────────────────────────────
 * 과제 지시는 `frontend/src/screens/Login.jsx` 를 고치라고 했지만 **그 파일은 없다**.
 * 이 저장소의 로그인 화면은 SPA 가 아니라 서버 렌더다:
 *     app/templates_html/login.html + app/static/js/login.js + app/static/js/clovi-login.js
 * 없는 React 화면을 새로 지어 놓으면 "화면이 있다" 와 "사용자가 그 화면을 본다" 가 갈린다
 * (저장소 불변 규칙 6). 그래서 **실제로 사용자가 보는 코드**를 시험한다:
 *
 *   1층 로그인 페이지(바닐라 JS) — 누른 뒤의 진행 표시, 실패 시 축하하지 않기,
 *                                  OS 설정과 무관하게 시선 추적이 도는 것.
 *   2층 SPA 인계(React)         — 로그인 페이지가 남긴 표식을 받아 첫 화면까지 이어지는
 *                                  환영 연출(폭죽 + 클로비). 이 층이 "뚝 끊긴다" 를 메운다.
 *
 * 1층은 파일을 읽어 jsdom 에 그대로 올린다. 문자열 grep 이 아니라 **실제 동작**을 본다 —
 * 이 저장소는 "테스트가 헛것이었다" 를 여섯 번 겪었다(불변 규칙 4).

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const readRepo = (rel) => readFileSync(path.join(REPO, rel), "utf8");

const LOGIN_JS = readRepo("app/static/js/login.js");
const CLOVI_JS = readRepo("app/static/js/clovi-login.js");
const LOGIN_CSS = readRepo("app/static/css/login.css");
const LOGIN_HTML = readRepo("app/templates_html/login.html");

const confettiMock = vi.fn();
vi.mock("canvas-confetti", () => ({ default: (...args) => confettiMock(...args) }));

import { LoginHandoff, LOGIN_HANDOFF_KEY, HANDOFF_FRESH_MS } from "../app/LoginHandoff.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/* ── 1층 픽스처 ──────────────────────────────────────────────────────────────
 * login.html 의 뼈대만 옮긴 것이다. 아래 `픽스처가 진짜 화면과 같은 뼈대인가` 테스트가
 * 여기 쓰인 id 가 실제 템플릿에 전부 있는지 확인한다 — 픽스처만 고쳐 놓고 초록을 보는
 * 사고를 막는다. */
const REQUIRED_IDS = [
  "login-form", "email", "email-error", "password", "password-error", "caps-hint",
  "toggle-password", "login-submit", "login-submit-label", "login-error",
  "login-hint", "server-status", "clovi-stage", "clovi-message",
];

const FIXTURE = `
  <main class="login-shell">
    <section class="hero">
      <div id="clovi-stage" class="clovi-stage" data-state="welcome">
        <img class="clovi-canonical-base" alt="" />
        <img class="clovi-eyes-layer" alt="" />
        <span class="clovi-success-badge" aria-hidden="true">Y</span>
      </div>
      <div class="clovi-card"><div><small>클로비</small><strong id="clovi-message">오늘 업무를 준비했어요</strong></div></div>
    </section>
    <section class="form-panel">
      <form id="login-form" action="/login" method="post" novalidate>
        <div class="field">
          <div class="input-wrap"><input id="email" name="email" type="email" /></div>
          <p id="email-error" class="field-message"></p>
        </div>
        <div class="field">
          <div class="input-wrap">
            <input id="password" name="password" type="password" />
            <button id="toggle-password" type="button" aria-pressed="false">표시</button>
          </div>
          <p id="password-error" class="field-message"></p>
          <p id="caps-hint" class="caps-warning" role="status" hidden></p>
        </div>
        <div id="login-error" class="status error" role="alert"></div>
        <button id="login-submit" class="login-button" type="submit">
          <span class="button-spinner" aria-hidden="true" hidden></span>
          <span id="login-submit-label" class="button-label">로그인</span>
          <svg class="button-arrow" aria-hidden="true"></svg>
        </button>
      </form>
      <aside id="login-hint" class="support-note" data-support-email=""></aside>
      <p id="server-status" class="server-status" aria-live="polite"></p>
    </section>
  </main>
`;

function setMatchMedia({ reduce = false, wide = false } = {}) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: /prefers-reduced-motion/.test(query) ? reduce : wide,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
}

/* 실제 두 스크립트를 순서대로 올린다. 순서가 계약이다 — login.js 가 먼저 submit 리스너를
 * 걸고 clovi-login.js 가 그 판정을 DOM 에서 읽는다(login.html 의 script 순서와 같다). */
function bootLoginPage(opts) {
  document.body.innerHTML = FIXTURE;
  setMatchMedia(opts);
  // eslint-disable-next-line no-new-func
  new Function(LOGIN_JS)();
  // eslint-disable-next-line no-new-func
  new Function(CLOVI_JS)();
  return {
    form: document.getElementById("login-form"),
    email: document.getElementById("email"),
    password: document.getElementById("password"),
    submit: document.getElementById("login-submit"),
    label: document.getElementById("login-submit-label"),
    spinner: document.querySelector(".button-spinner"),
    errorBox: document.getElementById("login-error"),
    stage: document.getElementById("clovi-stage"),
    message: document.getElementById("clovi-message"),
  };
}

function respondWith(payload, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(payload),
  });
  globalThis.fetch = fetchMock;
  window.fetch = fetchMock;
  return fetchMock;
}

/* 성공 경로는 연출을 **끝까지 기다린 뒤에야** 표식을 찍는다(clovi-login.js 900ms,
   login.js 상한 1200ms). 그 타이머가 다음 시험 도중에 발사되면 찍히면 안 되는 자리에
   표식이 생긴다 — 동작 줄이기 갈래가 있던 시절에는 그 갈래가 즉시 resolve 해서 안 보였다.
   제출한 시험은 afterEach 에서 끝까지 흘려 보낸다. */
let submitted = false;
const FLOW_DRAIN_MS = 1400;

async function submitLogin(ui, { email = "hong@example.com", password = "pw123456" } = {}) {
  submitted = true;
  ui.email.value = email;
  ui.password.value = password;
  ui.form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
}

const tick = (ms) => new Promise((r) => setTimeout(r, ms));

beforeEach(() => {
  confettiMock.mockReset();
  window.sessionStorage.clear();
  // 성공 경로는 여기로 이동한다. 해시만 바뀌는 주소라 jsdom 이 실제 문서 이동을 시도하지
  // 않는다 — 이 앱은 HashRouter 라 실제 next 경로도 이 모양이다.
  window.location.hash = "";
});

afterEach(async () => {
  if (submitted) {
    await tick(FLOW_DRAIN_MS);
    submitted = false;
  }
  // 축포는 가운데 → 왼쪽 → 오른쪽으로 나뉘어 130ms·240ms 뒤에 두 번 더 터진다(예약된 타이머).
  // 여기서 비우지 않으면 그 타이머가 **다음 테스트** 도중에 발사돼, 쏘지 않아야 하는 자리에서
  // 쏜 것으로 잡힌다. 실제로 이 파일에서 한 번 그렇게 깨졌다.
  if (confettiMock.mock.calls.length) await tick(300);
  document.body.innerHTML = "";
  delete window.matchMedia;
});

// ════════════════════════════════════════════════════════════════════════════
// 픽스처 무결성
// ════════════════════════════════════════════════════════════════════════════
describe("픽스처가 진짜 화면과 같은 뼈대인가", () => {
  it("여기서 쓰는 id 는 실제 login.html 에 전부 있다", () => {
    const missing = REQUIRED_IDS.filter((id) => !LOGIN_HTML.includes(`id="${id}"`));
    expect(missing).toEqual([]);
  });

  it("픽스처에도 같은 id 가 전부 있다", () => {
    document.body.innerHTML = FIXTURE;
    const missing = REQUIRED_IDS.filter((id) => !document.getElementById(id));
    expect(missing).toEqual([]);
  });
});

// ════════════════════════════════════════════════════════════════════════════
// 1. 진행 표시 — 누른 뒤 무슨 일이 일어나는지 보인다
// ════════════════════════════════════════════════════════════════════════════
describe("진행 표시", () => {
  it("누르는 즉시 버튼과 마스코트가 진행 중임을 말한다", async () => {
    respondWith({ ok: true, next: "/#/me" });
    const ui = bootLoginPage({ reduce: false });

    expect(ui.spinner.hidden).toBe(true);
    expect(ui.label.textContent).toBe("로그인");

    await submitLogin(ui);

    // 눌린 그 순간(네트워크 응답 전)에 이미 세 가지가 바뀐다.
    expect(ui.submit.getAttribute("aria-busy")).toBe("true");
    expect(ui.label.textContent).toBe("로그인 중…");
    expect(ui.spinner.hidden).toBe(false);
    expect(ui.stage.dataset.state).toBe("loading");
    expect(ui.message.textContent).toBe("안전하게 로그인하고 있어요");
  });

  it("동작 줄이기에서도 진행 정보는 그대로 남는다", async () => {
    respondWith({ ok: true, next: "/#/me" });
    const ui = bootLoginPage({ reduce: true });

    await submitLogin(ui);

    // 연출(회전하는 스피너)은 CSS 가 끄지만, 정보는 라벨·aria-busy·말풍선에 남는다.
    expect(ui.submit.getAttribute("aria-busy")).toBe("true");
    expect(ui.label.textContent).toBe("로그인 중…");
    expect(ui.message.textContent).toBe("안전하게 로그인하고 있어요");
  });
});

// ════════════════════════════════════════════════════════════════════════════
// 2. 첫 화면까지 이어지는 전환 — 로그인 페이지가 SPA 에 인계 표식을 남긴다
// ════════════════════════════════════════════════════════════════════════════
describe("첫 화면까지 이어지는 전환", () => {
  it("성공하면 이동 직전에 SPA 가 읽을 인계 표식을 남긴다", async () => {
    respondWith({ ok: true, next: "/#/me" });
    // 연출 대기(clovi-login.js 의 CELEBRATE_MS 900ms)는 이제 OS 설정과 무관하게 붙는다.
    // 표식은 그 뒤에 찍히므로, 상한(CELEBRATE_CAP_MS 1200ms)까지 기다려 본다.
    const ui = bootLoginPage({ reduce: true });

    await submitLogin(ui);
    await waitFor(
      () => expect(window.sessionStorage.getItem(LOGIN_HANDOFF_KEY)).toBeTruthy(),
      { timeout: 2500 },
    );

    const raw = window.sessionStorage.getItem(LOGIN_HANDOFF_KEY);
    expect(Number(raw)).toBeGreaterThan(0);
    expect(Date.now() - Number(raw)).toBeLessThan(HANDOFF_FRESH_MS);
  });

  it("표식의 키는 SPA 와 로그인 페이지가 같은 문자열을 쓴다", () => {
    // 두 층이 각자 문자열을 들고 있으면 한쪽만 바뀌는 순간 조용히 끊긴다.
    expect(LOGIN_JS).toContain(LOGIN_HANDOFF_KEY);
  });

  it("비밀번호 변경이 강제된 계정은 축하 대상이 아니다", async () => {
    respondWith({ ok: true, must_change_password: true, next: null });
    const ui = bootLoginPage({ reduce: true });

    await submitLogin(ui);
    await tick(30);

    expect(window.sessionStorage.getItem(LOGIN_HANDOFF_KEY)).toBeNull();
  });
});

// ════════════════════════════════════════════════════════════════════════════
// 3. 실패 경로 — 엉뚱하게 축하하지 않는다
// ════════════════════════════════════════════════════════════════════════════
describe("실패하면 축하하지 않는다", () => {
  const CASES = [
    ["비밀번호 오류", { error: { code: "invalid_credentials", message: "이메일 또는 비밀번호가 올바르지 않습니다." } }],
    ["잠긴 계정", { error: { code: "account_locked", message: "계정이 잠겼습니다. 약 10분 후 다시 시도하세요." } }],
    ["비활성 계정", { error: { code: "account_disabled", message: "비활성화된 계정입니다." } }],
  ];

  CASES.forEach(([name, payload]) => {
    it(`${name}: 성공 표정도 인계 표식도 없다`, async () => {
      respondWith(payload, false);
      const ui = bootLoginPage({ reduce: false });

      await submitLogin(ui);
      await tick(60);

      // 축하하지 않는다 — 이 세 줄이 이 테스트의 요점이라 먼저 본다.
      expect(ui.stage.dataset.state).not.toBe("success");
      expect(ui.label.textContent).not.toBe("로그인 완료");
      expect(window.sessionStorage.getItem(LOGIN_HANDOFF_KEY)).toBeNull();
      // 그리고 실패한 이유는 그대로 보인다.
      expect(ui.errorBox.textContent).toBe(payload.error.message);
    });
  });

  it("세션 만료로 되돌아온 화면도 축하하지 않는다", async () => {
    // 만료 안내는 로그인 **전** 상태다. 이 화면이 뜬 것만으로 표식이 생기면 안 된다.
    bootLoginPage({ reduce: false });
    await tick(30);
    expect(window.sessionStorage.getItem(LOGIN_HANDOFF_KEY)).toBeNull();
  });
});

// ════════════════════════════════════════════════════════════════════════════
// 4. prefers-reduced-motion — 로그인 페이지
// ════════════════════════════════════════════════════════════════════════════
describe("동작 줄이기: 로그인 페이지", () => {
  async function movePointerAndSettle() {
    window.cloviLogin.setState("idle");
    window.dispatchEvent(new window.MouseEvent("pointermove", { clientX: 900, clientY: 40, bubbles: true }));
    await tick(60);
  }

  it("기본 사용자의 눈은 포인터를 따라간다", async () => {
    const ui = bootLoginPage({ reduce: false });
    expect(ui.stage.style.getPropertyValue("--eye-x")).toBe("0px");

    await movePointerAndSettle();

    expect(ui.stage.style.getPropertyValue("--eye-x")).not.toBe("0px");
  });

  /* 정책이 뒤집혔다 (2026-09-03 — `ui/motion.js` 머리말). 예전에는 여기서 눈이 굳는 것을
   * 못박았다. 이 조직의 Windows 가 「애니메이션 효과 끔」이라 Firefox 가 reduce 를 보고했고,
   * 사용자에게는 그것이 「크롬은 되는데 파이어폭스는 안 된다」로 보였다. 지금은 설정과
   * 무관하게 따라간다. */
  it("동작 줄이기를 켜도 눈은 포인터를 따라간다", async () => {
    const ui = bootLoginPage({ reduce: true });

    await movePointerAndSettle();

    expect(ui.stage.style.getPropertyValue("--eye-x")).not.toBe("0px");
    expect(ui.stage.dataset.state).toBe("idle");
    expect(ui.message.textContent).toBe("오늘 업무를 준비했어요");
  });

  /* 사용자 지적: "접속한 이후에 그냥 마우스를 옮기면 움직이지 않음. 한번 눌러야 눈이 움직임."
   *
   * 위 두 시험은 `setState("idle")` 로 상태를 **직접 만들어 놓고** 포인터를 움직인다.
   * 그래서 화면을 그냥 연 사람이 겪는 경로를 한 번도 지나지 않았다 — 넓은 화면에서는
   * login.js 가 이메일 칸에 초점을 준다(정적 autofocus 대체, login.js:103). 그 초점 때문에
   * 등장 인사가 끝나는 자리에서 클로비가 idle 이 아닌 다른 상태로 내려앉으면, 시선 추적은
   * 시작조차 하지 않는다. 사용자가 "한번 눌러야" 라고 한 그 클릭은 초점을 떼는 클릭이다.
   *
   * 기준선(폐기한 목업(지시 64), 1368)은 이 자리에서
   * 언제나 idle 로 내려가고, idle 과 welcome 두 상태에서 포인터를 따라간다. */
  it("아무것도 누르지 않아도, 화면을 연 그대로 눈이 포인터를 따라간다", async () => {
    // 넓은 화면 = login.js 가 첫 칸에 초점을 주는 조건.
    const ui = bootLoginPage({ reduce: false, wide: true });
    expect(document.activeElement, "넓은 화면 전제가 깨졌다").toBe(ui.email);

    // 등장 인사(welcome 780ms)가 끝나 '쉬는 상태'로 내려갈 때까지 기다린다.
    await tick(900);

    // 클릭은 한 번도 하지 않는다. 마우스만 왼쪽 끝 → 오른쪽 끝으로 옮긴다.
    window.dispatchEvent(new window.MouseEvent("pointermove", { clientX: 80, clientY: 40, bubbles: true }));
    await tick(60);
    const atLeft = ui.stage.style.getPropertyValue("--eye-x");

    window.dispatchEvent(new window.MouseEvent("pointermove", { clientX: 900, clientY: 40, bubbles: true }));
    await tick(60);
    const atRight = ui.stage.style.getPropertyValue("--eye-x");

    expect(atRight, `눈이 ${atLeft} 에 굳어 있다 — 포인터를 따라가지 않는다`).not.toBe(atLeft);
  });

  /* 🔴 위 시험은 **버그가 있는 소스에서도 초록이었다.** 여기 하네스는 login.js 를 먼저
   * 통째로 실행하고 clovi-login.js 를 그 다음에 올리는데, login.js 의 `.focus()` 는 동기라
   * 초점 이벤트가 clovi-login.js 가 리스너를 걸기 **전에** 지나가 버린다. 실제 브라우저는
   * 그 순서를 보장하지 않는다 — 창이 뒤에 있으면 초점 이벤트가 늦게 온다. 실브라우저에서
   * 잰 값이 그것이다: 고친 뒤 idle·추적, 고치기 전 email·(3.8, 1.0) 고정.
   *
   * 그래서 타이밍을 흉내 내는 대신 **규칙**을 고정한다. 사람이 손대지 않았는데 온 초점은
   * 표정을 바꾸지 않는다. 이 시험은 관문(`userActed`)을 지우면 빨개진다. */
  it("스크립트가 준 초점은 표정을 바꾸지도, 시선을 멈추지도 않는다", async () => {
    const ui = bootLoginPage({ reduce: false, wide: true });
    await tick(900);
    expect(ui.stage.dataset.state, "등장 인사가 끝나면 쉬는 상태다").toBe("idle");

    // 브라우저가 늦게 흘려 준 초점(사람은 아무것도 안 했다).
    ui.email.dispatchEvent(new window.FocusEvent("focus"));
    await tick(20);

    expect(ui.stage.dataset.state, "사람이 고르지 않은 초점이 표정을 끌어내렸다").toBe("idle");

    window.dispatchEvent(new window.MouseEvent("pointermove", { clientX: 80, clientY: 40, bubbles: true }));
    await tick(60);
    const atLeft = ui.stage.style.getPropertyValue("--eye-x");
    window.dispatchEvent(new window.MouseEvent("pointermove", { clientX: 900, clientY: 40, bubbles: true }));
    await tick(60);
    expect(ui.stage.style.getPropertyValue("--eye-x"), `눈이 ${atLeft} 에 굳었다`).not.toBe(atLeft);
  });

  /* 관문이 기능을 **없애 버리지는 않았다**는 반대쪽. 사람이 실제로 칸을 고르면 표정은
   * 그대로 바뀐다 — 안 그러면 「고쳤다」가 아니라 「지웠다」이다. */
  it("사람이 고른 초점은 표정을 바꾼다", async () => {
    const ui = bootLoginPage({ reduce: false, wide: true });
    await tick(900);

    window.dispatchEvent(new window.MouseEvent("pointerdown", { bubbles: true }));
    ui.email.dispatchEvent(new window.FocusEvent("focus"));
    await tick(20);
    expect(ui.stage.dataset.state).toBe("email");

    window.dispatchEvent(new window.MouseEvent("pointerdown", { bubbles: true }));
    ui.password.dispatchEvent(new window.FocusEvent("focus"));
    await tick(20);
    expect(ui.stage.dataset.state).toBe("privacy");
  });

  /* 이메일 칸을 고른 **뒤에도** 마우스는 계속 움직인다. 고정 시선(3.8, 1.0)은 그 칸을 한 번
   * 쳐다보는 자세이지 눈을 굳히라는 뜻이 아니다. 반대로 privacy 는 「일부러 딴 곳을 본다」가
   * 표현 그 자체라 포인터가 덮으면 안 된다 — 두 규칙이 서로 다르다는 것을 함께 고정한다. */
  it("이메일 칸에서는 눈이 다시 포인터를 따라가고, 비밀번호 칸에서는 딴 곳을 본다", async () => {
    const ui = bootLoginPage({ reduce: false, wide: true });
    await tick(900);

    window.cloviLogin.setState("email");
    expect(ui.stage.style.getPropertyValue("--eye-x"), "들어갈 때는 그 칸을 본다").toBe("3.8px");
    window.dispatchEvent(new window.MouseEvent("pointermove", { clientX: 80, clientY: 40, bubbles: true }));
    await tick(60);
    const atLeft = ui.stage.style.getPropertyValue("--eye-x");
    window.dispatchEvent(new window.MouseEvent("pointermove", { clientX: 900, clientY: 40, bubbles: true }));
    await tick(60);
    expect(ui.stage.style.getPropertyValue("--eye-x"), `눈이 ${atLeft} 에 굳었다`).not.toBe(atLeft);

    window.cloviLogin.setState("privacy");
    const looksAway = ui.stage.style.getPropertyValue("--eye-x");
    expect(looksAway).toBe("-3.6px");
    window.dispatchEvent(new window.MouseEvent("pointermove", { clientX: 900, clientY: 40, bubbles: true }));
    await tick(60);
    expect(ui.stage.style.getPropertyValue("--eye-x"), "비밀번호를 치는 동안 눈이 따라다닌다").toBe(looksAway);
  });

  /* 정책이 뒤집혔다: 이 블록은 **없어야** 한다. 로그인 화면은 Jinja 라 SPA 의 theme.js
   * 전역 규칙이 안 닿으므로, 여기 한 줄이 남아 있으면 이 화면만 조용히 다시 굳는다. */
  it("login.css 에 애니메이션을 끄는 동작 줄이기 블록이 없다", () => {
    expect(LOGIN_CSS).not.toMatch(/@media\s*\(prefers-reduced-motion/);
  });

  it("clovi-login.js 에 동작 줄이기 판정이 없다 — 그 한 줄이 시선과 축포를 함께 끈다", () => {
    expect(CLOVI_JS).not.toMatch(/prefersReducedMotion|prefers-reduced-motion/);
  });
});

// ════════════════════════════════════════════════════════════════════════════
// 5. SPA 인계 — 첫 화면 위의 환영 연출
// ════════════════════════════════════════════════════════════════════════════
function renderHandoff(props) {
  return render(
    <ThemeModeProvider>
      <LoginHandoff {...props} />
    </ThemeModeProvider>
  );
}

function markHandoff(at = Date.now()) {
  window.sessionStorage.setItem(LOGIN_HANDOFF_KEY, String(at));
}

describe("SPA 인계 연출", () => {
  it("표식이 있으면 클로비와 환영 문구가 첫 화면 위에 뜬다", async () => {
    setMatchMedia({ reduce: false });
    markHandoff();

    renderHandoff({ ready: false });

    expect(screen.getByText("로그인되었습니다.")).toBeInTheDocument();
    expect(screen.getByText("업무 공간을 준비하고 있습니다.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "클로비가 인사합니다" })).toBeInTheDocument();
    // 폭죽 라이브러리는 **쏘는 순간에** 받는다(초기 번들에서 뺐다) — 정적 import 였을 때처럼
    // 같은 틱에 불리지 않는다. 연출 자체는 그대로 있다.
    await waitFor(() => expect(confettiMock).toHaveBeenCalled());
  });

  /* 🔴 **터졌는가**와 **보였는가**는 다른 사실이다.
   *
   * 위 시험은 confetti() 가 불렸다는 것만 본다. 그런데 이 판은 `inset: 0` 인 **불투명** 면이고
   * canvas-confetti 는 자기 캔버스를 `z-index: 100` 으로 만든다 — 판(modal+10 = 1310) 아래다.
   * 그래서 폭죽은 판 **뒤에서** 터지고 있었고, 코드도 시험도 초록인데 사람 눈에는 아무것도
   * 안 보였다. 사용자가 「로그인 이후 폭죽이 사라졌다」고 한 것이 그 상태다.
   *
   * 판이 걷힌 뒤에 보이지 않느냐 — 이 연출이 뜨는 자리는 언제나 차가운 첫 로드다. 인증
   * 조회와 라우트 청크가 늦으면 판은 상한(2.6초)까지 서 있고 폭죽 수명(160틱 ≈ 2.7초)이
   * 그 아래에서 다 지나간다. 그래서 층을 재는 이 시험이 필요하다. */
  it("폭죽이 환영 판보다 위에서 터진다 — 판 뒤에서 터지면 없는 것과 같다", async () => {
    setMatchMedia({ reduce: false });
    markHandoff();

    renderHandoff({ ready: false });
    await waitFor(() => expect(confettiMock).toHaveBeenCalled());

    // 판이 실제로 서는 층을 화면에서 읽는다 — 상수끼리 비교하면 판이 올라갈 때 같이
    // 안 따라와도 초록이다.
    const panelZ = Number(window.getComputedStyle(screen.getByRole("status")).zIndex);
    expect(Number.isFinite(panelZ), "판의 층을 못 읽었다").toBe(true);

    for (const [opts] of confettiMock.mock.calls) {
      // 층을 아예 안 주면 라이브러리 기본값 100 이다 — 판(1310) 한참 아래다.
      const z = typeof opts.zIndex === "number" ? opts.zIndex : 100;
      expect(z, `폭죽이 판(z-index ${panelZ}) 뒤 ${z} 에서 터진다 — 사람 눈에 안 보인다`)
        .toBeGreaterThan(panelZ);
    }
  });

  it("표식을 한 번 쓰면 지운다 — 새로고침마다 축하하지 않는다", async () => {
    setMatchMedia({ reduce: false });
    markHandoff();

    renderHandoff({ ready: false });
    await act(async () => { await tick(10); });

    expect(window.sessionStorage.getItem(LOGIN_HANDOFF_KEY)).toBeNull();
  });

  it("표식이 없으면 아무것도 뜨지 않는다", async () => {
    setMatchMedia({ reduce: false });

    renderHandoff({ ready: true });
    await act(async () => { await tick(10); });

    expect(screen.queryByText("로그인되었습니다.")).not.toBeInTheDocument();
    expect(confettiMock).not.toHaveBeenCalled();
  });

  it("오래된 표식은 무시한다 — 어제 로그인으로 오늘 축하하지 않는다", async () => {
    setMatchMedia({ reduce: false });
    markHandoff(Date.now() - HANDOFF_FRESH_MS - 1000);

    renderHandoff({ ready: true });
    await act(async () => { await tick(10); });

    expect(screen.queryByText("로그인되었습니다.")).not.toBeInTheDocument();
    expect(confettiMock).not.toHaveBeenCalled();
  });

  it("첫 화면이 준비되면 걷혀서 화면을 넘긴다", async () => {
    setMatchMedia({ reduce: false });
    markHandoff();

    const { rerender } = renderHandoff({ ready: false });
    expect(screen.getByText("로그인되었습니다.")).toBeInTheDocument();

    await act(async () => {
      rerender(
        <ThemeModeProvider>
          <LoginHandoff ready />
        </ThemeModeProvider>
      );
      await tick(900);
    });

    expect(screen.queryByText("로그인되었습니다.")).not.toBeInTheDocument();
  });

  it("첫 화면이 끝내 안 와도 상한에서 스스로 걷힌다", async () => {
    setMatchMedia({ reduce: false });
    markHandoff();

    renderHandoff({ ready: false });
    expect(screen.getByText("로그인되었습니다.")).toBeInTheDocument();

    await act(async () => { await tick(3200); });

    expect(screen.queryByText("로그인되었습니다.")).not.toBeInTheDocument();
  });
});

describe("동작 줄이기 설정과 무관한 SPA 인계 연출", () => {
  /* 정책이 뒤집혔다 (2026-09-03 — `ui/motion.js` 머리말): 동작 줄이기를 켠 화면에서도
   * 폭죽과 진행 막대가 그대로 있다. 정보가 같은 것은 예전과 같다. */
  it("폭죽도 진행 막대도 동작 줄이기와 무관하게 그대로 있다", async () => {
    setMatchMedia({ reduce: true });
    markHandoff();

    renderHandoff({ ready: false });
    await act(async () => { await tick(10); });

    expect(screen.getByText("로그인되었습니다.")).toBeInTheDocument();
    expect(screen.getByText("업무 공간을 준비하고 있습니다.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "클로비가 인사합니다" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    await waitFor(() => expect(confettiMock).toHaveBeenCalled());
  });

  it("기본 사용자에게는 진행 막대가 있다", async () => {
    setMatchMedia({ reduce: false });
    markHandoff();

    renderHandoff({ ready: false });

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("matchMedia 가 없는 환경에서도 예외 없이 뜬다", async () => {
    delete window.matchMedia;
    markHandoff();

    renderHandoff({ ready: false });

    expect(screen.getByText("로그인되었습니다.")).toBeInTheDocument();
  });
});
