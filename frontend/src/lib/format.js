// 백엔드는 UTC를 naive isoformat 문자열로 준다(예: "2026-07-18T16:21:23.704973").
// tz 표기가 없으면 UTC로 간주해 Z를 붙이고, 화면에는 Asia/Seoul로 표시한다(불변규칙 §9).
const KST = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", dateStyle: "medium", timeStyle: "short",
});

// 시:분만(채팅 말풍선용) — timeZone을 안 주면 브라우저 로컬 시간대로 나간다(발견: 2026-08-15
// whole-product 재감사, 다른 두 곳이 KST를 안 박고 있었다). KST 없는 로컬이 어긋나는 사람은
// 실제로 있다(VPN·해외 출장·시계를 안 맞춘 PC) — 그 사람에게만 팀 채팅 말풍선 시각이 몇 시간
// 밀려 보인다.
const KST_TIME_ONLY = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit",
});

export function fmtDateTime(v) {
  if (v == null || v === "") return "-";
  const s = String(v);
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return s;
  return KST.format(d);
}

// 백엔드 naive-UTC iso 를 Date 로 — tz 표기가 없으면 UTC로 간주해 Z를 붙인다(로컬 오해 방지).
export function toUTCDate(v) {
  if (v == null || v === "") return null;
  const s = String(v);
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/* ── `<input type="datetime-local">` ↔ API 경계 (F14) ────────────────────────
 *
 * `datetime-local` 은 **시간대가 없는 벽시계 문자열**("2026-08-10T09:00")을 준다. 이 앱에서
 * 사람이 읽고 쓰는 시각은 언제나 KST 다(§불변 9). 반면 저장소 규약은 **naive UTC** 다 —
 * 서버는 오프셋 없는 값을 UTC 로 읽는다. 그래서 벽시계를 그대로 보내면 9시간 밀린다:
 * '09:00 부터'로 지정한 공지가 실제로는 KST 18:00 에 떴다.
 *
 * 규약을 깨지 않고 **경계에서 변환**한다(app/home/service.py::window_utc_bounds 와 같은 발상).
 * 두 함수가 서로의 역이고, 필터 경로(DataScreen.buildUrl)와 폼 경로(kit FormModal)가 같은
 * 정의를 쓴다 — 한쪽만 고치면 다시 갈라진다.
 *
 * 오프셋을 "+09:00" 리터럴로 둔다: 한국은 서머타임이 없어 연중 고정이고, 저장소가 이미
 * 같은 값을 쓴다(app/audit/router.py 의 KST 경계 해석). */
const KST_OFFSET = "+09:00";
const KST_PARTS = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Seoul", hour12: false,
  year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
});

/** KST 벽시계("YYYY-MM-DDTHH:mm") → 서버가 순간으로 읽을 수 있는 오프셋 포함 ISO-8601. */
export function kstLocalToApi(v) {
  if (v == null || v === "") return v;
  const s = String(v);
  // 이미 시간대가 붙어 있으면 손대지 않는다(다른 경로가 만든 값일 수 있다).
  if (/[zZ]$|[+-]\d\d:?\d\d$/.test(s)) return s;
  return (/T\d\d:\d\d$/.test(s) ? s + ":00" : s) + KST_OFFSET;
}

/** 서버의 naive UTC iso → `datetime-local` 이 그대로 쓸 수 있는 KST 벽시계 문자열. */
export function apiToKstLocal(v) {
  const d = toUTCDate(v);
  if (!d) return "";
  const p = {};
  for (const part of KST_PARTS.formatToParts(d)) p[part.type] = part.value;
  // en-CA 는 24시 표기에서 자정을 "24" 로 낼 수 있다 — 입력칸이 거부하는 값이라 되돌린다.
  const hour = p.hour === "24" ? "00" : p.hour;
  return `${p.year}-${p.month}-${p.day}T${hour}:${p.minute}`;
}

