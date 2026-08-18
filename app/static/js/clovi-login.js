"use strict";

/* 로그인 화면의 표현/애니메이션 계층 — 클로비(마스코트)의 8가지 상태.
 *
 * 출처: reference/approved-login-baseline/static-login/script.js (승인된 디자인 원본).
 * 상태 이름, 말풍선 문구, 고정 시선 좌표, 지속 시간은 원본 값 그대로다. 이 화면은
 * "가능하면 개선"의 대상이 아니다 — 옮기기만 한다.
 *
 * ── 이 파일이 하지 않는 것 ────────────────────────────────────────────────
 * 네트워크를 만지지 않는다. fetch, 오류 코드 해석, 리다이렉트, /readyz 프로브, mailto 조립은
 * 전부 login.js에 있고 그 파일이 실제 서버 계약(app/auth/router.py)을 담고 있다. 원본
 * script.js에도 데모용 authenticate()가 있었지만 그건 config.js와 함께 버렸다 — 두 파일이
 * 같은 요청을 각자 짜면 언젠가 서로 다른 계약을 말하게 된다.
 *
 * ── 두 파일의 접합부(seam) ────────────────────────────────────────────────
 * login.html이 login.js를 먼저, 이 파일을 나중에 싣는다. 같은 요소의 이벤트 리스너는
 * 등록 순서대로 실행되므로, 여기 submit 핸들러가 돌 때 login.js는 이미 판정을 끝냈다.
 * 그 판정을 DOM에서 읽는다 — 상태를 주고받는 별도 채널을 만들지 않는다:
 *
 *   event.defaultPrevented === false  login.js가 없거나 초기화에 실패했다. 네이티브 POST가
 *                                     나가는 중 → loading (화면은 곧 넘어간다).
 *   #login-submit[disabled]           login.js가 요청을 띄웠다 → loading.
 *   그 외                              login.js의 클라이언트 검증이 막았다 → error(650ms).
 *                                     어느 칸이 틀렸는지는 aria-invalid가 말한다.
 *   #login-error 내용이 채워짐         실패 응답이 왔다 → error(850ms) → idle.
 *   loading 중 문서가 떠남             성공해서 login.js가 이동시키는 중이다 → success(잠금).
 *                                     실패 경로는 절대 이동하지 않으므로 이 신호는 성공에만 뜬다.
 *   #login-submit[aria-busy]          제출 중 표현(스피너/화살표/토글 잠금)의 단일 출처.
 *
 * ── 테스트/통합용 훅 ──────────────────────────────────────────────────────
 * window.cloviLogin.setState(name) — 8가지 상태를 직접 지정한다. 원본에서도 'greeting'은
 * UI 트리거 없이 상태 기계 안에만 있던 상태다(문구와 CSS는 정의돼 있다). 없는 트리거를
 * 지어내지 않으려고 그대로 두고, 대신 상태 기계를 밖에서 구동할 수 있게만 열어 둔다.
 * tests/regression/test_login_visual_contract.py가 8가지 전부를 이 훅으로 고정한다.
 */

