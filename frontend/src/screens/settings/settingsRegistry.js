// snake_case 백엔드 키를 한국어 이름으로. 한국어 콘솔에 raw 영문 키를 주 식별자로 노출하지 않는다.
export const SETTING_LABELS = {
  // 라벨과 설명(registry.py) 용어를 '보존'으로 통일한다 — 라벨은 '보관', 옆 설명은 '보존'이라 서로 다른 개념처럼 보였다.
  conversation_retention_days: "대화 보존 기간(일)",
  notification_retention_days: "알림 보존 기간(일)",
  trash_retention_days: "휴지통 보관 기간(일)",
  ui_branding: "브랜딩",
  // 메일 발송(9-9 P4). 라벨이 없으면 이 표에 `smtp` 라는 영문 키가 그대로 새어 나간다.
  smtp: "메일(SMTP) 발송",
  maintenance_mode: "유지보수 모드",
  maintenance_message: "점검 공지",
  password_policy: "비밀번호 정책",
  session_policy: "세션 정책",
  lockout_policy: "계정 잠금 정책",
  // N7: "로그인 허용" 이라 적혀 있었는데 실제로는 **생성 시에만** 검사한다
  // (`app/users/service.py`). 도메인을 좁혀도 기존 계정은 그대로 들어온다 —
  // 운영자가 이 값으로 접근을 끊을 수 있다고 믿으면 그게 보안 사고가 된다.
  allowed_email_domains: "계정 추가 허용 도메인",
  document_automation_enabled: "문서 자동화",
  // N6: 이 키가 세 맵에 **전부** 빠져 있어 관리자가 raw 영문 키 + raw JSON 으로 편집했다.
  // 이 파일이 그 드리프트를 예견해 경고까지 심어 놨는데 `import.meta.env.DEV` 게이트라
  // 운영에서는 침묵했다 — 예견해 놓고 못 잡은 셈이다.
  backup_schedule: "자동 백업 일정",
  // Notion 관리(9-4)와 AI 관리(9-5). 이 표에서는 숨기지만(DEDICATED_SCREEN_KEYS) 라벨은
  // 있어야 한다 - 감사 로그와 버전 기록이 이 이름으로 나온다.
  notion_tasks_database_id: "노션 작업 데이터베이스 id",
  notion_documents_database_id: "노션 문서 데이터베이스 id",
  notion_sprint_database_id: "노션 스프린트 데이터베이스 id",
  llm_enabled: "AI 사용 여부",
  llm_backend: "AI 백엔드",
  llm_executable: "AI 실행 파일",
  llm_model: "AI 모델",
  llm_timeout_seconds: "AI 제한 시간(초)",
  llm_max_concurrency: "AI 동시 실행 수",
};
export const settingLabel = (k) => SETTING_LABELS[k] || k;
// object 설정 편집 시 필요한 키·단위를 알려 준다(비개발자 관리자가 raw JSON을 추측하지 않게).
export const OBJECT_SCHEMA_HELP = {
  password_policy: 'JSON 예: {"min_length": 12, "min_classes": 3}, min_length(최소 글자 수), min_classes(문자 종류 수, 1~4).',
  session_policy: 'JSON 예: {"idle_timeout_seconds": 1800, "absolute_timeout_seconds": 28800}, 값은 초 단위입니다(30분=1800, 8시간=28800).',
  lockout_policy: 'JSON 예: {"max_failures": 5, "lock_seconds": 900}, max_failures(연속 로그인 실패 몇 회 만에 잠글지, 1~20), lock_seconds(잠금 유지 시간, 초 단위, 60~86400).',
  // 백엔드(_email_domains)는 빈 목록([])을 '도메인 제한 없음'으로 허용한다(round10 감사 C 반영).
  allowed_email_domains: 'JSON 예: ["example.com"], **계정을 새로 추가할 때** 허용할 이메일 도메인 목록입니다. 이미 있는 계정은 도메인을 좁혀도 계속 로그인합니다(로그인 검사가 아닙니다). 빈 목록([])이면 제한 없이 모든 이메일을 허용합니다.',
  ui_branding: 'JSON 예: {"product_name": "ClovirONE", "support_email": "help@example.com"}, 제품명, 지원 이메일 등 브랜딩 값.',
  // 비밀번호를 이 JSON 에 넣으면 설정 화면·감사·버전 스냅샷에 평문으로 남는다. 그래서
  // 서버는 **파일 이름**(password_ref)만 받는다 - 그 사실을 여기서 분명히 말한다.
  smtp: 'JSON 예: {"enabled": true, "host": "smtp.example.com", "port": 587, "security": "starttls", "from_address": "portal@example.com", "password_ref": "smtp_password"}, 비밀번호는 여기 적지 않습니다. 서버의 secret 파일 이름만 password_ref 에 적습니다.',
  // 백엔드(_backup_schedule)가 **저장 시점에** cron·타임존을 검증한다 — 여기 예시는 그것과
  // 같은 모양이라야 한다(틀린 예시를 그대로 붙여 넣으면 저장이 거부된다).
  backup_schedule: 'JSON 예: {"enabled": true, "cron": "0 3 * * *", "timezone": "Asia/Seoul", "keep": 14}, cron 은 분 시 일 월 요일(0 3 * * * = 매일 새벽 3시), keep 은 남길 백업 개수(1~365).',
};
export const WRITE_ROLES = ["admin", "system_admin"];
// maintenance_mode·maintenance_message는 전용 '유지보수' 화면(/maintenance)에서만 관리한다.
// 같은 안전 스위치를 두 화면에서 서로 다른 방식으로 다루지 않도록 설정 표에서는 숨긴다.
export const MAINTENANCE_KEYS = ["maintenance_mode", "maintenance_message"];
// Notion 관리(9-4)와 AI 관리(9-5) 키는 전용 화면에서만 다룬다. 유지보수 키와 **같은 이유**로
// 이 표에서 숨긴다: 같은 값을 두 화면에서 서로 다른 방식으로(여기서는 raw JSON, 저쪽에서는
// 연결 테스트가 붙은 폼으로) 다루면 두 화면이 서로 다른 것을 가르치게 된다.
//
// 게다가 이 키들은 서버가 **시스템 관리자만** 쓰게 막는다
// (app/settings/registry.py::SYSTEM_ADMIN_ONLY_KEYS). 여기 남겨 두면 부서 관리자에게
// 편집기가 열리고 저장에서 403 을 받는다 - 막다른 길이다.
export const DEDICATED_SCREEN_KEYS = [
  "notion_tasks_database_id", "notion_documents_database_id", "notion_sprint_database_id",
  "llm_enabled", "llm_backend", "llm_executable", "llm_model",
  "llm_timeout_seconds", "llm_max_concurrency",
];
// 이 object 설정들은 정해진 스키마가 있어 타입에 맞는 입력(숫자·분/시간·칩 목록)으로 편집할 수 있다.
// 비개발자 관리자가 raw JSON을 손으로 추측하지 않게 하려는 목적(registry.py 주석과 동일 취지) —
// 그 외 미지의 object 키는 여전히 JSON 텍스트로만 편집한다(스키마가 없으므로).
export const STRUCTURED_OBJECT_KEYS = ["password_policy", "session_policy", "lockout_policy", "allowed_email_domains", "ui_branding"];
// 평범한 int 설정도 상한이 있다(registry.py _positive_int(3650)) — object 설정들처럼 min/max와 범위
// 힌트를 붙여, 값을 저장 왕복 없이도 눈치챌 수 있게 한다(이전엔 이 둘만 아무 제약 없는 숫자 입력이었다).
export const INT_BOUNDS = { conversation_retention_days: [1, 3650], notification_retention_days: [1, 3650], trash_retention_days: [1, 365] };