/* 표 셀용 압축 표기 — `2026-08-18 15:33`.
 *
 * 산문에서는 `2026. 8. 18. 오후 3:33`(ko-KR medium+short)이 자연스럽지만, 표에서는 그
 * 표기가 21자라 좁은 열에서 두 줄로 접힌다(admin_users 1920 실측). 접힌 날짜는 행 높이를
 * 들쭉날쭉하게 만들고 세로로 훑을 수 없게 한다 — 표의 존재 이유가 비교인데 그것이 안 된다.
 *
 * 24시간제 + 고정 자릿수라 자리마다 같은 뜻이고, `tabular-nums` 와 함께 쓰면 위아래 숫자가
 * 정확히 겹쳐 보인다. 변환 자체는 `apiToKstLocal`(폼 입력용 KST 벽시계)과 **같은 규약**을
 * 쓴다 — 같은 순간을 두 곳에서 다르게 계산하지 않는다. */
export function fmtDateTimeCompact(v) {
  if (v == null || v === "") return "-";
  const local = apiToKstLocal(v);
  if (!local) return String(v);
  return local.replace("T", " ");
}

// 시:분(HH:MM) — 채팅 말풍선 시각용.
export function fmtTimeShort(v) {
  const d = toUTCDate(v);
  if (!d) return "";
  return KST_TIME_ONLY.format(d);
}

// 상대 시간(방금/N분 전/N시간 전/N일 전) — 좁은 알림 팝오버처럼 훑어보는 피드용.
// 7일이 넘거나 미래 값이면 절대 시각으로 폴백한다. 전체 목록/상세는 절대 시각(fmtDateTime)을 쓴다.
export function fmtRelative(v) {
  if (v == null || v === "") return "-";
  const s = String(v);
  const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return s;
  const sec = Math.round((Date.now() - d.getTime()) / 1000);
  if (sec < 0) return fmtDateTime(v);
  if (sec < 60) return "방금 전";
  const min = Math.round(sec / 60);
  if (min < 60) return min + "분 전";
  const hr = Math.round(min / 60);
  if (hr < 24) return hr + "시간 전";
  const day = Math.round(hr / 24);
  if (day < 7) return day + "일 전";
  return fmtDateTime(v);
}

// 짧은 기기/브라우저 표기 — user-agent 원문은 너무 길어 표·카드를 망가뜨린다. Users.jsx(관리자의
// 다른 사용자 세션 목록)에만 있었다가 Profile.jsx(내 기기 목록)로도 쓰이며 공용으로 옮겼다 —
// 후자는 원문을 자르지도, 전체 문구를 Tooltip으로 보존하지도 않아 긴 UA가 카드 레이아웃을 밀어냈다.
export function shortUA(ua) {
  if (!ua) return "-";
  const s = String(ua);
  return s.length > 60 ? s.slice(0, 60) + "…" : s;
}

