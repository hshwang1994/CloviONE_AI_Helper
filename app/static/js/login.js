"use strict";

(function () {
  const form = document.getElementById("login-form");
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");
  const errorBox = document.getElementById("login-error");
  const submitButton = document.getElementById("login-submit");
  const submitLabel = document.getElementById("login-submit-label");
  const submitLabelDefault = submitLabel ? submitLabel.textContent : "";
  const toggleButton = document.getElementById("toggle-password");
  const serverStatus = document.getElementById("server-status");

  const capsHint = document.getElementById("caps-hint");
  const loginHint = document.getElementById("login-hint");
  const hintSupportEmail = loginHint ? loginHint.getAttribute("data-support-email") : "";
  // 세션 만료로 튕겨나오기 전에 있던 화면(app/main.py PageAuthRequired → login.html hidden
  // input). 있으면 로그인 성공 후 '/' 대신 그리로 돌아간다.
  const nextInput = document.getElementById("login-next");

  // 핵심 요소가 하나라도 없으면(템플릿 편집으로 id가 사라진 경우) 여기서 예외가 나 submit
  // 핸들러가 바인딩되지 않고, 전 사용자가 원시 JSON 네이티브 폴백으로 떨어진다. 조용히
  // 죽지 않고 알린 뒤 멈춘다. errorBox도 이 크리티컬 목록에 넣는다 — submit 핸들러 안에서
  // errorBox.textContent가 8곳 넘게 무조건 참조되므로, errorBox만 없어져도(다른 필드는
  // 멀쩡해도) 첫 제출 시 바로 예외가 나 폼이 죽는다. 여기서 없으면 알릴 방법이 없으니
  // (그 자신이 알림 채널) 그냥 조용히 멈춘다.
  if (!form || !emailInput || !passwordInput || !submitButton || !errorBox) {
    if (errorBox) {
      errorBox.textContent = "로그인 폼을 초기화하지 못했습니다. 페이지를 새로고침해 주세요.";
    }
    return;
  }

  // 선택적 요소는 없을 수도 있으므로 각각 guard한다(단일 누락이 로그인 전체를 막지 않게).
  if (toggleButton) {
    toggleButton.addEventListener("click", function () {
      const hidden = passwordInput.type === "password";
      passwordInput.type = hidden ? "text" : "password";
      toggleButton.textContent = hidden ? "숨김" : "표시";
      toggleButton.setAttribute("aria-label", hidden ? "비밀번호 숨김" : "비밀번호 표시");
      // 라벨 텍스트만으로는 보조기술에 '지금 눌린 상태'가 프로그램적으로 전달되지 않는다
      // (라벨 재낭독에 의존). 토글 버튼의 표준 상태 신호인 aria-pressed를 함께 준다.
      toggleButton.setAttribute("aria-pressed", hidden ? "true" : "false");
      // 토글을 누르면 초점이 이 버튼으로 옮겨져 키보드/스크린리더 사용자가 비밀번호
      // 칸의 편집 위치를 잃는다 — 표시 상태만 바꾸고 초점은 다시 입력 칸으로 되돌린다.
      passwordInput.focus();
    });
  }

  // Caps Lock이 켜진 채 입력하면 대부분 '비밀번호가 틀렸다'로만 보고되어 원인을 모른다.
  // 켜져 있을 때만 힌트를 보인다(getModifierState 미지원 브라우저는 조용히 무시).
  // role="status" 라이브 리전은 hidden/visibility 토글이 아니라 '내용 변화'에만 낭독한다 —
  // 정적 텍스트의 hidden만 껐다 켜면 스크린리더가 캡스락 경고를 읽지 않는다(round30 감사 E).
  // 상태가 실제로 바뀔 때만 내용을 갱신해 키 입력마다 반복 낭독되지 않게 한다. 빈 상태도
  // .caps-hint의 min-height로 자리를 유지하므로 레이아웃은 튀지 않는다.
  const CAPS_MESSAGE = "캡스락이 켜져 있습니다.";
  function setCapsHint(on) {
    if (!capsHint) return;
    capsHint.hidden = false;
    const next = on ? CAPS_MESSAGE : "";
    if (capsHint.textContent !== next) capsHint.textContent = next;
  }
  function updateCaps(event) {
    if (!capsHint || typeof event.getModifierState !== "function") return;
    setCapsHint(event.getModifierState("CapsLock"));
  }
  passwordInput.addEventListener("keydown", updateCaps);
  passwordInput.addEventListener("keyup", updateCaps);
  passwordInput.addEventListener("blur", function () {
    setCapsHint(false);
  });
  // 위 리스너는 비밀번호 칸에 포커스가 있을 때 키 입력이 있어야만 감지한다. 다른 필드
  // (예: 이메일)에 포커스가 있는 동안 Caps Lock을 켰다가 그대로 Tab으로 비밀번호 칸에
  // 들어가 아무 키도 누르지 않고 제출하면 힌트가 절대 뜨지 않는다. 문서 전체 keyup에서
  // 마지막으로 알려진 상태를 기록해 두고, 비밀번호 칸이 포커스를 받는 순간 적용한다.
  let lastCapsLockState = null;
  document.addEventListener("keyup", function (event) {
    if (typeof event.getModifierState !== "function") return;
    lastCapsLockState = event.getModifierState("CapsLock");
  });
  passwordInput.addEventListener("focus", function () {
    if (!capsHint || lastCapsLockState === null) return;
    setCapsHint(lastCapsLockState);
  });

  // 실패 표식(aria-invalid)은 다음 제출 시작 시점에만 지워졌다 — 사용자가 이미 값을
  // 고쳤는데도 다시 제출하기 전까지 스크린리더가 계속 '유효하지 않음'으로 읽었다.
  // 다시 입력을 시작하는 즉시 지운다.
  function clearInvalidOnEdit(input) {
    input.addEventListener("input", function () {
      if (input.getAttribute("aria-invalid") === "true") {
        input.removeAttribute("aria-invalid");
      }
    });
  }
  clearInvalidOnEdit(emailInput);
  clearInvalidOnEdit(passwordInput);

  // 정적 autofocus를 대신한다 — 좁은(모바일) 화면에서는 초점을 주지 않아 로드 즉시
  // 소프트 키보드가 떠 레이아웃이 튀는 일을 막고, 넓은 화면에서만 첫 칸에 초점을 준다.
  // 이미 이메일이 채워져 있으면(no-JS 폴백 재렌더) 비밀번호 칸으로 초점을 옮긴다.
  try {
    if (window.matchMedia && window.matchMedia("(min-width: 1024px)").matches) {
      (emailInput.value ? passwordInput : emailInput).focus();
    }
  } catch (e) {
    // matchMedia 미지원 등 예외는 조용히 무시(초점만 못 줄 뿐 폼은 정상 동작).
  }

  // 서버 상태: 정상은 조용히, 오류만 눈에 띄게(상태 클래스로 CSS가 색을 정한다).
  // 이 페이지 자체가 같은 FastAPI 앱이 서빙하므로 화면이 떴다면 서버는 이미 살아 있다 —
  // '서버 연결 정상'을 늘 띄우면 아무 정보도 없이 자리만 차지한다. 정상은 비운다.
  function setServerStatus(text, isError) {
    if (!serverStatus) return;
    serverStatus.textContent = text;
    serverStatus.classList.toggle("is-error", !!isError);
  }
  // 이 페이지를 같은 FastAPI 앱이 방금 서빙했으므로 서버는 이미 살아 있다 — 일시적 blip
  // 하나로 '연결할 수 없습니다'를 띄우면 방금 뜬 화면과 모순된다. 한 번 재시도한 뒤에도
  // 실패할 때만, 그것도 부드러운 문구로 알린다.
  function probeHealth(retry) {
    // /healthz는 프로세스 liveness만 본다(DB 미확인, 항상 200) — DB가 죽어 로그인이 실제로
    // 안 되는 상황에서도 조용히 "정상"으로 보였다. /readyz(app/health/router.py)가 DB
    // 연결까지 확인해 503을 낸다 — 로그인 경로가 실제로 쓸 준비가 됐는지를 반영한다.
    fetch("/readyz")
      .then(function (r) {
        if (r.ok) { setServerStatus("", false); return; }
        if (retry) { window.setTimeout(function () { probeHealth(false); }, 1500); return; }
        setServerStatus("서버 응답이 느립니다. 잠시 후 다시 시도하세요.", true);
      })
      .catch(function () {
        if (retry) { window.setTimeout(function () { probeHealth(false); }, 1500); return; }
        setServerStatus("서버 응답이 느립니다. 잠시 후 다시 시도하세요.", true);
      });
  }
  // /readyz는 매 요청 새 DB 세션 + SELECT 1을 연다 — 익명 GET /login 렌더마다 이를
  // 태우면 WAL 쓰기 경합 중엔 이 페이지가 실제로는 멀쩡한데도 '느립니다'가 뜬다.
  // 로드 시엔 조용히 두고(이 페이지를 방금 서빙했으니 서버는 이미 살아 있다), 실제
  // 제출이 연결 문제로 실패했을 때만 늦게 한 번 확인한다.

  // 로그인 실패 응답 중 한국어 사용자 메시지가 확실한 코드만 그대로 보여준다. 5xx는
  // 영어 기본 메시지('Internal server error')를 실어 오므로(core/errors.py) 한국어 화면에
  // 영어가 새지 않도록 일반 문구로 대체한다.
  const KNOWN_ERROR_CODES = {
    invalid_credentials: true,
    account_locked: true,
    account_disabled: true,
    account_archived: true,
    rate_limited: true,
    validation_error: true,
    origin_mismatch: true,
  };
  // 눈에 띄는 오타(공백 포함, @ 누락)는 왕복 전에 잡아 준다. 서버(normalize_email)가 최종
  // 권한이다 — 사내망은 점 없는 내부 주소(user@host)도 유효하므로 도메인의 점은 강요하지 않는다.
  const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+$/;

  // account_disabled/archived는 '비밀번호를 잊으셨나요?' 안내로는 해결되지 않는다 —
  // 비밀번호는 맞았는데 계정 자체가 관리자 조치 없이는 안 풀린다. account_locked는 이
  // 둘과 다르다 — errorBox에 이미 뜬 AccountLockedError 메시지("약 N분 후 다시
  // 시도하거나...")가 말하듯 시간이 지나면 스스로 풀리는 일시적 잠금이다. 예전엔 세
  // 코드를 모두 '관리자가 확인 후 복구합니다'로 묶어, 바로 위 배너의 '잠시 후 다시
  // 시도하세요'와 서로 다른 말을 하는 것처럼 읽혔다(round28 감사 E). login.html은
  // no-JS 폴백(서버 재렌더) 때만 error_code로 같은 세 갈래를 고른다 — JS가 도는 정상
  // 경로에선 이 함수가 같은 판단을 한다.
  const ACCOUNT_ISSUE_CODES = { account_disabled: true, account_archived: true };
  // §2 규칙 6: innerHTML에 데이터를 넣지 않는다. 링크가 필요해 textContent 하나로는 못
  // 만들지만, 값(hintSupportEmail)은 브랜딩 설정값이지 사용자 입력이 아니고 그마저도
  // DOM API(createElement/createTextNode)로만 조립한다 — innerHTML 경로를 타지 않는다.
  function setLoginHint(code) {
    if (!loginHint) return;
    loginHint.textContent = "";
    const isLocked = code === "account_locked";
    const isAccountIssue = !!ACCOUNT_ISSUE_CODES[code];
    if (isLocked) {
      // 위 배너가 이미 안내한 대기 시간이 지나면 다시 로그인할 수 있다 — 관리자 개입을
      // 요구하지 않는다. 그래도 급한 경우에만 문의 수단을 보조로 덧붙인다.
      loginHint.appendChild(document.createTextNode(
        "이 잠금은 시간이 지나면 자동으로 풀립니다. 위에 안내된 시간 후 다시 로그인해 보세요."
      ));
      if (hintSupportEmail) {
        loginHint.appendChild(document.createTextNode(" 급하면 "));
        const a = document.createElement("a");
        // 주소는 인코딩하지 않는다 — encodeURIComponent가 '@'를 %40으로 바꾸면 일부
        // 메일 클라이언트가 mailto를 못 연다(RFC 6068). 쿼리(subject)만 인코딩한다.
        a.href = "mailto:" + hintSupportEmail + "?subject=" + encodeURIComponent("계정 문의");
        const strong = document.createElement("strong");
        strong.textContent = "관리자에게 문의";
        a.appendChild(strong);
        loginHint.appendChild(a);
        loginHint.appendChild(document.createTextNode("하세요."));
      }
      return;
    }
    loginHint.appendChild(document.createTextNode(
      isAccountIssue ? "계정 접근에 문제가 있습니다. " : "비밀번호를 잊으셨나요? "
    ));
    if (hintSupportEmail) {
      const a = document.createElement("a");
      const subject = isAccountIssue ? "계정 문의" : "비밀번호 재발급 요청";
      // 주소는 인코딩하지 않는다(RFC 6068) — 쿼리(subject)만 인코딩한다.
      a.href = "mailto:" + hintSupportEmail + "?subject=" + encodeURIComponent(subject);
      const strong = document.createElement("strong");
      strong.textContent = isAccountIssue ? "관리자에게 문의" : "관리자에게 재발급 요청";
      a.appendChild(strong);
      loginHint.appendChild(a);
      loginHint.appendChild(document.createTextNode(
        isAccountIssue ? "해 확인을 요청하세요." : "하면 임시 비밀번호로 다시 로그인할 수 있습니다."
      ));
    } else {
      const strong = document.createElement("strong");
      strong.textContent = "시스템 관리자";
      loginHint.appendChild(strong);
      // 계정 문의 분기도 비밀번호 재발급 분기와 같은 이유로 수동태를 쓴다 — support_email이
      // 없으면 누를 연락 수단이 아예 없는데 '문의하세요'는 갈 곳 없는 지시가 된다
      // (login.html의 같은 분기와 문구를 맞춘다).
      loginHint.appendChild(document.createTextNode(
        isAccountIssue ? "가 확인 후 계정을 복구합니다." : "가 임시 비밀번호를 재발급해 드립니다."
      ));
    }
  }

  // 로그인 요청이 응답 없이 멈추면(연결은 수립됐으나 무응답) 버튼이 '로그인 중…'으로 영영
  // 멈춘다. 타임아웃으로 중단해 사용자가 다시 시도할 수 있게 한다.
  // 성공 연출을 기다리는 상한. 이보다 오래 걸리면 연출을 포기하고 이동한다 —
// 로그인이 애니메이션 때문에 늦어지는 일은 없어야 한다.
const CELEBRATE_CAP_MS = 1200;
const SUBMIT_TIMEOUT_MS = 15000;

  /* 첫 화면까지 연출을 잇는 인계 표식.
   *
   * 로그인은 서버 렌더 페이지이고 다음 화면은 SPA 라, 성공하면 브라우저가 문서를 통째로
   * 갈아 끼운다 — 클로비가 웃는 순간 화면이 하얗게 비고, 인증 조회와 라우트 청크를 받는
   * 동안 아무 말이 없다. 그 빈자리를 SPA 쪽(frontend/src/app/LoginHandoff.jsx)이 이어받게
   * 이동 직전에 시각 하나를 남긴다.
   *
   * 값은 시각 하나뿐이다. 사용자 정보를 여기 담지 않는다 — sessionStorage 는 같은 탭의
   * 어떤 스크립트도 읽을 수 있고, 신원은 /api/me 가 쿠키로 확인해 주는 것이지 이 표식이
   * 증명하는 것이 아니다. SPA 는 이 값을 신선도 판단에만 쓴다.
   *
   * 키 문자열은 LoginHandoff.jsx 와 한 벌이다. 한쪽만 바꾸면 조용히 끊기므로
   * frontend/src/screens/login-first-impression.test.jsx 가 두 값이 같은지 확인한다. */
  const HANDOFF_KEY = "clovirone_login_welcome";
  function markLoginHandoff() {
    try {
      window.sessionStorage.setItem(HANDOFF_KEY, String(Date.now()));
    } catch (e) {
      // 시크릿 모드/저장소 차단 — 연출만 없고 로그인은 그대로 끝난다.
    }
  }

  // 429(rate_limited) 직후 버튼을 즉시 다시 눌러 한도를 재차 건드리지 않도록 짧은 쿨다운.
  let cooldownTimer = null;
  function startCooldown(seconds) {
    let remaining = seconds;
    submitButton.disabled = true;
    if (submitLabel) submitLabel.textContent = remaining + "초 후 재시도";
    cooldownTimer = window.setInterval(function () {
      remaining -= 1;
      if (remaining <= 0) {
        window.clearInterval(cooldownTimer);
        cooldownTimer = null;
        submitButton.disabled = false;
        if (submitLabel) submitLabel.textContent = submitLabelDefault;
      } else if (submitLabel) {
        submitLabel.textContent = remaining + "초 후 재시도";
      }
    }, 1000);
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    errorBox.textContent = "";
    // 오류 표식은 매 시도 시작에 지운다 — 스크린리더가 이전 오류 상태를 물고 있지 않게.
    emailInput.removeAttribute("aria-invalid");
    passwordInput.removeAttribute("aria-invalid");
    // novalidate라 브라우저 필수검사가 꺼져 있다 — 빈 값은 왕복 없이 즉시 막고 초점을 옮긴다.
    const emailValue = emailInput.value.trim();
    if (!emailValue || !passwordInput.value) {
      errorBox.textContent = "이메일과 비밀번호를 입력하세요.";
      const missing = !emailValue ? emailInput : passwordInput;
      missing.setAttribute("aria-invalid", "true");
      missing.focus();
      return;
    }
    if (!EMAIL_SHAPE.test(emailValue)) {
      errorBox.textContent = "이메일 주소 형식이 올바르지 않습니다.";
      emailInput.setAttribute("aria-invalid", "true");
      emailInput.focus();
      return;
    }
    submitButton.disabled = true;
    submitButton.setAttribute("aria-busy", "true");
    if (submitLabel) submitLabel.textContent = "로그인 중…";
    // 성공 시 window.location.href로 넘어가는 동안 finally가 라벨을 되돌려 깜빡이지
    // 않도록, 리다이렉트 직전 이 플래그를 세운다.
    let navigating = false;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(function () { controller.abort(); }, SUBMIT_TIMEOUT_MS);
    try {
      const response = await fetch("/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: emailInput.value.trim(),
          password: passwordInput.value,
          next: nextInput ? nextInput.value : undefined,
        }),
        signal: controller.signal,
      });
      let parseFailed = false;
      const data = await response.json().catch(function () { parseFailed = true; return null; });
      if (response.ok && data && data.ok) {
        // must_change_password가 next보다 항상 우선한다(서버가 이미 그렇게 정리해 next를
        // null로 돌려주지만, 방어적으로 여기서도 같은 순서를 지킨다).
        navigating = true;
        // 성공 연출을 **끝까지 보여 준 뒤** 이동한다(사용자 지적 P1). 예전에는 여기서 바로
        // 넘어가서, 클로비의 성공 표정과 배지가 뜨자마자 화면이 갈렸다.
        // clovi-login.js 가 없거나(스크립트 차단) 오래 걸려도 로그인이 막히면 안 되므로
        // 최대 대기 시간을 두고 경주시킨다 — 연출은 있으면 좋은 것이지 필수가 아니다.
        const target = data.must_change_password ? "/change-password" : (data.next || "/");
        const celebrate = window.cloviLogin && window.cloviLogin.celebrate
          ? window.cloviLogin.celebrate()
          : Promise.resolve();
        await Promise.race([
          celebrate,
          new Promise(function (resolve) { window.setTimeout(resolve, CELEBRATE_CAP_MS); }),
        ]);
        // 비밀번호 강제 변경은 축하할 자리가 아니다 — 그 사람은 아직 업무 공간에 들어온
        // 게 아니고, 다음 화면도 SPA 가 아니라 별도 페이지라 받아 줄 쪽이 없다.
        if (!data.must_change_password) markLoginHandoff();
        window.location.href = target;
        return;
      }
      const code = data && data.error && data.error.code;
      if (parseFailed) {
        // JSON 파싱 자체가 실패했다는 것은 FastAPI의 오류 핸들러가 아니라 그 앞단
        // (nginx 502/504 HTML 오류 페이지 등)에서 응답이 만들어졌다는 뜻이다 — 이건
        // '자격 증명이 틀렸다'는 일반 실패와 원인이 다르므로 구분되는 문구를 보인다.
        errorBox.textContent = "서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.";
        // 연결 계층 실패 — 이제서야 준비 상태를 늦게 확인한다(로드 시엔 안 한다).
        probeHealth(true);
      } else {
        errorBox.textContent =
          (code && KNOWN_ERROR_CODES[code] && data.error.message) || "로그인에 실패했습니다.";
      }
      // 자격 증명이 실제로 틀렸을 때만 두 필드를 aria-invalid로 표시한다. 계정 잠금·
      // 비활성·보관·요청 제한·origin 불일치는 이미 자격 증명 확인 이후에만 나는 오류라
      // (router.py) 입력값 자체는 틀리지 않았다 — 그 경우까지 '입력이 잘못됐다'고
      // 알리면 스크린리더 사용자에게 사실과 다른 신호를 준다.
      // validation_error도 이메일/비밀번호가 (서버 기준으로) 비어 있었다는 뜻이라 두 칸
      // 모두 실제로 값이 잘못됐다 — invalid_credentials와 같은 신호를 준다. 자동완성
      // 이상 동작 등으로 클라이언트측 빈값 검사를 우회해도 이 경로에서 잡힌다.
      if (!parseFailed && (!code || code === "invalid_credentials" || code === "validation_error")) {
        emailInput.setAttribute("aria-invalid", "true");
        passwordInput.setAttribute("aria-invalid", "true");
      }
      // 계정 잠금/비활성/보관은 위와 별개로 도움말 문구 자체를 계정 문의용으로 바꿔야
      // 사용자가 다음에 뭘 해야 하는지 안다(비밀번호 재발급 안내로는 못 푸는 문제).
      setLoginHint(code);
      // 실패 시 키보드 초점을 이메일로 되돌려 바로 다시 시도할 수 있게 한다.
      emailInput.focus();
      // 429 직후 즉시 재시도해 한도를 재차 건드리지 않도록 짧은 쿨다운을 건다. 서버가
      // 실제 리미터 상태로 계산한 대기 시간(retry_after_seconds)을 우선 쓰고, 없을 때만
      // (구버전 서버 등) 15초 추정값으로 대체한다 — 리미터를 재조정해도 화면이 안 어긋난다.
      if (code === "rate_limited") {
        const retryAfter = data && data.error && data.error.retry_after_seconds;
        startCooldown(typeof retryAfter === "number" && retryAfter > 0 ? retryAfter : 15);
      }
    } catch (err) {
      if (err && err.name === "AbortError") {
        errorBox.textContent = "서버 응답이 없습니다. 다시 시도하세요.";
      } else {
        errorBox.textContent = "서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.";
        // 연결 계층 실패 — 이제서야 준비 상태를 늦게 확인한다(로드 시엔 안 한다).
        probeHealth(true);
      }
    } finally {
      window.clearTimeout(timeoutId);
      // 성공 리다이렉트 중이면 라벨/버튼 상태를 되돌리지 않는다 — 페이지가 넘어가는
      // 사이 '로그인 중…'이 기본 '로그인'으로 잠깐 되돌아 깜빡이던 문제를 없앤다.
      if (navigating) return;
      submitButton.removeAttribute("aria-busy");
      // 쿨다운이 걸린 동안엔 버튼을 다시 열지 않는다(startCooldown이 타이머 만료 시 연다).
      if (cooldownTimer === null) {
        submitButton.disabled = false;
        if (submitLabel) submitLabel.textContent = submitLabelDefault;
      }
    }
  });
})();