// 강조색 프리셋의 한국어 이름 — 색만으로 고르게 두면 색각 이상 사용자는 무엇을 골랐는지 알 수 없고,
// 스크린리더는 아무것도 읽을 게 없다(WCAG 1.4.1). 이름을 모르면 hex를 그대로 읽어 준다.
export const ACCENT_NAMES = {
  "#536CD6": "기본 파랑",
  "#4058BD": "진한 파랑",
  "#6B5BC7": "보라",
  "#327C98": "청록",
};

// 초 단위 값을 왜곡 없이 표시한다 — 딱 떨어질 때만 상위 단위로, 아니면 하위 단위로 내려간다.
// (예전엔 Math.round로 90초를 '2분'처럼 보여 요약이 실제 저장값과 어긋났다.)
export function fmtDuration(sec) {
  if (sec == null) return "";
  if (sec % 3600 === 0) return sec / 3600 + "시간";
  if (sec % 60 === 0) return sec / 60 + "분";
  // 정확히 시간/분 단위로 안 떨어지는 값(예: JSON 고급 편집으로 만들어진 1830초)도 raw seconds로
  // 새지 않게, 복합 단위(N시간 M분 / N분 M초)로 표시한다.
  if (sec >= 3600) { const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60); return m ? h + "시간 " + m + "분" : h + "시간"; }
  if (sec >= 60) { const m = Math.floor(sec / 60), s = sec % 60; return s ? m + "분 " + s + "초" : m + "분"; }
  return sec + "초";
}