// 감사/승인 enum 한국어화 — "대상.동작" 꼴을 대상/동작으로 나눠 번역(감사 로그·대시보드·승인 공용).
export const OBJECT_KO = {
  user: "사용자", integration: "외부 연동", runner: "러너", workflow: "워크플로", prompt: "프롬프트",
  policy: "정책", template: "템플릿", schedule: "스케줄", approval: "승인", backup: "백업",
  setting: "설정", conversation: "대화", user_notion_mapping: "Notion 연결", notion_mapping: "Notion 연결",
  notification: "알림", document: "문서", job: "작업", role: "역할", session: "세션", auth: "인증",
  department: "부서", job_title: "직책", "job-title": "직책", message: "메시지",
  schedule_run: "예약 실행",
  // 백엔드가 실제로 저장하는 object_type 문자열(복수형·접미 포함) — 없으면 감사/대시보드 '대상'
  // 칸에 영어 원문이 새어 나온다(예: 'prompts', 'document_generation').
  prompts: "프롬프트", policies: "정책", app_setting: "설정", document_generation: "문서",
  // organization/feature_flag는 OBJ_ROUTE(registry/shared.js)에 먼저 추가됐지만 여기(표시용
  // 사전)엔 한 번도 안 들어와 있었다 — 감사 로그 '대상' 칸에 영어 원문이 샜다. ai_quota/
  // approval_delegation/announcement/offboarding(액션 접두사)/offboarding_run(object_type)은
  // MEGA CYCLE G에서 크로스링크와 함께 발견(같은 결함 부류, 표시만 다르다).
  organization: "조직", feature_flag: "기능 플래그", ai_quota: "AI 사용 상한",
  approval_delegation: "승인 위임", announcement: "공지", offboarding: "오프보딩",
  offboarding_run: "오프보딩",
};
export const VERB_KO = {
  create: "추가", update: "수정", delete: "삭제", enable: "활성화", disable: "비활성화",
  archive: "보관", unarchive: "복구", approve: "승인", reject: "거절", cancel: "취소",
  transition: "상태 변경", rollback: "롤백", grant: "부여", revoke: "회수", map: "연결",
  manual_map: "수동 연결", unmap: "연결 해제", sync: "동기화", run: "실행", undo: "되돌리기", verify: "검증",
  test: "테스트", login: "로그인", login_failed: "로그인 실패", logout: "로그아웃", unlock: "잠금 해제",
  reset_password: "비밀번호 재설정", "reset-password": "비밀번호 재설정",
  "revoke-sessions": "세션 해제", "new-version": "새 버전", "resolve-conflict": "충돌 해결",
  role_change: "역할 변경", change_config: "설정 변경", role_grant: "역할 부여",
  // 라우터가 실제로 쓰는 언더스코어 동작명(감사 로그) — 없으면 '작업' 칸에 영어 원문이 샌다.
  update_content: "내용 수정", new_version: "새 버전", revoke_sessions: "세션 해제", set_role: "역할 변경",
  // 승인/요청·CLI·기타 동작(감사 로그에 실제로 나타나는 값)
  change_requested: "변경 요청", rollback_requested: "롤백 요청", enable_requested: "활성화 요청",
  disable_requested: "비활성화 요청", role_change_requested: "역할 변경 요청",
  generate_requested: "생성 요청", generate: "생성 요청", resolve_conflict: "충돌 해결",
  retry_run: "실행 재시도", run_now: "지금 실행", clone: "복제", retry: "재시도",
  preview: "미리보기", publish: "발행", archive_expired: "만료 보관",
  restore: "복원", backup: "백업",
  // app/auth/router.py가 실제로 기록하는 본인 비밀번호 변경 감사 동작 — 없으면 감사 로그의
  // '작업' 칸이 "사용자, password_change_self"처럼 절반만 번역된 채 노출된다.
  password_change_self: "비밀번호 변경(본인)",
  // app/auth/router.py가 본인 비밀번호 변경 실패마다 기록하는 감사 동작(result="failure") —
  // 매핑이 없으면 감사 로그에서 가장 보안상 중요한 이벤트 중 하나가 raw 영어로 샌다
  // (product-quality-audit AREA=D).
  password_change_failed: "비밀번호 변경 실패",
};

// 잡(job) 유형(job_type) → 한국어. 예전엔 이 표가 registry(JOB_TYPE)에만 있어 Ops.jsx(진단)의
// '최근 작업 오류'가 raw 영어 enum(chat_message 등)을 그대로 노출했다. 여기 하나로 모아 공용화한다.
// 실제 enqueue되는 job_type만 담고(backup은 큐에 없지만 감사/기타 경로에서 새어 나오지 않게 함께 둠),
// 알 수 없는 유형은 raw 값으로 폴백한다.
export const JOB_TYPE_KO = {
  chat_message: "채팅 메시지", document_generate: "문서 생성", notion_mapping_sync: "Notion 동기화",
  schedule_run: "예약 실행", notion_sync: "Notion 동기화", backup: "백업",
};
export const jobTypeKo = (t) => (t == null || t === "" ? "-" : (JOB_TYPE_KO[t] || String(t)));

