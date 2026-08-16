"use strict";

(function () {
  const form = document.getElementById("cp-form");
  const currentInput = document.getElementById("current-password");
  const newInput = document.getElementById("new-password");
  const confirmInput = document.getElementById("confirm-password");
  const showToggle = document.getElementById("cp-show");
  const errorBox = document.getElementById("cp-error");
  const statusBox = document.getElementById("cp-status");
  const rulesBox = document.getElementById("cp-rules");
  const confirmStatus = document.getElementById("cp-confirm-status");
  const capsHint = document.getElementById("cp-caps-hint");
  const capsHintCurrent = document.getElementById("cp-caps-hint-current");
  const capsHintConfirm = document.getElementById("cp-caps-hint-confirm");
  const submitButton = document.getElementById("cp-submit");
  const logoutButton = document.getElementById("cp-logout");
  const backLink = document.getElementById("cp-back-link");

  // 자발적 변경(must_change=false)은 채팅/관리자 셸 어느 쪽 UserMenu에서도 올 수 있다.
  // 하드코딩된 '/'는 관리자에서 온 사람을 항상 채팅으로 돌려보낸다 — 같은 출처
  // referrer가 있으면 정적 기본값('/') 대신 그리로 되돌린다. referrer가 없거나
  // 다른 출처(외부 링크로 진입 등)면 안전한 기본값을 그대로 둔다(open-redirect 방지).
  if (backLink && document.referrer) {
    try {
      const ref = new URL(document.referrer);
      // /change-password(새로고침으로 진입) 또는 /login을 referrer로 그대로 쓰면 성공 후
      // 이 화면(또는 로그인)으로 되돌아와 무의미한 왕복이 된다 — 그 두 경로면 안전한
      // 기본값('/')을 유지한다(open-redirect도 방지: same-origin일 때만 덮어쓴다).
      const isSelfOrLogin =
        ref.pathname === "/change-password" || ref.pathname === "/login";
      if (ref.origin === window.location.origin && !isSelfOrLogin) {
        backLink.href = ref.pathname + ref.search + ref.hash;
      }
    } catch (e) {
      // referrer가 파싱 불가한 값이면 기본값('/')을 그대로 둔다.
    }
  }
  const submitLabelDefault = submitButton.textContent;
  const logoutLabelDefault = logoutButton ? logoutButton.textContent : "";

  // 정책값은 서버가 폼 data 속성으로 내려준다(관리자가 정책을 바꿔도 안내가 어긋나지 않게).
  const minLength = parseInt(form.getAttribute("data-min-length"), 10) || 12;
  const minClasses = parseInt(form.getAttribute("data-min-classes"), 10) || 3;
  const SPECIAL = "!@#$%^&*()-_=+[]{};:,.<>?/|~`'\"\\";

  // CSRF 토큰은 서버가 렌더 시점에 폼 data 속성으로 실어 준다 — /api/me 왕복이 필요 없다.
  // 이렇게 하면 그 왕복이 실패해(일시적 5xx/네트워크) 제출·탈출 버튼이 영영 잠기던
  // 함정이 사라진다. 토큰이 있으면 즉시 버튼을 연다. 성공 응답이 세션을 회전시키며
  // 새 토큰을 돌려주므로(server: session_service.create) let로 둬 갱신할 수 있게 한다.
  let csrfToken = form.getAttribute("data-csrf-token") || null;

  // login.js와 같은 이유: 요청이 응답 없이 멈추면(연결은 수립됐으나 무응답) 버튼이
  // '변경 중…'/로그아웃 처리 중으로 영영 멈춘다. 타임아웃으로 중단해 다시 시도할 수
  // 있게 한다(login.js:SUBMIT_TIMEOUT_MS와 동일한 예산).
  const SUBMIT_TIMEOUT_MS = 15000;

  function enableControls() {
    submitButton.disabled = false;
    submitButton.textContent = submitLabelDefault;
    submitButton.removeAttribute("aria-busy");
    if (logoutButton) {
      logoutButton.disabled = false;
      logoutButton.textContent = logoutLabelDefault;
      logoutButton.removeAttribute("aria-busy");
    }
  }

  // login.js의 429 쿨다운과 같은 이유: 요청 제한(rate_limited) 직후 바로 다시 눌러
  // 한도를 재차 건드리지 않도록 제출 버튼을 짧게 잠근다. 서버가 실제 리미터 상태로
  // 계산한 대기 시간(retry_after_seconds)을 우선 쓰고, 없을 때만 추정값(15초)을 쓴다.
  let cooldownTimer = null;
  function startCooldown(seconds) {
    let remaining = seconds;
    submitButton.disabled = true;
    // 요청은 이미 끝났다(429 응답을 받은 시점) — 진행 중 신호(aria-busy)를 지운다.
    // enableControls()는 이 쿨다운 경로에서 호출되지 않으므로, 여기서 직접 지우지 않으면
    // 쿨다운 창(retry_after_seconds, 15초 넘을 수 있음) 내내 버튼이 '처리 중'으로
    // 잘못 표시된 채 남는다.
    submitButton.removeAttribute("aria-busy");
    submitButton.textContent = remaining + "초 후 재시도";
    // 로그아웃 버튼은 잠그지 않는다 — 이 쿨다운은 change-password 엔드포인트의 rate
    // limiter 키에만 걸린 것이고 /logout은 별도 엔드포인트/리미터라 영향받지 않는다.
    // 강제 변경 화면에서 벗어나 다른 계정으로 로그인하려는 사용자를 여기 붙잡아 둘 이유가 없다.
    // submit()이 fetch 직전 두 버튼을 함께 잠그므로(경합 방지), 429 응답을 받은 시점엔
    // 그 요청은 이미 끝났다 — logoutButton을 여기서 즉시 풀지 않으면 must_change 사용자가
    // 유일한 탈출구(다른 계정으로 로그인)까지 쿨다운 동안 갇힌다.
    if (logoutButton) {
      logoutButton.disabled = false;
      logoutButton.textContent = logoutLabelDefault;
      logoutButton.removeAttribute("aria-busy");
    }
    cooldownTimer = window.setInterval(function () {
      remaining -= 1;
      if (remaining <= 0) {
        window.clearInterval(cooldownTimer);
        cooldownTimer = null;
        enableControls();
      } else {
        submitButton.textContent = remaining + "초 후 재시도";
      }
    }, 1000);
  }

  if (csrfToken) {
    enableControls();
  } else {
    // 서버가 토큰을 못 실어 준 예외 상황: 버튼은 disabled로 남기고 이유를 보인다.
    submitButton.disabled = true;
    if (logoutButton) logoutButton.disabled = true;
    errorBox.textContent = "세션 정보를 읽지 못했습니다. 새로고침 후 다시 시도해 주세요.";
  }

  // 문자 종류 판정을 서버와 맞춘다: 서버(core/security.py)는 유니코드 인식
  // islower/isupper/isdigit와 코드포인트 길이를 쓴다. 클라이언트도 \p{...} 유니코드
  // 속성과 코드포인트 배열로 계산해, ✓/· 힌트가 서버 판정과 어긋나지 않게 한다.
  function codePointLength(password) {
    return Array.from(password).length;
  }

  function countClasses(password) {
    let classes = 0;
    if (/\p{Ll}/u.test(password)) classes += 1;
    if (/\p{Lu}/u.test(password)) classes += 1;
    if (/\p{Nd}/u.test(password)) classes += 1;
    if (Array.from(password).some(function (c) { return SPECIAL.indexOf(c) !== -1; })) {
      classes += 1;
    }
    return classes;
  }

  // 세 칸을 한 번에 보이기/숨기기(12자·3종류 정책이라 오타 재입력 비용이 크다).
  if (showToggle) {
    showToggle.addEventListener("change", function () {
      const t = showToggle.checked ? "text" : "password";
      currentInput.type = t;
      newInput.type = t;
      confirmInput.type = t;
    });
  }

  // Caps Lock이 켜진 채 임시 비밀번호(대소문자 혼합)를 입력하면 '현재 비밀번호가 틀렸다'로만
  // 보고되어 원인을 모른다. 켜져 있을 때만 힌트를 보인다(getModifierState 미지원 시 조용히 무시).
  // 세 칸 모두 각자 바로 아래 전용 힌트를 쓴다(current/new/confirm) — 공용 힌트 하나를
  // 여러 칸이 나눠 쓰면 화면 아래쪽 칸에 있는 힌트가 위쪽 칸에 초점이 있을 때는 안 보인다
  // (round28 감사 E: 새 비밀번호 칸이 실제로 이 문제를 겪고 있었다).
  // role="status" 라이브 리전은 hidden 속성/visibility 토글이 아니라 '내용 변화'에만
  // 낭독한다 — 정적 텍스트의 hidden만 껐다 켜면 스크린리더가 캡스락 경고를 읽지 않는다
  // (round30 감사 E). 켜지면 문구를 채우고 꺼지면 비운다. 상태가 실제로 바뀔 때만
  // 내용을 갱신해(같은 값 재대입 방지) 키 입력마다 반복 낭독되지 않게 한다. 빈 상태도
  // .caps-hint의 min-height로 자리를 유지하므로 레이아웃은 튀지 않는다.
  const CAPS_MESSAGE = "캡스락이 켜져 있습니다.";
  function setCapsHint(hintEl, on) {
    if (!hintEl) return;
    hintEl.hidden = false;
    const next = on ? CAPS_MESSAGE : "";
    if (hintEl.textContent !== next) hintEl.textContent = next;
  }
  function updateCapsFor(hintEl, event) {
    if (!hintEl || typeof event.getModifierState !== "function") return;
    setCapsHint(hintEl, event.getModifierState("CapsLock"));
  }
  [[currentInput, capsHintCurrent], [newInput, capsHint], [confirmInput, capsHintConfirm]].forEach(
    function (pair) {
      const el = pair[0];
      const hintEl = pair[1];
      if (!el) return;
      el.addEventListener("keydown", function (event) { updateCapsFor(hintEl, event); });
      el.addEventListener("keyup", function (event) { updateCapsFor(hintEl, event); });
      el.addEventListener("blur", function () { setCapsHint(hintEl, false); });
    }
  );

  // 정책 위반 목록을 서버와 같은 규칙으로 계산한다(서버가 최종 권한, 여기선 왕복 전 힌트).
  function policyProblems(password) {
    const problems = [];
    if (codePointLength(password) < minLength) {
      problems.push("비밀번호는 최소 " + minLength + "자 이상이어야 합니다.");
    }
    if (countClasses(password) < minClasses) {
      problems.push("대문자, 소문자, 숫자, 특수문자 중 " + minClasses + "종 이상을 조합해야 합니다.");
    }
    return problems;
  }

  // 입력하는 동안 규칙 충족 여부를 즉시 보여준다 — 색이 아니라 ✓/· 기호로(색맹·CSS 무관).
  function ruleRow(met, label) {
    const el = document.createElement("div");
    el.textContent = (met ? "✓ " : "· ") + label;  // clovi-allow-glyph: 규칙 충족/미충족 표시. ✓ 와 짝을 이루는 글리프다
    // 기호(✓/·)가 1차 신호(색맹·CSS 무관), 색은 2차 보조 신호 — 충족된 규칙이
    // 옅은 회색 목록 속에 묻히지 않고 눈에 띄게 한다.
    el.className = met ? "cp-rule--met" : "cp-rule--pending";
    return el;
  }
  function renderRules() {
    const password = newInput.value;
    if (!rulesBox) return;
    rulesBox.textContent = "";
    // 항상 적용되는 기본 규칙 2줄(길이·문자 종류)은 입력이 비어 있어도 렌더한다 —
    // 예약된 #cp-rules 높이(base.css)가 설명 없는 빈칸으로 남지 않게 한다(round30 감사 E).
    const length = codePointLength(password);
    const classes = countClasses(password);
    rulesBox.appendChild(ruleRow(!!password && length >= minLength, minLength + "자 이상 (" + length + "자)"));
    rulesBox.appendChild(ruleRow(!!password && classes >= minClasses, "문자 종류 " + minClasses + "종 이상 (" + classes + "종)"));
    // 서버는 새 비밀번호가 기존과 같으면 거절한다(router.py) — 왕복 전에 알려 준다.
    if (password && currentInput.value) {
      rulesBox.appendChild(ruleRow(password !== currentInput.value, "기존 비밀번호와 다름"));
    }
  }
  // 확인 일치/불일치는 확인 칸 바로 아래에서 보여 준다(위 #cp-rules가 아니라) —
  // 사용자가 실제로 타이핑하는 자리에서 피드백이 갱신되게 한다(round30 감사 E).
  function renderConfirmMatch() {
    if (!confirmStatus) return;
    confirmStatus.textContent = "";
    if (!newInput.value || !confirmInput.value) return;
    confirmStatus.appendChild(
      ruleRow(newInput.value === confirmInput.value, "새 비밀번호 확인 일치")
    );
  }
  newInput.addEventListener("input", renderRules);
  newInput.addEventListener("input", renderConfirmMatch);
  confirmInput.addEventListener("input", renderConfirmMatch);
  currentInput.addEventListener("input", renderRules);
  // 로드 시 기본 규칙 2줄을 즉시 그려 예약 공간을 채운다.
  renderRules();

  // 오류로 aria-invalid가 걸린 칸을 사용자가 다시 편집하기 시작하면 표식을 지운다 —
  // 다음 제출 시도까지 기다리지 않고, 스크린리더가 이미 고치는 중인 값을 계속 '오류'로
  // 읽지 않게 한다.
  [currentInput, newInput, confirmInput].forEach(function (el) {
    el.addEventListener("input", function () {
      el.removeAttribute("aria-invalid");
    });
  });

  // 여러 정책 위반을 한 줄로 뭉치면 읽기 어렵다 — 항목별로 나눠 보여준다(§6 XSS: textContent).
  // details는 이 앱 자체의 ValidationAppError(문자열 배열)뿐 아니라, FastAPI의 일반
  // RequestValidationError 핸들러(app/core/errors.py _validation_error)가 만드는
  // {loc, msg} 객체 배열로도 올 수 있다(예: 요청 바디가 애초에 JSON 스키마와 안 맞는 경우).
  // 문자열만 가정하면 그 경로에서 "· [object Object]"가 그대로 화면에 새어 나간다.
  function detailText(d) {
    if (typeof d === "string") return d;
    if (d && typeof d === "object") {
      // {loc, msg} 모양이면 FastAPI의 기본 RequestValidationError 항목이다. PA-RC-0014부터
      // app/core/errors.py가 그 msg 자체를 err["type"]+ctx로 만든 한국어 문구로 바꿔
      // 보내므로(예: "최대 120자까지 입력할 수 있습니다") 그대로 쓴다 — 예전엔 Pydantic이
      // 영문을 그대로 실어 보내던 시절의 방어책으로 일반 안내("입력값을 확인해 주세요")로
      // 덮어썼지만, 지금 덮으면 서버가 이미 만들어 준 더 구체적인 문구를 버리게 된다.
      if (typeof d.msg === "string") return d.msg;
      try {
        return JSON.stringify(d);
      } catch (e) {
        return String(d);
      }
    }
    return String(d);
  }
  function showDetails(details) {
    errorBox.textContent = "";
    details.forEach(function (d) {
      const el = document.createElement("div");
      el.textContent = "· " + detailText(d);  // clovi-allow-glyph: 목록 글머리표
      errorBox.appendChild(el);
    });
  }

  // 로그아웃 후 로그인 화면으로. 세션이 살아 있으면 GET /login이 /로, /가 다시
  // /change-password로 돌려보내 무한 루프가 된다 — 그래서 반드시 세션을 먼저 폐기한다.
  if (logoutButton) {
    logoutButton.addEventListener("click", async function () {
      if (!csrfToken) {
        errorBox.textContent = "세션 정보를 아직 불러오지 못했습니다. 잠시 후 다시 시도하세요.";
        return;
      }
      logoutButton.disabled = true;
      // 두 버튼은 서로 독립적으로 잠기지 않았다 — 로그아웃 요청이 진행 중인 동안 제출
      // 버튼이 그대로 눌리면(또는 그 반대) 같은 CSRF 토큰으로 두 요청이 경합해 하나는
      // 세션 회전 이후의 무효 토큰으로 실패한다. 진행 중엔 둘 다 잠근다.
      submitButton.disabled = true;
      // 제출 버튼(cp-submit)은 '변경 중…' 라벨 + aria-busy로 진행 중임을 알린다 — 이
      // 버튼도 같은 패턴을 준다. disabled만으로는 느린 연결에서 클릭이 실제로 접수됐는지
      // 알 방법이 없다(왜 안 눌리나 vs 처리 중이나 구분 불가).
      logoutButton.textContent = "로그아웃 중…";
      logoutButton.setAttribute("aria-busy", "true");
      const controller = new AbortController();
      const timeoutId = window.setTimeout(function () { controller.abort(); }, SUBMIT_TIMEOUT_MS);
      try {
        const res = await fetch("/logout", {
          method: "POST",
          headers: { "X-CSRF-Token": csrfToken },
          signal: controller.signal,
        });
        // 세션을 실제로 폐기하지 못했으면 /login으로 보내지 않는다 — 살아 있는 세션 그대로
        // 이동하면 /login→/→/change-password 무한 루프에 갇힌다. 그 자리에 머물러 안내한다.
        if (!res.ok) {
          errorBox.textContent =
            "로그아웃에 실패했습니다. 새로고침 후 다시 시도하세요. 로그인은 그대로 유지됩니다.";
          enableControls();
          return;
        }
      } catch (err) {
        errorBox.textContent =
          (err && err.name === "AbortError")
            ? "서버 응답이 없습니다. 다시 시도하세요."
            : "서버에 연결할 수 없어 로그아웃하지 못했습니다. 연결을 확인한 뒤 다시 시도하세요.";
        enableControls();
        return;
      } finally {
        window.clearTimeout(timeoutId);
      }
      window.location.href = "/login";
    });
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    errorBox.textContent = "";
    // 이전 시도의 오류 표식을 지운다(스크린리더가 낡은 상태를 물지 않게).
    currentInput.removeAttribute("aria-invalid");
    newInput.removeAttribute("aria-invalid");
    confirmInput.removeAttribute("aria-invalid");
    // novalidate라 required가 꺼져 있다 — 빈 값은 왕복 없이 즉시 막는다(빈 현재 비밀번호가
    // '비밀번호가 틀렸다'는 401로 오해되던 문제도 함께 없앤다).
    // 아래 클라이언트측 검증 실패들은 서버측 실패(wrong_current_password 등, 아래 참고)와
    // 같은 부류의 오류이므로 동일하게 aria-invalid를 걸어 오류 문구·초점 이동과 프로그램적으로
    // 묶는다 — 스크린리더 사용자에게 그 필드가 왜 다시 초점을 받았는지 알려준다.
    if (!currentInput.value) {
      errorBox.textContent = "현재 비밀번호를 입력하세요.";
      currentInput.setAttribute("aria-invalid", "true");
      currentInput.focus();
      return;
    }
    if (!newInput.value || !confirmInput.value) {
      const empty = !newInput.value ? newInput : confirmInput;
      errorBox.textContent = "새 비밀번호와 확인을 모두 입력하세요.";
      empty.setAttribute("aria-invalid", "true");
      empty.focus();
      return;
    }
    if (newInput.value !== confirmInput.value) {
      errorBox.textContent = "새 비밀번호가 서로 일치하지 않습니다.";
      confirmInput.setAttribute("aria-invalid", "true");
      confirmInput.focus();
      return;
    }
    // 정책 위반과 '기존과 동일' 위반은 서로 다른 라운드에서 하나씩 드러나면 사용자가 고칠
    // 때마다 새 오류를 만난다 — 왕복(비밀번호 전송) 전에 둘 다 한 번에 모아서 보여준다.
    const problems = policyProblems(newInput.value);
    // 서버는 새 비밀번호가 기존과 같으면 거절한다(router.py) — 같은 라운드에 합쳐서 막는다.
    // 단, 이 비교는 "현재 비밀번호" 칸의 검증되지 않은 입력값을 기준으로 한다 — 실제
    // 계정 비밀번호와 다를 수 있다. 현재 비밀번호를 잘못 입력해 우연히 새 비밀번호와
    // 같아진 경우에도 이 문구가 뜰 수 있으므로, 오해하지 않도록 그 가능성을 함께 알린다.
    if (newInput.value === currentInput.value) {
      problems.push("새 비밀번호는 기존 비밀번호와 달라야 합니다(현재 비밀번호를 잘못 입력했을 수도 있습니다).");
    }
    if (problems.length) {
      showDetails(problems);
      newInput.setAttribute("aria-invalid", "true");
      newInput.focus();
      return;
    }
    if (!csrfToken) {
      errorBox.textContent = "세션 정보를 불러오지 못했습니다. 새로고침 후 다시 시도하세요.";
      return;
    }
    submitButton.disabled = true;
    // 로그아웃 버튼도 함께 잠근다 — 그렇지 않으면 이 요청이 진행 중(그리고 서버가 이미
    // 세션을 회전시킨) 상태에서 로그아웃을 눌러 옛(곧 무효가 될) csrfToken으로 경합할 수 있다.
    if (logoutButton) logoutButton.disabled = true;
    // Argon2 verify+hash가 수백 ms 걸릴 수 있다 — 진행 중임을 라벨·aria-busy로 알린다.
    // 실패 시 enableControls()가 라벨·aria-busy를 되돌린다.
    submitButton.textContent = "변경 중…";
    submitButton.setAttribute("aria-busy", "true");
    const controller = new AbortController();
    const timeoutId = window.setTimeout(function () { controller.abort(); }, SUBMIT_TIMEOUT_MS);
    try {
      const response = await fetch("/change-password", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({
          current_password: currentInput.value,
          new_password: newInput.value,
        }),
        signal: controller.signal,
      });
      const data = await response.json().catch(function () { return null; });
      if (response.ok && data && data.ok) {
        // 서버가 세션을 회전시키며(session_service.create) 새 csrf_token을 함께 돌려준다 —
        // 갱신하지 않으면 이 시점 이후(예: 리다이렉트 지연 중 로그아웃 클릭) 이미 무효가 된
        // 옛 토큰으로 다음 요청이 CSRF 실패한다.
        if (data.csrf_token) csrfToken = data.csrf_token;
        // 성공은 되돌릴 수 없고 다른 기기 세션이 모두 끊긴다 — 이동 전에 확실히 알린다.
        // 성공 문구는 role="status" 영역에 넣어 스크린리더가 읽게 한다(비활성 버튼 라벨은
        // 낭독이 보장되지 않는다).
        errorBox.textContent = "";
        if (rulesBox) rulesBox.textContent = "";
        submitButton.textContent = "이동 중…";
        submitButton.removeAttribute("aria-busy");
        if (statusBox) {
          // 되돌릴 수 없는 중요 동작의 확인은 옅은 도움말과 구분되게 성공 색·✓로 강조한다.
          statusBox.textContent = "✓ 비밀번호가 변경되었습니다. 다른 기기는 로그아웃됩니다. 잠시 후 이동합니다…";
          statusBox.classList.add("auth-success");
        }
        // backLink(있으면)는 이미 위에서 same-origin referrer를 검증해 계산해 둔 값이다
        // (관리자 셸에서 온 자발적 변경은 관리자로, 채팅에서 온 변경은 채팅으로). must_change
        // 강제 변경 화면은 cp-back-link 자체가 없다(뒤로 갈 '이전 화면'이 의미 없음) — 그
        // 경우만 안전한 기본값 '/'를 그대로 쓴다.
        // 2500ms: role="status" 라이브 리전이 전체 문장을 다 읽기 전에 이동하면 스크린
        // 리더 사용자는 안내를 끝까지 못 듣는다(1400ms는 너무 짧았다 — round28 감사 E).
        window.setTimeout(function () {
          window.location.href = backLink ? backLink.href : "/";
        }, 2500);
        return;
      }
      // 진짜 세션 만료/인증 요구(코드 'unauthorized')일 때만 로그인으로 보낸다. '현재 비밀번호
      // 불일치'는 같은 401이지만 코드가 'wrong_current_password'라 여기 머문다(루프 방지).
      // 음성 매치(!== wrong_current_password)가 아니라 양성 매치(=== unauthorized)로 좁힌다 —
      // 네트워크 단절/프록시가 본문 없는 401을 만들면 code는 undefined가 되는데, 음성 매치는
      // 그 경우도 '로그인 필요'로 오해해 실제로는 서버에 도달조차 못 한 요청을 로그아웃
      // 처리해 버린다. 매치되지 않는 401은 아래 wrong_current_password 분기나 최종 fallback으로
      // 흘러가 화면에 머문 채 오류를 보여준다.
      const code = data && data.error && data.error.code;
      if (response.status === 401 && code === "unauthorized") {
        // next를 안 실으면 재로그인 후 채팅으로 떨어진다. must_change 사용자는 로그인이
        // must_change_password 플래그를 보고 강제로 /change-password로 다시 보내 스스로
        // 복구되지만, 자발적 변경 도중이던 사용자는 그 안전장치가 없다 — next로 명시한다.
        window.location.href = "/login?next=" + encodeURIComponent("/change-password");
        return;
      }
      // csrf 만료는 로그인이 끊긴 게 아니다 — 새로고침으로 토큰을 다시 받아 재시도하면 된다.
      // 원문 메시지('CSRF 토큰이 …')만 보이면 사용자가 다음에 뭘 할지 모른다.
      if (response.status === 403 && code === "csrf_failed") {
        errorBox.textContent =
          "요청이 만료되었습니다. 새로고침한 뒤 다시 시도하세요. 로그인은 그대로 유지됩니다.";
        // enableControls()로 다시 열지 않는다 — csrfToken은 실제 새로고침(페이지 재렌더)
        // 전까지는 여전히 그 만료된 값 그대로이므로, 버튼을 다시 눌러도 같은 토큰을 다시
        // 보내 매번 같은 403이 반복될 뿐이다. 안내 문구가 요구하는 행동(새로고침)과
        // 버튼 상태를 맞춰, 잠긴 채로 그 사실을 알린다.
        submitButton.textContent = "새로고침 필요";
        submitButton.removeAttribute("aria-busy");
        // logoutButton은 여기서도 잠긴 채로 남는다(위에서 submitButton과 함께 disabled = true
        // 처리됨) — 하지만 라벨을 평상시 텍스트로 되돌리면 disabled인데 '눌러도 되는
        // 버튼'처럼 보인다(.btn-ghost:disabled가 시각적으로 흐리게 처리해도, 라벨 자체가
        // 활성 상태를 암시하는 문제는 남는다). submitButton과 같은 '잠금 사유' 라벨을 줘
        // 왜 안 눌리는지 명시한다 — 실제로 /logout은 별개 엔드포인트라 여전히 시도할 수
        // 있었을 수도 있지만, 같은 페이지 새로고침 한 번으로 두 버튼 모두 풀리므로 굳이
        // 여기서 재활성화하지 않고 동일한 안내로 통일한다.
        if (logoutButton) {
          logoutButton.textContent = "새로고침 필요";
          logoutButton.removeAttribute("aria-busy");
        }
        return;
      }
      // 5xx는 영어 기본 메시지('Internal server error')를 실어 오므로(core/errors.py),
      // 한국어 화면에 영어가 새지 않도록 일반 문구로 대체한다.
      if (response.status >= 500) {
        errorBox.textContent =
          "서버 오류로 비밀번호를 변경하지 못했습니다. 잠시 후 다시 시도해 주세요.";
        enableControls();
        return;
      }
      // '현재 비밀번호 불일치'(401, wrong_current_password)는 이 화면에 머문다 — 오류를
      // 현재 비밀번호 칸에 프로그램적으로 묶고(aria-invalid) 초점을 그리로 옮긴다.
      if (response.status === 401 && code === "wrong_current_password") {
        errorBox.textContent =
          (data && data.error && data.error.message) || "현재 비밀번호가 올바르지 않습니다.";
        currentInput.setAttribute("aria-invalid", "true");
        currentInput.focus();
        enableControls();
        return;
      }
      // rate_limited는 다른 실패와 달리 즉시 재제출을 허용하면 한도를 계속 재차 건드린다 —
      // enableControls()로 바로 여는 대신 실제 리미터 대기 시간만큼 버튼을 잠근다.
      if (response.status === 429 && code === "rate_limited") {
        errorBox.textContent =
          (data && data.error && data.error.message) || "비밀번호 변경 시도가 너무 많습니다. 잠시 후 다시 시도하세요.";
        const retryAfter = data && data.error && data.error.retry_after_seconds;
        startCooldown(typeof retryAfter === "number" && retryAfter > 0 ? retryAfter : 15);
        return;
      }
      // 다른 실패 분기(현재 비밀번호 불일치 등)는 모두 원인 필드에 aria-invalid를 걸고
      // 초점을 옮긴다 — 이 fallback(주로 서버 쪽 정책 재검증 실패 details, 그 외 알 수 없는
      // 오류)만 showDetails()/errorBox만 채우고 스크린리더 사용자를 원래 초점 위치에
      // 남겨 뒀다. 여기 도달하는 원인은 거의 항상 새 비밀번호 쪽이므로 그 칸을 표식한다.
      if (data && data.error && Array.isArray(data.error.details) && data.error.details.length) {
        showDetails(data.error.details);
      } else {
        // data.error.message는 여기 도달하는 경로에서 한국어라는 보장이 없다 — 예를 들어
        // app/core/errors.py의 일반 StarletteHTTPException 핸들러(message=str(exc.detail))는
        // Starlette가 만든 영문 문구(예: "Not Found")를 그대로 싣는다(RequestValidationError
        // 핸들러는 PA-RC-0014부터 한국어 고정 문구를 쓰지만, 그 사실에 기대지 않는다 — 이
        // fallback은 이 핸들러가 아닌 다른 어떤 예외 경로가 여기 떨어져도 안전해야 한다).
        // POST /change-password가 실제로 내는 코드(rate_limited·wrong_current_password·
        // unauthorized·csrf_failed·validation_error·500)는 모두 위의 전용 분기에서 처리되므로,
        // 이 fallback에 도달하는 code는 한국어가 보장되지 않는다 — 서버 메시지를 믿지 않고
        // 정적 한국어로 대체한다.
        errorBox.textContent = "비밀번호 변경에 실패했습니다.";
      }
      newInput.setAttribute("aria-invalid", "true");
      newInput.focus();
      enableControls();
    } catch (err) {
      errorBox.textContent =
        (err && err.name === "AbortError")
          ? "서버 응답이 없습니다. 다시 시도하세요."
          : "서버에 연결할 수 없습니다.";
      enableControls();
    } finally {
      window.clearTimeout(timeoutId);
    }
  });
})();