// object 설정은 raw JSON 대신 사람이 읽을 수 있는 한국어 요약을 보여준다(읽기 전용 역할 포함).
export function summarizeSetting(key, v) {
  // 나머지 object 설정은 이미 완결된 한국어 요약('최소 12자' 등)을 보여주는데, 정수 타입인 이
  // 두 보존 기간 키만 '값' 칸에 단위 없는 맨숫자('90')로 떨어져 옆 행들과 표기가 어긋났다.
  if ((key === "conversation_retention_days" || key === "notification_retention_days" || key === "trash_retention_days") && typeof v === "number") return v + "일";
  if (v == null || typeof v !== "object") return null;
  if (key === "password_policy") {
    const parts = [];
    if (v.min_length != null) parts.push("최소 " + v.min_length + "자");
    if (v.min_classes != null) parts.push(v.min_classes + "종류 이상");
    return parts.length ? parts.join(" / ") : null;
  }
  if (key === "session_policy") {
    const parts = [];
    if (v.idle_timeout_seconds != null) parts.push("유휴 " + fmtDuration(v.idle_timeout_seconds));
    if (v.absolute_timeout_seconds != null) parts.push("최대 " + fmtDuration(v.absolute_timeout_seconds));
    return parts.length ? parts.join(", ") : null;
  }
  if (key === "lockout_policy") {
    const parts = [];
    if (v.max_failures != null) parts.push(v.max_failures + "회 실패 시 잠금");
    if (v.lock_seconds != null) parts.push(fmtDuration(v.lock_seconds) + " 동안 잠김");
    return parts.length ? parts.join(", ") : null;
  }
  if (key === "allowed_email_domains") {
    // 백엔드는 빈 목록([])을 '도메인 제한 없음'으로 허용한다, 빈 값은 그 뜻을 분명히 요약한다.
    if (Array.isArray(v)) return v.length ? "도메인: " + v.join(", ") : "제한 없음(모든 도메인 허용)";
  }
  if (key === "backup_schedule") {
    /* 백업은 **복원이 필요해진 날**에야 안 도는 것을 알게 되는 부류다 — 요약이 켜짐/꺼짐과
       주기를 한 줄로 말해 주지 않으면 관리자가 raw JSON 을 눈으로 파싱해야 한다. */
    if (!v.enabled) return "비활성";
    const parts = ["활성"];
    if (v.cron) parts.push(String(v.cron) + " (" + String(v.timezone || "Asia/Seoul") + ")");
    if (v.keep != null) parts.push(v.keep + "개 보관");
    return parts.join(", ");
  }
  if (key === "ui_branding") {
    const parts = [];
    if (v.product_name) parts.push("제품명: " + String(v.product_name));
    if (v.support_email) parts.push("지원: " + String(v.support_email));
    return parts.length ? parts.join(", ") : null;
  }
  if (key === "smtp") {
    // VIS-54: 이 case 가 없어서 backup_schedule 과 같은 object 설정인데도 요약이 없어
    // displayValue()의 잘린 raw JSON({"enabled":false,"host":"",...)으로 새어 나갔다 -
    // 다른 object 설정과 같은 "켜짐/꺼짐 + 핵심 정보" 관례로 맞춘다. 비밀번호는
    // password_ref(파일 이름)일 뿐이라 여기 보여도 값 노출이 아니다.
    if (!v.enabled) return "비활성";
    const parts = ["활성"];
    if (v.host) parts.push(String(v.host) + ":" + (v.port != null ? v.port : "?"));
    if (v.security) parts.push(String(v.security));
    if (v.from_address) parts.push("발신: " + String(v.from_address));
    return parts.join(", ");
  }
  return null;
}