// 알림 유형(type) → 한국어. 예전엔 이 표가 NotificationBell(TYPE_KO)과 registry(NOTI_TYPE)에
// 따로 있어 서로 어긋났다(같은 유형이 벨과 목록에서 다르게 표시). 여기 하나로 모아 양쪽이 참조한다.
// 백엔드(notify_user/notify_admins)가 실제로 내보내는 유형만 담는다 — approval_approved/
// approval_rejected/document_ready/system 등은 발신되지 않아 표에 남기면 '온 적 없는 알림'을 암시한다.
// (product-quality-audit AREA=D/E: 이전엔 runner_unavailable/maintenance_announcement/
// password_change_required 세 개가 실제로 발신됨에도 빠져 있어 이 주석 자체가 틀렸었다 —
// app/runners/service.py:222, app/settings/router.py:71, app/users/service.py:361.)
export const TYPE_KO = {
  account_locked: "계정 잠금", job_failed: "작업 실패", approval_requested: "승인 요청",
  approval_decided: "승인 결정", approval_expired: "승인 만료", schedule_failed: "스케줄 실패",
  // 요청자 본인이 아니라 admin/system_admin이 남의 대기 요청을 대신 취소했을 때만 간다
  // (본인이 취소했으면 이미 알고 있어 안 보낸다, app/approvals/service.py::cancel).
  approval_cancelled: "승인 취소",
  // 기한(SLA)을 넘긴 대기 승인 — 워커가 관리자에게 한 번만 보낸다(0033, app/approvals/delegation.py).
  // 만료(approval_expired)와 다른 사건이다: 만료는 요청이 죽은 것이고, 이건 아직 살아 있는데 늦은 것이다.
  approval_overdue: "승인 기한 초과",
  // 위임받은 사실 자체를 당사자에게 알린다(X7). 예전에는 통보가 없어 자기에게 권한이
  // 생긴 줄도 몰랐다 — 여기 빠뜨리면 알림 목록에 원시 코드가 그대로 보인다.
  approval_delegated: "승인 권한 위임",
  runner_unavailable: "러너 장애", maintenance_announcement: "점검 공지",
  password_change_required: "비밀번호 변경 필요",
  // 그룹 채팅 생성·1:1 대화 시작 시 초대된 본인에게 간다(app/team_chat/service.py의
  // _notify_invited). related=("chat_room", room_id) 이고, 벨은 서버가 계산한
  // related_route(#/chat-rooms/<id>)로 그 방을 바로 연다.
  chat_invited: "채팅 초대",
  // 채팅 본문에서 `@내이름`으로 불렸을 때(app/team_chat/service.py의 notify_mentions).
  // related=("chat_mention", room_id) — 경로 계산은 서버 표(destinations.py)가 한다.
  // **이 표는 이름표일 뿐 경로가 아니다.** 유형이 늘어도 벨에 분기를 더하지 않는 이유다.
  chat_mentioned: "멘션",
  // ── 알림 5종 신설(X9 + §E-6 N2) ───────────────────────────────────────────
  // 서버(app/profiles/prefs.py의 NOTIFICATION_TYPES)와 짝이 맞아야 한다. 여기 빠지면
  // 알림 목록 화면이 영문 키를 그대로 노출한다 — registry.js의 mapCol은 표에 없는 값을
  // raw 문자열로 폴백하기 때문이다(벨의 typeKo는 "알림"으로 뭉개서 더 알기 어렵다).
  //
  // 담당자로 **새로** 지정된 사람에게 간다(app/tickets/service.py의 _notify_assignees_added).
  // related=("ticket", page_id)이고 경로 계산은 서버 표(destinations.py)가 한다.
  ticket_assigned: "티켓 배정",
  // 큐를 거쳐 만들어진 문서가 준비됐을 때 요청자에게(app/jobs/handlers/document_generate.py).
  document_ready: "문서 생성 완료",
  // 퇴사자의 티켓·방을 넘겨받은 후임에게 **요약 한 건**(app/offboarding/service.py).
  offboarding_handover: "업무 인수",
  // 이번 기간의 AI 호출 상한을 다 쓴 순간 본인에게(app/quotas/service.py).
  ai_quota_exhausted: "AI 사용 상한 도달",
  // 예약 백업 실패를 관리자에게(app/backups/service.py). 메일과 별개로 앱 안에도 남긴다.
  backup_failed: "백업 실패",
};
export const typeKo = (t) => (t == null || t === "" ? "알림" : (TYPE_KO[t] || "알림"));
// 장애/실패류 알림 유형 — 나머지(승인 결정, 점검 공지 등 정보성)와 시각적으로 구분해야
// 뒤섞인 목록에서 급한 것부터 훑을 수 있다(NotificationBell 팝오버, product-quality-audit AREA=D).
// backup_failed 도 여기 든다 — 백업이 멈춘 것은 정보성 공지가 아니라 오늘 손써야 하는 장애다.
export const NOTI_FAILURE_TYPES = new Set(["account_locked", "job_failed", "schedule_failed", "runner_unavailable", "backup_failed"]);
export const objKo = (v) => (v == null || v === "" ? "-" : (OBJECT_KO[v] || String(v)));
// "대상.동작" 및 다중 세그먼트(cli.user.enable, user.role_change_requested)를 한국어로.
export const actionKo = (v) => {
  if (v == null || v === "") return "-";
  let s = String(v), cli = false;
  if (s.startsWith("cli.")) { cli = true; s = s.slice(4); }
  const i = s.lastIndexOf(".");
  let out;
  if (i < 0) out = VERB_KO[s] || OBJECT_KO[s] || s;
  else {
    const obj = s.slice(0, i), verb = s.slice(i + 1);
    const objTxt = OBJECT_KO[obj] || obj, verbTxt = VERB_KO[verb] || verb;
    // 대상·동작이 같은 한국어로 번역되는 조합(예: approval.approve → "승인"·"승인")은
    // "승인, 승인"처럼 중복 노출된다 — 하나만 남기고 완료를 뜻하는 "됨"을 붙인다.
    out = objTxt === verbTxt ? objTxt + "됨" : objTxt + ", " + verbTxt;
  }
  return cli ? out + " (CLI)" : out;
};