(function () {
  const form = document.getElementById("login-form");
  const email = document.getElementById("email");
  const password = document.getElementById("password");
  const toggle = document.getElementById("toggle-password");
  const submit = document.getElementById("login-submit");
  const submitLabel = document.getElementById("login-submit-label");
  const submitSpinner = submit ? submit.querySelector(".button-spinner") : null;
  const submitArrow = submit ? submit.querySelector(".button-arrow") : null;
  const errorBox = document.getElementById("login-error");
  const cloviStage = document.getElementById("clovi-stage");
  const cloviMessage = document.getElementById("clovi-message");

  // 클로비 스테이지가 없는 화면(좁은 폭에서 히어로가 숨는 것과는 다르다 — DOM 자체가 없는
  // 경우)에서는 아무것도 하지 않는다. 폼은 login.js만으로 완전히 동작한다.
  if (!form || !email || !password || !submit || !cloviStage) return;

  // 원본 script.js의 stateMessages 그대로.
  const STATE_MESSAGES = {
    idle: "오늘 업무를 준비했어요",
    welcome: "반가워요. 업무를 시작해 볼까요?",
    greeting: "안녕하세요. 무엇을 도와드릴까요?",
    email: "회사 계정을 확인하고 있어요",
    privacy: "비밀번호는 보지 않을게요",
    loading: "안전하게 로그인하고 있어요",
    success: "로그인이 완료됐어요",
    error: "입력 내용을 다시 확인해 주세요",
  };

  // 상태별 고정 시선. 숫자는 원본 그대로이며 의미가 있다 —
  // privacy의 -3.6은 "비밀번호를 치는 동안 일부러 딴 곳을 본다"는 표현이다.
  // 이 범위는 app/static/brand/login/mascot-lock.json의 maximumEyeOffsetCssPx(4.0 / 2.5)
  // 안에 있다. 그 밖으로 나가면 눈 픽셀이 캐노니컬 원화를 벗어난다.
  const FIXED_GAZE = {
    email: [3.8, 1.0],
    privacy: [-3.6, 0],
    loading: [0, 0],
    error: [-1.8, 1.6],
  };

  let cloviState = "welcome";
  let cloviTimer = 0;
  let pointerFrame = 0;
  let latestPointer = null;
  let successLocked = false;

  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  /* 동작 줄이기 판정 한 곳. 매번 다시 묻는다 — OS 설정은 페이지를 열어 둔 채로도 바뀐다.
   *
   * CSS 애니메이션은 login.css 의 @media 블록이 끈다. 그런데 **JS 가 켜는 움직임**에는
   * 그 규칙이 닿지 않는다: 포인터를 따라 눈이 계속 움직이는 것이 그것이다. 시선 추적은
   * transform 값을 초당 수십 번 바꾸는 것이라, 지속 시간을 0으로 만들어도 눈은 여전히
   * 화면 위를 돌아다닌다. 시작하지 않는 것 말고는 끄는 방법이 없다.
   *
   * matchMedia 가 없는 브라우저는 false 로 본다 — 여기서 예외가 나면 표현 계층 전체가
   * 죽어 스피너도 표정도 멈춘다. */
  const prefersReducedMotion = () => {
    try {
      return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (e) {
      return false;
    }
  };

  const clearCloviTimer = () => {
    if (cloviTimer) window.clearTimeout(cloviTimer);
    cloviTimer = 0;
  };

  const setEyeOffset = (x, y) => {
    cloviStage.style.setProperty("--eye-x", x + "px");
    cloviStage.style.setProperty("--eye-y", y + "px");
  };

  /* 시선이 포인터를 따라가는 상태.
   *
   * 로그인 화면이 쓰는 포즈 목록이다 — idle 과
   * welcome 둘이다. 나머지 상태에는 뜻이 있는 고정 좌표(FIXED_GAZE)가 있어서, 포인터가
   * 그걸 덮으면 "비밀번호를 안 본다" 같은 표현이 마우스 위치에 따라 깨진다.
   *
   * welcome 이 여기 있는 이유: 등장 인사 780ms 동안에도 사람은 이미 마우스를 움직인다.
   * 그 사이 눈이 굳어 있으면 첫인상이 "안 움직이는 그림"이 된다. */
  const POINTER_TRACKED_STATES = ["idle", "welcome"];
  const tracksPointer = (state) => POINTER_TRACKED_STATES.indexOf(state) !== -1;

  const applyFixedGaze = (state) => {
    if (FIXED_GAZE[state]) setEyeOffset(FIXED_GAZE[state][0], FIXED_GAZE[state][1]);
    else if (!latestPointer || !tracksPointer(state)) setEyeOffset(0, 0);
  };

  const setCloviState = (nextState, options) => {
    const opts = options || {};
    clearCloviTimer();
    cloviState = nextState;
    cloviStage.dataset.state = nextState;
    if (cloviMessage) {
      cloviMessage.textContent = opts.message || STATE_MESSAGES[nextState] || STATE_MESSAGES.idle;
    }
    applyFixedGaze(nextState);
    if (opts.duration) {
      cloviTimer = window.setTimeout(function () {
        cloviTimer = 0;
        // after는 문자열이거나, 만료 시점에 판단해야 하는 함수다(restingState 참고).
        setCloviState(typeof opts.after === "function" ? opts.after() : opts.after || "idle");
      }, opts.duration);
    }
  };

  // ── 시선 추적 ─────────────────────────────────────────────────────────────
  const resetPointerTracking = () => {
    latestPointer = null;
    applyFixedGaze(cloviState);
  };

  const renderPointer = () => {
    pointerFrame = 0;
    if (!latestPointer || !tracksPointer(cloviState)) return;
    const rect = cloviStage.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height * 0.27;
    const normalizedX = clamp((latestPointer.x - centerX) / Math.max(window.innerWidth * 0.44, 1), -1, 1);
    const normalizedY = clamp((latestPointer.y - centerY) / Math.max(window.innerHeight * 0.48, 1), -1, 1);
    setEyeOffset((normalizedX * 4).toFixed(2), (normalizedY * 2.5).toFixed(2));
  };

  const handlePointerMove = (event) => {
    // 동작 줄이기를 켠 사용자에게는 시선을 아예 움직이지 않는다. 표정(data-state)과 말풍선은
    // 그대로 바뀌므로 전해지는 정보는 같다 — 끄는 것은 움직임이지 정보가 아니다.
    if (prefersReducedMotion()) return;
    // 터치는 제외한다 — 탭할 때마다 눈이 순간이동하고, 히어로는 좁은 화면에서 숨는다.
    if (event.pointerType && ["mouse", "pen"].indexOf(event.pointerType) === -1) return;
    latestPointer = { x: event.clientX, y: event.clientY };
    if (!pointerFrame) pointerFrame = window.requestAnimationFrame(renderPointer);
  };

  // ── 제출 중 표현 ──────────────────────────────────────────────────────────
  // 단일 출처는 login.js가 #login-submit에 거는 aria-busy다. 여기서 상태를 따로 기억하면
  // 두 파일이 어긋났을 때 스피너가 영원히 도는 화면이 남는다.
  const applyBusyPresentation = (busy) => {
    const locked = busy || successLocked;
    if (submitSpinner) submitSpinner.hidden = !busy;
    if (submitArrow) submitArrow.hidden = locked;
    if (toggle) toggle.disabled = locked;
    email.readOnly = locked;
    password.readOnly = locked;
    form.setAttribute("aria-busy", String(!!busy));
  };

  const isBusy = () => submit.getAttribute("aria-busy") === "true";

  // ── aria-invalid → .invalid ───────────────────────────────────────────────
  // login.js는 접근성 신호(aria-invalid)만 건다. 원본 디자인의 붉은 테두리는 .invalid에
  // 걸려 있으므로 둘을 붙여, 스크린리더가 듣는 것과 눈에 보이는 것이 항상 같게 한다.
  const syncInvalid = (input) => {
    const wrap = input.closest(".input-wrap");
    if (wrap) wrap.classList.toggle("invalid", input.getAttribute("aria-invalid") === "true");
  };

  const invalidObserver = new MutationObserver(function (records) {
    for (let i = 0; i < records.length; i += 1) syncInvalid(records[i].target);
  });
  invalidObserver.observe(email, { attributes: true, attributeFilter: ["aria-invalid"] });
  invalidObserver.observe(password, { attributes: true, attributeFilter: ["aria-invalid"] });

  // ── 포커스 → 표정 ─────────────────────────────────────────────────────────
  email.addEventListener("focus", function () {
    if (!submit.disabled && !successLocked) setCloviState("email");
  });
  email.addEventListener("blur", function () {
    if (!submit.disabled && cloviState === "email") setCloviState("idle");
  });
  password.addEventListener("focus", function () {
    if (!submit.disabled && !successLocked) setCloviState("privacy");
  });
  password.addEventListener("blur", function () {
    if (!submit.disabled && cloviState === "privacy") setCloviState("idle");
  });

  // ── 제출 ──────────────────────────────────────────────────────────────────
  form.addEventListener("submit", function (event) {
    if (successLocked) return;

    if (!event.defaultPrevented) {
      // login.js가 preventDefault를 하지 않았다 = 그 파일이 실행되지 않았거나 초기화에
      // 실패했다. 브라우저가 <form action="/login" method="post">를 네이티브로 보내는
      // 중이고 화면은 곧 넘어간다. 표정만 맞춰 두고 아무것도 막지 않는다.
      setCloviState("loading");
      return;
    }

    if (submit.disabled) {
      // login.js가 요청을 띄웠다. 원본과 같이 비밀번호가 보이는 상태였으면 다시 감춘다
      // (login.js가 이미 값을 읽어 본문을 만든 뒤라 안전하다). 토글의 라벨/aria는
      // login.js의 어휘("표시"/"숨김")로 되돌려 다음 클릭이 어긋나지 않게 한다.
      if (password.type === "text") {
        password.type = "password";
        if (toggle) {
          toggle.textContent = "표시";
          toggle.setAttribute("aria-label", "비밀번호 표시");
          toggle.setAttribute("aria-pressed", "false");
        }
      }
      applyBusyPresentation(true);
      setCloviState("loading");
      return;
    }

    // 여기까지 왔으면 login.js의 클라이언트 검증이 막은 것이다(빈 값 / 이메일 형식).
    // 원본과 같이 650ms 동안 error를 보인 뒤 문제가 있던 칸의 표정으로 돌아간다 —
    // login.js가 이미 그 칸으로 초점을 옮겨 놓았다.
    const emailInvalid = email.getAttribute("aria-invalid") === "true";
    setCloviState("error", { duration: 650, after: emailInvalid ? "email" : "privacy" });
  });

  // ── 결과 ──────────────────────────────────────────────────────────────────
  // 실패: login.js가 #login-error를 채운다(서버 메시지 또는 연결 실패 문구).
  // 매 제출 시작에 같은 요소를 빈 문자열로 지우므로, 채워질 때만 반응한다.
  const errorObserver = errorBox
    ? new MutationObserver(function () {
        if (successLocked) return;
        if (cloviState !== "loading") return;
        if (!errorBox.textContent.trim()) return;
        applyBusyPresentation(false);
        setCloviState("error", { message: "연결 상태를 다시 확인해 주세요", duration: 850, after: "idle" });
      })
    : null;
  if (errorObserver && errorBox) {
    errorObserver.observe(errorBox, { childList: true, characterData: true, subtree: true });
  }

  // 제출 중 표현은 aria-busy를 따라간다(쿨다운처럼 버튼만 잠긴 상태와 구분된다).
  const busyObserver = new MutationObserver(function () {
    if (successLocked) return;
    applyBusyPresentation(isBusy());
  });
  busyObserver.observe(submit, { attributes: true, attributeFilter: ["aria-busy"] });

  // 성공: login.js가 window.location.href로 이동시킨다. 실패 경로는 절대 이동하지 않으므로
  // "loading 중에 문서가 떠난다"는 것은 곧 성공을 뜻한다. 브라우저는 다음 문서가 그려지기
  // 전까지 이 화면을 계속 보여 주므로 성공 표정과 배지가 실제로 보인다.
  const markSuccess = () => {
    if (successLocked || cloviState !== "loading") return;
    successLocked = true;
    if (submitSpinner) submitSpinner.hidden = true;
    if (submitArrow) submitArrow.hidden = true;
    if (submitLabel) submitLabel.textContent = "로그인 완료";
    setCloviState("success");
  };
  // 문서가 떠날 때도 성공 표정으로 바꾼다 — 아래 celebrate() 를 못 부른 경로
  // (다른 탭에서 로그인, 스크립트 오류 등)에서도 마지막 모습이 '로딩 중'으로 남지 않게.
  window.addEventListener("beforeunload", markSuccess);

  /* 성공 연출을 **끝까지 보여 주고** 알린다 (사용자 지적 P1).
   *
   * 예전에는 `beforeunload` 만 걸려 있었다. 그때는 이미 브라우저가 다음 문서를 가지러 간
   * 뒤라, 760ms 짜리 `eye-success` 와 배지가 뜨자마자 화면이 갈렸다 — 사용자가
   * "로그인 이후 축하 애니메이션이 사라졌다" 고 한 것이 이것이다.
   *
   * 그래서 `login.js` 가 이동 **전에** 이걸 부르고 기다린다. 반환 promise 는 애니메이션
   * 길이(760ms)와 여유를 더한 뒤 resolve 한다.
   *
   * 동작 줄이기(prefers-reduced-motion)를 켠 사용자에게는 기다리지 않는다 — 그 설정의 뜻은
   * "연출을 보고 싶지 않다" 이므로, 보여 주지도 않으면서 붙잡아 두면 그냥 느린 로그인이다. */
  const CELEBRATE_MS = 900;
  const celebrate = () => {
    markSuccess();
    if (prefersReducedMotion()) return Promise.resolve();
    return new Promise((resolve) => window.setTimeout(resolve, CELEBRATE_MS));
  };

  // ── 주변 동작 ─────────────────────────────────────────────────────────────
  window.addEventListener("pointermove", handlePointerMove, { passive: true });
  document.addEventListener("mouseleave", resetPointerTracking);
  window.addEventListener("blur", resetPointerTracking);
  document.addEventListener("visibilitychange", function () {
    // 보이지 않는 탭에서 눈 애니메이션이 계속 돌면 배터리만 먹는다(auth.css의 .is-paused).
    document.body.classList.toggle("is-paused", document.hidden);
    if (document.hidden) resetPointerTracking();
  });

  /* 등장: 780ms 동안 welcome 인사를 하고 idle 로 내려간다.
   *
   * 한동안 여기서 activeElement를 보고 email/privacy로 내려앉게 했었다 — 이 저장소의
   * login.js가 넓은 화면(≥1024px)에서 첫 칸에 초점을 주기 때문에, "이메일에 초점이 가면
   * email 표정"이라는 규칙을 맞추려던 것이다. 그런데 email에는 고정 시선(3.8, 1.0)이 있어서
   * 시선 추적이 아예 시작되지 않았다. 사용자가 본 화면이 그것이다 —
   * "접속한 이후에 그냥 마우스를 옮기면 움직이지 않음. 한번 눌러야 눈이 움직임"
   * (그 클릭은 이메일 칸의 초점을 떼는 클릭이었다).
   *
   * 규칙의 출처는 초점 **이벤트**다. 스크립트가 대신 준 초점은 사용자가 그 칸을 고른 것이
   * 아니므로 표정을 바꾸지 않는다. 사용자가 실제로 칸을 고르면 focus 리스너가 잡는다. */
  setCloviState("welcome", { duration: 780, after: "idle" });

  window.addEventListener(
    "pagehide",
    function () {
      markSuccess();
      clearCloviTimer();
      if (pointerFrame) window.cancelAnimationFrame(pointerFrame);
      invalidObserver.disconnect();
      busyObserver.disconnect();
      if (errorObserver) errorObserver.disconnect();
    },
    { once: true },
  );

  // 상태 기계를 밖에서 구동하기 위한 최소한의 훅. 화면 동작을 바꾸지 않는다 —
  // 'greeting'처럼 원본에도 UI 트리거가 없던 상태를 회귀 테스트가 고정할 수 있게 한다.
  window.cloviLogin = {
    states: Object.keys(STATE_MESSAGES),
    getState: function () { return cloviState; },
    setState: function (name, options) { setCloviState(name, options); },
    // login.js 가 이동 직전에 부른다. 연출이 끝나면 resolve 하는 promise 를 돌려준다.
    celebrate: celebrate,
  };
})();
