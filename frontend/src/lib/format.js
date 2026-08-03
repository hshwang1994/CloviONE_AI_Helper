// 백엔드는 UTC를 naive isoformat 문자열로 준다(예: "2026-07-18T16:21:23.704973").
// tz 표기가 없으면 UTC로 간주해 Z를 붙이고, 화면에는 Asia/Seoul로 표시한다(불변규칙 §9).
const KST = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", dateStyle: "medium", timeStyle: "short",
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

// 시:분(HH:MM) — 채팅 말풍선 시각용.
export function fmtTimeShort(v) {
  const d = toUTCDate(v);
  if (!d) return "";
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
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
};
export const VERB_KO = {
  create: "생성", update: "수정", delete: "삭제", enable: "활성화", disable: "비활성화",
  archive: "보관", unarchive: "복구", approve: "승인", reject: "거절", cancel: "취소",
  transition: "상태 변경", rollback: "롤백", grant: "부여", revoke: "회수", map: "연결",
  manual_map: "수동 연결", unmap: "연결 해제", sync: "동기화", run: "실행", verify: "검증",
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
  // 기한(SLA)을 넘긴 대기 승인 — 워커가 관리자에게 한 번만 보낸다(0033, app/approvals/delegation.py).
  // 만료(approval_expired)와 다른 사건이다: 만료는 요청이 죽은 것이고, 이건 아직 살아 있는데 늦은 것이다.
  approval_overdue: "승인 기한 초과",
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
};
export const typeKo = (t) => (t == null || t === "" ? "알림" : (TYPE_KO[t] || "알림"));
// 장애/실패류 알림 유형 — 나머지(승인 결정, 점검 공지 등 정보성)와 시각적으로 구분해야
// 뒤섞인 목록에서 급한 것부터 훑을 수 있다(NotificationBell 팝오버, product-quality-audit AREA=D).
export const NOTI_FAILURE_TYPES = new Set(["account_locked", "job_failed", "schedule_failed", "runner_unavailable"]);
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