/* 사람 한 명의 소속을 한 줄로 — 서버 `core/people.affiliation` 과 같은 규칙.
 *
 * 사용자 지시: "채팅·대화·**댓글 작성**에서 어느 조직 어느 부서인지 나와야 한다."
 * 서버는 이미 `people` payload 를 통째로 보내는데 **프런트가 한 번도 안 읽고 있었다**(N4) —
 * 같은 이름 두 사람이 한 방에서 대화하면 말풍선만으로는 구분할 수 없었다.
 * 지시의 나머지 절반("댓글 작성")은 게시판이다 — 목록·글 상세·댓글이 `Board.jsx::AuthorLine`
 * 하나로 같은 규칙을 쓴다. 화면마다 소속을 다르게 조립하면 그때부터 또 어긋난다.
 *
 * 구분자로 가운뎃점을 쓰지 않는다(이 제품에서 그 문자를 화면에 쓰지 않기로 했다).
 */
export function affiliationOf(person, { withOrg = false } = {}) {
  if (!person) return "";
  const parts = [];
  if (withOrg && person.org) parts.push(person.org);
  if (person.dept) parts.push(person.dept);
  if (person.title) parts.push(person.title);
  return parts.join(" ");
}

/* 일괄 작업 부분 실패 토스트의 꼬리 문장 (UA-25).
 *
 * 휴지통·티켓·문서의 일괄 이동/복원/영구삭제는 모두 건별로 실패 사유를 이미
 * `{id, error}`로 돌려주는데(예: 이미 처리됨·권한 없음·Notion 보관 실패), 화면 쪽이
 * 그 사유를 안 보고 "권한이 없어"로 뭉개 놨었다 — Notion 장애로 실패해도 권한 문제로
 * 보여 관리자가 계정을 바꿔 재시도하는 헛수고를 시켰다. 사유가 여러 종류로 섞여도
 * 첫 번째만 보여준다(UsersBulk.jsx의 기존 관용과 같다: 실패를 성공 토스트로 덮지
 * 않되 전체 사유 분해까지는 안 한다).
 */
export function bulkFailureNote(failed) {
  const list = failed || [];
  if (!list.length) return "";
  const reason = (list[0] && list[0].error) || "권한이 없습니다.";
  return ` ${list.length}건은 건너뛰었습니다: ${reason}`;
}

/* 보관된(퇴사한) 계정임을 화면이 말한다 (N3). */
export const ARCHIVED_SUFFIX = "(보관됨)";
