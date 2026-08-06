import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
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
 *                                  동작 줄이기에서 시선 추적을 멈추기.
 *   2층 SPA 인계(React)         — 로그인 페이지가 남긴 표식을 받아 첫 화면까지 이어지는
 *                                  환영 연출(폭죽 + 클로비). 이 층이 "뚝 끊긴다" 를 메운다.
 *
 * 1층은 파일을 읽어 jsdom 에 그대로 올린다. 문자열 grep 이 아니라 **실제 동작**을 본다 —
 * 이 저장소는 "테스트가 헛것이었다" 를 여섯 번 겪었다(불변 규칙 4).
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

async function submitLogin(ui, { email = "hong@example.com", password = "pw123456" } = {}) {
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
    const ui = bootLoginPage({ reduce: true }); // 동작 줄이기 = 연출 대기 없음 → 바로 이동

    await submitLogin(ui);
    await tick(30);

    const raw = window.sessionStorage.getItem(LOGIN_HANDOFF_KEY);
    expect(raw).toBeTruthy();
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

  it("동작 줄이기를 켜면 눈이 움직이지 않는다", async () => {
    const ui = bootLoginPage({ reduce: true });

    await movePointerAndSettle();

    expect(ui.stage.style.getPropertyValue("--eye-x")).toBe("0px");
    // 표정과 말풍선(정보)은 그대로다. 끄는 것은 움직임이지 정보가 아니다.
    expect(ui.stage.dataset.state).toBe("idle");
    expect(ui.message.textContent).toBe("오늘 업무를 준비했어요");
  });

  it("login.css 가 동작 줄이기에서 애니메이션을 중립화한다", () => {
    // 이 화면에는 SPA 의 theme.js 전역 규칙이 닿지 않는다(Jinja 라 MUI 가 없다).
    // 그래서 같은 규칙이 이 파일에 따로 있어야 한다.
    const block = LOGIN_CSS.match(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*?\n\}/);
    expect(block, "login.css 에 동작 줄이기 블록이 없다").toBeTruthy();
    const body = block[0];
    expect(body).toMatch(/animation-duration:\s*[^;]*!important/);
    expect(body).toMatch(/animation-iteration-count:\s*1\s*!important/);
    expect(body).toMatch(/transition-duration:\s*[^;]*!important/);
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

    expect(screen.getByText("로그인되었습니다")).toBeInTheDocument();
    expect(screen.getByText("업무 공간을 준비하고 있습니다")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "클로비가 인사합니다" })).toBeInTheDocument();
    expect(confettiMock).toHaveBeenCalled();
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

    expect(screen.queryByText("로그인되었습니다")).not.toBeInTheDocument();
    expect(confettiMock).not.toHaveBeenCalled();
  });

  it("오래된 표식은 무시한다 — 어제 로그인으로 오늘 축하하지 않는다", async () => {
    setMatchMedia({ reduce: false });
    markHandoff(Date.now() - HANDOFF_FRESH_MS - 1000);

    renderHandoff({ ready: true });
    await act(async () => { await tick(10); });

    expect(screen.queryByText("로그인되었습니다")).not.toBeInTheDocument();
    expect(confettiMock).not.toHaveBeenCalled();
  });

  it("첫 화면이 준비되면 걷혀서 화면을 넘긴다", async () => {
    setMatchMedia({ reduce: false });
    markHandoff();

    const { rerender } = renderHandoff({ ready: false });
    expect(screen.getByText("로그인되었습니다")).toBeInTheDocument();

    await act(async () => {
      rerender(
        <ThemeModeProvider>
          <LoginHandoff ready />
        </ThemeModeProvider>
      );
      await tick(900);
    });

    expect(screen.queryByText("로그인되었습니다")).not.toBeInTheDocument();
  });

  it("첫 화면이 끝내 안 와도 상한에서 스스로 걷힌다", async () => {
    setMatchMedia({ reduce: false });
    markHandoff();

    renderHandoff({ ready: false });
    expect(screen.getByText("로그인되었습니다")).toBeInTheDocument();

    await act(async () => { await tick(3200); });

    expect(screen.queryByText("로그인되었습니다")).not.toBeInTheDocument();
  });
});

describe("동작 줄이기: SPA 인계 연출", () => {
  it("폭죽은 쏘지 않지만 같은 정보는 그대로 전한다", async () => {
    setMatchMedia({ reduce: true });
    markHandoff();

    renderHandoff({ ready: false });
    await act(async () => { await tick(10); });

    // 정보: 문구와 클로비는 기본 사용자와 똑같이 보인다.
    expect(screen.getByText("로그인되었습니다")).toBeInTheDocument();
    expect(screen.getByText("업무 공간을 준비하고 있습니다")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "클로비가 인사합니다" })).toBeInTheDocument();
    // 연출: 폭죽과 진행 막대(둘 다 움직임)는 없다.
    expect(confettiMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
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

    expect(screen.getByText("로그인되었습니다")).toBeInTheDocument();
  });
});