// 보안을 '약화'시키는 설정 변경을 감지해 확인 문구를 돌려준다(해당 없으면 null).
// 검증만 통과하면 한 클릭으로 커밋되던 위험, 롤백, 유지보수 토글처럼 확인 단계를 둔다.
export function securityDowngradeWarning(setting, value) {
  if (setting.key === "allowed_email_domains") {
    // 빈 목록([])은 백엔드에서 '모든 도메인 허용'이라 로그인 제한이 통째로 풀린다.
    if (Array.isArray(value) && value.length === 0)
      return "허용 이메일 도메인을 비우면 도메인 제한이 사라져 모든 이메일 도메인의 로그인이 허용됩니다. 계속할까요?";
    return null;
  }
  if (setting.key === "password_policy") {
    const cur = setting.value || {};
    const reasons = [];
    if (value && cur.min_length != null && value.min_length != null && value.min_length < cur.min_length)
      reasons.push("최소 글자 수 " + cur.min_length + " → " + value.min_length);
    if (value && cur.min_classes != null && value.min_classes != null && value.min_classes < cur.min_classes)
      reasons.push("문자 종류 수 " + cur.min_classes + " → " + value.min_classes);
    if (reasons.length)
      return "비밀번호 정책을 약화합니다(" + reasons.join(", ") + "). 인증 강도가 낮아집니다, 계속할까요?";
    return null;
  }
  // 세션 제한 시간을 늘리는 것도 password_policy 약화·도메인 제한 해제와 같은 성격의 보안 완화다 —
  // 로그인 세션이 더 오래 살아남는다(탈취된 세션의 유효 기간이 늘어난다). 이전엔 이 키만 확인 없이
  // 한 클릭 저장돼 다른 두 보안 설정과 다르게 취급됐다.
  if (setting.key === "session_policy") {
    const cur = setting.value || {};
    const reasons = [];
    if (value && cur.idle_timeout_seconds != null && value.idle_timeout_seconds != null && value.idle_timeout_seconds > cur.idle_timeout_seconds)
      reasons.push("유휴 제한 " + fmtDuration(cur.idle_timeout_seconds) + " → " + fmtDuration(value.idle_timeout_seconds));
    if (value && cur.absolute_timeout_seconds != null && value.absolute_timeout_seconds != null && value.absolute_timeout_seconds > cur.absolute_timeout_seconds)
      reasons.push("최대 세션 길이 " + fmtDuration(cur.absolute_timeout_seconds) + " → " + fmtDuration(value.absolute_timeout_seconds));
    if (reasons.length)
      return "세션 정책을 완화합니다(" + reasons.join(", ") + "). 세션이 더 오래 유지됩니다. 계속할까요?";
    // 유휴 제한을 줄이는 것은 '완화'가 아니라 반대(강화)지만, 다른 위험이 있다: absolute_timeout_seconds
    // 와 달리 idle_timeout_seconds 는 세션 생성 시점에 굳지 않고 매 요청마다 그때의 설정값으로 다시
    // 계산된다(app/core/sessions.py::validate). 그래서 "신규 세션부터 적용"이 아니라 저장 즉시 이미
    // 로그인된 모든 세션에 적용되고, 유휴 상태인 사용자는(저장한 관리자 자신 포함) 그 자리에서
    // 로그아웃될 수 있다 — 늘릴 때만 확인받고 줄일 때는 조용히 저장되던 것이 비대칭이었다.
    if (value && cur.idle_timeout_seconds != null && value.idle_timeout_seconds != null && value.idle_timeout_seconds < cur.idle_timeout_seconds) {
      return "유휴 제한을 " + fmtDuration(cur.idle_timeout_seconds) + " → " + fmtDuration(value.idle_timeout_seconds)
        + " 로 줄입니다. 신규 세션부터가 아니라 저장 즉시 이미 로그인된 모든 세션에 적용되어, "
        + "유휴 상태인 사용자는(나 자신 포함) 그 자리에서 로그아웃될 수 있습니다. 계속할까요?";
    }
    return null;
  }
  // 임계값을 늘리거나(더 많은 실패를 허용) 잠금 시간을 줄이면(공격자가 더 빨리 재시도) 둘 다
  // 무차별 대입 방어를 약화한다 — password_policy/session_policy와 같은 확인 게이트.
  if (setting.key === "lockout_policy") {
    const cur = setting.value || {};
    const reasons = [];
    if (value && cur.max_failures != null && value.max_failures != null && value.max_failures > cur.max_failures)
      reasons.push("실패 허용 횟수 " + cur.max_failures + "회 → " + value.max_failures + "회");
    if (value && cur.lock_seconds != null && value.lock_seconds != null && value.lock_seconds < cur.lock_seconds)
      reasons.push("잠금 시간 " + fmtDuration(cur.lock_seconds) + " → " + fmtDuration(value.lock_seconds));
    if (reasons.length)
      return "계정 잠금 정책을 완화합니다(" + reasons.join(", ") + "). 무차별 대입(브루트포스) 공격에 더 취약해집니다, 계속할까요?";
    return null;
  }
  return null;
}

export function displayValue(v) {
  if (v == null || v === "") return "-";
  if (typeof v === "object") { const s = JSON.stringify(v); return s.length > 72 ? s.slice(0, 72) + "…" : s; }
  if (typeof v === "boolean") return v ? "활성" : "비활성";
  return String(v);
}
