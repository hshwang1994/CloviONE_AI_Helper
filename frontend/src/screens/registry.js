import React from "react";
import { badgeCol, mapCol, dateCol, jsonField, objectField, readCol, linkCol, listField, previewField, activeCol, truncateCol } from "./DataScreen.jsx";
import { objKo, actionKo, fmtDateTime, TYPE_KO } from "../lib/format.js";
import { Badge } from "../ui/kit.jsx";

// 바이트 크기를 사람이 읽을 수 있게(백업 크기 등). null이면 '-'.
const fmtBytes = (n) => {
  if (n == null || n === "") return "-";
  const b = Number(n);
  if (!isFinite(b)) return String(n);
  if (b < 1024) return b + " B";
  const u = ["KB", "MB", "GB", "TB"]; let v = b / 1024, i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return (Math.round(v * 10) / 10) + " " + u[i];
};

const SCHED_RUN = { queued: "대기", running: "실행 중", succeeded: "성공", failed: "실패", skipped: "건너뜀" };
// 감사 로그 대상 필터 옵션 — 값은 백엔드가 실제로 저장하는 object_type 문자열과 정확히 일치해야 한다
// (백엔드가 == 정확 일치로 필터하므로 어긋나면 항상 0건). prompt/policy/setting/document는 복수형·접미
// 형태로 저장되고('prompts'/'policies'/'app_setting'/'document_generation'), 'role'은 저장되지 않는다.
const OBJTYPE_OPTS = [["user", "사용자"], ["integration", "외부 연동"], ["runner", "러너"], ["workflow", "워크플로"],
  ["prompts", "프롬프트"], ["policies", "정책"], ["template", "템플릿"], ["schedule", "스케줄"], ["schedule_run", "예약 실행"],
  ["approval", "승인"], ["backup", "백업"], ["app_setting", "설정"], ["document_generation", "문서"],
  ["user_notion_mapping", "Notion 연결"], ["job", "작업"], ["department", "부서"], ["job_title", "직책"]]
  .map((p) => ({ value: p[0], label: p[1] }));
const field = (key, label) => ({ key, label });               // 상세 전용 평문 필드
const objField = (key, label) => ({ key, label, render: (r) => objKo(r[key]) });

/* 목록 화면 설정 — 열/엔드포인트만 다르고 렌더는 DataScreen이 공통 처리한다.
 * 상태 열은 badgeCol(배지), enum 열은 mapCol/actionKo(한국어)로. 값은 서버 계약 그대로. */
const PROVIDER = { n8n: "n8n", http_service: "HTTP 서비스", notion_via_n8n: "Notion(n8n 경유)" };
const WF_MODE = { read: "읽기", write: "쓰기" };
const SCHED_TYPE = { cron: "Cron 반복", once: "1회 실행" };
const DOC_MODE = { preview_then_approve: "미리보기 후 승인", preview_only: "미리보기만", auto_publish: "자동 발행" };
const MAP_SOURCE = { workflow: "워크플로 자동", manual: "수동 지정" };
// 실제 enqueue되는 job_type 문자열과 정확히 일치해야 한다(chat_message·document_generate·notion_mapping_sync).
// 실제 enqueue되는 job_type만 매핑한다(backup은 큐에 없어 제거 — 오해 방지).
const JOB_TYPE = { chat_message: "채팅 메시지", document_generate: "문서 생성", notion_mapping_sync: "Notion 동기화", schedule_run: "예약 실행" };
const RUNNER_MAINT_OPTS = [["normal", "정상"], ["degraded", "성능 저하"], ["maintenance", "점검"]].map((p) => ({ value: p[0], label: p[1] }));

// 감사/승인 enum 한국어화는 공용 lib/format.js(objKo·actionKo)에서 온다.
const objCol = (key, label) => ({ key, label, render: (r) => objKo(r[key]) });
// title 속성으로 원문 action 문자열을 마우스 오버 시 보여준다 — 감사 로그의 '작업' 필터는 이
// 원문과 정확히 일치해야 하는데(정확 일치 필터), 열은 한국어 번역만 보여줘서 필터에 뭘 입력해야
// 할지 목록만 보고는 알 방법이 없었다(truncateCol이 이미 쓰는 title 힌트 패턴과 동일).
const actionCol = (key, label) => ({ key, label, render: (r) => React.createElement("span", { title: r[key] }, actionKo(r[key])) });

const col = (key, label) => ({ key, label });
const opt = (pairs) => pairs.map((p) => ({ value: p[0], label: p[1] }));
// 백엔드 허용값과 정확히 일치해야 한다(none/bearer/api_key_header) — 옛 header/basic은 422였다.
const AUTH_OPTS = opt([["none", "없음"], ["bearer", "Bearer 토큰"], ["api_key_header", "API 키(헤더)"]]);
const PROVIDER_OPTS = opt([["http_service", "HTTP 서비스"], ["n8n", "n8n"], ["notion_via_n8n", "Notion(n8n 경유)"]]);
const WFMODE_OPTS = opt([["read", "읽기"], ["write", "쓰기"]]);
// 워크플로 백엔드는 POST/GET만 허용한다(WorkflowConfig._method_known).
const HTTP_OPTS = opt([["POST", "POST"], ["GET", "GET"]]);
const SCHEDT_OPTS = opt([["cron", "Cron 반복"], ["once", "1회 실행"]]);
// 간편 주기 — 고르면 백엔드가 Cron 식을 생성한다(cron.PRESETS). 빈 값은 '직접 입력'.
const SCHED_PRESET_OPTS = opt([["", "사용 안 함(직접 입력)"], ["daily", "매일"], ["weekly", "매주"], ["monthly", "매월"]]);
// 스케줄 고급 정책 — 백엔드 허용값과 정확히 일치(misfire: skip/run_once, concurrency: skip/allow).
const MISFIRE_OPTS = opt([["skip", "건너뛰기(skip)"], ["run_once", "한 번만 실행(run_once)"]]);
const CONCURRENCY_OPTS = opt([["skip", "건너뛰기(skip)"], ["allow", "동시 실행 허용(allow)"]]);
// 'runner' 대상은 target_ref가 가리키는 워크플로 실행 경로만 백엔드가 소비하지 않는다
// (apply_template_bindings의 워크플로 재지정은 target_type===workflow일 때만 동작 —
// app/documents/service.py). 반면 prompt_id/policy_id/input_schema/approval_policy 바인딩은
// target_type과 무관하게 config.template_id로 여전히 적용된다 — '아무 효과 없음'이 아니라
// '대상 워크플로 재지정만' 안 되는 것이다. 그래도 이 화면의 '이 템플릿으로 문서 생성' 버튼은 대상
// 워크플로가 필요하므로(templates.actions 참고) 신규 생성은 워크플로만 선택 가능하게 한다.
const TARGET_OPTS = opt([["workflow", "워크플로"]]);
// 백엔드는 템플릿의 target_type=runner도 검증·저장은 해 주고(app/templates/router.py), 실제로
// prompt/policy/입력 스키마/승인 정책 바인딩도 target_type과 무관하게 계속 적용한다(위 주석 참고) —
// 다만 apply_template_bindings의 대상 워크플로 재지정만 target_type==workflow일 때만 동작한다.
// '이 템플릿으로 문서 생성' 버튼이 대상 워크플로를 필요로 하므로, 신규 생성은 워크플로만 선택
// 가능하게 한다(기존 러너 대상 행은 detailFields의 _runner_target_note로 별도 안내).
const TEMPLATE_TARGET_OPTS = TARGET_OPTS;
const SCHED_TARGET_OPTS = opt([["workflow", "워크플로"], ["system", "시스템"]]);
// 상태 변경(쓰기) 액션 role 게이트 — 백엔드 RBAC와 일치시켜 읽기 전용 역할(operator/auditor)에게
// 항상 403이 되는 버튼을 애초에 숨긴다(DataScreen canDo가 a.roles로 필터).
const WRITE_ROLES = ["admin", "system_admin"];            // 생성/수정/onoff/발행/롤백/승인·거절/동기화 등
const OPS_ROLES = ["operator", "admin", "system_admin"];  // 운영성 액션(헬스/테스트/지금 실행/작업 재시도·취소 등)
// 관리 콘솔 역할(일반 사용자 role=user 제외) — 알림의 '관련 항목 보기'처럼 관리자 해시 경로로만
// 이동하는 액션을 일반 사용자에게 숨긴다(일반 사용자가 누르면 채팅으로 튕겨 나간다).
const ADMIN_VIEW_ROLES = ["operator", "admin", "system_admin", "auditor"];
// 생성 권한이 없는 역할(operator/auditor)에게는 렌더되지도 않는 '+ 추가' 버튼을 누르라고 안내하지 않는다.
// 쓰기 역할(admin/system_admin)에겐 CTA 안내를, 그 외엔 읽기 전용 안내를 준다(schedules/documents/backup 패턴).
const writerEmptyHelp = (writerMsg, readerMsg) => (role) => (role === "admin" || role === "system_admin") ? writerMsg : readerMsg;
// 알림의 관련 대상(related_object_type) → 해당 관리 화면 해시 경로(문서 화면 navigate 방식과 동일).
// 값은 REGISTRY 키(App.jsx가 "/"+key로 라우팅) 및 별도 화면(users/settings) 경로와 일치해야 한다.
const OBJ_ROUTE = {
  integration: "#/integrations", runner: "#/runners", workflow: "#/workflows",
  prompts: "#/prompts", policies: "#/policies", template: "#/templates",
  schedule: "#/schedules", schedule_run: "#/schedules", approval: "#/approvals",
  backup: "#/backup", document_generation: "#/documents", document: "#/documents",
  user_notion_mapping: "#/notion-mapping", job: "#/jobs",
  department: "#/departments", job_title: "#/job-titles", user: "#/users",
  app_setting: "#/settings",
};
// OBJ_ROUTE 대상 화면 중 일부는 App.jsx의 SCREEN_ROLES로 더 좁게 제한된다(예: 사용자·부서·직책은
// admin/system_admin만, 작업 큐는 operator/admin/system_admin만 — auditor 제외). '관련 항목 보기'가
// 그 화면에 못 들어가는 역할에게도 똑같이 노출되면 클릭 즉시 403 막다른 길이 된다 — 여기 없는
// object_type은 대상 화면이 role 제한이 없어(App.jsx SCREEN_ROLES 미지정) 그대로 둔다.
const OBJ_ROUTE_ROLES = { user: WRITE_ROLES, department: WRITE_ROLES, job_title: WRITE_ROLES, job: OPS_ROLES };
const canReachObjRoute = (objType, role) => !OBJ_ROUTE_ROLES[objType] || (role != null && OBJ_ROUTE_ROLES[objType].includes(role));
// 대상 화면 중 일부는 이제 id 기반 딥링크(onQuery: p.<param> → 상세 드로어를 곧바로 연다)를 지원한다
// (runners: ?id=, jobs: ?job_id=, notion-mapping: ?user_id= — 이 셋은 object_id가 곧 그 파라미터 값).
// workflow/integration/schedule/document_generation도 각 화면이 이제 ?id= 딥링크(onQuery)를 지원해
// 여기 추가한다(runners와 동일한 패턴 — 백엔드 GET .../{id} 단건 조회가 이미 존재함).
// 여기 없는 object_type은 대상 화면에 그런 딥링크가 없어 여전히 목록 전체로만 이동한다.
// document_generation과 document는 둘 다 OBJ_ROUTE에서 같은 문서 화면(#/documents)을 가리키는
// object_type 별칭이다(감사/알림은 'document_generation', 승인의 object_type은 'document') — 문서
// 화면의 onQuery가 둘 다 ?id=를 같은 방식으로 소비하므로 두 별칭 모두 등록해 어느 쪽에서 와도 동작한다.
const OBJ_ID_PARAM = { runner: "id", job: "job_id", user_notion_mapping: "user_id",
  workflow: "id", integration: "id", schedule: "id", document_generation: "id", document: "id",
  approval: "id", template: "id",
  // prompts/policies는 이름 기준 버전 관리 화면이지만 각 버전 행의 id로도 상세를 곧바로 연다
  // (onQuery: { open: 'select', id }가 GET /{id}로 단건 조회 — nameVersionsAction과 별개 경로).
  // 감사/알림의 '관련 항목 보기'가 이 두 object_type만 빠져 있어 늘 '관련 목록 열기'로 격하됐었다.
  prompts: "id", policies: "id" };
const objRouteHref = (objType, objId) => {
  const base = OBJ_ROUTE[objType];
  const param = OBJ_ID_PARAM[objType];
  return (base && param && objId != null && objId !== "") ? base + "?" + param + "=" + encodeURIComponent(objId) : base;
};
// 이름이 곧 계약인 워크플로 — 편집·비활성화가 실제로는 그 시스템에 영향을 주지 않거나(채팅), 다른
// 모듈이 정확 일치로 찾는 식별자다(Notion 동기화). 이 화면만 보면 '평범한 워크플로 하나'로 보이지만
// 실제로는 특별 취급해야 한다 — 상세에 경고를 보여준다(app/workflows/service.py:152,161,165 참고).
// 이 두 행도 '수정'으로 값을 고칠 수 있다(백엔드 PATCH가 지원) — 다만 다른 모듈이 정확 일치로
// 찾는 계약 식별자인 '이름'만은 이 화면에서 바꿀 수 없게 편집 폼에서 뺀다(그 외 수신 주소·용도·
// 담당자·태그·모드는 편집 가능). 이름 변경이 꼭 필요하면 시스템 관리자에게 문의한다.
const RESERVED_EDIT_HINT = " ‘수정’에서 수신 주소, 용도, 담당자, 태그, 모드는 바꿀 수 있지만, 이름(다른 모듈이 계약으로 찾는 식별자)은 이 화면에서 바꿀 수 없습니다, 이름 변경이 꼭 필요하면 시스템 관리자에게 문의하세요.";
const RESERVED_WORKFLOW_NOTES = {
  "ClovirONE AI 업무 도우미": "이 행은 실제 채팅이 사용하는 수신 주소입니다, 여기서 수신 주소를 바꾸거나 비활성화하면 전 사용자의 채팅이 즉시 멈춥니다(미시딩된 새 설치에서만 서버 기본값으로 대체됩니다). 변경, 비활성화는 반드시 확인 후 진행하세요." + RESERVED_EDIT_HINT,
  "notion-user-mapping": "이 이름은 'Notion 사용자 연결' 화면의 자동 동기화, 검증이 정확히 일치시켜 찾는 식별자입니다. 이름을 바꾸거나 비활성화하면 전 사용자의 Notion 매핑 조회가 조용히 멈추고(오류: 'Notion 매핑 Workflow가 구성/활성화되지 않았습니다'), 자동 동기화도 이 워크플로를 더 이상 찾지 못합니다." + RESERVED_EDIT_HINT,
};
// 위 예약 워크플로는 비활성화가 실제 서비스를 멈춘다 — onoff() 공통 확인 문구 대신 행별 강한 경고를 준다.
const reservedDisableConfirm = (r) => RESERVED_WORKFLOW_NOTES[r.name]
  ? RESERVED_WORKFLOW_NOTES[r.name] + "\n\n정말 비활성화하시겠습니까?"
  : "비활성화하시겠습니까?";
// 백업 오류는 SQLite/파일시스템 원시 예외 문자열을 그대로 담아 온다 — 알려진 사유 코드만 한국어로
// 치환하고, 그 외(원시 예외 등)는 원문을 그대로 보여준다(정보 손실 방지).
const BACKUP_REASON_KO = { file_missing: "백업 파일 없음", checksum_mismatch: "체크섬 불일치", database_error: "데이터베이스 오류", integrity_check: "무결성 검사 실패" };
const backupReasonText = (raw) => {
  if (raw == null || raw === "") return "";
  const s = String(raw);
  const key = Object.keys(BACKUP_REASON_KO).find((k) => s === k || s.startsWith(k + ":") || s.startsWith(k + "="));
  return key ? BACKUP_REASON_KO[key] : s;
};
// 스케줄 실행이 건너뛰어질 때(app/schedules/scheduler.py _record_skip) error_message에 알려진 사유
// 코드를 그대로 담아 온다 — backupReasonText와 동일한 패턴으로 한국어로 치환하고, 그 외(실제 예외
// 메시지 등)는 원문을 그대로 보여준다(정보 손실 방지).
const SCHED_SKIP_REASON_KO = { misfire_skip: "누락(정책: 건너뛰기)", concurrent_run_active: "이미 실행 중이라 건너뜀" };
const schedSkipReasonText = (raw) => {
  if (raw == null || raw === "") return "-";
  const s = String(raw);
  return SCHED_SKIP_REASON_KO[s] || s;
};
// 사용자 화면(Users.jsx)의 ROLE_KO와 동일한 5개 역할 라벨 — 승인 화면이 user.role_change 요청의
// request_payload(role/previous_role)를 렌더할 때 raw 값이 아니라 이 라벨을 보여주는 데 쓴다.
const ROLE_KO = { user: "일반 사용자", operator: "운영자", auditor: "감사자", admin: "관리자", system_admin: "시스템 관리자" };
// 승인 요청 내용(request_payload)의 최상위 키를 한국어로 — 나머지는 온통 한국어인 콘솔에서 이
// 값들만 raw 영어 식별자로 남아 있었다. 알 수 없는 키는 원문 그대로 보여준다(정보 손실 방지).
const APPROVAL_PAYLOAD_KEY_KO = { role: "역할", previous_role: "이전 역할", target_name: "대상 이름",
  target_email: "대상 이메일", target_user_id: "대상 사용자 ID", source_row_count: "원본 행 수",
  target_parent_page: "대상 페이지", generation_id: "문서 생성 ID", config: "설정", definition: "정의",
  period: "기간", mode: "모드", reason: "사유", comment: "메모" };
// enable/disable 공통 액션(활성 값에 따라 노출) — enable/disable는 쓰기 권한 필요.
// disableConfirm을 넘기면 행별로 다른 확인 문구를 쓴다(예: 워크플로의 예약 행 — 비활성화가 실제
// 서비스를 멈추는 경우 일반 "비활성화하시겠습니까?"보다 강한 경고가 필요하다).
// extraEnableWhen(r) — '활성화' 버튼을 !r.enabled 외에 추가 조건으로도 숨겨야 하는 리소스용(예:
// 스케줄의 실행 시각이 이미 지난 once형 — 눌러도 백엔드가 항상 409 'once 스케줄의 실행 시각이
// 이미 지났습니다'로 거절한다. 눌러도 항상 실패하는 버튼을 애초에 숨긴다).
const onoff = (base, disableConfirm, extraEnableWhen) => [
  { label: "활성화", variant: "primary", roles: WRITE_ROLES, when: (r) => !r.enabled && (!extraEnableWhen || extraEnableWhen(r)), path: (r) => base + "/" + r.id + "/enable" },
  { label: "비활성화", variant: "danger", roles: WRITE_ROLES, when: (r) => r.enabled, path: (r) => base + "/" + r.id + "/disable", confirm: disableConfirm || "이 항목을 비활성화할까요?" },
];
// 승인 대기가 아닌(종료된) 상태
const APPROVAL_DONE = ["approved", "rejected", "expired", "cancelled"];
// active 토글 공통(부서·직책) — /enable·/disable 하위경로가 없어 PATCH 본문으로 처리한다.
const activeToggle = (base) => [
  { label: "활성화", variant: "primary", roles: WRITE_ROLES, when: (r) => !r.active, method: "PATCH", path: (r) => base + "/" + r.id, body: { active: true } },
  // r.user_count가 이미 같은 행 열에 로드돼 있으므로, 실제로 몇 명이 영향을 받는지 확인 문구에 반영한다
  // (0명이든 200명이든 똑같은 경고였다 — 사용 중인 부서/직책을 무심코 끄기 쉬웠다).
  { label: "비활성화", variant: "danger", roles: WRITE_ROLES, when: (r) => r.active, method: "PATCH", path: (r) => base + "/" + r.id, body: { active: false },
    confirm: (r) => r.user_count
      ? "비활성화하면 이 항목을 쓰는 사용자 " + r.user_count + "명이 사용자 폼에서 더 이상 새로 고를 수 없게 됩니다. 계속할까요?"
      : "비활성화하면 사용자 폼에서 새로 고를 수 없게 됩니다. 계속할까요?" },
];
// 사용 여부 필터 공통(부서·직책).
const ACTIVE_FILTER = [{ key: "active", type: "select", label: "사용", options: opt([["true", "사용 중"], ["false", "미사용"]]) }];
// 버전 스냅샷 열 — 각 버전 행의 config 스냅샷(r.snapshot)에서 값을 읽어 보여준다(롤백 전 내용 확인).
const snapCol = (key, label, map) => ({ key: "snap_" + key, label, render: (r) => {
  const v = r.snapshot ? r.snapshot[key] : undefined;
  if (v == null || v === "") return "-";
  return map ? (map[v] || String(v)) : String(v);
} });
// 버전 기록·롤백 공통 액션(config-versioned 리소스: 연동·러너·워크플로).
// extraCols: 스냅샷에서 뽑아 보여줄 추가 열(base_url/auth_type/enabled 등) — 블라인드 롤백 방지.
// confirmFn(sub, parent) — 기본 확인 문구를 행별로 강화해야 하는 리소스(예: 워크플로의 예약 행)를
// 위한 선택적 오버라이드. DataScreen.jsx의 SubListDrawer.act()가 confirm을 (하위 행, 부모 행) 두
// 인자로 호출하므로 parent(부모 행)를 읽어 경고 문구를 만들 수 있다.
const versionsAction = (base, extraCols, confirmFn) => ({
  label: "버전 기록",
  subList: {
    title: "버전 기록",
    endpoint: (r) => base + "/" + r.id + "/versions",
    columns: [col("version", "버전"), col("created_by", "변경자 ID"), dateCol("created_at", "시각"), ...(extraCols || [])],
    emptyTitle: "버전 기록이 없습니다",
    rowAction: {
      label: "이 버전으로 롤백", variant: "danger", roles: WRITE_ROLES,
      path: (sub, r) => base + "/" + r.id + "/rollback",
      body: (sub) => ({ version: sub.version }),
      confirm: confirmFn || ((sub) => "버전 " + sub.version + "(으)로 롤백할까요? 현재 설정을 이 버전으로 되돌립니다."),
    },
  },
});
// 이름 기준 버전 관리 리소스(프롬프트·정책)의 '버전 기록' 액션 — 같은 이름의 모든 버전을 모아
// 롤백(그 버전을 새 발행본으로 복원)과 버전 비교(현재 행 버전과의 통합 diff)를 하위 행에서 바로 건다.
// 상태와 무관하게 노출한다(백엔드는 롤백·조회에 상태 전제조건이 없다).
const nameVersionsAction = (base, title) => ({
  label: "버전 기록",
  subList: {
    title,
    // '비교' 액션은 명시적 from/to 선택기가 없다 — from은 클릭한 하위 행, to는 지금 열려 있는
    // 버전(부모 행)으로 암묵적으로 정해진다. 무엇을 비교하는지 미리 알려준다.
    hint: "비교 기준은 지금 열려 있는 버전입니다.",
    // 이 하위 목록은 부모 목록과 동일한 GET(page_size 상한 500, app/prompts/router.py)을 쓴다 —
    // 부모(prompts/policies)의 paginated:true+capWarning:500 처리와 맞춰, 500건을 넘는 이름은
    // 뒷페이지를 계속 볼 수 있게 한다(예전엔 첫 페이지 500건만 오고 더 볼 방법이 없었다).
    paginated: true,
    endpoint: (r, p) => base + "?name=" + encodeURIComponent(r.name) + "&page=" + ((p && p.page) || 1),
    // _prompt_view/_policy_view가 감사 로그의 actor_name과 동일한 패턴으로 created_by_name/
    // created_by_email을 이미 계산해 돌려준다 — 원시 UUID 대신 그 이름을 보여준다.
    columns: [col("version", "버전"), badgeCol("status", "상태"),
      { key: "created_by", label: "작성자", render: (r) => r.created_by_name || r.created_by_email || r.created_by || "-" },
      dateCol("created_at", "생성")],
    emptyTitle: "버전 기록이 없습니다",
    rowActions: [
      { label: "이 버전으로 롤백", variant: "danger", roles: WRITE_ROLES,
        path: () => base + "/rollback",
        body: (sub) => ({ name: sub.name, version: sub.version }),
        confirm: (sub) => "버전 " + sub.version + "(으)로 롤백할까요? 그 버전 내용을 새 발행본으로 복원합니다." },
      // 비교는 조회형(GET) — 통합 diff 문자열을 안내 모달로 보여준다(같은 버전끼리는 숨김).
      { label: "비교", method: "GET",
        when: (sub, parent) => parent && sub.version !== parent.version,
        path: (sub, parent) => base + "/diff/view?name=" + encodeURIComponent(sub.name) + "&from=" + sub.version + "&to=" + parent.version,
        info: (res) => (res && res.diff && String(res.diff).trim()) ? String(res.diff) : "선택한 버전과 기준(현재) 버전의 내용이 동일합니다." },
      // 이 버전 목록을 가져오는 GET base?name=... 응답이 이미 각 버전의 전체 content를 포함한다
      // (app/prompts/router.py _prompt_view) — 그런데 이 하위 목록은 version/status/작성자/생성일만
      // 보여주고 실제 지시문 내용은 어디서도 읽을 방법이 없었다. 이미 불러온 데이터를 그대로(네트워크
      // 호출 없이) 안내 모달로 보여준다(schedules 실행 이력의 '전체 보기'와 동일한 localInfo 패턴).
      // content는 프롬프트(텍스트)·정책(JSON 객체) 둘 다에 쓰이는 공용 helper라 타입을 가려 표시한다.
      { label: "내용 보기", localInfo: (sub) => {
        const c = sub.content;
        if (c == null || c === "") return "(내용 없음)";
        return typeof c === "string" ? c : JSON.stringify(c, null, 2);
      } },
    ],
  },
});
// 헬스/테스트 결과 정직 표시 공통(up/ok면 성공, 아니면 원인 포함 오류).
// checked_url — 실제로 어느 주소를 찔렀는지(health_url, 비었으면 base_url로 대체) 함께 보여준다.
// health_url을 잘못 설정했거나 비워 뒀을 때, 토스트만 보고는 실제 대체(base_url)가 일어났는지
// 알 수 없었다(app/integrations/service.py run_health_check가 이미 checked_url을 돌려주는데도 버려졌었다).
const healthResult = (res) => ({ ok: res.status === "up", msg: (res.status === "up" ? "정상" + (res.latency_ms != null ? ` (${res.latency_ms}ms)` : "") : "중단: " + (res.detail || "확인 실패")) + (res.checked_url ? " (" + res.checked_url + ")" : "") });
// '테스트'는 연결 확인일 뿐, 러너가 실제로 작업을 받을 수 있는지(can_dispatch)와는 별개다 —
// 백엔드가 의도적으로 비활성/점검 상태 러너도 테스트만은 통과시킨다(새 러너를 켜기 전에 미리
// 확인할 수 있게). 통과 문구가 '작업이 실제로 배분된다'는 뜻으로 오해되지 않게 구분해 둔다.
// 백엔드 POST /{id}/test(app/runners/router.py)는 {ok, status_code}만 돌려주고 status 필드는 절대
// 주지 않는다 — res.status 검사는 항상 undefined라 사실상 죽은 코드였다. res.ok만으로 판정한다.
const testResult = (res) => ({ ok: res.ok !== false, msg: (res.ok !== false) ? "테스트 통과(연결 확인됨), 비활성/점검 상태면 실제 작업은 배분되지 않습니다." : "테스트 실패: " + (res.detail || ("HTTP " + (res.status_code || "?"))) });
// 워크플로 '테스트'는 GET 도달성만 확인한다(실제 실행/POST 검증 아님) — 통과를 과장하지 않게 문구를 분리한다.
// 백엔드 provider_n8n.test()는 'reachable'/'unreachable'만 반환한다(ok/failed 필드 없음) — healthResult처럼
// 정확 일치로 판정해야 timeout/connection_refused('unreachable')가 올바로 '연결 실패'로 표시된다.
const reachResult = (res) => { const ok = res.status === "reachable"; return { ok, msg: ok ? "연결 확인됨(도달 가능)" : "연결 실패: " + (res.detail || res.status || ("HTTP " + (res.status_code || "?"))) }; };

// 문서 생성 폼 필드 — '+ 문서 생성' 헤더 작업과 실패/품질미달 행의 '재시도' 행 작업이 공유한다
// (재시도는 같은 폼을 워크플로/모드/설정은 물려받고 기간만 비운 채로 다시 연다).
// 문서 생성 폼 — 예전엔 config 전체를 raw JSON으로 손수 적게 해 무슨 키를 넣어야 할지 알기 어려웠다.
// 실제로 백엔드(app/documents/service.py)가 읽는 키를 명명 입력으로 펼치고, 그 외 드문 키만 '고급(JSON)'
// 하나로 남긴다. 제출 시 docConfigTransform이 이들을 다시 config dict로 조립한다(백엔드 계약 유지).
const DOC_GENERATE_FIELDS = [
  { name: "workflow_id", label: "워크플로 ID", type: "text", required: true, help: "‘업무 자동화 흐름(워크플로)’ 화면에서 대상 워크플로의 ID를 확인해 입력하세요." },
  { name: "period", label: "기간", type: "text", required: true, help: "예: 2026-07 또는 2026-W29 (문서가 다룰 기간)" },
  { name: "mode", label: "모드", type: "select", value: "preview_then_approve", options: opt([["preview_then_approve", "미리보기 후 승인"], ["preview_only", "미리보기만"], ["auto_publish", "자동 발행"]]), help: "‘자동 발행’이라도 대상 워크플로/템플릿이 승인을 요구하면 미리보기 후 승인 흐름으로 전환됩니다." },
  { name: "template_id", label: "템플릿 ID(선택)", type: "text", help: "‘템플릿’ 화면 상세의 ID. 넣으면 그 템플릿의 프롬프트, 정책, 기본값이 함께 적용됩니다." },
  { name: "source_database", label: "원본 Notion DB(선택)", type: "text", help: "문서에 담을 데이터를 읽어올 Notion 데이터베이스 ID(또는 이름)." },
  { name: "output_format", label: "출력 형식", type: "select", value: "", options: opt([["", "(기본: 마크다운)"], ["markdown", "마크다운"], ["html", "HTML"]]) },
  { name: "title_rule", label: "제목 규칙(선택)", type: "text", help: "생성 문서 제목 규칙. 예: 주간 보고서 {week}" },
  { name: "date_range_start", label: "대상 기간 시작(선택)", type: "date", help: "문서가 다룰 데이터의 시작일." },
  { name: "date_range_end", label: "대상 기간 끝(선택)", type: "date" },
  { name: "target_parent_page", label: "발행 위치: 상위 페이지 ID(선택)", type: "text", help: "생성된 문서를 붙일 Notion 상위 페이지 ID." },
  { name: "target_database", label: "발행 위치: DB ID(선택)", type: "text", help: "생성된 문서를 추가할 Notion 데이터베이스 ID." },
  { name: "config_extra", label: "고급 설정(JSON, 선택)", type: "json", jsonObject: true, help: '위에 없는 키(filter, grouping, prompt_template, prompt_id, policy_id, template_version 등)를 직접 넣습니다. 같은 키가 있으면 이 값이 우선합니다. 예: {"filter":{"상태":"완료"},"template_version":1}' },
];
// 명명 필드 → config dict 조립(빈 값은 넣지 않는다). date_range는 {start,end} 중첩.
const _DOC_STR_KEYS = ["template_id", "source_database", "output_format", "title_rule", "target_parent_page", "target_database"];
function docConfigTransform(body) {
  const { template_id, source_database, output_format, title_rule, target_parent_page, target_database,
    date_range_start, date_range_end, config_extra, ...rest } = body;
  const named = { template_id, source_database, output_format, title_rule, target_parent_page, target_database };
  const config = {};
  _DOC_STR_KEYS.forEach((k) => { const v = named[k]; if (v != null && String(v).trim() !== "") config[k] = v; });
  if ((date_range_start && String(date_range_start).trim()) || (date_range_end && String(date_range_end).trim())) {
    config.date_range = { start: date_range_start || "", end: date_range_end || "" };
  }
  if (config_extra && typeof config_extra === "object" && !Array.isArray(config_extra)) Object.assign(config, config_extra);
  return { ...rest, config };  // rest = workflow_id·period·mode
}
// config dict → 명명 필드(재시도 프리필·템플릿 프리필). 알려진 키 외에는 config_extra로 모은다.
function docConfigInitial({ workflow_id = "", mode = "preview_then_approve", config = {}, period = "" } = {}) {
  const c = config || {};
  const dr = c.date_range || {};
  const known = new Set([..._DOC_STR_KEYS, "date_range", "period"]);
  const extra = {};
  Object.keys(c).forEach((k) => { if (!known.has(k)) extra[k] = c[k]; });
  const out = {
    workflow_id: workflow_id || "", period, mode: mode || "preview_then_approve",
    template_id: c.template_id || "", source_database: c.source_database || "",
    output_format: c.output_format || "", title_rule: c.title_rule || "",
    target_parent_page: c.target_parent_page || "", target_database: c.target_database || "",
    date_range_start: dr.start || "", date_range_end: dr.end || "",
  };
  if (Object.keys(extra).length) out.config_extra = extra;
  return out;
}
const docGenerateResult = () => ({ ok: true, msg: "문서 생성을 요청했습니다(진행 중). 잠시 후 목록이 자동으로 새로고침됩니다." });

// 템플릿의 '문서 생성 기본값(input_schema)'도 raw JSON이었다 — 문서 생성 폼과 같은 방식으로 명명
// 필드로 펼친다(템플릿은 재사용 기본값이라 template_id·기간·모드는 없다). toApiBody/fromRow가 input_schema
// dict와 상호 변환한다.
const _TPL_STR_KEYS = ["source_database", "output_format", "title_rule", "target_parent_page", "target_database"];
const TEMPLATE_SCHEMA_FIELDS = [
  { name: "source_database", label: "원본 Notion DB(선택)", type: "text", help: "이 템플릿으로 만드는 문서가 데이터를 읽어올 Notion 데이터베이스 ID(또는 이름). 문서 생성 시 기본값으로 채워집니다." },
  { name: "output_format", label: "출력 형식", type: "select", value: "", options: opt([["", "(기본: 마크다운)"], ["markdown", "마크다운"], ["html", "HTML"]]) },
  { name: "title_rule", label: "제목 규칙(선택)", type: "text", help: "생성 문서 제목 규칙. 예: 주간 보고서 {week}" },
  { name: "target_parent_page", label: "발행 위치: 상위 페이지 ID(선택)", type: "text", help: "생성된 문서를 붙일 Notion 상위 페이지 ID." },
  { name: "target_database", label: "발행 위치: DB ID(선택)", type: "text", help: "생성된 문서를 추가할 Notion 데이터베이스 ID." },
  { name: "input_schema_extra", label: "고급 기본값(JSON, 선택)", type: "json", jsonObject: true, help: '위에 없는 키(filter, grouping, prompt_template 등)를 직접 넣습니다. 같은 키가 있으면 이 값이 우선합니다.' },
];
function assembleInputSchema(body) {
  const named = { source_database: body.source_database, output_format: body.output_format, title_rule: body.title_rule, target_parent_page: body.target_parent_page, target_database: body.target_database };
  const schema = {};
  _TPL_STR_KEYS.forEach((k) => { const v = named[k]; if (v != null && String(v).trim() !== "") schema[k] = v; });
  if (body.input_schema_extra && typeof body.input_schema_extra === "object" && !Array.isArray(body.input_schema_extra)) Object.assign(schema, body.input_schema_extra);
  return schema;
}
function disassembleInputSchema(is) {
  const s = is || {};
  const extra = {};
  Object.keys(s).forEach((k) => { if (!_TPL_STR_KEYS.includes(k)) extra[k] = s[k]; });
  const out = { source_database: s.source_database || "", output_format: s.output_format || "", title_rule: s.title_rule || "", target_parent_page: s.target_parent_page || "", target_database: s.target_database || "" };
  if (Object.keys(extra).length) out.input_schema_extra = extra;
  return out;
}

export const REGISTRY = {
  integrations: {
    key: "integrations", area: "연동", title: "외부 연동", endpoint: "/api/admin/integrations",
    help: "이 시스템이 불러다 쓰는 외부 서비스(n8n, Claude 러너 등)를 등록하고 점검합니다. 활성/비활성화는 이 연동을 참조하는 러너의 실제 호출을 막습니다(러너 화면에서 이 연동을 선택한 경우에 한함).",
    emptyTitle: "등록된 외부 연동이 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 외부 연동 추가’로 n8n, 러너 등 외부 서비스를 등록하고 상태를 점검하세요.", "외부 연동은 관리자가 등록합니다. 등록되면 여기에 상태와 함께 표시됩니다."),
    // 첫 화면 진입 시 단계별 안내(§9) — 연동→러너→워크플로 체인의 첫 단계라 다음 화면으로 가는
    // relatedLink도 함께 준다.
    emptySituation: "이 관리 콘솔이 아직 n8n, 러너 같은 외부 서비스를 하나도 모릅니다.",
    emptyPrerequisite: "등록할 서비스의 서버 주소(Base URL)를 미리 확인하세요(SSRF allowlist에 있어야 합니다).",
    emptySteps: ["‘+ 외부 연동 추가’로 이름과 서버 주소를 입력합니다.", "저장 후 ‘헬스체크’로 연결을 확인합니다.", "정상이면 ‘활성화’로 실제 사용을 시작합니다."],
    emptyExpected: "등록한 연동은 목록에 상태와 함께 표시되고, ‘자동화 작업 실행기(러너)’ 화면에서 이 연동을 선택할 수 있습니다.",
    emptyRelatedLink: { href: "#/runners", label: "다음: 러너 등록으로 이동" },
    createLabel: "+ 외부 연동 추가",
    // 다른 화면(러너 상세의 integration_id)이 ?id=로 넘겨주는 딥링크를 소비해 그 연동의 상세
    // 드로어를 곧바로 연다(단건 GET — runners.onQuery와 동일한 패턴).
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "integration",
    // GET /api/admin/integrations는 쿼리 파라미터를 받지 않는다(app/integrations/router.py) —
    // clientFilter:true로 이미 받아 온 전체 목록을 화면에서 직접 거른다(runners.filters와 동일한
    // 필요, 다만 백엔드가 서버 필터를 지원하지 않아 client 쪽 패턴을 쓴다).
    filters: [
      { key: "provider_type", type: "select", label: "유형", clientFilter: true, options: PROVIDER_OPTS },
      { key: "enabled", type: "select", label: "활성", clientFilter: true, options: opt([["true", "활성"], ["false", "비활성"]]) },
      // 'unknown'(미확인)도 넣는다 — 모델 기본값이 HEALTH_UNKNOWN이라 새로 만든/디스커버리 시딩된
      // 연동은 헬스체크 전까지 이 상태다. 옵션이 없으면 '정상'/'중단'을 골랐을 때 미확인 행이 조용히
      // 다 빠져(신규 설치의 가장 흔한 상태) 목록 대부분이 사라졌다.
      { key: "last_health_status", type: "select", label: "상태 확인", clientFilter: true, options: opt([["up", "정상"], ["down", "중단"], ["unknown", "미확인"]]) },
    ],
    // base_url은 SSRF allowlist상 항상 서버-로컬(127.0.0.1 등) 주소다 — 클릭 가능한 링크로 보이면
    // 관리자 자신의 브라우저에서 그 루프백 주소를 열게 되어 항상 실패한다(워크플로의 webhook_url과
    // 동일한 이유로 평문으로만 보여준다).
    columns: [col("name", "이름"), mapCol("provider_type", "유형", PROVIDER), badgeCol("enabled", "활성"),
      badgeCol("last_health_status", "상태 확인"), truncateCol("base_url", "서버 주소", 60), col("config_version", "버전")],
    // admin은 auth_type='none'인 연동만 새로 만들 수 있다(백엔드 _guard_secret_binding_create가 그 외
    // 값을 403). 예전엔 옵션을 그대로 다 보여주고 help 문구만으로 고르지 말라고 부탁했다 — 골라도
    // 항상 403이 되는 선택지를 애초에 못 고르게, system_admin이 아니면 옵션 자체를 '없음'만 준다
    // (러너 '복제' 액션의 role-분기 패턴, registry.js runners.actions와 동일한 발상).
    create: { roles: WRITE_ROLES, fields: (role) => [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "provider_type", label: "유형", type: "select", value: "http_service", options: PROVIDER_OPTS },
      { name: "base_url", label: "서버 주소(Base URL)", type: "text", required: true, help: "allowlist에 있어야 합니다." },
      { name: "health_url", label: "상태 확인 주소(Health URL)", type: "text", help: "비우면 Base URL로 헬스체크" },
      { name: "auth_type", label: "인증", type: "select", value: "none",
        options: role === "system_admin" ? AUTH_OPTS : AUTH_OPTS.filter((o) => o.value === "none"),
        help: role === "system_admin" ? undefined : "admin은 인증 없는(‘없음’) 연동만 새로 만들 수 있습니다, Bearer, API 키가 필요한 연동은 system_admin에게 요청하세요." },
      { name: "secret_ref", label: "인증 정보 이름(Secret)", type: "text", help: "서버 secrets 파일 이름(값 아님). ‘없음’이 아닌 인증이면 반드시 지정하세요." },
      { name: "description", label: "설명", type: "textarea" },
      { name: "enabled", label: "활성", type: "checkbox", value: false, checkLabel: "활성(끄면 등록만 하고 헬스체크 후 켤 수 있음)" },
    ] },
    // 등록 후 값을 고칠 수 있게 명시적 PATCH 편집 폼(기능·인증·설명 포함).
    editMethod: "PATCH", edit: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text" },
      { name: "provider_type", label: "유형", type: "select", options: PROVIDER_OPTS },
      { name: "base_url", label: "서버 주소(Base URL)", type: "text" },
      { name: "health_url", label: "상태 확인 주소(Health URL)", type: "text" },
      { name: "auth_type", label: "인증", type: "select", options: AUTH_OPTS },
      { name: "secret_ref", label: "인증 정보 이름(Secret)", type: "text", help: "‘없음’이 아닌 인증이면 반드시 지정하세요." },
      { name: "description", label: "설명", type: "textarea" },
    ] },
    actions: [
      // 비활성화는 이 연동을 참조하는(러너 화면에서 이 연동을 선택한) 러너의 실제 호출을 모두 막는다
      // (provider_http.invoke가 RunnerUnavailableError) — 일반 확인 문구 대신 파급을 분명히 경고한다.
      ...onoff("/api/admin/integrations", "이 외부 연동을 비활성화하면, 이 연동을 참조하는(러너 화면에서 이 연동을 선택한) 러너들의 실제 작업 호출이 모두 실패하게 됩니다. 계속 비활성화할까요?"),
      { label: "헬스체크", roles: OPS_ROLES, path: (r) => "/api/admin/integrations/" + r.id + "/health", result: healthResult },
      versionsAction("/api/admin/integrations", [
        // integration_snapshot()(app/integrations/service.py)이 실제로 되돌리는 값에는 name·
        // provider_type도 포함된다 — 안 보이면 롤백이 이름(다른 시스템이 정확 일치로 찾는 경우도
        // 있다)·유형까지 조용히 되돌리는데도 확인 화면엔 안 보였다(블라인드 롤백 방지).
        snapCol("name", "이름"), snapCol("provider_type", "유형", PROVIDER),
        snapCol("base_url", "서버 주소"),
        snapCol("health_url", "상태 확인 주소"),
        snapCol("secret_ref", "인증 정보 이름"),
        snapCol("auth_type", "인증", { none: "없음", bearer: "Bearer 토큰", api_key_header: "API 키(헤더)" }),
        snapCol("enabled", "활성", { true: "활성", false: "비활성" })]),
      // integration은 감사 로그의 유효한 object_type이고 모든 쓰기가 이 타입으로 기록된다 —
      // policies/departments 등과 동일한 딥링크.
      // operator는 연동 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=integration&object_id=" + r.id },
    ],
    // provider_type·base_url은 이미 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    // id는 러너 create의 integration_id 입력에 쓰이므로 상세에서 확인·복사할 수 있게 노출.
    detailFields: [field("id", "연동 ID"), truncateCol("health_url", "상태 확인 주소", 80), mapCol("auth_type", "인증", { none: "없음", bearer: "Bearer 토큰", api_key_header: "API 키(헤더)" }), field("secret_ref", "인증 정보 이름"),
      // auth_type이 '없음'이면 secret_status는 null이다(원래 정상) — 일반 Badge는 null을 '알 수 없음'으로
      // 오해하게 표시하므로, 인증 자체가 필요 없는 경우엔 '해당 없음'으로 구분한다(그 외엔 기존 배지 재사용).
      { key: "secret_status", label: "인증 정보 상태", render: (r) => r.auth_type === "none" ? "해당 없음" : badgeCol("secret_status", "인증 정보 상태").render(r) },
      field("description", "설명"), dateCol("last_health_at", "마지막 점검"), dateCol("created_at", "생성"), dateCol("updated_at", "수정")],
  },
  runners: {
    key: "runners", area: "연동", title: "자동화 작업 실행기(러너)", endpoint: "/api/admin/runners",
    // '수정'에서 점검 상태를 바꾸는 안내는 그 버튼을 실제로 볼 수 있는 쓰기 역할(admin/system_admin)
    // 에게만 준다 — 읽기 전용 역할(operator/auditor)은 이 화면을 볼 수 있어도 '수정' 버튼이 없다.
    help: (role) => "실제 업무(티켓 처리, 요청 해석)를 수행하는 실행기입니다. 상태 확인 후 켜세요. 성능 저하, 차단된 러너는 헬스 체크가 한 번 성공하면 자동 복구됩니다."
      + ((role === "admin" || role === "system_admin") ? " 강제로 멈추려면 ‘수정’에서 점검 상태를 ‘점검’으로 바꾸세요." : ""),
    emptyTitle: "등록된 러너가 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 러너 추가’로 티켓 처리, 요청 해석을 수행할 실행기를 등록하고 상태 확인 후 켜세요.", "러너는 관리자가 등록합니다. 등록되면 여기에 표시됩니다."),
    // 첫 화면 진입 시 단계별 안내(§9) — 연동→러너→워크플로 체인의 두 번째 단계.
    emptySituation: "실제 업무를 처리할 실행기가 아직 하나도 등록되지 않았습니다.",
    emptyPrerequisite: "이 러너가 사용할 서버 주소(Base URL)를 미리 확인하세요(SSRF allowlist에 있어야 합니다). 외부 연동과 묶을 계획이면 그 연동을 먼저 등록해 두세요.",
    emptySteps: ["‘+ 러너 추가’로 이름과 서버 주소를 입력합니다.", "저장 후 ‘헬스’, ‘테스트’로 연결을 확인합니다.", "정상이면 ‘활성화’로 작업 배분을 시작합니다."],
    emptyExpected: "등록한 러너는 목록에 상태, 점검 상태와 함께 표시되고, 프롬프트/템플릿에서 이 러너를 지정할 수 있습니다.",
    // 연동→러너→워크플로 체인의 두 번째 단계 — integrations는 이미 runners로의 다음 단계 링크를
    // 갖고 있었지만(반대 방향), runners 자신은 다음 단계(workflows)로의 링크가 없어 체인이 절반만
    // 이어졌다. EmptyState는 링크를 하나만 표시할 수 있어(kit.jsx), 이 화면은 '다음' 방향을 준다
    // (integrations→runners 역방향은 integrations.emptyRelatedLink가 이미 담당).
    emptyRelatedLink: { href: "#/workflows", label: "다음: 워크플로 등록으로 이동" },
    createLabel: "+ 러너 추가",
    // 다른 화면(템플릿의 target_ref, 프롬프트의 runner_id)이 ?id=로 넘겨주는 딥링크를 소비해 그
    // 러너의 상세 드로어를 곧바로 연다(단건 GET — jobs.onQuery와 동일한 패턴).
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "runner",
    // 이 화면은 paginated가 아니라 클라이언트 검색창이 항상 뜨는데, searchFields가 없으면 기본 검색이
    // JSON.stringify(row) 전체(id·secret_ref·raw enum·ISO 타임스탬프·capabilities/retry_policy JSON)를
    // 훑어 화면에 안 보이는 값까지 매칭했다(예: 'up'/'normal'로 오탐) — 눈에 보이는 열만 검색 대상으로 좁힌다.
    searchFields: ["name", "owner", "base_url", "version"],
    // 목록이 많아지면 상태/활성 여부로 좁혀 볼 수 있게 한다(예전엔 client-side 문자열 검색뿐이었다).
    filters: [
      { key: "maintenance_state", type: "select", label: "점검 상태", options: RUNNER_MAINT_OPTS },
      { key: "enabled", type: "select", label: "활성", options: opt([["true", "활성"], ["false", "비활성"]]) },
    ],
    columns: [col("name", "이름"), badgeCol("enabled", "활성"), badgeCol("maintenance_state", "상태"),
      // 회로 차단(연속 실패로 배분이 300초 막힘) 상태를 목록에서 바로 본다 — degraded 배지로는 구분되지 않는다.
      // key는 상세 드로어의 circuit_open_until(해제 시각) 필드와 겹치지 않도록 별도 이름을 쓴다.
      { key: "circuit_blocked", label: "차단", render: (r) => {
        const v = r.circuit_open_until; if (!v) return "-";
        const s = String(v); const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
        const t = new Date(iso).getTime();
        return (!Number.isNaN(t) && t > Date.now()) ? "차단됨(회로 열림)" : "-";
      } },
      badgeCol("last_health_status", "상태 확인"), col("consecutive_failures", "연속 실패"), col("config_version", "설정 버전"),
      // base_url은 SSRF allowlist상 서버-로컬(127.0.0.1:8787-8789 등) 주소만 유효하다 — 클릭 가능한
      // 링크로 보이면 관리자 자신의 브라우저에서 그 루프백 주소를 열게 되어 항상 실패한다(연동
      // 화면의 base_url과 동일한 이유로 평문으로만 보여준다).
      truncateCol("base_url", "서버 주소", 60),
      col("owner", "담당자"), col("version", "버전")],
    // admin은 auth_type='none'인 러너만 새로 만들 수 있다(백엔드 _guard_secret_binding_create가 그 외
    // 값을 403). 연동 생성 폼과 동일하게, 골라도 항상 403이 되는 선택지를 애초에 못 고르게 role에
    // 따라 옵션 자체를 좁힌다(registry.js integrations.create와 동일 패턴).
    create: { roles: WRITE_ROLES, fields: (role) => [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "base_url", label: "서버 주소(Base URL)", type: "text", required: true, help: "예: http://127.0.0.1:8790 (allowlist에 있어야 함)" },
      { name: "health_url", label: "상태 확인 주소(Health URL)", type: "text", help: "비우면 Base URL로 헬스체크" },
      { name: "auth_type", label: "인증", type: "select", value: "none",
        options: role === "system_admin" ? AUTH_OPTS : AUTH_OPTS.filter((o) => o.value === "none"),
        help: role === "system_admin" ? undefined : "admin은 인증 없는(‘없음’) 러너만 새로 만들 수 있습니다, Bearer, API 키가 필요한 러너는 system_admin에게 요청하세요." },
      { name: "secret_ref", label: "인증 정보 이름(Secret)", type: "text", help: "서버 secrets 디렉터리 파일 이름(값 아님). ‘없음’이 아닌 인증이면 반드시 지정하세요." },
      { name: "timeout_seconds", label: "타임아웃(초)", type: "number", value: 60 },
      { name: "concurrency_limit", label: "동시 실행 수", type: "number", value: 1 },
      { name: "version", label: "러너 버전(선택)", type: "text", help: "러너 소프트웨어 버전 문자열(설정 버전과 별개)." },
      // integration_id는 생성 시에만 지정할 수 있고 수정 폼에는 없다(백엔드 RunnerUpdateRequest에
      // 필드가 없음). 러너 삭제(DELETE) 엔드포인트도 없어, 오타가 나면 이 화면에서는 되돌릴 방법이
      // 없다(비활성화만 가능) — 그래서 제출 전에 ID가 맞는지 미리 확인하라고 안내한다.
      { name: "integration_id", label: "연동 ID(선택)", type: "text", help: "이 러너를 연결할 외부 연동의 ID(‘외부 연동’ 화면에서 확인). 생성 후에는 이 화면에서 다시 바꿀 수 없으니(수정 폼에 없고 러너 삭제 경로도 없습니다), 제출 전에 ID가 맞는지 다시 확인하세요." },
      { name: "owner", label: "담당자(선택)", type: "text" },
      { name: "description", label: "설명", type: "textarea" },
    ] },
    // 점검 상태(maintenance_state)·담당자까지 편집 가능하게 명시적 edit 폼(PATCH)을 둔다.
    // (capabilities/tags/retry_policy 는 런타임에 아무 영향이 없는 메타데이터라 폼에서 제거 — 러너
    //  호출 경로엔 재시도 로직이 없고 기능/태그로 결정되는 동작도 없다. 혼란만 주던 JSON 입력을 없앤다.)
    editMethod: "PATCH", edit: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text" },
      { name: "base_url", label: "서버 주소(Base URL)", type: "text" },
      { name: "health_url", label: "상태 확인 주소(Health URL)", type: "text" },
      { name: "auth_type", label: "인증", type: "select", options: AUTH_OPTS },
      { name: "secret_ref", label: "인증 정보 이름(Secret)", type: "text", help: "‘없음’이 아닌 인증이면 반드시 지정하세요." },
      { name: "timeout_seconds", label: "타임아웃(초)", type: "number" },
      { name: "concurrency_limit", label: "동시 실행 수", type: "number" },
      { name: "maintenance_state", label: "점검 상태", type: "select", options: RUNNER_MAINT_OPTS, help: "‘점검’이면 새 작업 배분이 멈춥니다." },
      { name: "owner", label: "담당자", type: "text" },
      { name: "version", label: "러너 버전", type: "text" },
      { name: "description", label: "설명", type: "textarea" },
    ] },
    actions: [
      ...onoff("/api/admin/runners"),
      { label: "헬스", roles: OPS_ROLES, path: (r) => "/api/admin/runners/" + r.id + "/health", result: healthResult },
      { label: "테스트", roles: OPS_ROLES, path: (r) => "/api/admin/runners/" + r.id + "/test", result: testResult },
      // 복제는 원본의 auth_type/secret_ref를 물려받는다. secret이 걸린 러너 복제는 system_admin만 허용(백엔드 가드)
      // → admin에겐 auth_type==='none'인 러너에서만 노출해 403 데드엔드를 막는다.
      { label: "복제", roles: ["system_admin"], path: (r) => "/api/admin/runners/" + r.id + "/clone", fields: [
        { name: "name", label: "새 러너 이름", type: "text", required: true },
      ] },
      { label: "복제", roles: ["admin"], when: (r) => r.auth_type === "none", path: (r) => "/api/admin/runners/" + r.id + "/clone", fields: [
        { name: "name", label: "새 러너 이름", type: "text", required: true },
      ] },
      versionsAction("/api/admin/runners", [snapCol("base_url", "서버 주소"),
        // 백엔드는 base_url/secret_ref/health_url/auth_type을 모두 동일하게 민감 필드로 취급한다
        // (health_url도 secret이 다른 대상으로 전송될 수 있어 포함) — 스냅샷도 네 필드 모두 보여줘야
        // 블라인드 롤백을 실제로 막는다.
        snapCol("health_url", "상태 확인 주소"),
        snapCol("secret_ref", "인증 정보 이름"),
        snapCol("auth_type", "인증", { none: "없음", bearer: "Bearer 토큰", api_key_header: "API 키(헤더)" }),
        snapCol("enabled", "활성", { true: "활성", false: "비활성" }),
        // apply_runner_config가 실제로 되돌리는 값은 이 다섯 필드뿐 아니다 — maintenance_state가
        // 바뀌면 배분이 멈추거나 재개될 수 있고, timeout/동시 실행 수·담당자도 조용히 되돌아갈 수
        // 있다(블라인드 롤백 방지, 위 네 필드와 동일한 이유).
        snapCol("maintenance_state", "점검 상태", { normal: "정상", degraded: "성능 저하", maintenance: "점검" }),
        snapCol("timeout_seconds", "타임아웃(초)"),
        snapCol("concurrency_limit", "동시 실행 수"),
        snapCol("owner", "담당자")]),
      // operator는 러너 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES) —
      // approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=runner&object_id=" + r.id },
    ],
    // base_url·config_version은 이미 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을
    // 그린다 — 예전엔 여기 다시 넣어 '서버 주소'·'설정 버전'이 드로어에 두 번 보였다).
    detailFields: [field("id", "러너 ID"),
      // RUNNER_PROVIDER_TYPES가 현재 'local_http' 하나뿐이라 목록/생성 폼엔 노출하지 않지만, API가
      // 실제로 돌려주는 필드다(app/runners/service.py runner_view) — 두 번째 provider_type이 생기기
      // 전까지는 상세에서만 참고용으로 보여준다. 다른 enum(auth_type 등)처럼 raw 값이 아니라
      // 한국어 라벨로 감싼다(이 화면의 다른 enum 표시와 일관).
      mapCol("provider_type", "제공자 유형", { local_http: "로컬 HTTP" }),
      // health_url도 base_url과 동일한 SSRF allowlist(서버-로컬 주소만 유효) 제약을 받는다 — 클릭
      // 가능한 링크는 항상 실패하는 죽은 앵커였다(위 base_url 열과 동일한 이유로 평문으로 보여준다).
      truncateCol("health_url", "상태 확인 주소", 80), mapCol("auth_type", "인증", { none: "없음", bearer: "Bearer 토큰", api_key_header: "API 키(헤더)" }), field("secret_ref", "인증 정보 이름"),
      // auth_type이 '없음'이면 secret_status는 null이다(원래 정상 — app/runners/service.py: secrets.status는
      // secret_ref가 있을 때만 호출된다) — 일반 Badge는 null을 '알 수 없음'으로 오해하게 표시하므로,
      // 인증 자체가 필요 없는 경우엔 '해당 없음'으로 구분한다(Integrations 상세와 동일 패턴).
      { key: "secret_status", label: "인증 정보 상태", render: (r) => r.auth_type === "none" ? "해당 없음" : badgeCol("secret_status", "인증 정보 상태").render(r) },
      // owner·version은 이제 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다
      // — 예전엔 여기 다시 넣어 '담당자'·'러너 버전'이 드로어에 두 번 보였다. base_url/config_version
      // 중복 제거와 동일한 이유·패턴).
      field("timeout_seconds", "타임아웃(초)"), field("concurrency_limit", "동시 실행 수"),
      // integration_id는 검증 없는 자유 입력(오타가 조용히 저장될 수 있다) — 최소한 '외부 연동'
      // 화면으로 바로 확인하러 갈 수 있게 클릭 가능한 링크로 보여준다(원시 텍스트로 방치하지 않음).
      // 이 파일은 .js라 JSX 대신 React.createElement를 직접 쓴다(빌드 설정이 .jsx/.tsx에만 JSX
      // 변환을 적용하므로).
      // 연동 화면이 이제 ?id=로 특정 연동 상세를 곧바로 여는 딥링크(onQuery)를 지원한다 — 무필터
      // 전체 목록에만 떨어지던 죽은 앵커가 아니라 실제로 그 연동으로 데려간다.
      { key: "integration_id", label: "연동 ID", render: (r) => r.integration_id ? React.createElement("a", { href: "#/integrations?id=" + encodeURIComponent(r.integration_id) }, r.integration_id) : "-" },
      dateCol("last_health_at", "마지막 상태 확인"), dateCol("circuit_open_until", "회로 차단 해제"), dateCol("created_at", "생성"), dateCol("updated_at", "수정"), field("description", "설명")],
  },
  workflows: {
    key: "workflows", area: "연동", title: "업무 자동화 흐름(워크플로)", endpoint: "/api/admin/workflows",
    help: "n8n 워크플로를 등록해 관리합니다. 읽기/쓰기, 승인 필요 여부를 표시합니다. ‘테스트’는 수신 주소의 도달 가능성(GET 연결)만 확인하며, 실제 실행을 보장하지 않습니다.",
    emptyTitle: "등록된 워크플로가 없습니다",
    // 워크플로는 READ_ROLES(operator/auditor 포함)가 읽을 수 있지만 생성은 WRITE_ROLES 전용이다
    // (nav 항목엔 role 게이트가 없어 읽기 전용 역할도 이 화면에 닿는다) → 없는 버튼을 누르라고 안내하지 않는다.
    emptyHelp: writerEmptyHelp("‘+ 워크플로 추가’로 n8n 워크플로의 수신 주소(Webhook)를 등록해 관리하세요.", "워크플로는 관리자가 등록합니다. 등록되면 여기에 상태와 함께 표시됩니다."),
    // 연동→러너→워크플로 체인의 세 번째(마지막) 단계 — 앞의 두 화면(integrations/runners)과 동일한
    // 단계별 안내(§9)를 준다(예전엔 워크플로만 emptyTitle/emptyHelp뿐이었다).
    emptySituation: "이 관리 콘솔이 아직 n8n 워크플로를 하나도 모릅니다.",
    emptyPrerequisite: "등록할 워크플로의 수신 주소(Webhook)가 allowlist에 있는지 확인하세요(config/allowed-workflows.json).",
    emptySteps: ["‘+ 워크플로 추가’로 이름과 수신 주소(Webhook)를 입력합니다.", "저장 후 ‘테스트’로 수신 주소 도달을 확인합니다.", "정상이면 ‘활성화’로 실제 사용을 시작합니다."],
    emptyExpected: "등록한 워크플로는 목록에 상태와 함께 표시되고, 템플릿, 스케줄, 문서 자동 생성 화면에서 이 워크플로를 대상으로 지정할 수 있습니다.",
    emptyRelatedLink: { href: "#/runners", label: "이전: 러너 목록 보기" },
    createLabel: "+ 워크플로 추가",
    // 다른 화면(템플릿의 target_ref, 스케줄의 target_ref, 문서의 workflow_id)이 ?id=로 넘겨주는
    // 딥링크를 소비해 그 워크플로의 상세 드로어를 곧바로 연다(단건 GET — runners.onQuery와 동일한 패턴).
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "workflow",
    // 목록이 커지면 활성 여부/모드/승인 필요로 좁혀 볼 수 있게 한다. list_workflows(app/workflows/router.py)는
    // 쿼리 파라미터를 전혀 받지 않으므로(전체 목록만 반환) clientFilter:true로 표시해 이미 받아 온
    // 목록을 DataScreen.jsx가 화면에서 직접 거르게 한다(서버로 보내면 조용히 무시돼 아무 효과 없는
    // 필터가 된다).
    filters: [
      { key: "enabled", type: "select", label: "활성", clientFilter: true, options: opt([["true", "활성"], ["false", "비활성"]]) },
      { key: "operation_mode", type: "select", label: "모드", clientFilter: true, options: WFMODE_OPTS },
      { key: "approval_required", type: "select", label: "승인 필요", clientFilter: true, options: opt([["true", "필요"], ["false", "불필요"]]) },
    ],
    // webhook_url은 SSRF allowlist가 127.0.0.1:5678/localhost:5678(서버 쪽 n8n)로만 제한하므로,
    // 클릭하면 서버가 아니라 관리자 자신의 브라우저에서 그 루프백 주소를 열게 되어 항상 실패한다
    // (연동·러너의 base_url과 달리 여긴 클릭 가능한 링크가 사실상 죽은 기능이었다) — 평문으로만 보여준다.
    // purpose·owner도 목록 열로 노출 — prompts 화면이 이미 같은 이유로(각 행이 '무엇을 위한 것인지'
    // 상세를 하나씩 열지 않고도 알 수 있게) purpose를 승격한 것과 동일한 패턴(registry.js:572-577).
    columns: [col("name", "이름"), truncateCol("purpose", "용도", 40), col("owner", "담당자"),
      mapCol("operation_mode", "모드", WF_MODE), badgeCol("approval_required", "승인 필요"),
      badgeCol("enabled", "활성"),
      // provider_n8n.test()는 'reachable'/'unreachable'만 기록한다 — 한 번도 테스트한 적 없는 행은
      // last_test_status가 그냥 null이라, 일반 Badge는 이걸 '알 수 없음'으로 보여준다(오류처럼 읽힘).
      // '미검증'으로 구분해 실제로 테스트가 실패한 적이 있는지와 헷갈리지 않게 한다.
      // last_test_at도 함께 보여준다(상대 시각) — '연결됨' 배지만 보면 방금 테스트한 것과 몇 달 전
      // 테스트한 것이 똑같아 보였다(연결 상태가 실제로 얼마나 최신인지 목록에서 바로 가늠할 수 있게).
      { key: "last_test_status", label: "테스트", render: (r) => {
        const badge = r.last_test_status ? React.createElement(Badge, { value: r.last_test_status }) : React.createElement(Badge, { value: "untested" });
        if (!r.last_test_at) return badge;
        const s = String(r.last_test_at); const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
        const t = new Date(iso).getTime();
        if (Number.isNaN(t)) return badge;
        const m = Math.floor(Math.max(0, Date.now() - t) / 60000);
        const rel = m < 1 ? "방금" : (m < 60 ? m + "분 전" : (m < 1440 ? Math.floor(m / 60) + "시간 전" : Math.floor(m / 1440) + "일 전"));
        return React.createElement(React.Fragment, null, badge, ", " + rel);
      } },
      col("config_version", "버전"), truncateCol("webhook_url", "수신 주소", 60)],
    // 예약 워크플로(채팅·Notion 동기화)도 '수정'을 연다 — 백엔드 PATCH가 편집을 지원하므로(예:
    // n8n 호스트·포트가 바뀌면 수신 주소를 고쳐야 한다). 계약 식별자인 '이름'만 편집 폼에서 빼
    // 바꿀 수 없게 잠근다(아래 edit.fields의 filter 참고) — 예전엔 editWhen으로 전 필드를 막아 놓고
    // 힌트로는 'DB 직접 조치 필요'라 안내해, 정작 PATCH가 되는데도 대안 경로가 없다고 오해시켰다.
    // id는 템플릿 target_ref·스케줄 target_ref·문서 workflow_id 입력에 쓰이므로 상세에서 확인·복사할 수 있게 노출.
    detailFields: [field("id", "워크플로 ID"),
      // 이름이 계약인 워크플로(채팅·Notion 동기화)는 실제 동작과 이 화면의 컨트롤이 어긋난다는 점을
      // 상세에서 바로 알린다(RESERVED_WORKFLOW_NOTES) — 그 외 행은 "-"만 보여준다.
      { key: "_reserved_note", label: "[주의] 이 워크플로에 대해", render: (r) => RESERVED_WORKFLOW_NOTES[r.name] || "-" },
      // purpose·owner는 이제 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
      field("http_method", "HTTP 메서드"),
      { key: "tags", label: "태그", render: (r) => (r.tags && r.tags.length) ? r.tags.join(", ") : "-" },
      dateCol("last_test_at", "마지막 테스트"), dateCol("created_at", "생성"), dateCol("updated_at", "수정")],
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "webhook_url", label: "수신 주소(Webhook URL)", type: "text", required: true, help: "n8n 워크플로의 웹훅 주소 (예: http://127.0.0.1:5678/webhook/my-flow, allowlist에 있어야 함)" },
      { name: "purpose", label: "용도", type: "textarea" },
      { name: "http_method", label: "HTTP 메서드", type: "select", value: "POST", options: HTTP_OPTS },
      { name: "operation_mode", label: "모드", type: "select", value: "read", options: WFMODE_OPTS, help: "쓰기는 데이터를 변경합니다." },
      { name: "owner", label: "담당자", type: "text" },
      { name: "tags", label: "태그(JSON 배열)", type: "json", help: '예: ["report","weekly"]' },
      { name: "approval_required", label: "승인 필요", type: "checkbox", value: false, checkLabel: "실행 전 승인 필요", help: "자동(예약) 실행 게이팅은 쓰기(write) 워크플로에만 적용됩니다, 읽기 워크플로는 예약 실행 시 승인 없이 실행됩니다. 단, ‘문서 자동 생성’의 자동 발행은 읽기/쓰기와 무관하게 이 값이 켜진 모든 워크플로/템플릿에 적용됩니다(app/documents/service.py: publish_approval_required)." },
      { name: "enabled", label: "활성", type: "checkbox", value: true, checkLabel: "활성", help: "먼저 ‘테스트’로 수신 주소 도달을 확인한 뒤 켜는 것을 권장합니다." },
    ] },
    // 편집은 PATCH(부분 갱신) — 예약 워크플로 행에서는 name 필드를 아예 빼서 계약 이름이 바뀌지
    // 않게 잠근다(PATCH라 보내지 않으면 그대로 유지된다). 그 외 행은 name 포함 전 필드 편집 가능.
    editMethod: "PATCH", edit: { roles: WRITE_ROLES, fields: (role, row) => [
      { name: "name", label: "이름", type: "text" },
      { name: "webhook_url", label: "수신 주소(Webhook URL)", type: "text", help: "n8n 워크플로의 웹훅 주소 (예: http://127.0.0.1:5678/webhook/my-flow, allowlist에 있어야 함)" },
      { name: "purpose", label: "용도", type: "textarea" },
      { name: "http_method", label: "HTTP 메서드", type: "select", options: HTTP_OPTS },
      { name: "operation_mode", label: "모드", type: "select", options: WFMODE_OPTS, help: "쓰기는 데이터를 변경합니다." },
      { name: "owner", label: "담당자", type: "text" },
      { name: "tags", label: "태그(JSON 배열)", type: "json" },
      { name: "approval_required", label: "승인 필요", type: "checkbox", checkLabel: "실행 전 승인 필요", help: "자동(예약) 실행 게이팅은 쓰기(write) 워크플로에만 적용됩니다. 단, ‘문서 자동 생성’의 자동 발행은 읽기/쓰기와 무관하게 이 값이 켜진 모든 워크플로/템플릿에 적용됩니다." },
    ].filter((f) => !(f.name === "name" && row && RESERVED_WORKFLOW_NOTES[row.name])) },
    actions: [
      ...onoff("/api/admin/workflows", reservedDisableConfirm),
      { label: "테스트", roles: OPS_ROLES, path: (r) => "/api/admin/workflows/" + r.id + "/test", result: reachResult },
      versionsAction("/api/admin/workflows", [
        // name·http_method도 스냅샷에 보여준다 — workflow_snapshot()이 롤백으로 되돌리는 값에
        // 포함되는데(app/workflows/service.py) 예전엔 목록에 없어 특히 name(다른 시스템이 정확
        // 일치로 찾는 식별자)이 롤백으로 조용히 바뀔 수 있었다(블라인드 롤백 방지).
        snapCol("name", "이름"), snapCol("http_method", "HTTP 메서드"),
        snapCol("webhook_url", "수신 주소"),
        snapCol("operation_mode", "모드", { read: "읽기", write: "쓰기" }),
        snapCol("enabled", "활성", { true: "활성", false: "비활성" }),
        // 승인 필요 여부도 스냅샷에 보여준다 — 안 보이면 롤백으로 승인 게이트가 조용히 꺼질 수 있다(블라인드 롤백 방지).
        snapCol("approval_required", "승인 필요", { true: "필요", false: "불필요" }),
        // workflow_snapshot()이 되돌리는 나머지 필드(app/workflows/service.py:20-37) — 안 보이면
        // 롤백이 용도·담당자·태그·요청/응답 스키마(다른 시스템이 계약으로 쓰는 값)까지 조용히
        // 되돌리는데도 확인 화면엔 안 보였다(블라인드 롤백 방지, 위 필드들과 동일한 이유).
        snapCol("purpose", "용도"), snapCol("owner", "담당자"),
        { key: "snap_tags", label: "태그", render: (r) => { const v = r.snapshot && r.snapshot.tags; return (v && v.length) ? v.join(", ") : "-"; } },
        ],
        // 이름이 계약인 워크플로(채팅·Notion 동기화)는 비활성화와 마찬가지로 롤백도 실제 서비스에
        // 영향을 준다(웹훅 주소·모드가 롤백으로 통째로 바뀔 수 있다) — onoff의 reservedDisableConfirm과
        // 동일한 강한 경고를 롤백 확인에도 붙인다.
        (sub, parent) => {
          const base = "버전 " + sub.version + "(으)로 롤백할까요? 현재 설정을 이 버전으로 되돌립니다.";
          const note = parent && RESERVED_WORKFLOW_NOTES[parent.name];
          return note ? note + "\n\n" + base : base;
        }),
      // operator는 워크플로 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=workflow&object_id=" + r.id },
    ],
  },
  prompts: {
    key: "prompts", area: "콘텐츠", title: "프롬프트", endpoint: "/api/admin/prompts",
    // 워크플로 화면의 '테스트'가 실제 실행이 아니라 도달성만 확인한다고 밝히듯, 여기도 상태 전이
    // 버튼이 내용 검증을 뜻하지 않는다는 점을 밝힌다(전이는 순수 상태 기록일 뿐 — app/prompts/service.py).
    help: "AI에게 주는 지시문을 버전으로 관리합니다. ‘테스트로’, ‘검토로’, ‘발행’은 상태만 바꿀 뿐, 러너로 실제 실행하거나 내용을 검증하지 않습니다, 내용 검증은 화면 밖에서 직접 확인하세요. 발행하면 이 프롬프트 이름을 참조하는 템플릿이 다음 문서 생성부터 이 버전을 사용하게 됩니다.",
    emptyTitle: "등록된 프롬프트가 없습니다",
    // 읽기 전용 역할(operator/auditor)에는 렌더되지 않는 '+ 추가' 버튼을 누르라고 안내하지 않는다.
    // 안내 문구의 생명주기는 실제 강제되는 전이(draft→test→review→published)에 맞춘다('테스트' 단계 포함).
    emptyHelp: writerEmptyHelp("‘+ 프롬프트 추가’로 AI에게 줄 지시문을 만들어 초안→테스트→검토→발행 순으로 버전 관리하세요.", "프롬프트는 관리자가 등록합니다. 등록되면 버전이 여기에 표시됩니다."),
    // 다른 온보딩 화면(연동/러너)처럼 단계별 안내를 준다(생명주기: 초안→테스트→검토→발행).
    emptySituation: "AI에게 줄 지시문(프롬프트)이 아직 하나도 없습니다.",
    emptySteps: ["‘+ 프롬프트 추가’로 초안을 만듭니다.", "‘테스트로 → 검토로’ 순으로 상태를 올립니다.", "‘발행’하면 이 이름을 참조하는 템플릿이 다음 문서 생성부터 이 버전을 사용합니다."],
    emptyExpected: "발행된 버전이 실제 사용되며, 같은 이름의 이전 발행본은 자동으로 보관됩니다.",
    createLabel: "+ 프롬프트 추가",
    // 템플릿 화면의 '프롬프트 ID' 링크가 ?id=로 넘겨주는 딥링크를 소비해 그 프롬프트의 상세 드로어를
    // 곧바로 연다(단건 GET — runners.onQuery와 동일한 패턴). 이 라우터의 GET /{row_id}는 {"item":...}
    // 모양으로 응답한다(app/prompts/router.py get_one) — runner/job과 selectKey가 다르다.
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "item",
    // 백엔드 list_all은 page/page_size 파라미터를 받아 실제로 페이지네이션한다(app/prompts/router.py) —
    // 예전엔 registry.js가 이걸 전혀 안 써서 500건 상한 경고에만 의존했다. paginated:true로 실제
    // '다음' 컨트롤을 켠다(total이 없는 응답이라도 DataScreen 페이저가 pageSize 가득 찬 페이지면
    // '다음'을 계속 켜 둔다) — capWarning은 그래도 남겨 500건 상한 자체는 계속 알린다.
    paginated: true,
    capWarning: 500,
    // 이름으로 좁혀 한 프롬프트의 버전들만 모아 본다(백엔드 ?name= 정확 일치 필터). 상태로도 좁힐 수
    // 있게 한다(백엔드가 지원 — app/prompts/router.py) — 목록이 모든 버전을 다 보여주므로 이름 없이
    // '지금 발행된 것만'·'검토 대기만' 같은 질문에 답할 방법이 없었다.
    // status 기본값을 'published'로 스코프한다(정책 화면과 동일 — 여전히 '전체'로 바꿀 수 있다).
    // 기본값이 없으면 첫 방문마다 초안/테스트/검토/발행/보관 버전이 모두 뒤섞여, '지금 실제로 쓰이는
    // 것'을 알아보려면 매번 손으로 필터를 걸어야 했다. name도 정책처럼 현재 페이지 값으로 자동완성 제안.
    filters: [{ key: "name", type: "text", label: "이름(정확히)", datalistFrom: (items) => items.map((r) => r.name) },
      { key: "status", type: "select", label: "상태", value: "published", options: opt([["draft", "초안"], ["test", "테스트"], ["review", "검토"], ["published", "발행됨"], ["archived", "보관됨"]]) }],
    // 용도(purpose)를 목록 열로 노출 — _prompt_view가 이미 돌려주는데도 상세에만 있어 여러 버전이
    // 쌓인 목록에서 각 프롬프트가 '무엇을 위한 것인지' 행마다 열어보지 않고는 알 수 없었다.
    // runner_id도 목록 열로 노출 — 예전엔 상세를 열어야만 어느 러너와 연관되었는지 보였다.
    // purpose는 최대 2000자에 create/edit 폼도 여러 줄 textarea라 자르지 않으면 표가 옆으로 밀린다
    // (list_field 상세는 여전히 truncateCol의 title 속성으로 전체 확인 가능 — 오류 열과 동일 패턴).
    // runner_id는 러너 화면으로 바로 확인하러 갈 수 있게 클릭 가능한 링크로 보여준다(러너 상세의
    // integration_id와 동일한 패턴 — 원시 UUID로 방치하지 않음).
    // runner_id는 이제 링크로 보여준다 — 러너 화면이 ?id= 기반 딥링크(onQuery)를 지원하게 되어,
    // 클릭하면 그 러너의 상세 드로어가 곧바로 열린다(러너 상세의 integration_id와 동일한 패턴).
    columns: [col("name", "이름"), truncateCol("purpose", "용도", 60),
      { key: "runner_id", label: "러너 ID", render: (r) => r.runner_id ? React.createElement("a", { href: "#/runners?id=" + encodeURIComponent(r.runner_id) }, r.runner_id) : "-" },
      col("version", "버전"), badgeCol("status", "상태"), dateCol("created_at", "생성")],
    // 상세에서 실제 지시문(발행본 포함)을 읽을 수 있게 — 편집은 초안만이라 그 외엔 읽기 전용으로 노출.
    // purpose·runner_id는 이제 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    detailFields: [field("id", "프롬프트 ID"),
      { key: "created_by", label: "작성자", render: (r) => r.created_by_name || r.created_by_email || r.created_by || "-" },
      // 초안이 아니면 '수정' 버튼이 통째로 사라진다(editWhen 아래) — policies와 동일한 이유로 편집
      // 안내를 남긴다(registry.js policies의 _edit_note와 동일 패턴).
      { key: "_edit_note", label: "편집 안내", render: (r) => r.status !== "draft" ? "이 버전은 초안이 아니라 편집할 수 없습니다, 아래 ‘새 버전’으로 편집 가능한 초안을 만드세요." : "-" },
      dateCol("published_at", "발행 시각"), jsonField("content", "프롬프트 내용")],
    // purpose는 서버에서 최대 2000자까지 허용한다(app/prompts/router.py) — 한 줄 text 입력은 좁아서
    // textarea로(워크플로의 purpose 필드와 동일한 대우).
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "purpose", label: "용도", type: "textarea" },
      { name: "runner_id", label: "러너 ID(선택)", type: "text", help: "이 프롬프트와 연관지을 러너의 ID(참고용 메타데이터, 이 값만으로 실행되지는 않습니다). ‘러너’ 화면에서 확인." },
      { name: "content", label: "프롬프트 내용", type: "textarea", required: true, help: "AI에게 주는 지시문입니다. 무엇을, 어떤 형식으로 만들지 구체적으로 적으세요. 예: ‘아래 티켓 목록을 프로젝트별로 묶어 주간 보고서를 마크다운 표로 요약해줘. 완료, 지연 건수를 강조할 것.’ 이 이름을 참조하는 템플릿이 문서 생성 시 이 내용을 사용합니다." },
    ] },
    // 수정은 ContentUpdateRequest(PATCH) 계약: 내용·용도만(이름은 새 버전으로만 바뀜). 초안일 때만 편집 가능(그 외 409).
    editMethod: "PATCH", editWhen: (r) => r.status === "draft", edit: { roles: WRITE_ROLES, fields: [
      { name: "content", label: "프롬프트 내용", type: "textarea", required: true, help: "AI에게 주는 지시문입니다. 무엇을, 어떤 형식으로 만들지 구체적으로 적으세요. 예: ‘아래 티켓 목록을 프로젝트별로 묶어 주간 보고서를 마크다운 표로 요약해줘. 완료, 지연 건수를 강조할 것.’ 이 이름을 참조하는 템플릿이 문서 생성 시 이 내용을 사용합니다." },
      { name: "purpose", label: "용도", type: "textarea" },
      { name: "runner_id", label: "러너 ID(선택)", type: "text", help: "이 프롬프트와 연관지을 러너의 ID(참고용 메타데이터, 이 값만으로 실행되지는 않습니다). ‘러너’ 화면에서 확인. 비우면 연결 해제." },
    ] },
    actions: [
      { label: "테스트로", roles: WRITE_ROLES, when: (r) => r.status === "draft", path: (r) => "/api/admin/prompts/" + r.id + "/transition", body: { status: "test" }, confirm: "이 버전을 테스트 단계로 옮길까요? 상태만 바뀔 뿐, 러너로 실제 실행되거나 내용이 검증되지는 않습니다." },
      { label: "검토로", roles: WRITE_ROLES, when: (r) => r.status === "test", path: (r) => "/api/admin/prompts/" + r.id + "/transition", body: { status: "review" }, confirm: "이 버전을 검토 단계로 옮길까요? 상태만 바뀔 뿐 내용이 검증되지는 않습니다." },
      { label: "초안으로 되돌리기", roles: WRITE_ROLES, when: (r) => r.status === "test" || r.status === "review", path: (r) => "/api/admin/prompts/" + r.id + "/transition", body: { status: "draft" }, confirm: "이 버전을 초안으로 되돌려 다시 편집할까요?" },
      { label: "발행", variant: "primary", roles: WRITE_ROLES, when: (r) => r.status === "review", path: (r) => "/api/admin/prompts/" + r.id + "/transition", body: { status: "published" }, confirm: "이 버전을 발행할까요? 발행되면 실제 사용되며, 현재 발행 중인 같은 이름의 버전은 자동으로 보관(archive)됩니다." },
      // 새 버전은 백엔드가 어떤 상태에서든 새 초안으로 분기한다(발행본에만 국한하지 않음).
      // keepSelection — 새 버전을 만드는 목적이 '바로 이어서 편집'이므로, 드로어를 닫고 목록으로
      // 튕겨 내지 않고 응답이 돌려준 새 초안(item)으로 드로어를 갱신해 이어서 '수정'을 누를 수 있게 한다.
      { label: "새 버전", roles: WRITE_ROLES, when: (r) => r.status !== "draft", path: (r) => "/api/admin/prompts/" + r.id + "/new-version", keepSelection: true },
      // 버전 목록 + 행에서 롤백·비교(diff). 상태와 무관하게 노출(발행본이 없어도 이력·복원 가능).
      nameVersionsAction("/api/admin/prompts", "프롬프트 버전 기록"),
      { label: "보관", variant: "danger", roles: WRITE_ROLES, when: (r) => r.status !== "archived", path: (r) => "/api/admin/prompts/" + r.id + "/transition", body: { status: "archived" }, confirm: "이 버전을 보관할까요? 보관하면 더 이상 발행, 사용되지 않지만 이력으로는 목록에 남습니다." },
      // prompts는 감사 로그의 유효한 object_type이고(router.py: action=f"{kind}.create" 등, kind="prompts")
      // 모든 쓰기가 이 타입으로 기록된다 — 구조적으로 동일한 policies에 이미 있는 딥링크와 맞춘다.
      // operator는 프롬프트 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx
      // SCREEN_ROLES) — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=prompts&object_id=" + r.id },
    ],
  },
  policies: {
    key: "policies", area: "콘텐츠", title: "정책", endpoint: "/api/admin/policies",
    // 정책은 프롬프트보다 실제 파급력이 크다 — 발행하면 app/documents/service.py apply_template_bindings()/
    // _resolve_published_binding()가 이 정책 '이름'을 참조하는 모든 Template에 그 순간부터 현재 발행
    // 버전의 JSON을 그대로 n8n 페이로드에 inline한다(문서 생성이 다시 일어날 때마다). '테스트로'·
    // '검토로'·'발행'·'보관'은 상태만 바꿀 뿐 JSON 내용을 검증하지 않는다(프롬프트와 동일).
    help: "업무 규칙(정책)을 관리합니다. ‘테스트로’, ‘검토로’, ‘발행’, ‘보관’은 상태만 바꿀 뿐, 내용(JSON)을 검증하지 않습니다, 내용 검증은 화면 밖에서 직접 확인하세요. 발행하면 이 정책 이름을 참조하는 모든 템플릿이 그 즉시(다음 문서 생성부터) 새 버전의 JSON을 그대로 사용하게 됩니다, 프롬프트보다 실제 파급력이 큽니다.",
    emptyTitle: "등록된 정책이 없습니다",
    // 정책도 프롬프트와 동일하게 4단계 생명주기(초안→테스트→검토→발행)를 강제한다 — '등록하고
    // 발행하세요'는 마치 한 단계로 끝나는 것처럼 읽혀, 새 관리자가 초안 행에서 비활성 '발행' 버튼을
    // 만나고 이유를 못 찾았다(프롬프트 registry.js:404와 동일 문구로 맞춘다).
    emptyHelp: writerEmptyHelp("‘+ 정책 추가’로 업무 규칙(JSON)을 만들어 초안→테스트→검토→발행 순으로 버전 관리하세요.", "정책은 관리자가 등록합니다. 등록되면 버전이 여기에 표시됩니다."),
    createLabel: "+ 정책 추가",
    // 템플릿 화면의 '정책 ID' 링크가 ?id=로 넘겨주는 딥링크를 소비해 그 정책의 상세 드로어를 곧바로
    // 연다(runners.onQuery와 동일한 패턴). 이 라우터의 GET /{row_id}는 {"item":...} 모양으로
    // 응답한다(app/prompts/router.py _build_router가 prompts/policies를 함께 만드는 get_one).
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "item",
    // 백엔드 list_all은 프롬프트와 동일하게 page/page_size를 지원한다(app/prompts/router.py의 같은
    // 엔드포인트를 정책도 공유) — paginated:true로 실제 '다음' 컨트롤을 켠다(프롬프트 registry.js와
    // 동일). capWarning은 500건 상한 자체를 계속 알린다.
    paginated: true,
    capWarning: 500,
    // 이름으로 좁혀 한 정책의 버전들만 모아 본다(백엔드 ?name= 정확 일치 필터). 상태로도 좁힐 수 있게
    // 한다(백엔드 list_all이 status를 지원한다 — 프롬프트와 동일 엔드포인트) — 이름 없이 '지금 검토
    // 대기 중인 정책만' 같은 질문에 답할 방법이 없었다.
    // status 기본값을 'published'로 스코프한다(여전히 '전체'로 바꿀 수 있다) — 기본값이 없으면
    // 첫 방문마다 초안/테스트/검토/발행/보관 버전이 모두 뒤섞여, '지금 실제로 쓰이는 것'을
    // 알아보려면 매번 손으로 필터를 걸어야 했다.
    // name 필터는 백엔드가 정확 일치만 지원한다(model.name == name) — 이름을 미리 몰라도 시도할
    // 수 있게, 이미 불러온 현재 페이지에서 뽑은 이름으로 자동완성 제안(datalist)을 준다.
    filters: [{ key: "name", type: "text", label: "이름(정확히)", datalistFrom: (items) => items.map((r) => r.name) },
      { key: "status", type: "select", label: "상태", value: "published", options: opt([["draft", "초안"], ["test", "테스트"], ["review", "검토"], ["published", "발행됨"], ["archived", "보관됨"]]) }],
    columns: [col("name", "이름"), col("version", "버전"), badgeCol("status", "상태"), dateCol("created_at", "생성")],
    // id는 템플릿의 policy_id 입력에 쓰이므로 상세에서 확인할 수 있게 노출한다(라벨은 프롬프트의
    // '프롬프트 ID'와 맞춰 어느 화면 상세를 보고 있는지 분명히 한다 — 템플릿의 policy_id 도움말이
    // '정책 화면 상세의 ID를 입력'이라 안내한다).
    // created_by는 _policy_view가 감사 로그의 actor_name과 동일한 패턴으로 created_by_name/
    // created_by_email을 이미 계산해 돌려준다 — 원시 UUID 대신 그 이름을 보여준다(프롬프트 상세와 동일 패턴).
    detailFields: [field("id", "정책 ID"),
      { key: "created_by", label: "작성자", render: (r) => r.created_by_name || r.created_by_email || r.created_by || "-" },
      // 초안이 아니면 '수정' 버튼이 통째로 사라진다(editWhen 아래) — 이유를 밝히지 않으면 이 화면을
      // 처음 보는 관리자는 왜 버튼이 없는지 알 방법이 없다. '새 버전'이 실제 대안이라고 안내한다.
      { key: "_edit_note", label: "편집 안내", render: (r) => r.status !== "draft" ? "이 버전은 초안이 아니라 편집할 수 없습니다, 아래 ‘새 버전’으로 편집 가능한 초안을 만드세요." : "-" },
      dateCol("published_at", "발행 시각"), jsonField("content", "규칙(JSON)")],
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      // 서버 기본값("{}")과 맞춘다(app/prompts/router.py PolicyCreateRequest.content) — 값 없이는
      // 다른 registry create 필드처럼 즉시 제출 가능해야 한다(예전엔 최소 "{}"라도 직접 타이핑해야 했다).
      { name: "content", label: "규칙(JSON)", type: "json", required: true, value: '{\n  "required_fields": ["title"]\n}', help: '이 정책 이름을 참조하는 템플릿이 문서를 만들 때 n8n 페이로드에 그대로 실립니다. 업무 규칙을 JSON 객체로 적습니다. 위 기본값은 "제목은 필수"라는 뜻의 예시입니다, 필요에 맞게 바꾸세요(예: {"required_fields":["title","owner"],"min_length":10}).' },
    ] },
    editMethod: "PATCH", editWhen: (r) => r.status === "draft", edit: { roles: WRITE_ROLES, fields: [
      { name: "content", label: "규칙(JSON)", type: "json", required: true, help: '예: {"required_fields":["title"]}' },
    ] },
    actions: [
      { label: "테스트로", roles: WRITE_ROLES, when: (r) => r.status === "draft", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "test" }, confirm: "이 버전을 테스트 단계로 옮길까요? 상태만 바뀔 뿐, 러너로 실제 실행되거나 내용(JSON)이 검증되지는 않습니다." },
      { label: "검토로", roles: WRITE_ROLES, when: (r) => r.status === "test", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "review" }, confirm: "이 버전을 검토 단계로 옮길까요? 상태만 바뀔 뿐 내용(JSON)은 검증되지 않습니다." },
      { label: "초안으로 되돌리기", roles: WRITE_ROLES, when: (r) => r.status === "test" || r.status === "review", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "draft" }, confirm: "이 버전을 초안으로 되돌려 다시 편집할까요?" },
      { label: "발행", variant: "primary", roles: WRITE_ROLES, when: (r) => r.status === "review", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "published" }, confirm: "이 버전을 발행할까요? 발행되면 실제 사용되며, 현재 발행 중인 같은 이름의 버전은 자동으로 보관(archive)됩니다." },
      // keepSelection — 새 버전을 만드는 목적이 '바로 이어서 편집'이므로(내용은 초안일 때만 편집
      // 가능), 프롬프트의 '새 버전'과 동일하게 드로어를 닫지 않고 새 초안으로 갱신한다.
      { label: "새 버전", roles: WRITE_ROLES, when: (r) => r.status !== "draft", path: (r) => "/api/admin/policies/" + r.id + "/new-version", keepSelection: true },
      // 정책도 프롬프트와 동일하게 버전 기록 + 롤백 + 비교(diff)를 노출한다(잘못 발행된 규칙 복원 경로).
      nameVersionsAction("/api/admin/policies", "정책 버전 기록"),
      // 이 화면 자신의 help가 '발행하면 이 정책 이름을 참조하는 모든 템플릿이 즉시 영향받는다'고
      // 경고하면서도(위 help), 어떤 템플릿이 실제로 이 정책을 참조하는지 볼 방법이 어디에도 없었다
      // — 발행·보관·롤백 전에 파급 범위를 미리 확인할 수 있게 한다. list_templates가 policy_id
      // 쿼리 파라미터를 지원하지 않으므로(app/templates/router.py) 이미 있는 전체 목록 GET을 그대로
      // 불러와 화면에서 filterRows로 policy_id가 일치하는 행만 걸러 보여준다(clientFilter와 동일한 발상).
      { label: "이 정책을 쓰는 템플릿", subList: {
        title: "이 정책을 쓰는 템플릿",
        endpoint: () => "/api/admin/templates",
        filterRows: (t, parent) => t.policy_id === parent.id,
        columns: [col("name", "이름"), mapCol("target_type", "대상 유형", { workflow: "워크플로", runner: "러너" }), badgeCol("enabled", "활성")],
        emptyTitle: "이 정책을 쓰는 템플릿이 없습니다",
        emptyHelp: "아직 이 정책 이름을 policy_id로 참조하는 템플릿이 없습니다.",
      } },
      { label: "보관", variant: "danger", roles: WRITE_ROLES, when: (r) => r.status !== "archived", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "archived" }, confirm: "이 버전을 보관할까요? 보관하면 더 이상 발행, 사용되지 않지만 이력으로는 목록에 남습니다." },
      // policies는 감사 로그의 유효한 object_type이고(OBJTYPE_OPTS) 모든 쓰기 액션이 이 타입으로
      // 기록된다 — 부서·직책과 동일한 딥링크를 추가한다.
      // operator는 정책 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=policies&object_id=" + r.id },
    ],
  },
  templates: {
    key: "templates", area: "콘텐츠", title: "템플릿", endpoint: "/api/admin/templates",
    help: "자주 하는 자동화를 템플릿으로 저장합니다. 생성 직후에는 비활성 상태이며, 비활성 템플릿은 프롬프트, 정책, 입력값 바인딩과 승인 정책이 모두 적용되지 않습니다(승인 정책만이 아닙니다), 활성화해야 전부 적용됩니다.",
    emptyTitle: "등록된 템플릿이 없습니다",
    emptyHelp: writerEmptyHelp("자주 쓰는 자동화를 템플릿으로 저장하려면 ‘+ 템플릿 추가’를 누르세요. 대상 워크플로/러너와 연결됩니다. 생성 직후에는 비활성 상태이므로 활성화해야 적용됩니다.", "템플릿은 관리자가 등록합니다. 등록되면 여기에 표시됩니다."),
    createLabel: "+ 템플릿 추가",
    // 문서 화면의 '템플릿 ID' 링크가 ?id=로 넘겨주는 딥링크를 소비해 그 템플릿의 상세 드로어를
    // 곧바로 연다(runners.onQuery와 동일한 패턴). 이 라우터의 GET /{template_id}는 {"template":...}
    // 모양으로 응답한다(app/templates/router.py get_template).
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "template",
    // templates는 paginated도 searchable도 아니라 클라이언트 검색창이 뜨는데, searchFields가 없으면
    // JSON.stringify(row) 전체(id·target_ref·prompt_id·policy_id·created_by UUID·ISO 타임스탬프)를 훑어
    // 화면에 안 보이는 값까지 매칭했다 — 사람이 보는 텍스트(이름·설명)만 검색 대상으로 좁힌다.
    searchFields: ["name", "description"],
    // 백엔드는 target_type/enabled 쿼리 파라미터를 지원하지 않으므로(app/templates/router.py
    // list_templates가 파라미터를 전혀 받지 않는다) clientFilter:true로 이미 받아 온 전체 목록을
    // 화면에서 직접 거른다(workflows.filters와 동일한 이유·패턴).
    filters: [
      { key: "target_type", type: "select", label: "대상 유형", clientFilter: true, options: opt([["workflow", "워크플로"], ["runner", "러너"]]) },
      { key: "enabled", type: "select", label: "활성", clientFilter: true, options: opt([["true", "활성"], ["false", "비활성"]]) },
    ],
    // target_ref는 다른 화면(대상 유형이 워크플로일 때 '업무 자동화 흐름') 엔티티의 ID다 — 러너
    // 상세의 integration_id와 동일한 이유로 원시 텍스트 대신 그 화면으로 바로 이동하는 링크로 보여준다.
    columns: [col("name", "이름"),
      // target_type='runner' 행은 목록을 훑는 것만으로는 대상 워크플로 재지정이 안 된다는 특이점이
      // 안 보였다(상세를 열어야만 _runner_target_note로 알 수 있었다) — 경고 배지로 목록에서 바로 신호한다.
      { key: "target_type", label: "대상 유형", render: (r) => r.target_type === "runner"
        ? React.createElement(Badge, { value: "러너(대상 워크플로 재지정 미지원)", kind: "warn" })
        : ({ workflow: "워크플로", runner: "러너" }[r.target_type] || r.target_type || "-") },
      // 신규로는 target_type='runner'를 고를 수 없지만(TEMPLATE_TARGET_OPTS) 예전에 만들어진 행은
      // 여전히 유효하다(edit 폼의 '러너(신규 선택 불가, 기존 값 유지)' 옵션 참고) — 그 행도 대상
      // 화면으로 이동할 수 있게 target_type에 따라 링크 대상을 분기한다.
      { key: "target_ref", label: "대상 ID", render: (r) => {
        if (!r.target_ref) return "-";
        // 워크플로 화면은 이제 ?id=로 특정 워크플로 상세를 곧바로 여는 딥링크(onQuery)를 지원한다.
        if (r.target_type === "workflow") return React.createElement("a", { href: "#/workflows?id=" + encodeURIComponent(r.target_ref) }, r.target_ref);
        // 러너 화면은 이제 ?id=로 특정 러너 상세를 곧바로 여는 딥링크(onQuery)를 지원한다 — 무필터
        // 전체 목록에만 떨어지던 죽은 앵커가 아니라 실제로 그 러너로 데려간다.
        if (r.target_type === "runner") return React.createElement("a", { href: "#/runners?id=" + encodeURIComponent(r.target_ref) }, r.target_ref);
        return r.target_ref;
      } },
      badgeCol("enabled", "활성"), dateCol("created_at", "생성")],
    // id는 문서 생성 폼의 config template_id 입력에 쓰이므로 상세에서 확인·복사할 수 있게 노출.
    // target_ref는 이제 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    // created_by는 프롬프트·정책과 동일한 이유로(_view가 이미 돌려준다) 노출한다 — 이 템플릿을
    // 누가 만들었는지 지금까지는 API가 값을 줘도 화면 어디에도 안 보였다.
    // prompt_id·policy_id는 다른 화면 엔티티의 ID다 — 러너 상세의 integration_id와 동일한 이유로
    // 원시 텍스트 대신 해당 화면으로 바로 이동하는 링크로 보여준다(target_ref는 위 columns에서 처리).
    detailFields: [field("id", "템플릿 ID"), field("description", "설명"),
      // target_type='runner' 행은 신규로는 못 만들지만(TEMPLATE_TARGET_OPTS) 예전에 만들어진 행은
      // 여전히 정상 UI로 보인다 — 실제로는 apply_template_bindings가 target_type==='workflow'일
      // 때만 대상을 해석하므로, 이 행의 '이 템플릿으로 문서 생성' 등 자동 소비 경로가 없다는 점을
      // 상세에서 명시한다(RESERVED_WORKFLOW_NOTES와 동일한 '겉보기엔 정상이지만 아님' 패턴).
      { key: "_runner_target_note", label: "[주의] 대상 유형", render: (r) => r.target_type === "runner"
        ? "이 템플릿의 대상 유형은 '러너'입니다, 대상 워크플로 재지정(자동 문서 생성의 워크플로 호출)만 적용되지 않습니다. 프롬프트, 정책, 입력 스키마, 승인 정책 바인딩은 여전히 config.template_id를 통해 정상 적용됩니다."
        : "-" },
      // 프롬프트/정책 화면이 이제 ?id=로 특정 행 상세를 곧바로 여는 딥링크(onQuery)를 지원한다 —
      // 무필터 전체 목록에만 떨어지던 죽은 앵커가 아니라 실제로 그 프롬프트/정책으로 데려간다.
      { key: "prompt_id", label: "프롬프트 ID", render: (r) => r.prompt_id ? React.createElement("a", { href: "#/prompts?id=" + encodeURIComponent(r.prompt_id) }, r.prompt_id) : "-" },
      { key: "policy_id", label: "정책 ID", render: (r) => r.policy_id ? React.createElement("a", { href: "#/policies?id=" + encodeURIComponent(r.policy_id) }, r.policy_id) : "-" },
      // 비활성 템플릿은 '이 템플릿으로 문서 생성' CTA가 숨겨진다(enabled && workflow일 때만) — 왜
      // 그 버튼이 없는지 상세에서 바로 설명한다(RESERVED_WORKFLOW_NOTES와 동일한 '혼란 지점 안내' 패턴).
      { key: "_inactive_note", label: "[주의] 활성 상태", render: (r) => r.enabled ? "-" : "이 템플릿은 비활성 상태입니다, 활성화해야 문서 생성에 사용되고 프롬프트, 정책, 입력 스키마, 승인 정책 바인딩이 적용됩니다." },
      field("created_by", "작성자 ID"), jsonField("input_schema", "입력 스키마"),
      // approval_policy는 폼에선 체크박스('발행 전 승인 필요')로 다루면서 상세에선 raw JSON({"required":true})을
      // 보여줘 계약 형태가 새고 폼 어휘와 어긋났다 — 폼과 같은 어휘로 예/아니오만 보여준다.
      { key: "approval_policy", label: "승인 정책", render: (r) => "발행 전 승인 필요: " + ((r.approval_policy && r.approval_policy.required) ? "예" : "아니오") },
      dateCol("updated_at", "수정")],
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "description", label: "설명", type: "textarea" },
      { name: "target_type", label: "대상 유형", type: "select", value: "workflow", options: TEMPLATE_TARGET_OPTS },
      { name: "target_ref", label: "대상 ID", type: "text", required: true, help: "대상 유형이 워크플로면 ‘업무 자동화 흐름(워크플로)’ 화면에서, 러너면 ‘자동화 작업 실행기(러너)’ 화면에서 대상의 ID를 확인해 입력하세요." },
      { name: "prompt_id", label: "프롬프트 ID(선택)", type: "text", help: "‘프롬프트’ 화면에서 확인." },
      { name: "policy_id", label: "정책 ID(선택)", type: "text", help: "‘정책’ 화면 상세의 ID를 입력." },
      // apply_template_bindings(app/documents/service.py)는 input_schema를 {**input_schema, **config}로
      // '문서 생성' config의 기본값 dict로 평평하게 병합할 뿐, 필드 정의(required 등)를 해석하지 않는다
      // — 예전 예시({"fields":[...]})는 실제로 없는 동적 폼 기능을 암시했다.
      // 백엔드가 dict로 타입하고 비-객체(배열/문자열/숫자)는 422로 거절한다(router.py) — jsonObject:true로
      // 클라이언트에서 먼저 객체 여부를 검증한다(documents.config 필드와 동일 — 서버 왕복 전에 막는다).
      ...TEMPLATE_SCHEMA_FIELDS,
      // 백엔드 검증기(_approval_policy_shape, app/templates/router.py)는 {"required": true|false}
      // 딱 하나의 형태만 받는다 — 사실상 불리언 하나인데 JSON 문법·정확한 키 이름을 직접 타이핑하게
      // 했던 것을 워크플로의 approval_required와 같은 체크박스로 바꾼다(오타·형식 오류 여지 제거).
      { name: "approval_policy_required", label: "승인 정책", type: "checkbox", value: false, checkLabel: "발행 전 승인 필요" },
    ] },
    actions: [
      // 템플릿 데드엔드 해소 — 이 템플릿으로 곧바로 '문서 생성' 폼을 연다(대상 워크플로 ID·template_id 프리필).
      // 백엔드 apply_template_bindings가 config.template_id로 프롬프트·정책·입력 스키마·대상 워크플로를 해석한다.
      // 비활성 템플릿은 문서 서비스가 무시하므로 활성 + 워크플로 대상일 때만 노출한다(러너 대상은 문서 생성 대상 아님).
      { label: "이 템플릿으로 문서 생성", variant: "primary", roles: WRITE_ROLES, when: (r) => r.enabled && r.target_type === "workflow",
        navigate: (r) => "#/documents?template_id=" + encodeURIComponent(r.id) + "&workflow_id=" + encodeURIComponent(r.target_ref) },
      ...onoff("/api/admin/templates"),
      // 템플릿은 버전 기록/롤백이 없는 유일한 콘텐츠 화면이다(정책·프롬프트·연동·러너·워크플로와 달리) —
      // 최소한 감사 로그로라도 변경 이력을 볼 수 있게 한다(template은 이미 OBJTYPE_OPTS에 있다).
      // operator는 이 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES) —
      // approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=template&object_id=" + r.id },
    ],
    // PUT은 전체 교체다 → 편집은 기존 값을 모두 함께 돌려보내야 바인딩(prompt/policy/스키마)이 지워지지 않는다.
    editMethod: "PUT", edit: { roles: WRITE_ROLES, fields: (role, row) => [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "description", label: "설명", type: "textarea" },
      // target_type의 선택지는 원래 워크플로만 준다(TEMPLATE_TARGET_OPTS) — 하지만 백엔드는 예전에
      // 만들어진 target_type='runner' 행도 여전히 유효하게 검증·저장한다. 그 값을 옵션에서 빼면
      // 그런 행을 열 때마다 값이 목록에 없는 select가 되어(브라우저가 첫 옵션으로 되돌리거나 빈
      // 값으로 표시) 저장 시 조용히 다른 대상으로 바뀔 위험이 있다 — 현재 값이 'runner'면 그 값을
      // 그대로 유지할 수 있는 선택지를 하나 더 끼워 넣는다(신규로 고르지는 못하게, 기존 값만 유지).
      { name: "target_type", label: "대상 유형", type: "select",
        options: (row && row.target_type === "runner")
          ? [...TEMPLATE_TARGET_OPTS, { value: "runner", label: "러너(신규 선택 불가, 기존 값 유지)" }]
          : TEMPLATE_TARGET_OPTS },
      { name: "target_ref", label: "대상 ID", type: "text", required: true, help: "대상 유형이 워크플로면 ‘업무 자동화 흐름(워크플로)’ 화면에서, 러너면 ‘자동화 작업 실행기(러너)’ 화면에서 대상의 ID를 확인해 입력하세요." },
      { name: "prompt_id", label: "프롬프트 ID(선택)", type: "text", help: "‘프롬프트’ 화면에서 확인." },
      { name: "policy_id", label: "정책 ID(선택)", type: "text", help: "‘정책’ 화면 상세의 ID를 입력." },
      ...TEMPLATE_SCHEMA_FIELDS,
      { name: "approval_policy_required", label: "승인 정책", type: "checkbox", checkLabel: "발행 전 승인 필요" },
    ] },
    // approval_policy_required(체크박스) ↔ approval_policy:{required:bool}, 그리고 input_schema(dict) ↔
    // 명명 필드(source_database 등) 상호 변환. 폼은 사람이 읽는 필드를, 백엔드는 계약 형태를 본다.
    fromRow: (r) => ({ ...r, approval_policy_required: !!(r.approval_policy && r.approval_policy.required), ...disassembleInputSchema(r.input_schema) }),
    toApiBody: (body) => {
      const { approval_policy_required, source_database, output_format, title_rule, target_parent_page, target_database, input_schema_extra, ...rest } = body;
      return { ...rest, approval_policy: { required: !!approval_policy_required }, input_schema: assembleInputSchema(body) };
    },
  },
  schedules: {
    key: "schedules", area: "자동화", title: "실행 일정(스케줄)", endpoint: "/api/admin/schedules",
    help: "정해진 시간에 자동 실행을 예약합니다.",
    emptyTitle: "예약된 일정이 없습니다",
    // 문서 화면의 '정기 실행으로 예약'에서 넘어온 ?workflow_id= 쿼리를 생성 폼 프리필로 소비한다
    // (템플릿 → 문서 생성 프리필과 동일한 onQuery 패턴). 대상 유형은 워크플로로 고정해 시작한다.
    // ?id=는 다른 화면(승인의 '대상 보기' 등)이 특정 스케줄로 딥링크할 때 쓴다 — runners.onQuery와
    // 동일한 패턴으로 그 스케줄의 상세 드로어를 곧바로 연다.
    onQuery: (p) => p.id
      ? { open: "select", id: p.id }
      : (p.workflow_id ? { open: "create", initial: { target_type: "workflow", target_ref: p.workflow_id } } : null),
    selectKey: "schedule",
    // 생성 권한이 없는 역할(operator/auditor)에게는 없는 버튼('+ 스케줄 추가')을 누르라고 안내하지 않는다(백업·문서 화면과 동일 패턴).
    emptyHelp: (role) => (role === "admin" || role === "system_admin")
      ? "‘+ 스케줄 추가’로 Cron 또는 1회 실행 일정을 만들어 워크플로를 자동 실행하세요."
      : "실행 일정은 관리자가 등록합니다. 등록되면 예약과 다음 실행 시각이 여기에 표시됩니다.",
    createLabel: "+ 스케줄 추가",
    // list_schedules(app/schedules/router.py)는 쿼리 파라미터를 전혀 받지 않는다(항상 전체 목록) —
    // clientFilter:true로 이미 받아 온 목록을 화면에서 직접 거른다(workflows.filters와 동일 패턴).
    // 스케줄은 삭제/보관 엔드포인트가 없어 비활성·완료된 once형도 계속 목록에 남으므로, 활성만
    // 보고 싶을 때 걸러낼 방법이 지금까지 없었다.
    filters: [
      { key: "enabled", type: "select", label: "활성", clientFilter: true, options: opt([["true", "활성"], ["false", "비활성"]]) },
      { key: "schedule_type", type: "select", label: "유형", clientFilter: true, options: SCHEDT_OPTS },
      { key: "target_type", type: "select", label: "대상 유형", clientFilter: true, options: SCHED_TARGET_OPTS },
    ],
    // 1회(once) 일정은 Cron 식이 없다 → 빈 칸 대신 유형 라벨을 보여준다(실제 실행 시각은 '다음 실행' 열).
    // target_type/target_ref도 목록 열로 노출 — 이 일정이 실제로 무엇을 실행하는지(어느 워크플로/
    // 시스템)가 예전엔 상세를 하나씩 열어야만 보였다. target_ref는 대상이 워크플로일 때 그 화면으로
    // 바로 이동하는 링크로 보여준다(러너 상세의 integration_id와 동일한 패턴).
    columns: [col("name", "이름"), mapCol("schedule_type", "유형", SCHED_TYPE),
      { key: "cron_expression", label: "실행 일정(Cron)", render: (r) => r.schedule_type === "once" ? "1회 실행(‘다음 실행’ 참고)" : (r.cron_expression == null || r.cron_expression === "" ? "-" : String(r.cron_expression)) },
      mapCol("target_type", "대상 유형", { workflow: "워크플로", system: "시스템" }),
      // 워크플로 화면의 ?id= 딥링크(onQuery)로 그 워크플로 상세를 곧바로 연다(무필터 전체 목록 아님).
      { key: "target_ref", label: "대상 ID", render: (r) => (r.target_ref && r.target_type === "workflow") ? React.createElement("a", { href: "#/workflows?id=" + encodeURIComponent(r.target_ref) }, r.target_ref) : (r.target_ref || "-") },
      badgeCol("enabled", "활성"),
      // 비활성화(disable_schedule)는 next_run_at을 지우지 않는다(백엔드가 enabled만 끈다) — 그대로
      // 보여주면 '이 시각에 다시 실행될 것'처럼 읽힌다. 비활성 행은 활성 배지로 알 수 있으니 이 열은
      // 무의미한 미래 시각 대신 '-'로 지워 이중 확인을 강제하지 않는다.
      { key: "next_run_at", label: "다음 실행", render: (r) => r.enabled ? fmtDateTime(r.next_run_at) : "-" },
      dateCol("last_run_at", "마지막 실행"),
      // 백엔드가 now > end_at이면 cron 일정을 자동 비활성화한다(scheduler.py advance_next_run) —
      // 상세를 하나씩 열지 않고도 곧 만료될 일정을 목록에서 바로 훑을 수 있게 노출한다.
      dateCol("end_at", "유효 기간(종료)")],
    // 관리자(비-system_admin)가 활성 스케줄의 정의를 바꾸면 백엔드가 재승인 위해 자동 비활성화한다 → 저장 후 경고.
    onSaved: (res, { toast, prev }) => {
      const s = res && res.schedule;
      if (prev && prev.enabled && s && s.enabled === false) {
        toast("저장했지만 정의 변경으로 비활성화되었습니다, 다시 활성화(승인)해야 실행됩니다.", "error");
        return true;
      }
      return false;
    },
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "description", label: "설명", type: "text" },
      { name: "schedule_type", label: "유형", type: "select", value: "cron", options: SCHEDT_OPTS },
      { name: "preset", label: "간편 주기(선택)", type: "select", value: "", options: SCHED_PRESET_OPTS, help: "고르면 Cron 식이 자동 생성됩니다. ‘사용 안 함’이면 아래 Cron 식/실행 시각을 직접 입력하세요." },
      // 이 폼은 유형(cron/once)에 따른 조건부 표시가 없다 — 두 필드가 항상 함께 보이므로, 각각 어느
      // 유형에서만 쓰이는지 help로 명시해 반대 유형의 값을 채우고 무시되는 걸 모르는 일을 줄인다.
      { name: "cron_expression", label: "Cron 식", type: "text", help: "예: 0 9 * * 1 (매주 월 09:00). 간편 주기를 골랐으면 비워도 됩니다. (유형이 ‘1회 실행’이면 이 값은 쓰이지 않습니다.)" },
      { name: "run_at", label: "실행 시각(1회형, ISO)", type: "text", help: "예: 2026-08-01T09:00:00+09:00, 시간대 표기가 없으면 UTC로 해석됩니다(KST면 +09:00을 붙이세요). (유형이 ‘Cron 반복’이면 이 값은 쓰이지 않습니다.)" },
      { name: "timezone", label: "시간대", type: "text", value: "Asia/Seoul", help: "Cron 평가에 쓰이는 시간대(run_at에는 적용되지 않음)." },
      { name: "target_type", label: "대상 유형", type: "select", value: "workflow", options: SCHED_TARGET_OPTS },
      { name: "target_ref", label: "대상 ID", type: "text", required: true, help: "워크플로: '업무 자동화 흐름(워크플로)' 화면의 ID(승인 필요 없음으로 설정된 워크플로만 스케줄 대상 가능). 시스템: 유효한 값은 'noop' 뿐입니다." },
      { name: "payload_template", label: "실행 페이로드(JSON)", type: "json", help: "워크플로에 보낼 기본 페이로드. 비우면 빈 값으로 실행됩니다." },
      { name: "retry_policy", label: "재시도 정책(JSON)", type: "json", help: '예: {"max_attempts": 3}, 일시 오류 시 최대 재시도 횟수(1~10, 기본 3). app/schedules/scheduler.py가 이 값으로 재시도/백오프를 결정합니다.' },
      // 기본값을 명시하지 않으면 FormModal이 null을 보내 백엔드(non-Optional str)가 422로 거절한다
      // → 모든 기본 경로 스케줄 생성이 실패했다. 백엔드 기본값(skip)과 맞춘다.
      { name: "misfire_policy", label: "누락 처리 정책", type: "select", value: "skip", options: MISFIRE_OPTS },
      { name: "concurrency_policy", label: "동시 실행 정책", type: "select", value: "skip", options: CONCURRENCY_OPTS },
      { name: "timeout_seconds", label: "타임아웃(초)", type: "number" },
      { name: "start_at", label: "시작 시각(ISO, 선택)", type: "text", help: "유효 기간의 시작. 예: 2026-08-01T00:00:00+09:00" },
      { name: "end_at", label: "종료 시각(ISO, 선택)", type: "text", help: "유효 기간의 끝. 예: 2026-12-31T23:59:59+09:00" },
    ] },
    // target_type·target_ref는 이제 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    // end_at은 이제 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    // 목록의 '다음 실행' 열은 비활성 행에서 '-'로 지워지므로(무의미한 미래 시각 오해 방지), 비활성
    // once형이 언제 실행 예정인지 수정 폼을 열지 않고는 볼 수 없었다 — 상세에서는 활성 여부와
    // 무관하게 예정 시각을 보여준다(비활성이면 라벨로 명시). 목록 열과 key가 겹치지 않게 별도 key.
    detailFields: [field("id", "스케줄 ID"), field("owner_user_id", "소유자"),
      { key: "_next_run_scheduled", label: "다음 실행(예정)", render: (r) => r.next_run_at ? fmtDateTime(r.next_run_at) + (r.enabled ? "" : " (현재 비활성)") : "-" },
      field("description", "설명"), field("timezone", "시간대"), mapCol("misfire_policy", "누락 처리 정책", { skip: "건너뛰기", run_once: "한 번만 실행" }), mapCol("concurrency_policy", "동시 실행 정책", { skip: "건너뛰기", allow: "동시 실행 허용" }), field("timeout_seconds", "타임아웃(초)"), dateCol("start_at", "시작 시각"), dateCol("created_at", "생성"), jsonField("payload_template", "실행 페이로드"), jsonField("retry_policy", "재시도 정책")],
    actions: [
      // once형은 백엔드 enable이 실행 시각이 이미 지났으면 항상 409('실행 시각이 이미 지났습니다')로
      // 거절한다 — 눌러도 항상 실패하는 '활성화'를 숨긴다. next_run_at이 아예 없거나(이미 실행됨),
      // 있어도 그 시각이 이미 과거면(비활성인 채 run_at이 지나감) 둘 다 숨긴다('수정'으로 새 run_at
      // 지정 후에만 다시 노출). cron형은 그대로 노출한다.
      ...onoff("/api/admin/schedules", undefined, (r) => {
        if (r.schedule_type !== "once") return true;
        if (!r.next_run_at) return false;
        const s = String(r.next_run_at); const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
        const t = new Date(iso).getTime();
        return Number.isNaN(t) ? true : t > Date.now();
      }),
      // run-now는 비동기로 큐잉될 뿐이라 이 토스트 이후 결과를 알 방법이 없었다(목록엔 자동 갱신도
      // 상태 열도 없다) — 최소한 어디서 결과를 확인할지 명확히 안내한다.
      { label: "지금 실행", roles: OPS_ROLES, when: (r) => r.enabled, path: (r) => "/api/admin/schedules/" + r.id + "/run-now", confirm: "이 일정을 지금 한 번 실행할까요?",
        result: (res) => ({ ok: true, msg: (res.deduplicated ? "이미 실행 중이라 중복 실행을 건너뛰었습니다." : "실행을 시작했습니다(비동기).") + " 결과는 ‘실행 이력’에서 확인하세요." }) },
      // 미리보기: 다음 실행 시각뿐 아니라 '실제로 보낼 페이로드'와 대상까지 안내 모달로 보여준다.
      { label: "미리보기", roles: OPS_ROLES, path: (r) => "/api/admin/schedules/" + r.id + "/dry-run",
        info: (res) => {
          const r0 = res || {};   // 빈/비-JSON 2xx면 api()가 null을 준다 — res.x 직접 접근은 throw
          const t = (r0.next_fire_times_utc || []).slice(0, 5).map(fmtDateTime);
          const lines = [];
          lines.push("다음 실행 예정:\n" + (t.length ? t.map((x) => ", " + x).join("\n") : "  (예정된 실행 시각 없음)"));
          if (r0.target_type || r0.target_ref) lines.push("\n대상: " + (r0.target_type || "?") + " / " + (r0.target_ref || "?"));
          const pp = r0.payload_preview;
          lines.push("\n보낼 페이로드:\n" + (pp == null ? "  (없음)" : (typeof pp === "string" ? pp : JSON.stringify(pp, null, 2))));
          return lines.join("\n");
        } },
      { label: "실행 이력", subList: {
        title: "스케줄 실행 이력",
        paginated: true,
        filters: [{ key: "status", type: "select", label: "결과", options: opt([["failed", "실패"], ["succeeded", "성공"], ["running", "실행 중"], ["queued", "대기"], ["skipped", "건너뜀"]]) }],
        endpoint: (r, p) => "/api/admin/schedules/" + r.id + "/runs?page=" + ((p && p.page) || 1) + (p && p.filters && p.filters.status ? "&status=" + encodeURIComponent(p.filters.status) : ""),
        // _run_view가 request_payload(실제로 보낸 값)도 돌려주는데 목록엔 전혀 없었다 — 실패 원인
        // 진단의 핵심 두 값(보낸 것/받은 것) 중 하나가 아예 안 보였다. 둘 다 진단용 요약으로 노출한다.
        columns: [dateCol("scheduled_at", "예정"), mapCol("status", "결과", SCHED_RUN), dateCol("started_at", "시작"), dateCol("finished_at", "종료"), col("retry_count", "재시도"),
          { key: "request_payload", label: "보낸 페이로드", render: (r) => { const v = r.request_payload; if (v == null || v === "" || (typeof v === "object" && !Object.keys(v).length)) return "-"; const s = typeof v === "string" ? v : JSON.stringify(v); return s.length > 60 ? s.slice(0, 60) + "…" : s; } },
          { key: "response_summary", label: "응답 요약", render: (r) => { const v = r.response_summary; if (v == null || v === "") return "-"; const s = typeof v === "string" ? v : JSON.stringify(v); return s.length > 60 ? s.slice(0, 60) + "…" : s; } },
          // 건너뛴 실행(_record_skip, app/schedules/scheduler.py)은 error_message에 원문 영어 사유
          // 코드('misfire_skip'/'concurrent_run_active')를 그대로 담아 온다 — backupReasonText와 동일한
          // 패턴으로 한국어로 치환하고, 그 외(실제 예외 메시지)는 원문 그대로 보여준다.
          { key: "error_message", label: "오류", render: (r) => schedSkipReasonText(r.error_message) }],
        emptyTitle: "실행 이력이 없습니다", emptyHelp: "아직 이 일정이 실행된 적이 없습니다(또는 이 필터에 해당하는 기록이 없습니다).",
        rowActions: [
          // 목록 열은 진단 핵심 두 값(보낸 페이로드/응답 요약)을 60자로 자른다 — 그 너머는 볼 방법이
          // 없었다. 이미 불러온 행 데이터를 그대로(전체 길이) 안내 모달로 보여준다(네트워크 호출 없음).
          { label: "전체 보기", localInfo: (sub) => {
              const fmt = (v) => (v == null || v === "" || (typeof v === "object" && !Object.keys(v).length)) ? "(없음)" : (typeof v === "string" ? v : JSON.stringify(v, null, 2));
              const lines = ["보낸 페이로드:\n" + fmt(sub.request_payload), "\n응답 요약:\n" + fmt(sub.response_summary)];
              if (sub.error_message) lines.push("\n오류:\n" + fmt(sub.error_message));
              return lines.join("\n");
            } },
          // 재시도는 비활성 스케줄에서 409가 나므로 부모 스케줄이 활성일 때만 노출한다.
          // keepOpen — 방금 재시도한 결과(대기→성공/실패로 바뀌는 것)를 보려고 이 실행 이력을 계속
          // 보고 있는 것인데, 예전엔 성공 즉시 드로어가 닫혀 다시 열어야 했다(같은 목록을 벗어나지
          // 않는 작업이므로 목록만 새로고침하고 드로어는 열어 둔다).
          { label: "재시도", roles: OPS_ROLES, when: (sub, parent) => sub.status === "failed" && !!(parent && parent.enabled),
            path: (sub) => "/api/admin/schedules/runs/" + sub.id + "/retry", keepOpen: true,
            confirm: () => "이 실패한 실행을 다시 시도할까요?" },
        ],
        // 부모 스케줄이 비활성이면 위 '재시도' 버튼이 통째로 숨겨진다(백엔드 _require_execution_gate가
        // 항상 거절하므로) — 그 자리에 이유를 알려준다(DataScreen.jsx SubListDrawer가 소비).
        actionHint: (sub, parent) => (sub.status === "failed" && parent && !parent.enabled)
          ? "이 일정이 비활성 상태라 재시도할 수 없습니다, 먼저 활성화하세요." : null,
      } },
      // operator는 스케줄 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=schedule&object_id=" + r.id },
    ],
    // PUT 전체 교체 → 필수(target_type/target_ref)와 핵심 필드를 모두 함께 보낸다(누락 시 422).
    // 고급 필드(payload_template/retry_policy/misfire/concurrency/timeout/start_at/end_at)도
    // 함께 돌려보내야 한다 — 빠지면 PUT이 이 값들을 기본값으로 되돌린다(라운드트립). _view가 다 준다.
    editMethod: "PUT", edit: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "description", label: "설명", type: "text" },
      { name: "schedule_type", label: "유형", type: "select", options: SCHEDT_OPTS },
      { name: "preset", label: "간편 주기(선택)", type: "select", value: "", options: SCHED_PRESET_OPTS, help: "고르면 Cron 식이 자동 생성됩니다." },
      { name: "cron_expression", label: "Cron 식", type: "text", help: "유형이 ‘1회 실행’이면 이 값은 쓰이지 않습니다." },
      // 이미 실행된 once형은 next_run_at이 비어 있어 이 폼도 run_at을 빈 채로 연다(백엔드 _view가
      // next_run_at이 있을 때만 run_at을 돌려줌) — 그대로 저장하면 백엔드가 422('once 스케줄에는
      // run_at이 필요합니다')로 거절한다. 왜 비어 있는지·무엇을 채워야 하는지 여기서 미리 알린다.
      { name: "run_at", label: "실행 시각(1회형, ISO)", type: "text", help: "시간대 표기가 없으면 UTC로 해석됩니다(KST면 +09:00). 유형이 ‘Cron 반복’이면 이 값은 쓰이지 않습니다. 이미 실행된 1회형 일정은 이 칸이 비어 있습니다, 다시 저장하려면 새 실행 시각을 입력하세요(비워 두면 저장이 거절됩니다)." },
      { name: "timezone", label: "시간대", type: "text" },
      { name: "target_type", label: "대상 유형", type: "select", options: SCHED_TARGET_OPTS },
      { name: "target_ref", label: "대상 ID", type: "text", required: true, help: "워크플로: 워크플로 화면의 ID(승인 필요 없음 워크플로만 가능). 시스템: 'noop'." },
      { name: "payload_template", label: "실행 페이로드(JSON)", type: "json" },
      { name: "retry_policy", label: "재시도 정책(JSON)", type: "json", help: '예: {"max_attempts": 3}, 일시 오류 시 최대 재시도 횟수(1~10, 기본 3).' },
      { name: "misfire_policy", label: "누락 처리 정책", type: "select", options: MISFIRE_OPTS },
      { name: "concurrency_policy", label: "동시 실행 정책", type: "select", options: CONCURRENCY_OPTS },
      { name: "timeout_seconds", label: "타임아웃(초)", type: "number" },
      { name: "start_at", label: "시작 시각(ISO, 선택)", type: "text" },
      { name: "end_at", label: "종료 시각(ISO, 선택)", type: "text" },
    ] },
  },
  documents: {
    key: "documents", area: "자동화", title: "문서 자동 생성", endpoint: "/api/admin/documents",
    help: "Notion 문서를 자동으로 만듭니다. ‘+ 문서 생성’으로 워크플로와 기간을 지정하면 생성 결과가 아래 기록에 남고, ‘승인 대기’ 문서는 ‘승인’ 화면에서 발행합니다.",
    emptyTitle: "생성된 문서가 없습니다",
    // 읽기 전용 역할(operator/auditor)에는 없는 버튼('+ 문서 생성')을 누르라고 안내하지 않는다.
    emptyHelp: (role) => (role === "admin" || role === "system_admin")
      ? "‘+ 문서 생성’으로 워크플로와 기간을 지정하면 Notion 문서를 자동으로 만들고 그 기록이 여기에 남습니다."
      : "문서 생성 권한이 있는 관리자가 생성하면 여기에 기록이 남습니다.",
    // 연동/러너 화면처럼 단계별 온보딩 안내를 준다(canOnboard가 primary 헤더 작업 '+ 문서 생성'을 근거로
    // 쓰기 역할에만 보여준다). 문서 자동화가 설정에서 꺼져 있으면 '+ 문서 생성'이 409로 실패하므로
    // 선행 조건과 설정 화면 확인을 안내하고, 워크플로 등록이 선행이라 relatedLink로 이어 준다.
    emptySituation: "아직 자동 생성된 Notion 문서가 없습니다.",
    emptyPrerequisite: "대상 워크플로가 먼저 등록, 활성화돼 있어야 하고, 설정에서 ‘문서 자동화’가 켜져 있어야 합니다(꺼져 있으면 생성이 409로 거절됩니다, #/settings에서 확인).",
    emptySteps: ["‘+ 문서 생성’으로 대상 워크플로와 기간을 지정합니다.", "모드에 따라 미리보기/승인 대기/발행으로 진행됩니다.", "‘승인 대기’ 문서는 ‘승인’ 화면에서 발행합니다."],
    emptyExpected: "요청한 문서 생성 건이 상태와 함께 이 목록에 남고, 발행되면 Notion 링크가 표시됩니다.",
    emptyRelatedLink: { href: "#/workflows", label: "먼저: 워크플로 등록으로 이동" },
    // 템플릿 화면의 '이 템플릿으로 문서 생성'에서 넘어온 해시 쿼리를 생성 폼에 프리필한다(DataScreen이 소비).
    // template_id는 config JSON 안으로 넣고, 워크플로 템플릿의 대상 ID를 workflow_id로 채운다.
    // ?id=는 다른 화면(승인의 '대상 보기' 등)이 특정 문서 생성 건으로 딥링크할 때 쓴다 — runners.onQuery와
    // 동일한 패턴으로 그 문서의 상세 드로어를 곧바로 연다.
    onQuery: (p) => p.id
      ? { open: "select", id: p.id }
      : (p.template_id ? { open: "header", label: "+ 문서 생성", initial: docConfigInitial({ workflow_id: p.workflow_id, config: { template_id: p.template_id } }) } : null),
    selectKey: "generation",
    paginated: true,
    // 비동기 생성(pending→미리보기/승인대기 등) 상태 전이를 화면이 자동으로 따라간다.
    // '승인 대기'는 다른 화면(승인)에서만 풀리므로 여기서 무한 폴링하지 않는다 — pending만 추적한다.
    pollWhile: (r) => r.status === "pending",
    // status는 백엔드가 지원하는 서버 필터. mode는 백엔드 목록이 받지 않으므로 clientFilter로 현재
    // 페이지에서 거른다(위 paginated+clientFilter 경고 Callout이 그 한계를 함께 안내한다).
    filters: [{ key: "status", type: "select", label: "상태", options: opt([["pending", "대기"], ["preview_ready", "미리보기 완료"], ["quality_failed", "품질 미달"], ["awaiting_approval", "승인 대기"], ["published", "발행됨"], ["failed", "실패"]]) },
      { key: "mode", type: "select", label: "모드", clientFilter: true, options: opt([["preview_then_approve", "미리보기 후 승인"], ["preview_only", "미리보기만"], ["auto_publish", "자동 발행"]]) }],
    headerActions: [
      { label: "+ 문서 생성", variant: "primary", primary: true, roles: WRITE_ROLES, path: () => "/api/admin/documents/generate",
        result: docGenerateResult, fields: DOC_GENERATE_FIELDS, transform: docConfigTransform },
    ],
    // 첫 열은 원시 UUID 대신 사람이 읽는 식별자(미리보기 제목 → 없으면 UUID)로 행을 구분한다.
    // 실제 UUID(id)는 감사 로그 대조·API 문의 등에 필요한데 어디에도 안 보였다 — 두 분기 모두 끝에
    // 붙여 항상 보이게 한다(제목이 있어도 UUID를 확인·복사할 방법이 있어야 한다).
    columns: [{ key: "id", label: "문서", render: (r) => {
      const idSuffix = r.id ? ", " + r.id : "";
      if (r.preview && r.preview.title) return String(r.preview.title) + idSuffix;
      // 미리보기 제목이 없는 행(대기·품질 미달·실패 — 정확히 운영자가 가장 자주 찾아보는 상태들)은
      // 원시 UUID 대신 기간·상태로 사람이 알아볼 수 있는 라벨을 만든다(스케줄 실행 이력의 동일한
      // 문제와 같은 이유 — 목록을 훑을 때 UUID만으로는 어느 행인지 구분할 수 없었다).
      const st = { pending: "대기", preview_ready: "미리보기 완료", quality_failed: "품질 미달", awaiting_approval: "승인 대기", published: "발행됨", failed: "실패" }[r.status] || r.status || "?";
      return "기간 " + (r.period || "?") + " 문서 (" + st + ")" + idSuffix;
    } },
      col("period", "기간"), mapCol("mode", "모드", DOC_MODE), badgeCol("status", "상태"),
      // generation_view가 requested_by를 최상위로 이미 돌려주는데 목록엔 없어 각 행을 요청한 사람을
      // 보려면 상세를 하나씩 열어야 했다(승인 화면은 이미 목록에서 요청자를 바로 보여준다).
      col("requested_by", "요청자"),
      linkCol("published_ref", "발행 링크"), dateCol("created_at", "생성")],
    // 미리보기 본문·품질 문제·오류를 상세에서 읽는다(미리보기만/품질미달 결과 확인).
    // requested_by는 generation_view가 최상위로 준다 — 누가 요청했는지 상세에서 바로 본다(원시 UUID라 'ID'로 라벨링).
    // template_id는 generation_view가 감사·운영 조회를 위해 일부러 최상위로 승격한 필드다(어느
    // 템플릿이 이 문서를 만들었는지) — config JSON 안에 묻히지 않게 직접 노출한다.
    // id는 이미 목록 첫 열(제목 없으면 원시 UUID로 표시)이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    // workflow_id·template_id는 다른 화면 엔티티의 ID다 — 러너 상세의 integration_id와 동일한
    // 이유로 원시 텍스트 대신 그 화면으로 바로 이동하는 링크로 보여준다.
    detailFields: [
      // 워크플로 화면의 ?id= 딥링크(onQuery)로 그 워크플로 상세를 곧바로 연다(무필터 전체 목록 아님).
      { key: "workflow_id", label: "워크플로 ID", render: (r) => r.workflow_id ? React.createElement("a", { href: "#/workflows?id=" + encodeURIComponent(r.workflow_id) }, r.workflow_id) : "-" },
      // 템플릿 화면이 이제 ?id=로 특정 템플릿 상세를 곧바로 여는 딥링크(onQuery)를 지원한다 — 무필터
      // 전체 목록에만 떨어지던 죽은 앵커가 아니라 실제로 그 템플릿으로 데려간다.
      { key: "template_id", label: "템플릿 ID", render: (r) => r.template_id ? React.createElement("a", { href: "#/templates?id=" + encodeURIComponent(r.template_id) }, r.template_id) : "-" },
      // requested_by는 이제 목록 열(요청자)이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
      jsonField("config", "요청 설정"), previewField("preview", "미리보기"), listField("quality_problems", "품질 문제"), field("error_message", "오류"), dateCol("updated_at", "수정")],
    // '승인 대기' 문서는 여기서 발행할 수 없다(백엔드에 문서별 발행 API 없음) — 승인 화면으로 안내한다.
    actions: [
      // '문서 자동 생성' 화면 자체엔 반복/예약 실행 경로가 없다(수동 '+ 문서 생성' 버튼뿐) — 새 인프라를
      // 만드는 대신 이미 있는 스케줄 화면으로 보내 같은 워크플로를 대상으로 한 Schedule을 만들게 한다
      // (템플릿의 '이 템플릿으로 문서 생성'과 동일한 화면 간 프리필 패턴, schedules.onQuery가 소비).
      { label: "정기 실행으로 예약", roles: WRITE_ROLES, when: (r) => !!r.workflow_id,
        navigate: (r) => "#/schedules?workflow_id=" + encodeURIComponent(r.workflow_id) },
      // 특정 문서의 승인 요청으로 딥링크할 수단은 없지만(document.publish 승인은 이 생성 건의 id를
      // approval.object_id로 직접 담지 않는다), 최소한 '대기' 상태로는 걸러 보여준다 — approvals.onQuery가
      // 이제 ?status=를 소비해 실제로 '대기' 큐만 남기고 승인/거절/만료/취소 이력에 묻히지 않게 한다.
      { label: "승인 대기 목록으로", when: (r) => r.status === "awaiting_approval", navigate: () => "#/approvals?status=pending" },
      // 실패·품질 미달 문서는 같은 기간/대상으로 재생성할 수 없다(화면 help가 이미 이렇게 안내한다) —
      // '+ 문서 생성' 폼을 이 행의 워크플로·모드·설정으로 프리필해 다시 열어, 기간부터 다시 입력해
      // 새로 만들 수 있게 한다(빈 폼에 UUID·JSON을 처음부터 다시 옮겨 적지 않게).
      { label: "재시도", roles: WRITE_ROLES, when: (r) => r.status === "failed" || r.status === "quality_failed",
        path: () => "/api/admin/documents/generate", result: docGenerateResult, fields: DOC_GENERATE_FIELDS, transform: docConfigTransform,
        // 실패 행의 워크플로·모드·설정은 물려받고 기간만 비워 다시 연다. docConfigInitial이 config를
        // 명명 필드로 풀어 채운다(period는 known 키라 config_extra로 새지 않는다).
        initial: (r) => docConfigInitial({ workflow_id: r.workflow_id, mode: r.mode, config: r.config, period: "" }) },
      // document_generation은 감사 로그의 유효한 object_type이고(app/documents/router.py가 이 이름으로
      // 기록한다) OBJTYPE_OPTS에도 이미 있다 — 부서·직책과 동일한 딥링크를 추가한다.
      // operator는 이 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES) —
      // 다른 화면들의 동일한 '감사 로그에서 보기'와 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=document_generation&object_id=" + r.id },
    ],
  },
  approvals: {
    key: "approvals", area: "자동화", title: "승인", endpoint: "/api/admin/approvals",
    // self_approval_allowed는 서버 설정 파일에만 있고(app/core/feature_flags.py) 이 관리 콘솔에는
    // 그 값을 보거나 바꿀 화면이 없다 — '정책 설정에 따라 달라질 수 있어요'는 마치 이 화면 어딘가에
    // 바꿀 수 있는 정책 설정이 있는 것처럼 읽혀 없는 컨트롤을 찾게 만들었다. 서버 쪽 설정임을 명시한다.
    help: "위험할 수 있는 작업의 승인 요청을 처리합니다. 본인 요청은 기본적으로 본인이 승인할 수 없습니다(서버 설정 파일로만 조정되며, 이 화면에서는 바꿀 수 없습니다). 승인 요청은 72시간(기본값)이 지나면 자동으로 만료됩니다, 처리하지 않고 두면 다음에 다시 열었을 때 '만료'로 바뀌어 있을 수 있습니다.",
    // 실제 승인 실행자는 5종(app/approvals/service.py): schedule.enable, runner.change_config,
    // integration.change_config, user.role_change, document.publish. 예전 문구는 3종만 언급해
    // 스케줄 활성화·문서 발행 승인이 왜 여기 뜨는지 안내가 없었다.
    emptyTitle: "승인 요청이 없습니다", emptyHelp: "스케줄 활성화, 연동/러너 설정 변경, 역할 변경, 문서 발행처럼 승인이 필요한 작업이 요청되면 여기에서 승인, 거절, 취소합니다.",
    emptyRelatedLink: { href: "#/approval-delegations", label: "부재 시 대리 승인자 설정" },
    // 다른 화면/미래의 딥링크가 ?id=로 특정 승인 건을 곧바로 열 수 있게 한다(runners.onQuery와 동일한
    // 패턴 — 백엔드 GET /api/admin/approvals/{id}가 이미 존재하는데 지금까지 아무 화면도 호출하지 않았다).
    // 문서 화면의 '승인 대기 목록으로'가 ?status=pending을 붙여 넘어온다 — 감사 화면의 open:'filter'
    // 인텐트와 동일한 방식으로 소비해 무필터 전체 목록이 아니라 실제로 '대기' 상태만 걸러 보여준다.
    onQuery: (p) => p.id
      ? { open: "select", id: p.id }
      : (p.status ? { open: "filter", values: { status: p.status } } : null),
    selectKey: "approval",
    paginated: true,
    // 승인 큐는 여러 관리자·자동 만료(72h)가 동시에 건드릴 수 있는 경합 자원이다 — 화면을 열어둔 채로
    // 다른 관리자가 먼저 처리한 pending 행을 눌러 낡은 409를 보지 않도록 자동 새로고침한다.
    pollWhile: (r) => r.status === "pending",
    // 상태 기본값을 'pending'으로 스코프한다(여전히 '전체'로 바꿀 수 있다) — 승인 대장은 append-only라
    // 기본값 없이는 매 방문마다 실제 처리 가능한 대기 건이 승인/거절/만료/취소 이력에 묻혀 보였다.
    filters: [{ key: "status", type: "select", label: "상태", value: "pending", options: opt([["pending", "대기"], ["approved", "승인됨"], ["rejected", "거절됨"], ["expired", "만료"], ["cancelled", "취소됨"]]) }],
    // 만료 시각은 대기(pending)일 때만 의미가 있다 — 종료된 행은 원래 만료 시각을 계속 보여주면 오해를 낳으므로 '-'.
    // 요청자 열 — router.py가 배치로 requester_name/requester_email을 미리 붙여 주므로(누가 요청했는지
    // 목록에서 바로 보이게), 각 행을 열어보지 않고도 트리아지할 수 있게 노출한다.
    columns: [actionCol("request_type", "유형"), objCol("object_type", "대상"),
      // 예약/시스템이 자동 생성한 document.publish 승인은 requested_by="system"이다(사람이 아니므로
      // resolve_names가 못 찾는다) — 그 원시 영어 리터럴이 그대로 새지 않게 한국어로 특별 취급한다.
      { key: "requester_name", label: "요청자", render: (r) => r.requester_name || r.requester_email || (r.requested_by === "system" ? "시스템(자동)" : r.requested_by) || "-" },
      badgeCol("status", "상태"), dateCol("requested_at", "요청 시각"),
      // 기한(SLA, 0033)은 만료와 **다른 축**이다: 만료는 요청이 죽는 시각, 기한은 사람이 답해야
      // 하는 시각이다. 둘을 한 열로 합치면 "아직 살아 있지만 이미 늦었다"를 표현할 수 없다.
      // 판정은 서버(approval_view)가 한 `overdue` 를 그대로 쓴다 — 화면이 시각을 다시 비교하면
      // 브라우저 시계가 틀린 PC 에서 목록과 상세가 서로 다른 답을 낸다.
      { key: "due_at", label: "기한", render: (r) => {
        if (APPROVAL_DONE.includes(r.status) || !r.due_at) return "-";
        const text = fmtDateTime(r.due_at);
        return r.overdue
          ? React.createElement(Badge, { value: "기한 초과 · " + text, kind: "danger" })
          : text;
      } },
      { key: "expires_at", label: "만료", render: (r) => APPROVAL_DONE.includes(r.status) ? "-" : fmtDateTime(r.expires_at) }],
    // 승인 전에 '무엇을 적용하는지'를 반드시 보여준다(내용 없이 승인 금지). request_payload가 핵심.
    // 요청자는 위 columns에서 이름/이메일로 이미 보여주므로 여기선 원시 ID만(대조용). 결정자는
    // approval_view가 requester_name과 마찬가지로 approver_name/approver_email을 함께 돌려준다
    // (app/approvals/service.py) — 원시 UUID 대신 그 이름을 보여준다.
    // request_payload를 원시 JSON 한 덩어리(예: document.publish의 {"generation_id":...})가 아니라 최상위
    // 키/값 행으로 펼쳐 승인 전에 '무엇을 적용하는지' 읽기 쉽게 보여준다(내용 없이 승인 금지). 중첩은 JSON.
    detailFields: [field("object_id", "대상 ID"), field("requested_by", "요청자 ID"),
      // 위임으로 결재된 건은 '누구를 대신했는가'가 남는다(0033) — 이 줄이 없으면 운영자가
      // 어떻게 승인할 수 있었는지 화면 어디에도 설명이 없다.
      { key: "decided_on_behalf_of", label: "대리 결재", render: (r) => r.decided_on_behalf_of
        ? (r.decided_on_behalf_of_name || r.decided_on_behalf_of) + "님의 위임으로 결재"
        : "-" },
      // user.role_change 요청은 role/previous_role을 raw 값(예: 'admin')으로 담아 온다 — Users.jsx의
      // ROLE_KO가 화면 곳곳에서 이미 한국어 라벨로 보여주는 값인데, 여기만 generic objectField가
      // 그대로 노출했다. role/previous_role만 ROLE_KO로 치환하고 나머지 키는 그대로(generic) 보여준다.
      { key: "request_payload", label: "요청 내용", render: (r) => {
        const p = r.request_payload;
        if (p == null || p === "") return "-";
        if (typeof p !== "object") return React.createElement("pre", { className: "c-detail-json" }, String(p));
        const entries = Array.isArray(p) ? p.map((x, i) => [String(i), x]) : Object.entries(p);
        if (!entries.length) return "-";
        const fmtVal = (k, v) => {
          if (r.request_type === "user.role_change" && (k === "role" || k === "previous_role") && typeof v === "string") return ROLE_KO[v] || v;
          if (v != null && typeof v === "object") return React.createElement("pre", { className: "c-detail-json" }, JSON.stringify(v, null, 2));
          return (v == null || v === "") ? "-" : String(v);
        };
        return React.createElement("div", null, entries.map(([k, v], i) => React.createElement("div", { className: "c-kv", key: i },
          React.createElement("span", { className: "c-kv-k" }, APPROVAL_PAYLOAD_KEY_KO[k] || k),
          React.createElement("span", { className: "c-kv-v" }, fmtVal(k, v)))));
      } },
      dateCol("decided_at", "결정 시각"),
      { key: "approver_name", label: "결정자", render: (r) => r.approver_name || r.approver_email || r.approver_id || "-" },
      field("decision_comment", "결정 메모")],
    // 승인/거절은 결정 권한(admin/system_admin)만, 취소는 운영 역할까지. 백엔드 RBAC와 일치시켜
    // 읽기 전용 역할(operator/auditor)에게 항상 403이 되는 버튼을 숨긴다.
    actions: [
      // 자기 요청은 자기 승인·거절이 백엔드에서 금지된다(403) → 본인 요청 행에서는 두 버튼을 숨긴다(취소만 남긴다).
      { label: "승인", variant: "primary", roles: WRITE_ROLES, when: (r, ctx) => !APPROVAL_DONE.includes(r.status) && (!ctx || r.requested_by !== ctx.userId), path: (r) => "/api/admin/approvals/" + r.id + "/approve",
        fields: [{ name: "comment", label: "승인 메모(선택)", type: "textarea", help: "승인 사유, 조건 등을 남기면 감사 기록에 함께 저장됩니다." }] },
      { label: "거절", variant: "danger", roles: WRITE_ROLES, when: (r, ctx) => !APPROVAL_DONE.includes(r.status) && (!ctx || r.requested_by !== ctx.userId), path: (r) => "/api/admin/approvals/" + r.id + "/reject",
        fields: [{ name: "comment", label: "거절 사유(선택)", type: "textarea", help: "거절 사유를 남기면 감사 기록에 함께 저장됩니다." }] },
      // operator는 '본인 요청'만 취소 가능(백엔드 RBAC) → 남의 요청엔 항상 403이 되는 취소 버튼을 숨긴다.
      // admin/system_admin은 모든 요청을 취소할 수 있다.
      { label: "취소", roles: OPS_ROLES, when: (r, ctx) => !APPROVAL_DONE.includes(r.status) && (!ctx || r.requested_by === ctx.userId || ctx.role === "admin" || ctx.role === "system_admin"), path: (r) => "/api/admin/approvals/" + r.id + "/cancel", confirm: "이 요청을 취소할까요?" },
      // 승인 판단 전에 대상 엔티티 화면으로 이동해 현재 상태를 확인할 수 있게 한다(목록 화면이라 딥링크는 목록까지).
      // 대상 화면 중 일부(사용자·부서·직책)는 role이 더 좁게 제한된다 — canReachObjRoute로 그 역할이
      // 실제로 들어갈 수 있는 대상일 때만 노출해 클릭 즉시 403 막다른 길이 되지 않게 한다.
      // 대상 화면이 id 기반 딥링크를 지원하면(OBJ_ID_PARAM) 목록 전체가 아니라 바로 그 대상으로
      // 이동한다 — 그렇지 않은 대상 유형은 예전처럼 목록으로만 이동한다(objRouteHref가 그대로 base 반환).
      { label: "대상 보기", when: (r, ctx) => !!OBJ_ROUTE[r.object_type] && canReachObjRoute(r.object_type, ctx && ctx.role), navigate: (r) => objRouteHref(r.object_type, r.object_id) },
      // document.publish 승인은 request_payload가 {"generation_id":...}뿐이라(app/jobs/handlers/document_generate.py)
      // 실제로 무엇을 발행하는지 이 화면만으로는 알 수 없었다 — 대상 문서를 조회해 제목·본문을 바로 보여준다
      // (내용 없이 승인 금지 원칙을 이 요청 유형에도 지킨다).
      { label: "발행 내용 보기", when: (r) => r.request_type === "document.publish" && !!(r.request_payload && r.request_payload.generation_id),
        method: "GET", path: (r) => "/api/admin/documents/" + r.request_payload.generation_id,
        info: (res) => {
          const g = (res && res.generation) || res || {};
          const p = g.preview || {};
          const lines = ["상태: " + (g.status || "?")];
          if (p.title) lines.push("제목: " + p.title);
          if (p.body) lines.push("\n본문:\n" + p.body);
          if (g.quality_problems && g.quality_problems.length) lines.push("\n품질 문제:\n" + g.quality_problems.map((x) => ", " + x).join("\n"));
          return lines.join("\n");
        } },
      // 승인/거절/취소 결정은 모두 object_type='approval'로 감사 로그에 기록된다(app/approvals/router.py).
      // operator는 승인 화면(OPS_ROLES)엔 들어오지만 감사 화면엔 못 들어간다(App.jsx SCREEN_ROLES) —
      // '대상 보기'의 canReachObjRoute와 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=approval&object_id=" + r.id },
    ],
  },
  departments: {
    key: "departments", area: "사용자", title: "부서 관리", endpoint: "/api/admin/departments",
    help: "부서 이름을 한 곳에서 관리합니다. 사용자 폼의 '부서'는 여기 목록에서 고릅니다.", createLabel: "+ 부서 추가",
    emptyTitle: "등록된 부서가 없습니다", emptyHelp: "‘+ 부서 추가’로 부서를 만들면 사용자 폼의 '부서' 목록에 바로 나타납니다.",
    // 이 화면은 paginated가 아니라 클라이언트 검색창이 항상 뜨는데, searchFields가 없으면 기본 검색이
    // JSON.stringify(row) 전체(원시 UUID·boolean·UTC-ISO created_at)를 훑어 화면에 보이는 값과 무관하게
    // 매칭했다(예: KST 생성일을 그대로 쳐도 자정 경계 근처에서 못 찾음) — 이름만 검색 대상으로 좁힌다(직책 화면과 동일).
    searchFields: ["name"],
    searchPlaceholder: "부서 이름으로 검색",
    filters: ACTIVE_FILTER,
    // usage_count(소속 인원)는 보관(soft-delete)된 사용자도 센다(app/org/service.py 주석: '보관된
    // 사용자도 센다') — 열 라벨에서 바로 그 사실을 알려, 활성 인원만으로 오해해 삭제 가능 여부를
    // 잘못 판단하지 않게 한다.
    columns: [col("name", "부서 이름"), activeCol("사용"), col("user_count", "소속 인원(보관 포함)"), dateCol("created_at", "생성")],
    // id는 감사 로그의 object_id와 대조할 때 쓰이므로 상세에서 노출한다.
    // 삭제 버튼은 소속 인원>0이면 아래 actions에서 통째로 숨겨진다(사용 중이면 비활성화만 가능) — 그
    // 이유가 코드 주석에만 있어 화면엔 아무 설명 없이 버튼만 사라졌었다. 상세에 이유를 남긴다.
    detailFields: [field("id", "부서 ID"),
      { key: "_delete_note", label: "삭제 안내", render: (r) => r.user_count ? "사용 중인 부서(소속 인원 " + r.user_count + "명, 보관 계정 포함)는 삭제할 수 없습니다, 대신 ‘비활성화’를 이용하세요." : "-" }],
    create: { roles: WRITE_ROLES, fields: [{ name: "name", label: "부서 이름", type: "text", required: true, help: "사용자 폼의 '부서' 목록에 바로 나타납니다." }] },
    // 활성 토글은 확인 문구가 붙은 아래 활성/비활성 액션으로만 처리한다(수정 폼의 무경고 체크박스 제거).
    // required:true — 비워서 제출하면 FormModal이 {"name": null}을 보내 백엔드가 '값이 없어졌다'로
    // 해석하고 조용히 무시(no-op)한다(성공 토스트까지 뜬다). 클라이언트에서 먼저 막아 이 거짓
    // 성공 피드백을 없앤다(create 필드는 이미 required였는데 edit만 빠져 있었다).
    edit: { roles: WRITE_ROLES, fields: [{ name: "name", label: "부서 이름", type: "text", required: true, help: "이름을 바꾸면 이 부서를 쓰는 모든 사용자(소속 인원)에게 즉시 반영됩니다." }] },
    actions: [
      ...activeToggle("/api/admin/departments"),
      // 사용 중(소속 인원>0)인 부서는 삭제가 항상 409 → 미사용일 때만 노출한다(대신 '비활성화').
      { label: "삭제", variant: "danger", roles: WRITE_ROLES, when: (r) => !r.user_count, method: "DELETE", path: (r) => "/api/admin/departments/" + r.id, confirm: "이 부서를 지울까요? 되돌릴 수 없습니다." },
      // 사용자 상세의 '감사 로그에서 보기'(Users.jsx)와 동일한 딥링크 — department는 OBJTYPE_OPTS에
      // 이미 있고 감사 화면 onQuery가 object_type/object_id를 소비하므로 클릭 한 번으로 이 부서에
      // 일어난 변경 이력을 볼 수 있다.
      { label: "감사 로그에서 보기", navigate: (r) => "#/audit?object_type=department&object_id=" + r.id },
    ],
  },
  "job-titles": {
    key: "job-titles", area: "사용자", title: "직책 관리", endpoint: "/api/admin/job-titles",
    help: "직책 이름을 한 곳에서 관리합니다. 사용자 폼의 '직책'은 여기 목록에서 고릅니다.", createLabel: "+ 직책 추가",
    emptyTitle: "등록된 직책이 없습니다", emptyHelp: "‘+ 직책 추가’로 직책을 만들면 사용자 폼의 '직책' 목록에 바로 나타납니다.",
    // 부서→직책→사용자 온보딩 체인(사용자 생성은 직책이 있어야 가능 — Users.jsx) — 연동→러너→워크플로
    // 체인처럼 다음 단계(사용자)로 이어 준다. 단계별 안내는 canOnboard가 쓰기 역할에만 보여준다.
    emptySituation: "부서, 직책, 사용자 온보딩 체인의 한 단계입니다, 아직 직책이 하나도 없습니다.",
    emptySteps: ["‘+ 직책 추가’로 필요한 직책을 만듭니다.", "사용할 직책을 모두 등록합니다.", "사용자 화면에서 계정을 만들 때 이 직책을 배정합니다."],
    emptyExpected: "등록한 직책은 사용자 폼의 ‘직책’ 목록에 바로 나타납니다.",
    emptyRelatedLink: { href: "#/users", label: "다음: 사용자 등록으로 이동" },
    // 이 화면은 paginated가 아니라 클라이언트 검색창이 항상 뜨는데, 기본 검색은 JSON.stringify(row)
    // 전체(원시 UUID·ISO created_at 포함)를 훑는다 — 화면에 보이는 '생성' 열은 KST로 포맷된 값인데
    // 검색은 원시 UTC ISO 문자열을 매칭해, 화면에 보이는 그대로 타이핑해도 자정 경계 근처에서
    // 못 찾을 수 있었다(오탐/누락 방지를 위해 실제로 보이는 필드인 이름만 검색 대상으로 좁힌다).
    searchFields: ["name"],
    searchPlaceholder: "직책 이름으로 검색",
    filters: ACTIVE_FILTER,
    // usage_count(보유 인원)는 보관(soft-delete)된 사용자도 센다(부서와 동일한 계산 — app/org/service.py).
    // 라벨은 부서 화면과 다르게 '보유'를 쓴다 — 직책은 사람이 '보유'하는 것이지 '소속'되는 게 아니다.
    columns: [col("name", "직책 이름"), activeCol("사용"), col("user_count", "보유 인원(보관 포함)"), dateCol("created_at", "생성")],
    // 삭제 버튼은 소속 인원>0이면 아래 actions에서 통째로 숨겨진다(부서와 동일한 이유) — 상세에 이유를 남긴다.
    detailFields: [field("id", "직책 ID"),
      { key: "_delete_note", label: "삭제 안내", render: (r) => r.user_count ? "사용 중인 직책(보유 인원 " + r.user_count + "명, 보관 계정 포함)은 삭제할 수 없습니다, 대신 ‘비활성화’를 이용하세요." : "-" }],
    create: { roles: WRITE_ROLES, fields: [{ name: "name", label: "직책 이름", type: "text", required: true, help: "사용자 폼의 '직책' 목록에 바로 나타납니다." }] },
    // 활성 토글은 확인 문구가 붙은 아래 활성/비활성 액션으로만 처리한다(수정 폼의 무경고 체크박스 제거).
    // required:true — 부서와 동일한 이유(비워서 제출하면 조용한 no-op + 거짓 성공 토스트가 됐다).
    edit: { roles: WRITE_ROLES, fields: [{ name: "name", label: "직책 이름", type: "text", required: true, help: "이름을 바꾸면 이 직책을 쓰는 모든 사용자(보유 인원)에게 즉시 반영됩니다." }] },
    actions: [
      ...activeToggle("/api/admin/job-titles"),
      // 사용 중(소속 인원>0)인 직책은 삭제가 항상 409 → 미사용일 때만 노출한다(대신 '비활성화').
      { label: "삭제", variant: "danger", roles: WRITE_ROLES, when: (r) => !r.user_count, method: "DELETE", path: (r) => "/api/admin/job-titles/" + r.id, confirm: "이 직책을 지울까요? 되돌릴 수 없습니다." },
      // job_title은 OBJTYPE_OPTS에 이미 있고 이 id를 감사 로그에서 대조할 수 있게 상세에 노출해
      // 두었다(위 detailFields 주석 참고) — 그런데 실제로 눌러서 갈 방법이 없었다. Users.jsx의
      // '감사 로그에서 보기' 버튼과 동일한 딥링크를 추가한다.
      { label: "감사 로그에서 보기", navigate: (r) => "#/audit?object_type=job_title&object_id=" + r.id },
    ],
  },
  "notion-mapping": {
    key: "notion-mapping", area: "사용자", title: "Notion 사용자 연결", endpoint: "/api/admin/notion-mapping",
    help: "직원 계정과 Notion 사용자를 연결합니다. 자동 매칭되며 수동 지정도 가능합니다. (‘notion-user-mapping’ 워크플로가 등록, 활성화되어 있어야 자동 동기화, 검증이 동작합니다.)",
    // 사용자 화면(Users.jsx)의 'Notion 연결 확인' 링크가 ?user_id=를 붙여 이 화면으로 온다 — 다른
    // 9개 id 딥링크 화면(runners.onQuery 등)과 동일하게 GET /{user_id}({"mapping":...} 응답,
    // app/notion_mapping/router.py get_mapping)로 그 사용자의 상세 드로어를 곧바로 연다(예전엔 필터만
    // 채워 목록에서 다시 찾아야 했다).
    onQuery: (p) => p.user_id ? { open: "select", id: p.user_id } : null,
    selectKey: "mapping",
    emptyTitle: "표시할 사용자가 없습니다",
    // 읽기 전용 역할(operator/auditor)에는 자기 권한 밖 버튼('자동 동기화' 등)을 누르라고 안내하지 않는다.
    emptyHelp: (role) => (role === "admin" || role === "system_admin")
      ? "사용자 디렉터리의 계정이 여기에 나타납니다. ‘자동 동기화’로 Notion 사용자와 매칭하거나, 행에서 검증, 수동 연결하세요. (‘notion-user-mapping’ 워크플로가 필요합니다.)"
      : "사용자 디렉터리의 계정이 여기에 나타납니다. Notion 연결은 관리자가 수행합니다.",
    paginated: true, searchable: true,
    // 서버 검색(q)은 직원 이메일/이름만 매칭한다(app/notion_mapping/router.py) — notion_email은 검색
    // 대상이 아닌데 눈에 보이는 열이라 'Notion 이메일로 찾기'를 시도하면 결과가 없어도 이유를 알 수
    // 없었다. placeholder로 검색 범위를 명시해 조용한 0건을 줄인다.
    searchPlaceholder: "검색(직원 이메일, 이름, Notion 이메일은 검색되지 않음)",
    filters: [{ key: "status", type: "select", label: "상태", options: opt([["unmapped", "미연결"], ["verified", "확인됨"], ["conflict", "충돌"]]) },
      // 사용자 상세의 딥링크(onQuery, 위 참고)가 채우는 필드 — 직접 입력도 가능하게 남겨 둔다.
      { key: "user_ids", type: "text", label: "사용자 ID" },
      // 백엔드는 source 쿼리 파라미터를 지원하지 않는다(app/notion_mapping/router.py) —
      // clientFilter:true로 이미 받아 온(현재 페이지) 목록을 화면에서 직접 거른다(부서/직책의 active
      // 필터와 동일한 패턴). 수동으로 덮어쓴 연결만 따로 감사하고 싶을 때 지금까지는 방법이 없었다.
      { key: "source", type: "select", label: "출처", clientFilter: true, options: opt([["workflow", "워크플로 자동"], ["manual", "수동 지정"]]) }],
    columns: [col("user_email", "사용자"), col("user_display_name", "이름"), badgeCol("status", "상태"),
      // 실패로 'unmapped'로 되돌아온 행을 '한 번도 시도 안 함'과 구분한다 — 대량 트리아지 때 각 행을
      // 열지 않아도 사유를 바로 읽을 수 있게 실제 메시지를 보여준다(길면 말줄임, title 속성으로 전체 확인).
      truncateCol("error_message", "오류", 40),
      col("notion_email", "Notion 이메일"), mapCol("source", "출처", MAP_SOURCE), dateCol("last_verified_at", "마지막 검증")],
    // 충돌 해결 시 어떤 Notion 사용자 후보가 있는지 상세에서 보여준다(blind guess 방지).
    // error_message·last_verified_at은 이미 위 columns에 있다 — 드로어는 columns+detailFields를 합쳐
    // 그리므로 여기 다시 넣으면 같은 라벨이 두 번(다른 렌더로) 나온다. 여기서는 중복 제거.
    // 드로어는 columns+detailFields를 key 기준으로 합치므로(중복 시 columns가 우선) error_message를
    // 그대로 다시 넣으면 목록의 40자 truncateCol이 그대로 이어져 상세에서도 잘린다 — 진단에 필요한
    // 전체 오류 메시지를 보여줄 별도 key(다른 화면의 path_full/last_error_full과 동일 패턴)를 쓴다.
    // candidates는 '충돌 해결' 액션의 select(위 optionsFrom)가 이미 사람이 읽는 형태(이메일 — id)로
    // 보여준다 — 상세에서 같은 데이터를 원시 JSON으로 한 번 더 보여주면 같은 정보가 두 번(하나는
    // 정리된 선택지, 하나는 원시 덩어리) 나온다. 동일한 '이메일, id' 목록으로 통일한다.
    detailFields: [field("notion_user_id_masked", "Notion ID(마스킹)"),
      { key: "candidates", label: "연결 후보", render: (r) => {
        const cs = r.candidates;
        if (!cs || !cs.length) return "-";
        return React.createElement("ul", null, cs.map((c, i) => React.createElement("li", { key: i },
          (c.notion_email ? c.notion_email + ", " : "") + c.notion_user_id)));
      } }],
    // '오류(전체)' 상세 필드는 여기서 별도로 두지 않는다 — 위 columns의 truncateCol("error_message", ...)가
    // 이미 title 속성으로 전체 텍스트를 마우스 오버 시 보여주며, 드로어도 열+detailFields 합집합을
    // 그리므로 그 열이 그대로 드로어 안에도 나타난다. 예전엔 같은 내용을 자른 버전/전체 버전으로
    // 두 번(혼란스러운 near-duplicate로) 보여줬다.
    headerActions: [
      // '자동 동기화'는 POST /sync가 즉시 202로 큐잉될 뿐 30초를 기다리지 않는다(그 30초 문구는
      // 개별 '검증' 액션의 것 — verify_mapping이 실제로 동기 30초 타임아웃이다). 백그라운드 작업
      // 자체는 SYNC_TIMEOUT_SECONDS=90초까지 걸릴 수 있다(app/jobs/handlers/notion_mapping_sync.py).
      // primary:true — 백업(+ 백업 실행)·문서(+ 문서 생성) 화면과 동일하게, 이 화면의 headline
      // 액션을 EmptyState CTA로도 승격한다(그렇지 않으면 목록이 완전히 비어 있을 때 이 버튼이 안 보였다).
      { label: "자동 동기화", primary: true, roles: WRITE_ROLES, path: () => "/api/admin/notion-mapping/sync", confirm: "Notion 사용자와 자동 매칭을 다시 실행할까요? 수동으로 지정한 연결도 일치하는 후보가 없으면 해제될 수 있습니다. Notion 조회에 최대 1~2분 정도 걸릴 수 있으며, 화면은 진행 상태를 자동으로 갱신합니다.",
        // 202 큐 작업 — 완료를 단정하지 않고 실제 상태를 반영해 안내한다.
        result: (res) => {
          const running = res && (res.status === "running" || res.deduplicated);
          return { ok: true, kind: "info", msg: running
            ? "이미 동기화가 진행 중입니다. 완료되면 목록이 자동으로 갱신됩니다."
            : "동기화 작업을 시작했습니다(진행 중). 완료되면 목록이 자동으로 갱신됩니다." };
        },
        // 큐 작업이 끝날 때까지 폴링해 완료 시점에 목록을 갱신하고 결과를 알린다(화면에서 완료 피드백 제공).
        // 폴링은 최대 40초(20×2s)까지만 기다린다 — SYNC_TIMEOUT_SECONDS보다 짧게 끝나면 그 뒤로는
        // 아무도 다시 목록을 갱신하지 않는다(QueryClient가 refetchOnWindowFocus:false). '자동으로
        // 갱신됩니다'는 지키지 못할 약속이었다 — 새로고침이 필요하다고 정직하게 안내한다.
        pollJob: { getId: (res) => res && res.job_id, interval: 2000, maxTries: 20,
          doneMsg: "자동 동기화가 완료되었습니다. 목록을 갱신했습니다.",
          failMsg: "자동 동기화 작업이 실패했습니다",
          timeoutMsg: "동기화가 아직 진행 중입니다. 이 화면은 자동으로 갱신되지 않을 수 있으니, 잠시 후 새로고침해 확인하세요." } },
    ],
    // 검증·수동 연결·충돌 해결·연결 해제는 모두 상태 변경(쓰기) — 백엔드 RBAC와 일치시켜 쓰기 역할만 노출.
    actions: [
      { label: "검증", roles: WRITE_ROLES, path: (r) => "/api/admin/notion-mapping/" + r.user_id + "/verify",
        // 자동 검증은 워크플로 재소스로 매칭한다 — 수동으로 지정한 연결(source==='manual')을
        // 무일치로 덮어써 지울 수 있으므로(service.py no-match 처리) 그 경우만 별도로 경고한다.
        confirm: (r) => r.source === "manual"
          ? "이 사용자를 지금 검증할까요? 수동으로 지정한 연결입니다, 자동 검증이 일치를 못 찾으면 연결이 해제될 수 있습니다. (Notion에 직접 조회하므로 최대 30초까지 걸릴 수 있습니다.)"
          : "이 사용자를 지금 검증할까요? Notion에 직접 조회하므로 최대 30초까지 걸릴 수 있습니다.",
        result: (res) => {
          const m = (res && res.mapping) || res || {};   // res===null(빈 2xx)이면 res.mapping 접근이 throw — 널가드
          // status==='verified'인데 error_message가 새로 채워졌다면 이번 조회 자체가 실패한 것이다
          // (백엔드 verify_mapping이 n8n 조회 예외를 삼키고 상태는 건드리지 않은 채 error_message만
          // 채워 돌려준다 — 상태만 보면 '검증됨'이라 거짓 성공 토스트가 뜬다). 기존 연결은 유지되지만
          // 이번 시도는 실패로 알린다.
          if (m.status === "verified" && !m.error_message) return { ok: true, msg: "검증 완료: 연결됨" };
          if (m.status === "verified" && m.error_message) return { ok: false, kind: "warn", msg: "검증 중 오류가 발생했습니다(기존 연결은 유지됨): " + m.error_message };
          // 충돌은 실패가 아니라 '관리자 해결이 필요한' 정상 분기 — 오류 톤으로 표시하지 않는다.
          if (m.status === "conflict") return { ok: false, kind: "info", msg: "충돌 감지: 여러 Notion 사용자가 일치합니다. 아래 ‘충돌 해결’에서 지정하세요." };
          // '미연결(unmapped)'은 시스템 실패가 아니라 정상적인 검증 결과다 → 정보 톤으로 안내(오류 톤 과장 금지).
          // 백엔드 verify_mapping은 no-match에도 error_message('일치하는 Notion 사용자가 없습니다.')를 채우므로
          // error_message 유무로 갈라선 안 된다(그렇게 하면 이 정보 분기가 죽고 정상 결과가 빨간 오류로 뜬다).
          if (m.status === "unmapped") return { ok: false, kind: "info", msg: (m.error_message || "연결된 Notion 사용자를 찾지 못했습니다") + " 필요하면 ‘수동 연결’로 지정하세요." };
          // 예상 밖 상태(verified/conflict/unmapped 외)만 진짜 실패로 표시한다.
          return { ok: false, msg: "검증 실패: " + (m.error_message || m.status || "일치하는 Notion 사용자를 찾지 못했습니다") };
        } },
      { label: "수동 연결", roles: WRITE_ROLES, path: (r) => "/api/admin/notion-mapping/" + r.user_id + "/map", fields: [
        { name: "notion_user_id", label: "Notion 사용자 ID", type: "text", required: true, help: "Notion 워크스페이스의 사용자 ID(8~64자, 영문, 숫자, 하이픈)." },
        { name: "notion_email", label: "Notion 이메일(선택)", type: "text" },
      ] },
      { label: "충돌 해결", roles: WRITE_ROLES, when: (r) => r.status === "conflict", path: (r) => "/api/admin/notion-mapping/" + r.user_id + "/resolve-conflict", fields: [
        // 후보 목록에서 바로 고른다(원시 JSON에서 8~64자 id를 복사·붙여넣는 실수 방지).
        { name: "notion_user_id", label: "연결할 Notion 사용자", type: "select", required: true,
          optionsFrom: (r) => (r.candidates || []).map((c) => ({ value: c.notion_user_id, label: (c.notion_email ? c.notion_email + ", " : "") + c.notion_user_id })),
          help: "이 사용자와 충돌한 Notion 후보 중 올바른 사람을 고르세요." },
      ] },
      // 충돌 행도 해제 가능(후보가 모두 오답일 때 '미연결'로 초기화). 백엔드 unmap은 어떤 상태에서도 동작한다.
      { label: "연결 해제", variant: "danger", roles: WRITE_ROLES, when: (r) => r.status === "verified" || r.status === "conflict" || r.source === "manual", path: (r) => "/api/admin/notion-mapping/" + r.user_id + "/unmap", confirm: "이 사용자의 Notion 연결을 해제할까요?" },
      // user_notion_mapping은 감사 로그의 유효한 object_type이고(OBJTYPE_OPTS, object_id=user_id) 이
      // 화면의 검증/수동 연결/충돌 해결/해제/동기화가 모두 이 타입으로 기록된다 — 부서·직책과 동일한 딥링크.
      // operator는 이 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — 다른 화면들의 동일한 '감사 로그에서 보기'와 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=user_notion_mapping&object_id=" + r.user_id },
    ],
  },
  jobs: {
    key: "jobs", area: "운영", title: "작업 큐", endpoint: "/api/admin/jobs",
    // 이 화면이 순수 관찰용(모니터링)으로 읽히지 않게, 실제로 조작 가능한 액션(재시도/취소)이
    // 있다는 것도 헤더에서 바로 안내한다(러너 화면의 help가 이미 자신의 버튼을 언급하는 것과 동일한 패턴).
    help: "채팅, 문서 생성, Notion 동기화, 예약 실행 같은 백그라운드 작업의 처리 현황과 실패를 봅니다. 실패한 작업은 '재시도', 대기 중인 작업은 '취소'할 수 있습니다.",
    // job_type은 chat_message/document_generate뿐 아니라 notion_mapping_sync·schedule_run도
    // 이 화면에 똑같이 나타난다(아래 filters의 job_type 옵션과 JOB_TYPE 맵 참고) — 두 유형만
    // 예시로 들면 처음 보는 사람은 이 화면이 Notion 동기화·예약 실행 작업도 보여준다는 걸 모른다.
    emptyTitle: "처리된 작업이 없습니다", emptyHelp: "채팅, 문서 생성, Notion 동기화, 예약 실행 같은 백그라운드 작업이 실행되면 처리 현황과 실패 내역이 여기에 표시됩니다.",
    // 감사 로그·알림에서 특정 작업으로 딥링크할 때(?job_id=) 무필터 전체 목록 대신 그 작업의 상세
    // 드로어를 곧바로 연다 — GET /api/admin/jobs/{id}는 이미 pollJobUntilDone이 쓰는 엔드포인트다.
    onQuery: (p) => p.job_id ? { open: "select", id: p.job_id } : null,
    selectKey: "job",
    paginated: true,
    // 큐가 정체된 실제 장애 상황에선 실패/대기 행을 빠르게 훑어야 한다 — 감사 화면과 동일한
    // 이유(registry.js audit pageSize:100 주석 참고)로 기본값 20보다 넉넉하게 둔다.
    pageSize: 100,
    // 큐 정체를 이 화면에서 바로 감지 — 대기/실행/실패 카운트와 '실행 가능(ready)'·가장 오래된 대기 age.
    summary: {
      endpoint: "/api/admin/jobs/stats",
      poll: true,   // 대기/실행/실패 카운트도 목록과 함께 주기적으로 갱신(정체를 실시간 감지).
      // (s, {setFilter}) — Dashboard.jsx/Ops.jsx는 이미 이 화면 바깥에서 동일한 카운트 데이터로
      // onClick 드릴다운을 건다(Ops.jsx 주석: '문제를 보여주기만 하고 조치할 방법이 없는 죽은
      // 타일'을 피하려는 목적) — 정작 이 화면 자신의 StatCard는 그 드릴다운이 없어 같은 데이터를
      // 보여주면서도 클릭해도 아무 일이 없었다. 목록의 status 필터로 직접 좁혀 준다.
      cards: (s, ctx) => {
        const cards = [
          { value: s.queued != null ? s.queued : 0, label: "대기", kind: s.queued > 0 ? "warn" : undefined, onClick: () => ctx.setFilter("status", "queued") },
          { value: s.running != null ? s.running : 0, label: "실행 중", onClick: () => ctx.setFilter("status", "running") },
          // '실행 가능(ready)'은 status 값이 아니라 대기 중 행 중 available_at이 이미 지난 부분집합의
          // 계산값이다(백엔드에 그 자체의 status 필터가 없다) — '대기'와 동일하게 좁혀 준 뒤 목록의
          // '대기' 열(지연 표시)에서 직접 훑게 한다(전혀 드릴다운이 없는 것보다는 낫다).
          { value: s.ready != null ? s.ready : 0, label: "실행 가능(ready)", kind: s.ready > 0 ? "warn" : undefined, onClick: () => ctx.setFilter("status", "queued") },
          { value: s.failed != null ? s.failed : 0, label: "실패", kind: s.failed > 0 ? "danger" : undefined, onClick: () => ctx.setFilter("status", "failed") },
          { value: s.succeeded != null ? s.succeeded : 0, label: "완료", onClick: () => ctx.setFilter("status", "succeeded") },
          { value: s.cancelled != null ? s.cancelled : 0, label: "취소됨", onClick: () => ctx.setFilter("status", "cancelled") },
        ];
        if (s.oldest_queued_at) {
          const str = String(s.oldest_queued_at);
          const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(str) ? str : str + "Z";
          const t = new Date(iso).getTime();
          if (!Number.isNaN(t)) {
            const m = Math.floor(Math.max(0, Date.now() - t) / 60000);
            const age = m < 1 ? "<1분" : (m < 60 ? m + "분" : Math.floor(m / 60) + "시간 " + (m % 60) + "분");
            // 다른 타일과 달리 이 '가장 오래된 대기' 카드만 드릴다운이 없어(백로그로 빨갛게 물들어도
            // 눌러도 아무 일이 없었다) — 인접한 '실행 가능(ready)' 타일과 같은 대기 큐로 좁혀 준다.
            cards.push({ value: age, label: "가장 오래된 대기", kind: m >= 10 ? "danger" : (m >= 1 ? "warn" : undefined), onClick: () => ctx.setFilter("status", "queued") });
          }
        }
        return cards;
      },
    },
    // 대기·실행 중인 작업이 있으면 상태 전이(대기→실행→완료/실패)를 자동으로 따라간다.
    pollWhile: (r) => r.status === "queued" || r.status === "running",
    filters: [
      { key: "status", type: "select", label: "상태", options: opt([["queued", "대기"], ["running", "실행 중"], ["succeeded", "완료"], ["failed", "실패"], ["cancelled", "취소됨"]]) },
      { key: "job_type", type: "select", label: "유형", options: opt([["chat_message", "채팅 메시지"], ["document_generate", "문서 생성"], ["notion_mapping_sync", "Notion 동기화"], ["schedule_run", "예약 실행"]]) },
    ],
    columns: [dateCol("created_at", "생성"), mapCol("job_type", "유형", JOB_TYPE), badgeCol("status", "상태"),
      // 대기 중인데 실행 예정 시각이 이미 지났으면 지연(백로그) 신호 — 워커 정체를 이 화면에서 바로 감지.
      { key: "available_at", label: "대기", render: (r) => {
        if (r.status !== "queued" || !r.available_at) return "-";
        const s = String(r.available_at); const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
        const t = new Date(iso).getTime(); if (Number.isNaN(t)) return "-";
        const diff = Date.now() - t; if (diff <= 0) return "대기 중";
        const m = Math.floor(diff / 60000);
        if (m < 1) return "지연 <1분"; if (m < 60) return "지연 " + m + "분";
        return "지연 " + Math.floor(m / 60) + "시간 " + (m % 60) + "분";
      } },
      { key: "attempt_count", label: "시도", render: (r) => r.max_attempts != null ? r.attempt_count + " / " + r.max_attempts : String(r.attempt_count) },
      // 실패 사유를 목록에서 바로 훑을 수 있게(예전엔 상세 드로어를 하나씩 열어야만 보였다) — 스케줄
      // 실행 이력의 truncate-at-60 패턴과 동일. title 속성으로 truncateCol과 동일하게 마우스 오버 시
      // 전체 텍스트를 미리 볼 수 있게 한다.
      { key: "last_error", label: "오류", render: (r) => { const v = r.last_error; if (!v) return "-"; const s = String(v); return s.length > 60 ? React.createElement("span", { title: s }, s.slice(0, 60) + "…") : s; } }],
    // available_at·last_error는 목록 열에도 있지만 그 열은 각각 '지연 여부만'(대기 상태 한정)과
    // '60자로 자른 요약'만 보여준다 — 상세에서는 같은 값을 실제 시각/전체 텍스트로 보여줘야 하므로
    // (드로어 중복 제거는 key 기준이라) 목록 열과 겹치지 않는 별도 key를 쓴다.
    detailFields: [field("id", "작업 ID"), field("idempotency_key", "멱등키"), field("user_id", "요청자 ID"), field("conversation_id", "대화 ID"), field("message_id", "메시지 ID"),
      { key: "available_at_full", label: "실행 예정", render: (r) => fmtDateTime(r.available_at) },
      dateCol("started_at", "시작"), dateCol("finished_at", "종료"),
      { key: "duration_ms", label: "소요 시간", render: (r) => r.duration_ms != null ? (Math.round(r.duration_ms / 100) / 10) + "초" : "-" }, // 백엔드 오류 문자열(f"{type(exc).__name__}: {exc}", worker.py)은 pydantic ValidationError 등에서
      // 흔히 여러 줄이다, jsonField와 동일한 <pre>로 렌더해 줄바꿈이 살아 있게 한다(plain span은
      // word-break만 있고 white-space 보존이 없어 여러 줄이 한 줄로 뭉개졌다).
      { key: "last_error_full", label: "마지막 오류", render: (r) => (r.last_error == null || r.last_error === "" ? "-" : React.createElement("pre", { className: "c-detail-json" }, String(r.last_error))) }],
    actions: [
      { label: "재시도", variant: "primary", roles: OPS_ROLES, when: (r) => r.status === "failed", path: (r) => "/api/admin/jobs/" + r.id + "/retry", confirm: "이 작업을 다시 시도할까요?" },
      { label: "취소", variant: "danger", roles: OPS_ROLES, when: (r) => r.status === "queued", path: (r) => "/api/admin/jobs/" + r.id + "/cancel", confirm: "대기 중인 이 작업을 취소할까요? 연결된 티켓, 문서, 스케줄도 정리됩니다." },
      // 재시도/취소는 모두 object_type='job'으로 감사 로그에 기록된다(app/jobs/router.py) — 다른
      // 화면과 동일한 딥링크. operator는 이 화면(OPS_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다
      // (App.jsx SCREEN_ROLES.audit=admin/system_admin/auditor) — admin/system_admin에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin"], navigate: (r) => "#/audit?object_type=job&object_id=" + r.id },
    ],
  },
  audit: {
    key: "audit", area: "운영", title: "감사 로그", endpoint: "/api/admin/audit",
    help: "누가 무엇을 언제 바꿨는지 기록을 봅니다. 자주 쓰는 필터 조합은 ‘저장된 뷰’로 이름을 붙여 두면 다시 부를 수 있고, ‘CSV 내보내기’는 지금 화면에 걸린 필터를 그대로 적용해 내려받습니다.",
    // 내보내기·이상 징후 (0033, PLAN Phase 6). 내보내기는 브라우저가 직접 그 주소로 가야
    // Content-Disposition 이 먹으므로 download 액션이다(DataScreen.runAction 주석 참조) —
    // 지금 화면의 서버 필터가 그대로 붙어, 화면에서 본 것과 파일 내용이 어긋나지 않는다.
    headerActions: [
      // page/page_size 는 빼고 보낸다 — 내보내기는 '지금 보고 있는 한 페이지'가 아니라
      // '이 필터에 걸리는 전부'다(서버가 무시하긴 하지만 주소에 남으면 뜻이 헷갈린다).
      { label: "CSV 내보내기", download: (qs) => {
        const kept = qs.split("&").filter((kv) => kv && !/^page(_size)?=/.test(kv)).join("&");
        return "/api/admin/audit/export.csv" + (kept ? "?" + kept : "");
      } },
      { label: "이상 징후 보기", navigate: () => "#/audit-anomalies" },
    ],
    emptyTitle: "감사 기록이 없습니다", emptyHelp: "사용자, 설정, 연동 등에 변경이 생기면 누가 무엇을 언제 바꿨는지 여기에 기록됩니다.",
    // 다른 화면(예: 사용자 상세의 '감사 로그에서 보기')에서 넘어온 ?object_type=&object_id= 쿼리를
    // 필터로 소비한다(DataScreen의 open:'filter' 인텐트). 백엔드가 object_id를 이미 지원한다
    // (app/audit/router.py) — 이 화면이 그 필터를 실제로 적용하지 않아 늘 무필터 목록만 보여줬었다.
    // user_id도 받는다 — '이 사용자가 무엇을 했는지'(행위자로 필터)를 보는 딥링크용. object_type/
    // object_id(무엇이 바뀌었는지)와는 독립적인 축이라 함께 와도 각각 그대로 적용한다.
    onQuery: (p) => (p.object_type || p.object_id || p.user_id)
      ? { open: "filter", values: { object_type: p.object_type, object_id: p.object_id, user_id: p.user_id } }
      : null,
    paginated: true,
    // 백엔드 최대 100(app/core/pagination.py MAX_PAGE_SIZE)까지 지원하는데 기본값 20에 머물러 있었다
    // — 감사·조사 화면 특성상(넓은 기간을 훑어야 함) 페이지당 더 많이 받아 클릭 수를 줄인다.
    pageSize: 100,
    filters: [
      { key: "object_type", type: "select", label: "대상", options: OBJTYPE_OPTS },
      // 특정 엔티티에 일어난 모든 사건을 추적한다(상세의 '대상 ID'·부서/직책 상세 id를 붙여넣는다).
      { key: "object_id", type: "text", label: "대상 ID" },
      // 감사 action은 백엔드가 정확 일치(==)로 필터한다(router: AuditLog.action == action). 실제 값은
      // '대상.동작'을 조합한 열린 네임스페이스라(예: user.update, prompts.update_content, cli.user.enable,
      // user.role_change_requested) 유한한 select로 담으면 유효한 값을 가려 버린다 — 정확한 문자열을
      // 그대로 입력받는 자유 입력을 유지하되, 라벨로 정확 일치임을 분명히 한다.
      // '작업'은 정확 일치 자유 입력인데, 목록의 '작업' 열은 한국어 번역만 보여줘(원문은 hover title뿐)
      // 필터에 뭘 입력해야 할지 알 방법이 없었다 — 현재 페이지의 실제 action 문자열로 자동완성 제안을 준다.
      { key: "action", type: "text", label: "작업(정확히, 예: user.update)", datalistFrom: (items) => items.map((r) => r.action) },
      { key: "user_id", type: "text", label: "행위자 ID" },
      // 백엔드 _parse_boundary(app/audit/router.py)는 하루 단위가 아니라 시각(오프셋 포함 ISO-8601)까지
      // 정밀하게 필터할 수 있는데, <input type="date">로는 하루 경계만 만들 수 있어 그 정밀도가
      // 화면에서 닿지 않았다 — datetime-local로 바꿔 시:분까지 지정하고 KST(+09:00)로 변환해 보낸다.
      { key: "since", type: "datetime-local", label: "시작 시각(KST)" },
      { key: "until", type: "datetime-local", label: "종료 시각(KST)" },
    ],
    // 행위자는 이름 → 이메일 → (UUID) 순으로 표시하고, user_id가 없으면 시스템/CLI 동작이므로 '시스템'.
    columns: [dateCol("created_at", "시각"), actionCol("action", "작업"), objCol("object_type", "대상"),
      // object_type/action/actor로만 필터해도(대상 ID로 좁히지 않으면) 같은 유형·같은 작업·같은
      // 행위자의 여러 행이 목록에서 서로 구별되지 않았다 — 대상 ID를 목록에 바로 노출한다.
      truncateCol("object_id", "대상 ID", 24),
      badgeCol("result", "결과"),
      { key: "user_id", label: "행위자", render: (r) => r.actor_name || r.actor_email || (r.user_id ? r.user_id : "시스템") }],
    // '무엇을 바꿨는지'(before→after)와 포렌식 필드(기록 ID·행위자·대상 ID·IP·요청 ID)를 상세에서 본다.
    // user_id는 이미 목록 열(행위자, 이름/이메일 우선 표시)이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    // before/after는 objectField로 최상위 키/값 행으로 펼쳐 보여준다(원시 JSON 두 덩어리를 눈으로
    // diff하지 않아도 되게 — 승인 화면의 request_payload와 동일한 가독성 패턴).
    // object_id는 위 columns에 이미 truncateCol("object_id", "대상 ID", 24)로 있다 — 같은 key를 다시
    // 쓰면 mergeDetailFields가 columns 쪽(자른 버전)만 남기고 이 평문 버전은 조용히 버려져(드로어의
    // 원래 목적인 '전체 대상 ID 확인'이 실제로는 절대 렌더되지 않았다) — backup 화면의 path_full과
    // 동일한 패턴으로 별도 key를 쓴다.
    detailFields: [field("id", "기록 ID"), field("actor_name", "행위자 이름"), field("actor_email", "행위자 이메일"),
      // 이름 있는 행위자는 목록/상세 어디에도 raw user_id를 안 보여줬는데(중복이라 뺐다), '행위자 ID'
      // 필터는 그 UUID를 요구했다 — 필터에 넣을 값을 이 화면에서 확인·복사할 수 있게 원문을 노출한다.
      { key: "user_id_full", label: "행위자 ID(원문)", render: (r) => r.user_id || "시스템/CLI" },
      // '작업' 열은 한국어 번역만 보여주고 원문은 hover title뿐이라(터치 불가·복사 불가) 정확 일치
      // 필터에 넣을 값을 얻을 수 없었다 — 원문 action 문자열을 평문으로 노출한다.
      { key: "action_raw", label: "작업(원문)", render: (r) => r.action || "-" },
      { key: "object_id_full", label: "대상 ID", render: (r) => r.object_id || "-" },
      // '무엇이 바뀌었나'가 이 화면의 핵심인데 before/after 두 블록을 눈으로 diff해야 했다 — 실제로
      // 값이 달라진 키만 골라 'before → after'로 요약해 준다(프롬프트/정책 버전 비교와 같은 발상).
      { key: "_diff_summary", label: "변경 요약", render: (r) => {
        const b = (r.before && typeof r.before === "object") ? r.before : null;
        const a = (r.after && typeof r.after === "object") ? r.after : null;
        if (!b && !a) return "-";
        const keys = Array.from(new Set([...(b ? Object.keys(b) : []), ...(a ? Object.keys(a) : [])]));
        const fmt = (v) => v == null ? "-" : (typeof v === "object" ? JSON.stringify(v) : String(v));
        const changed = keys.filter((k) => JSON.stringify(b ? b[k] : undefined) !== JSON.stringify(a ? a[k] : undefined));
        if (!changed.length) return "변경된 항목 없음";
        return React.createElement("ul", null, changed.map((k, i) => React.createElement("li", { key: i }, k + ": " + fmt(b ? b[k] : undefined) + " → " + fmt(a ? a[k] : undefined))));
      } },
      objectField("before", "변경 전"), objectField("after", "변경 후"), field("client_ip", "IP"), field("request_id", "요청 ID")],
    // 감사 행이 가리키는 엔티티의 관리 화면으로 바로 이동한다(대상 유형이 라우팅 가능한 경우).
    actions: [
      // 대상 화면 중 일부(사용자·부서·직책·작업 큐)는 role이 이 감사 화면 자체보다 더 좁게 제한된다
      // (App.jsx SCREEN_ROLES) — auditor가 그 화면들에 못 들어가는데 버튼만 보이면 클릭 즉시 403이다.
      // schedule_run은 제외한다 — '#/schedules'로 보내도 특정 실행 행을 찾아 주지 못한다(스케줄
      // 화면에 그런 딥링크가 없다) — 알림 화면의 동일한 제외(registry.js notifications.actions)와 맞춘다.
      // 대상 유형이 OBJ_ID_PARAM에 있으면(workflow/integration/schedule/runner/job/user_notion_mapping/
      // document_generation) 그 화면이 ?id= 딥링크를 지원하므로 목록이 아니라 그 행 하나를 직접 연다
      // — 라벨도 실제 동작대로 '관련 항목 보기'로 구분한다(예전엔 이 딥링크 인프라가 있는데도 아무
      // 곳에서도 쓰지 않아, jobs.onQuery의 '감사 로그/알림에서 딥링크' 주석이 거짓이었다).
      { label: "관련 항목 보기", when: (r, ctx) => !!OBJ_ROUTE[r.object_type] && !!OBJ_ID_PARAM[r.object_type] && !!r.object_id && canReachObjRoute(r.object_type, ctx && ctx.role), navigate: (r) => objRouteHref(r.object_type, r.object_id) },
      // 그 외(딥링크 미지원 대상 유형, 또는 object_id 없음)는 여전히 목록 전체로만 이동한다 — 라벨을
      // 실제 동작대로 정직하게 맞춘다.
      { label: "관련 목록 열기", when: (r, ctx) => !!OBJ_ROUTE[r.object_type] && r.object_type !== "schedule_run" && !(OBJ_ID_PARAM[r.object_type] && r.object_id) && canReachObjRoute(r.object_type, ctx && ctx.role), navigate: (r) => OBJ_ROUTE[r.object_type] },
    ],
  },
  notifications: {
    key: "notifications", area: "운영", title: "알림", endpoint: "/api/notifications",
    help: "나에게 온 알림을 확인합니다.",
    emptyTitle: "새 알림이 없습니다",
    // 일반 사용자(role=user)는 승인/작업 실패 알림을 거의 받지 않는다 → 관리자 중심 예시를 보여주지 않는다(알림 벨과 동일).
    emptyHelp: (role) => role === "user" ? "나에게 온 알림이 여기에 표시됩니다." : "승인, 작업 실패 등 나에게 온 알림이 여기에 표시됩니다.",
    paginated: true,
    // 목록 응답이 이미 unread 총합을 함께 돌려준다(app/notifications/router.py) — 벨 팝오버의
    // '안 읽음 N'과 같은 값을 이 화면에서도 그대로 보여준다(행마다 배지를 세지 않아도 되게).
    unreadCountKey: "unread",
    // 안 읽은 알림만 골라 보는 트리아지(백엔드 unread_only 쿼리).
    filters: [{ key: "unread_only", type: "select", label: "읽음 상태", options: opt([["true", "안 읽음만"]]) }],
    // 제목을 첫 열로 둔다 — DataScreen의 상세 드로어 제목(detailTitle)은 columns[0]을 쓰는데, 예전엔
    // 그게 mapCol('type')이라 같은 유형('승인 요청' 등)의 알림이 모두 같은 제목으로 열려 어느 알림을
    // 보고 있는지 구분이 안 됐다 — 각 알림의 실제 제목이 드로어 제목으로도 보이게 한다.
    columns: [col("title", "제목"), mapCol("type", "유형", TYPE_KO), readCol("read_at", "읽음"), dateCol("created_at", "시각")],
    // related_object_id는 원래 상세에서 원시 UUID로만 보여줬다 — 바로 옆 '관련 항목 보기'/'관련
    // 목록 열기' 액션 버튼이 이미 같은 id를 실제로 이동 가능한 링크로 해석해 주므로, 클릭도
    // 복사도 안 되는 평문 UUID 한 줄은 정보 없이 자리만 차지했다(drop).
    detailFields: [field("body", "내용"), objField("related_object_type", "관련 대상")],
    headerActions: [
      // unread===0이면 눌러도 항상 '0건을 읽음 처리했습니다' 무의미 토스트만 나므로, 안 읽은 알림이
      // 있을 때만 노출한다(같은 화면 상단 StatCard의 unread 값과 동일한 기준).
      { label: "모두 읽음", when: (ctx) => ctx.unreadCount > 0, path: () => "/api/notifications/read-all", confirm: "모든 알림을 읽음 처리할까요?",
        result: (res) => ({ ok: true, msg: (res && res.read_count != null ? res.read_count : 0) + "건을 읽음 처리했습니다." }) },
    ],
    actions: [
      // keepSelection은 쓰지 않는다 — POST /api/notifications/{id}/read(app/notifications/router.py
      // mark_read)는 {"ok": true}만 돌려주고 갱신된 항목(res.item)을 포함하지 않는다. DataScreen의
      // keepSelection 분기는 res.item이 있을 때만 드로어를 그 항목으로 갱신하고, 없으면 그냥
      // setSel(null)로 닫는다(runAction) — 즉 여기선 keepSelection을 켜 놔도 항상 드로어가 닫혔다.
      // 실제 동작(닫힘)과 의도가 어긋났던 것을 없앤다.
      // localPatch — 서버가 {"ok":true}만 돌려주고 갱신된 항목을 안 주므로(위 주석), 드로어를 곧장
      // 닫는 대신 read_at을 로컬에서 채워 드로어를 열어 둔 채로 '읽음' 상태를 바로 보여준다.
      { label: "읽음 처리", when: (r) => !r.read_at, path: (r) => "/api/notifications/" + r.id + "/read",
        localPatch: (r) => ({ ...r, read_at: new Date().toISOString() }) },
      // 관련 대상(승인·작업·스케줄 등)이 있으면 해당 관리 화면으로 이동한다(문서 화면 navigate 방식과 동일).
      // 대상은 모두 관리자 콘솔 경로라 일반 사용자(role=user)에겐 숨긴다 — 누르면 채팅으로 튕겨 나가기 때문.
      // ADMIN_VIEW_ROLES 통과만으로는 부족하다 — 대상 화면 중 일부(사용자·부서·직책·작업 큐)는
      // auditor 등을 추가로 제외한다(App.jsx SCREEN_ROLES) — canReachObjRoute로 실제 도달 가능할 때만 노출.
      // schedule_run은 제외한다 — '#/schedules'로 보내도 특정 실행 행을 찾아 주지 못해(스케줄
      // 화면에 그런 딥링크가 없다) 클릭해도 실제로는 아무것도 못 찾는 겉보기 기능이었다
      // (NotificationBell.jsx의 동일한 제외와 맞춘다).
      // related_object_type이 OBJ_ID_PARAM에 있으면(감사 로그 액션과 동일한 기준) 그 화면이 ?id=
      // 딥링크를 지원하므로 목록이 아니라 그 항목 하나를 직접 연다 — 라벨도 실제 동작대로 구분한다.
      { label: "관련 항목 보기", roles: ADMIN_VIEW_ROLES,
        when: (r, ctx) => !!(r.related_object_type && OBJ_ROUTE[r.related_object_type] && OBJ_ID_PARAM[r.related_object_type] && r.related_object_id) && canReachObjRoute(r.related_object_type, ctx && ctx.role),
        navigate: (r) => objRouteHref(r.related_object_type, r.related_object_id) },
      // 그 외(딥링크 미지원 대상 유형, 또는 related_object_id 없음)는 여전히 목록 전체로만 이동한다 —
      // 라벨을 실제 동작대로 정직하게 알린다. schedule_run도 이제 여기 포함한다 — 예전엔 따로
      // 빼서 이 알림 유형만 클릭할 게 아무것도 없었다(스케줄 화면에 실행 건별 딥링크가 없다는
      // 이유였지만, 목록 전체로라도 보내는 게 아무 동작도 없는 것보다는 낫다 — schedule_run은
      // OBJ_ROUTE에서 이미 '#/schedules'로 매핑돼 있다).
      { label: "관련 목록 열기", roles: ADMIN_VIEW_ROLES,
        when: (r, ctx) => !!(r.related_object_type && OBJ_ROUTE[r.related_object_type]) && !(OBJ_ID_PARAM[r.related_object_type] && r.related_object_id) && canReachObjRoute(r.related_object_type, ctx && ctx.role),
        navigate: (r) => OBJ_ROUTE[r.related_object_type] },
    ],
  },
  backup: {
    key: "backup", area: "운영", title: "백업", endpoint: "/api/admin/backups",
    // 웹 콘솔에서 실행되는 이 백업은 단일 파일 스냅샷(var/exports/web-*.sqlite3)이며, 웹에서
    // 복원할 수 없고 rollback 스크립트의 입력도 아니다(system_admin이 '복원 안내'에서 상세를 볼 수
    // 있지만, 그 경고가 role 게이트된 모달 안에만 있어 다른 역할은 볼 방법이 없었다 — 항상 보이는
    // help로 옮겨 어떤 역할이 봐도 오해하지 않게 한다).
    help: "데이터베이스를 백업합니다. 오래된 백업은 자동 정리됩니다. 이 목록은 웹 콘솔 DB 스냅샷입니다, 웹에서 복원할 수 없으며 서버의 rollback 스크립트 입력도 아닙니다. 복원은 시스템 관리자가 서버에서 별도 스크립트로만 수행합니다.",
    emptyTitle: "아직 백업이 없습니다",
    // 백업 프로세스가 도중에 죽으면(OOM-kill·systemd 재시작) 행이 status='running'인 채로 남고,
    // reap_stuck_running()이 다음 GET에서만 정리한다(app/backups/service.py, 60분 임계값) — 이미
    // 열어 둔 탭이 그 GET을 스스로 트리거하지 않으므로, 다른 화면들과 동일하게 진행 중 행이 있으면
    // 자동 새로고침해 그 전이를 화면이 따라가게 한다.
    pollWhile: (r) => r.status === "running",
    // 백업 실행·복원·검증은 모두 system_admin 전용(백엔드 RBAC). 그 외 역할에는 CTA 대신 읽기 전용 안내를 준다.
    emptyHelp: (role) => role === "system_admin"
      ? "‘+ 백업 실행’으로 지금 데이터베이스를 백업하세요. 오래된 백업은 자동 정리됩니다."
      : "아직 백업이 없습니다. 백업은 시스템 관리자가 실행할 수 있습니다.",
    // 첫 실행 시스템 관리자에게 단계별 안내를 준다(canOnboard가 primary 헤더 작업 '+ 백업 실행'을
    // 근거로 system_admin에만 보여준다). 다른 운영 화면(연동/러너)의 온보딩 패턴과 통일.
    emptySituation: "아직 데이터베이스 백업이 하나도 없습니다.",
    emptyPrerequisite: "백업은 웹 콘솔 DB 스냅샷입니다, 웹에서 복원할 수 없고 복원은 서버에서 별도 스크립트로만 수행합니다.",
    emptySteps: ["‘+ 백업 실행’으로 지금 스냅샷을 만듭니다.", "상태가 ‘확인됨(verified)’이 되는지 확인합니다.", "정기적으로 백업하는 습관을 들입니다(오래된 백업은 자동 정리됩니다)."],
    emptyExpected: "실행한 백업이 상태, 크기와 함께 목록에 남고, 최근의 정상 백업이 자동 보관됩니다.",
    headerActions: [
      { label: "복원 안내", method: "GET", roles: ["system_admin"], path: () => "/api/admin/backups/restore-instructions",
        // 웹 콘솔 스냅샷의 실제 복원법(web_snapshot_note)과 rollback 입력 규칙(rollback_input)까지 함께 보여준다.
        info: (res) => {
          const r0 = res || {};   // 빈/비-JSON 2xx면 api()가 null을 준다 — res.x 직접 접근은 throw
          const asText = (v) => v == null ? "" : (typeof v === "string" ? v : JSON.stringify(v, null, 2));
          const parts = [asText(r0.note), asText(r0.web_snapshot_note), asText(r0.rollback_input)].filter((x) => x);
          const steps = (r0.steps || []).map((s, i) => (i + 1) + ". " + s).join("\n");
          if (steps) parts.push(steps);
          return parts.join("\n\n");
        } },
      // primary:true → 백업이 하나도 없는 첫 실행 화면의 CTA가 '복원 안내'가 아니라 이 버튼이 된다(system_admin에게만).
      // 백업 실패 사유는 sqlite3 원시 예외 텍스트가 그대로 올 수 있다(app/backups/sqlite_backup.py) —
      // 알려진 사유 코드만 한국어로 치환해 영어가 그대로 새지 않게 한다(backupReasonText).
      { label: "+ 백업 실행", variant: "primary", primary: true, roles: ["system_admin"], path: () => "/api/admin/backups", confirm: "지금 데이터베이스 백업을 실행할까요?",
        result: (res) => { const s = res.backup && res.backup.status; const ok = s === "verified" || s === "succeeded"; return { ok, msg: ok ? "백업 완료" : ("백업 실패: " + backupReasonText((res.backup && res.backup.error_message) || "확인 실패")) }; } },
    ],
    // 경로는 파일명만 목록에 보이고(내부 배포 경로 노출·너비 낭비 방지), 전체 경로는 상세에서 본다.
    columns: [dateCol("created_at", "생성"), badgeCol("status", "상태"), { key: "size_bytes", label: "크기", render: (r) => fmtBytes(r.size_bytes) },
      { key: "path", label: "파일", render: (r) => { const p = r.path; if (p == null || p === "") return "-"; const s = String(p); const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\")); return i >= 0 ? s.slice(i + 1) : s; } }],
    // 목록 열은 파일명만 보여주고(위 columns "파일") 상세는 전체 경로를 보여준다 — 둘 다 실제로는
    // r.path를 읽지만 표시가 다르므로(파일명 vs 전체 경로), 새 드로어 중복 제거(key 기준, DataScreen.jsx
    // mergeDetailFields)가 이 상세 전용 항목을 columns의 "파일"과 같은 것으로 오인해 지우지 않도록
    // key를 다르게 둔다.
    // id는 감사 로그의 object_id(object_type=backup)와 대조할 때 필요한데, 템플릿·감사 기록 상세와
    // 달리 이 화면만 id를 어디에도 보여주지 않아 대조할 방법이 없었다.
    // backup_type은 현재 항상 "sqlite"뿐이지만(app/backups/models.py 하드코딩), 다른 상태 열(status)처럼
    // mapCol/badgeCol 대신 raw 값을 그대로 보여주고 있었다 — 미래에 두 번째 유형이 생겨도 번역 없는
    // 원문이 새지 않게 지금부터 작은 맵으로 감싼다.
    detailFields: [field("id", "백업 ID"), mapCol("backup_type", "유형", { sqlite: "SQLite" }), { key: "path_full", label: "전체 경로", render: (r) => r.path || "-" }, field("created_by", "실행자 ID"), field("checksum", "체크섬"), dateCol("verified_at", "검증 시각"),
      { key: "error_message", label: "오류", render: (r) => r.error_message ? backupReasonText(r.error_message) : "-" }],
    // 검증 엔드포인트는 상태와 무관하게 어떤 backup id도 받아들인다(app/backups/router.py) — 예전엔
    // status===verified|succeeded일 때만 버튼을 보여줘서, 한 번 failed가 된 행은 재검증할 방법이
    // 영영 사라졌다(백엔드는 지원하는데 UI만 막고 있었다). 상태와 무관하게 항상 노출한다.
    actions: [
      // status==='running'인 동안은 백업 파일이 아직 쓰이는 중이고 체크섬도 null이다(app/backups/service.py
      // run_backup()) — 이 창에 '검증'을 누르면 expected_checksum=None이라 체크섬 비교를 건너뛰고
      // PRAGMA integrity_check만 돈다(app/backups/sqlite_backup.py). 완료된 백업에만 노출한다.
      { label: "검증", roles: ["system_admin"], when: (r) => r.status !== "running", path: (r) => "/api/admin/backups/" + r.id + "/verify",
        result: (res) => ({ ok: !!(res.verify && res.verify.ok), msg: (res.verify && res.verify.ok) ? "검증 완료: 정상" : "검증 실패: " + backupReasonText((res.verify && res.verify.reason) || "손상 가능성") }) },
      // operator는 백업 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=backup&object_id=" + r.id },
    ],
  },
  rbac: {
    key: "rbac", area: "사용자", title: "권한 매트릭스", endpoint: "/api/admin/rbac-matrix",
    help: "누가 무엇을 할 수 있는지 한 화면에서 봅니다. 이 표는 서버의 권한 정의(app/core/authz.py) 하나에서 그대로 옵니다 — 화면이 따로 들고 있는 사본이 없으므로 규칙을 고치면 이 표도 함께 바뀝니다.",
    emptyTitle: "권한 정의를 불러오지 못했습니다",
    // 열이 곧 역할이라 서버 응답에서 만든다 — 여기에 역할 배열을 적으면 두 벌이 되고,
    // 백엔드에서 규칙을 고쳐도 이 표만 옛 열을 계속 보여 준다(tests/security/test_rbac_matrix.py가 고정).
    columnsFrom: (data) => [
      col("capability", "할 수 있는 일"),
      col("area", "영역"),
      ...((data && data.roles) || []).map((role) => ({
        key: "role_" + role.value, label: role.label, align: "center",
        render: (r) => (r.allowed || []).includes(role.value)
          ? React.createElement(Badge, { value: "허용", kind: "ok" })
          : React.createElement("span", { "aria-label": "허용 안 됨" }, "—"),
      })),
    ],
    // 검색은 '할 수 있는 일'과 '영역'만 대상으로 — 기본(JSON.stringify)이면 allowed 배열의
    // 원시 역할 값('system_admin')까지 매칭해 화면에 안 보이는 값으로 결과가 걸린다.
    searchFields: ["capability", "area", "note"],
    searchPlaceholder: "권한 이름으로 검색",
    detailFields: [field("id", "권한 키"), field("note", "설명"),
      { key: "allowed", label: "허용 역할", render: (r) => (r.allowed || []).join(", ") || "-" }],
  },
  "org-tree": {
    key: "org-tree", area: "사용자", title: "조직도", endpoint: "/api/admin/departments/tree",
    help: "부서 계층을 한눈에 봅니다. 이름 앞의 들여쓰기가 상하 관계입니다. 상위 부서는 ‘부서 관리’ 화면에서 지정합니다.",
    emptyTitle: "등록된 부서가 없습니다",
    emptyHelp: "‘부서 관리’에서 부서를 만들고 상위 부서를 지정하면 여기에 계층으로 표시됩니다.",
    emptyRelatedLink: { href: "#/departments", label: "부서 관리로 이동" },
    searchFields: ["name", "path"],
    searchPlaceholder: "부서 이름으로 검색",
    filters: ACTIVE_FILTER,
    columns: [
      // 들여쓰기가 곧 트리다 — 표 하나로 조직도를 그리기 위한 유일한 장치라 여기서만 만든다.
      // 공백 문자가 아니라 좌측 패딩(rem)이라 4K에서 루트 폰트사이즈 레버를 그대로 따라간다.
      { key: "name", label: "부서", render: (r) => React.createElement(
        "span",
        { style: { paddingInlineStart: (r.depth || 0) * 1.25 + "rem" }, title: r.path },
        (r.depth ? "└ " : "") + r.name + (r.cycle ? " (상위 관계 오류)" : ""),
      ) },
      activeCol("사용"),
      col("user_count", "소속 인원(보관 포함)"),
      col("subtree_user_count", "하위 포함 인원"),
      col("child_count", "하위 부서"),
    ],
    detailFields: [field("id", "부서 ID"), field("path", "전체 경로"),
      { key: "parent_name", label: "상위 부서", render: (r) => r.parent_name || "(최상위)" },
      { key: "cycle", label: "상위 관계 오류", render: (r) => r.cycle
        ? "이 부서는 상위 관계가 고리를 이루고 있어 최상위로 끌어올려 표시했습니다. ‘부서 관리’에서 상위 부서를 다시 지정하세요."
        : "-" }],
    actions: [
      { label: "소속 인원 보기", roles: WRITE_ROLES, navigate: (r) => "#/users?department_id=" + r.id },
      { label: "부서 관리에서 열기", roles: WRITE_ROLES, navigate: () => "#/departments" },
    ],
  },
  /* ── 관리자 백로그 잔여 (PLAN Phase 6, 마이그레이션 0033) ───────────────────
   *
   * 아래 여덟 화면은 전부 DataScreen 계약에 맞췄다. 새 화면 컴포넌트를 만들지 않은 이유:
   * 목록 + 필터 + 상세 드로어 + 액션이라는 모양이 이미 이 계약 그대로이고, 손으로 쓰면
   * 401 처리·페이지네이션·"검색 결과 없음"과 "데이터 없음" 구분을 화면마다 다시 유도해야
   * 한다(그리고 매번 조금씩 다르게 된다). 달력(스케줄러)만 표로 표현할 수 없어 별도 화면이다.
   */
  impersonation: {
    key: "impersonation", area: "사용자", title: "임퍼소네이션(대리 보기)",
    endpoint: "/api/admin/impersonation/sessions",
    help: "다른 사용자의 화면을 그 사람 눈으로 읽기만 합니다. 임퍼소네이션 중에는 모든 쓰기가 서버에서 차단되고, 누가 누구를 언제 봤는지가 이 목록과 감사 로그에 남습니다. 시작하면 화면 위에 띠가 뜹니다.",
    emptyTitle: "임퍼소네이션 기록이 없습니다",
    emptyHelp: "‘대리 보기 시작’으로 사용자를 지정하면 그 사람의 화면을 읽기 전용으로 볼 수 있습니다.",
    emptySituation: "지원 문의를 받았는데 그 사용자에게 무엇이 보이는지 확인할 방법이 없었습니다.",
    emptyPrerequisite: "대상 사용자의 ID가 필요합니다(‘사용자’ 화면에서 확인).",
    emptySteps: [
      "‘대리 보기 시작’에 대상 사용자 ID와 사유를 적습니다.",
      "화면 위 띠가 뜨면 그 사용자의 눈으로 보고 있는 상태입니다.",
      "확인이 끝나면 띠의 ‘대리 보기 종료’를 누릅니다(최대 30분 뒤 자동 종료).",
    ],
    emptyExpected: "시작·종료가 이 목록과 감사 로그에 남고, 그동안의 쓰기 시도는 전부 차단되며 횟수가 기록됩니다.",
    paginated: true,
    filters: [{ key: "active", type: "select", label: "진행 중", options: opt([["true", "진행 중"], ["false", "종료됨"]]) }],
    columns: [
      { key: "actor_name", label: "관리자", render: (r) => r.actor_name || r.actor_user_id },
      { key: "target_name", label: "대상", render: (r) => r.target_name || r.target_user_id },
      dateCol("started_at", "시작"), dateCol("ended_at", "종료"),
      { key: "active", label: "상태", render: (r) => React.createElement(Badge, { value: r.active ? "진행 중" : "종료", kind: r.active ? "warn" : "neutral" }) },
      { key: "blocked_write_count", label: "차단된 쓰기", align: "right" },
    ],
    detailFields: [
      field("id", "기록 ID"), field("reason", "사유"), field("client_ip", "접속 IP"),
      field("target_email", "대상 이메일"), field("actor_email", "관리자 이메일"),
      { key: "ended_reason", label: "종료 사유", render: (r) => ({ manual: "관리자가 종료", logout: "로그아웃", target_unavailable: "대상 계정 사용 불가", expired: "시간 초과 자동 종료" })[r.ended_reason] || r.ended_reason || "-" },
      { key: "read_count", label: "조회 횟수" },
      { key: "_blocked_note", label: "차단 안내", render: (r) => r.blocked_write_count ? "이 세션에서 쓰기 시도가 " + r.blocked_write_count + "회 차단됐습니다. 임퍼소네이션 중에는 어떤 변경도 되지 않습니다." : "-" },
    ],
    headerActions: [
      { label: "대리 보기 시작", variant: "primary", primary: true, roles: WRITE_ROLES,
        path: () => "/api/admin/impersonation/start",
        fields: [
          { name: "user_id", label: "대상 사용자 ID", type: "text", required: true, help: "‘사용자’ 화면에서 대상 계정의 ID를 복사해 붙여 넣으세요. 자신과 같거나 더 높은 권한의 계정은 지정할 수 없습니다." },
          { name: "reason", label: "사유", type: "textarea", help: "왜 보는지 적어 두면 감사 기록에 함께 남습니다(예: 문의 #123 재현 확인)." },
        ],
        // 시작하면 '내가 누구인지'가 바뀐다 — 화면을 통째로 다시 읽어야 사이드바·상단 배너가
        // 함께 바뀐다(부분 갱신하면 관리자 메뉴에 사용자 데이터가 섞인 화면이 된다).
        reloadAfter: true,
        result: () => ({ ok: true, msg: "대리 보기를 시작했습니다. 화면을 다시 불러옵니다 — 위쪽 띠에서 종료할 수 있습니다." }) },
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: () => "#/audit?action=impersonation.start" },
    ],
    actions: [
      { label: "이 관리자의 기록만", navigate: (r) => "#/impersonation?actor_user_id=" + encodeURIComponent(r.actor_user_id) },
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=user&object_id=" + encodeURIComponent(r.target_user_id) },
    ],
    onQuery: (p) => (p.actor_user_id || p.target_user_id || p.active)
      ? { open: "filter", values: { actor_user_id: p.actor_user_id, target_user_id: p.target_user_id, active: p.active } }
      : null,
  },
  "approval-delegations": {
    key: "approval-delegations", area: "자동화", title: "승인 위임",
    endpoint: "/api/admin/approval-delegations",
    help: "결재자가 자리를 비우는 동안 다른 사람이 대신 승인할 수 있게 합니다. 위임을 받은 사람은 평소 승인 권한이 없어도 위임 기간에만 결재할 수 있고, 그 결재에는 누구를 대신했는지가 함께 기록됩니다. 기간이 지나면 저절로 닫힙니다.",
    emptyTitle: "등록된 위임이 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 위임 추가’로 부재 기간과 대리 승인자를 지정하세요.", "위임은 관리자가 등록합니다."),
    emptySituation: "결재자가 휴가를 가면 승인 큐가 그동안 멈춥니다.",
    emptyPrerequisite: "위임하는 사람(승인 권한이 있는 계정)과 대신할 사람의 사용자 ID가 필요합니다.",
    emptySteps: ["‘+ 위임 추가’에 두 사람의 ID와 기간을 적습니다.", "기간이 시작되면 상태가 ‘진행 중’이 됩니다.", "일찍 끝내려면 ‘위임 거두기’를 누릅니다."],
    emptyExpected: "위임 기간에는 대리 승인자가 승인·거절을 할 수 있고, 결재 기록에 대신한 사람이 남습니다.",
    createLabel: "+ 위임 추가",
    searchFields: ["delegator_name", "delegate_name", "reason"],
    searchPlaceholder: "이름으로 검색",
    filters: [{ key: "state", type: "select", label: "상태", options: opt([["active", "진행 중"], ["scheduled", "예정"], ["ended", "종료"], ["revoked", "거둠"]]) }],
    columns: [
      { key: "delegator_name", label: "위임한 사람", render: (r) => r.delegator_name || r.delegator_user_id },
      { key: "delegate_name", label: "대리 승인자", render: (r) => r.delegate_name || r.delegate_user_id },
      { key: "state", label: "상태", render: (r) => React.createElement(Badge, {
        value: ({ active: "진행 중", scheduled: "예정", ended: "종료", revoked: "거둠" })[r.state] || r.state,
        kind: r.state === "active" ? "ok" : r.state === "scheduled" ? "info" : "neutral",
      }) },
      dateCol("starts_at", "시작"), dateCol("ends_at", "종료"),
      truncateCol("reason", "사유", 40),
    ],
    detailFields: [field("id", "위임 ID"), field("delegator_email", "위임한 사람 이메일"),
      field("delegate_email", "대리 승인자 이메일"), dateCol("revoked_at", "거둔 시각"), dateCol("created_at", "등록")],
    create: { roles: WRITE_ROLES, fields: [
      { name: "delegator_user_id", label: "위임하는 사람(사용자 ID)", type: "text", required: true, help: "승인 권한이 있는 계정이어야 합니다(관리자·시스템 관리자). ‘사용자’ 화면에서 ID를 복사하세요." },
      { name: "delegate_user_id", label: "대리 승인자(사용자 ID)", type: "text", required: true, help: "이 사람은 위임 기간에만 승인·거절을 할 수 있습니다." },
      { name: "starts_at", label: "시작", type: "datetime-local", required: true },
      { name: "ends_at", label: "종료", type: "datetime-local", required: true, help: "최대 90일. 기간이 지나면 권한이 저절로 닫힙니다." },
      { name: "reason", label: "사유", type: "text", help: "예: 7/20~7/25 휴가" },
    ] },
    actions: [
      { label: "위임 거두기", variant: "danger", roles: WRITE_ROLES, when: (r) => r.state === "active" || r.state === "scheduled",
        path: (r) => "/api/admin/approval-delegations/" + r.id + "/revoke",
        confirm: "이 위임을 지금 거둘까요? 대리 승인자는 즉시 결재할 수 없게 됩니다." },
      { label: "승인 큐 보기", navigate: () => "#/approvals" },
    ],
  },
  announcements: {
    key: "announcements", area: "운영", title: "공지 배너",
    endpoint: "/api/admin/announcements",
    help: "모든 화면 위쪽에 띠로 뜨는 공지입니다. 사용자가 닫으면 그 사람에게는 다시 뜨지 않습니다(브라우저가 아니라 계정에 기록되므로 다른 PC에서도 닫힌 상태가 유지됩니다).",
    emptyTitle: "등록된 공지가 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 공지 추가’로 점검 예고나 안내를 띄우세요.", "공지는 관리자가 등록합니다."),
    emptySituation: "점검이나 장애를 알릴 곳이 알림 벨밖에 없었습니다(놓치기 쉽습니다).",
    emptySteps: ["‘+ 공지 추가’로 제목과 내용을 적습니다.", "필요하면 노출 기간을 정합니다(비우면 끌 때까지 계속).", "‘사용 안 함’으로 바꾸면 즉시 내려갑니다."],
    emptyExpected: "활성 공지는 모든 화면 위쪽에 띠로 뜨고, 사용자가 닫으면 그 계정에는 다시 뜨지 않습니다.",
    createLabel: "+ 공지 추가",
    paginated: true,
    searchFields: ["title", "body"],
    searchPlaceholder: "제목·내용으로 검색",
    filters: [
      { key: "active", type: "select", label: "사용", options: opt([["true", "사용"], ["false", "사용 안 함"]]) },
      { key: "level", type: "select", label: "중요도", options: opt([["info", "안내"], ["warning", "주의"], ["critical", "긴급"]]) },
    ],
    columns: [
      col("title", "제목"),
      { key: "level", label: "중요도", render: (r) => React.createElement(Badge, {
        value: ({ info: "안내", warning: "주의", critical: "긴급" })[r.level] || r.level,
        kind: r.level === "critical" ? "danger" : r.level === "warning" ? "warn" : "info",
      }) },
      mapCol("audience", "대상", { all: "모든 사용자", admin: "관리자군에게만" }),
      activeCol("사용"),
      dateCol("starts_at", "시작"), dateCol("ends_at", "종료"),
    ],
    detailFields: [field("id", "공지 ID"), field("body", "내용"),
      { key: "dismissible", label: "닫기 허용", render: (r) => r.dismissible ? "닫을 수 있음" : "닫을 수 없음(기간이 끝나야 사라짐)" },
      field("link_url", "링크 주소"), field("link_label", "링크 문구"), dateCol("created_at", "등록")],
    create: { roles: WRITE_ROLES, fields: [
      { name: "title", label: "제목", type: "text", required: true },
      { name: "body", label: "내용", type: "textarea" },
      { name: "level", label: "중요도", type: "select", value: "info", options: opt([["info", "안내"], ["warning", "주의"], ["critical", "긴급"]]) },
      { name: "audience", label: "대상", type: "select", value: "all", options: opt([["all", "모든 사용자"], ["admin", "관리자군에게만(운영자 이상)"]]) },
      { name: "starts_at", label: "노출 시작(선택)", type: "datetime-local", help: "비우면 즉시 노출됩니다." },
      { name: "ends_at", label: "노출 종료(선택)", type: "datetime-local", help: "비우면 ‘사용 안 함’으로 바꿀 때까지 계속 노출됩니다." },
      { name: "dismissible", label: "닫기 허용", type: "checkbox", value: true, checkLabel: "사용자가 닫을 수 있음", help: "끄면 닫기 버튼이 없습니다 — 그런 공지는 반드시 종료 시각을 정하세요." },
      { name: "link_url", label: "링크 주소(선택)", type: "text" },
      { name: "link_label", label: "링크 문구(선택)", type: "text" },
      { name: "active", label: "사용", type: "checkbox", value: true, checkLabel: "지금 사용" },
    ] },
    editMethod: "PATCH",
    edit: { roles: WRITE_ROLES, fields: [
      { name: "title", label: "제목", type: "text", required: true },
      { name: "body", label: "내용", type: "textarea" },
      { name: "level", label: "중요도", type: "select", options: opt([["info", "안내"], ["warning", "주의"], ["critical", "긴급"]]) },
      { name: "audience", label: "대상", type: "select", options: opt([["all", "모든 사용자"], ["admin", "관리자군에게만(운영자 이상)"]]) },
      { name: "starts_at", label: "노출 시작(선택)", type: "datetime-local" },
      { name: "ends_at", label: "노출 종료(선택)", type: "datetime-local" },
      { name: "dismissible", label: "닫기 허용", type: "checkbox", checkLabel: "사용자가 닫을 수 있음" },
      { name: "link_url", label: "링크 주소(선택)", type: "text" },
      { name: "link_label", label: "링크 문구(선택)", type: "text" },
      { name: "active", label: "사용", type: "checkbox", checkLabel: "지금 사용" },
    ] },
    actions: [
      { label: "사용", roles: WRITE_ROLES, when: (r) => !r.active, method: "PATCH", path: (r) => "/api/admin/announcements/" + r.id, body: { active: true } },
      { label: "사용 안 함", roles: WRITE_ROLES, when: (r) => r.active, method: "PATCH", path: (r) => "/api/admin/announcements/" + r.id, body: { active: false }, confirm: "이 공지를 내릴까요? 모든 화면에서 즉시 사라집니다." },
      { label: "삭제", variant: "danger", roles: WRITE_ROLES, method: "DELETE", path: (r) => "/api/admin/announcements/" + r.id, confirm: "이 공지를 지울까요? 되돌릴 수 없습니다(닫음 기록도 함께 의미를 잃습니다)." },
    ],
  },
  "ai-quotas": {
    key: "ai-quotas", area: "자동화", title: "AI 사용 상한",
    endpoint: "/api/admin/ai-quotas",
    help: "AI 호출을 사용자·기간별로 제한합니다. 상한이 걸리는 곳은 AI 도우미 문장 생성과 문서 자동 생성 요청 두 곳입니다 — 채팅 전송처럼 자주 일어나는 경로에는 걸지 않습니다(그 경로에 기록을 걸면 읽기가 쓰기로 바뀌어 느려집니다). 사용자별 상한이 전체 상한보다 우선합니다. 상한 행이 하나도 없으면 제한이 없습니다.",
    emptyTitle: "설정된 상한이 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 상한 추가’로 하루 또는 한 달 상한을 정하세요. 아무것도 없으면 제한이 없습니다.", "상한은 관리자가 설정합니다."),
    emptySituation: "AI 호출 비용에 상한이 없어, 한 사람이 많이 써도 알아챌 방법이 없습니다.",
    emptySteps: ["‘+ 상한 추가’에서 ‘전체’ 범위로 하루 상한을 정합니다.", "특정 사용자만 늘리거나 줄이려면 ‘사용자’ 범위로 한 줄 더 만듭니다.", "목록의 ‘현재 사용’ 열로 소비 상황을 확인합니다."],
    emptyExpected: "상한에 도달하면 그 사용자의 AI 요청이 거절되고, 언제 풀리는지 안내됩니다.",
    createLabel: "+ 상한 추가",
    columns: [
      mapCol("scope_type", "범위", { global: "전체", user: "사용자" }),
      { key: "user_name", label: "대상", render: (r) => r.scope_type === "global" ? "(전체)" : (r.user_name || r.user_id || "-") },
      mapCol("period", "기간", { day: "하루", month: "한 달" }),
      { key: "max_calls", label: "상한", align: "right" },
      { key: "used", label: "현재 사용", align: "right", render: (r) => (r.used == null ? "-" : r.used + " / " + r.max_calls) },
      dateCol("resets_at", "초기화"),
    ],
    detailFields: [field("id", "상한 ID"), field("user_email", "대상 이메일"), field("note", "메모"),
      dateCol("created_at", "등록"), dateCol("updated_at", "수정"),
      { key: "_over", label: "상태", render: (r) => (r.used != null && r.used >= r.max_calls) ? "상한에 도달했습니다 — 이 대상의 AI 요청이 지금 거절됩니다." : "여유가 있습니다." }],
    create: { roles: WRITE_ROLES, fields: [
      { name: "scope_type", label: "범위", type: "select", value: "global", required: true, options: opt([["global", "전체"], ["user", "사용자"]]) },
      { name: "user_id", label: "사용자 ID", type: "text", help: "범위가 ‘사용자’일 때만 필요합니다. ‘사용자’ 화면에서 ID를 복사하세요." },
      { name: "period", label: "기간", type: "select", value: "day", required: true, options: opt([["day", "하루"], ["month", "한 달"]]) },
      { name: "max_calls", label: "상한(횟수)", type: "number", required: true, help: "0이면 차단입니다(무제한이 아닙니다). 무제한으로 두려면 이 줄을 지우세요. 기간 경계는 한국 시간 기준입니다." },
      { name: "note", label: "메모", type: "text" },
    ] },
    editMethod: "PATCH",
    edit: { roles: WRITE_ROLES, fields: [
      { name: "max_calls", label: "상한(횟수)", type: "number", required: true },
      { name: "note", label: "메모", type: "text" },
    ] },
    actions: [
      { label: "삭제", variant: "danger", roles: WRITE_ROLES, method: "DELETE", path: (r) => "/api/admin/ai-quotas/" + r.id, confirm: "이 상한을 지울까요? 지우면 이 범위·기간에는 제한이 없어집니다." },
    ],
  },
  "feature-flags": {
    key: "feature-flags", area: "운영", title: "기능 플래그",
    endpoint: "/api/admin/feature-flags",
    help: "모듈을 켜고 끄는 스위치입니다. ‘파일’ 소유 플래그는 여기서 바꾸면 재시작 없이 즉시 반영됩니다. ‘설정 화면’ 소유 플래그는 여기서 바꿀 수 없습니다 — 값의 주인이 한 곳이어야 하기 때문입니다(‘설정’ 화면에서 바꾸세요).",
    emptyTitle: "플래그 정의를 불러오지 못했습니다",
    searchFields: ["name", "description"],
    searchPlaceholder: "플래그 이름으로 검색",
    filters: [{ key: "owner", type: "select", label: "값의 주인", clientFilter: true, options: opt([["file", "파일(여기서 변경)"], ["db", "설정 화면"]]) }],
    columns: [
      col("name", "플래그"),
      { key: "value", label: "현재", render: (r) => React.createElement(Badge, { value: r.value ? "켜짐" : "꺼짐", kind: r.value ? "ok" : "neutral" }) },
      mapCol("owner", "값의 주인", { file: "파일", db: "설정 화면" }),
      { key: "has_consumer", label: "실제 효과", render: (r) => r.has_consumer ? "있음" : "없음(읽는 코드 없음)" },
      truncateCol("description", "설명", 70),
    ],
    detailFields: [
      field("description", "설명"), field("edit_hint", "변경 안내"),
      { key: "default", label: "기본값", render: (r) => r.default ? "켜짐" : "꺼짐" },
      { key: "_no_consumer", label: "주의", render: (r) => r.has_consumer ? "-" : "이 플래그를 읽는 코드가 아직 없습니다 — 켜거나 꺼도 동작이 달라지지 않습니다." },
    ],
    actions: [
      { label: "켜기", variant: "primary", roles: WRITE_ROLES, when: (r) => r.editable_here && !r.value,
        method: "PUT", path: (r) => "/api/admin/feature-flags/" + encodeURIComponent(r.name), body: { enabled: true },
        confirm: (r) => r.name + " 플래그를 켤까요? 재시작 없이 즉시 반영됩니다." },
      { label: "끄기", variant: "danger", roles: WRITE_ROLES, when: (r) => r.editable_here && r.value,
        method: "PUT", path: (r) => "/api/admin/feature-flags/" + encodeURIComponent(r.name), body: { enabled: false },
        confirm: (r) => r.name + " 플래그를 끌까요? 이 기능을 쓰는 화면이 즉시 사라지거나 요청이 거절됩니다." },
      { label: "설정 화면에서 열기", when: (r) => !r.editable_here, navigate: () => "#/settings" },
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=feature_flag&object_id=" + encodeURIComponent(r.name) },
    ],
  },
  "audit-anomalies": {
    key: "audit-anomalies", area: "운영", title: "감사 이상 징후",
    endpoint: "/api/admin/audit/anomalies",
    help: "감사 로그에서 눈여겨볼 만한 것을 규칙으로 골라냅니다. 통계 모델이나 AI가 아니라 셀 수 있는 사실만 봅니다 — 그래서 같은 데이터면 언제 열어도 같은 결과가 나오고, 각 항목에 왜 걸렸는지(근거·임계값)가 함께 표시됩니다. 여기 걸렸다고 곧바로 문제인 것은 아니며, 확인할 대상을 좁혀 주는 목록입니다.",
    emptyTitle: "눈여겨볼 징후가 없습니다",
    emptyHelp: "선택한 기간의 감사 로그에서 규칙에 걸린 항목이 없습니다. 기간을 늘려 다시 확인할 수 있습니다.",
    filters: [{ key: "window_hours", type: "select", label: "기간", value: "24", options: opt([["6", "최근 6시간"], ["24", "최근 24시간"], ["168", "최근 7일"], ["720", "최근 30일"]]) }],
    columns: [
      { key: "severity", label: "중요도", render: (r) => React.createElement(Badge, {
        value: ({ high: "높음", medium: "보통", low: "낮음" })[r.severity] || r.severity,
        kind: r.severity === "high" ? "danger" : r.severity === "medium" ? "warn" : "info",
      }) },
      mapCol("kind", "유형", {
        failure_burst: "실패 급증", volume_spike: "동작 급증", off_hours: "심야 변경",
        critical_action: "권한·계정 변경", new_actor_action: "처음 하는 동작",
      }),
      { key: "actor_name", label: "행위자", render: (r) => r.actor_name || r.actor_id || "시스템" },
      col("title", "요약"),
      { key: "count", label: "건수", align: "right" },
      dateCol("last_at", "마지막"),
    ],
    detailFields: [
      field("detail", "설명"),
      { key: "evidence", label: "근거", render: (r) => (r.evidence || []).join(" · ") || "-" },
      { key: "threshold", label: "임계값", render: (r) => r.threshold == null ? "-" : String(r.threshold) },
      dateCol("first_at", "처음"), field("actor_email", "행위자 이메일"),
    ],
    actions: [
      { label: "이 사람의 감사 로그", roles: ["admin", "system_admin", "auditor"], when: (r) => !!r.actor_id, navigate: (r) => "#/audit?user_id=" + encodeURIComponent(r.actor_id) },
      { label: "실패만 보기", roles: ["admin", "system_admin", "auditor"], when: (r) => r.kind === "failure_burst" && !!r.actor_id, navigate: (r) => "#/audit?user_id=" + encodeURIComponent(r.actor_id) + "&result=failure" },
    ],
    headerActions: [
      { label: "감사 로그 전체", roles: ["admin", "system_admin", "auditor"], navigate: () => "#/audit" },
    ],
  },
  "restore-drills": {
    key: "restore-drills", area: "운영", title: "복구 리허설",
    endpoint: "/api/admin/backups/rehearsals",
    help: "백업은 복원해 본 적이 없으면 백업이 아닙니다. 리허설은 백업을 실제로 되돌려 무결성·행 수·스키마를 대조하고, 복원본으로 앱을 띄워 읽기 경로까지 확인합니다. 앱이 스스로 돌리지 않으므로(메모리를 두 배로 쓰기 때문) 서버에서 명령을 실행하면 결과가 여기에 남습니다.",
    emptyTitle: "복구 리허설 기록이 없습니다",
    emptyHelp: "아직 한 번도 복원을 시험하지 않았습니다. 아래 순서로 실행하면 결과가 이 목록에 남습니다.",
    emptySituation: "백업 파일은 쌓이는데, 그것으로 실제 복원이 되는지는 아무도 확인한 적이 없습니다.",
    emptyPrerequisite: "서버에 접속할 수 있어야 합니다(웹에서 실행하지 않습니다).",
    emptySteps: [
      "서버에서 scripts/restore_rehearsal.py --record 를 실행합니다.",
      "백업 → 검증 → 복원 → 무결성 → 행 수 대조 → 스키마 → 실제 부팅 순으로 7단계가 돕니다.",
      "끝나면 결과 한 줄이 이 목록에 남습니다(실패하면 실패한 단계도 함께).",
    ],
    emptyExpected: "‘마지막으로 복원을 시험한 게 언제인가’에 이 화면 하나로 답할 수 있게 됩니다.",
    emptyRelatedLink: { href: "#/backup", label: "백업 목록으로 이동" },
    summary: {
      endpoint: "/api/admin/backups/schedule",
      cards: (data) => {
        const s = (data && data.schedule) || {};
        const last = data && data.last_backup;
        const drill = data && data.last_rehearsal;
        return [
          { value: s.enabled ? s.cron : "꺼짐", label: s.enabled ? "자동 백업 (" + (s.timezone || "Asia/Seoul") + ")" : "자동 백업", kind: s.enabled ? "ok" : "warn" },
          { value: last ? fmtDateTime(last.created_at) : "없음", label: "마지막 백업", kind: last ? "ok" : "danger" },
          { value: drill ? (drill.ok ? "통과" : "실패") : "한 번도 안 함", label: "마지막 리허설", kind: drill ? (drill.ok ? "ok" : "danger") : "warn" },
          { value: s.keep == null ? "-" : String(s.keep), label: "보관 개수" },
        ];
      },
    },
    columns: [
      { key: "ok", label: "결과", render: (r) => React.createElement(Badge, { value: r.ok ? "통과" : "실패", kind: r.ok ? "ok" : "danger" }) },
      dateCol("started_at", "시작"), dateCol("finished_at", "종료"),
      { key: "_rows", label: "행 수", align: "right", render: (r) => (r.summary && r.summary.rows != null) ? String(r.summary.rows) : "-" },
      { key: "_head", label: "스키마", render: (r) => (r.summary && r.summary.alembic_head) || "-" },
      truncateCol("source_label", "원본", 50),
    ],
    detailFields: [
      field("id", "기록 ID"),
      { key: "failures", label: "실패한 단계", render: (r) => (r.failures || []).join(" · ") || "없음" },
      { key: "_summary", label: "요약", render: (r) => JSON.stringify(r.summary || {}) },
    ],
    headerActions: [
      { label: "백업 목록", navigate: () => "#/backup" },
      { label: "백업 일정 설정", roles: WRITE_ROLES, navigate: () => "#/settings" },
    ],
  },
  "prompt-usage": {
    key: "prompt-usage", area: "콘텐츠", title: "프롬프트 사용 통계",
    endpoint: "/api/admin/prompts/usage/stats",
    help: "프롬프트가 실제로 쓰이고 있는지 이름별로 봅니다. ‘쓰이지 않음’은 이 이름을 참조하는 템플릿·스케줄이 없고 문서 생성에도 쓰인 적이 없다는 뜻입니다 — 정리 대상을 고를 때 씁니다. 버전 비교와 되돌리기는 ‘프롬프트’ 화면의 ‘버전 기록’에서 합니다.",
    emptyTitle: "등록된 프롬프트가 없습니다",
    emptyHelp: "‘프롬프트’ 화면에서 프롬프트를 만들면 여기에 사용 현황이 표시됩니다.",
    emptyRelatedLink: { href: "#/prompts", label: "프롬프트 화면으로 이동" },
    searchFields: ["name"],
    searchPlaceholder: "프롬프트 이름으로 검색",
    filters: [{ key: "unused", type: "select", label: "사용 여부", clientFilter: true, options: opt([["true", "쓰이지 않음"], ["false", "쓰이는 중"]]) }],
    columns: [
      col("name", "이름"),
      { key: "unused", label: "사용", render: (r) => React.createElement(Badge, { value: r.unused ? "쓰이지 않음" : "쓰이는 중", kind: r.unused ? "warn" : "ok" }) },
      { key: "versions", label: "버전 수", align: "right" },
      { key: "published_version", label: "발행 버전", align: "right", render: (r) => r.published_version == null ? "없음" : String(r.published_version) },
      { key: "template_refs", label: "템플릿", align: "right" },
      { key: "schedule_refs", label: "스케줄", align: "right" },
      { key: "document_runs", label: "문서 생성", align: "right" },
    ],
    detailFields: [
      { key: "template_names", label: "참조하는 템플릿", render: (r) => (r.template_names || []).join(", ") || "없음" },
      { key: "schedule_names", label: "참조하는 스케줄", render: (r) => (r.schedule_names || []).join(", ") || "없음" },
      { key: "latest_version", label: "최신 버전" },
      badgeCol("latest_status", "최신 상태"),
      dateCol("last_published_at", "마지막 발행"),
    ],
    actions: [
      { label: "이 프롬프트 버전 보기", navigate: (r) => "#/prompts?name=" + encodeURIComponent(r.name) },
    ],
    headerActions: [
      { label: "정책 사용 통계", navigate: () => "#/policy-usage" },
    ],
  },
  "policy-usage": {
    key: "policy-usage", area: "콘텐츠", title: "정책 사용 통계",
    endpoint: "/api/admin/policies/usage/stats",
    help: "정책이 실제로 쓰이고 있는지 이름별로 봅니다. 정책은 발행하는 순간 그 이름을 참조하는 모든 템플릿이 다음 문서 생성부터 새 내용을 쓰므로, 어디서 쓰이는지를 먼저 확인하고 발행하세요.",
    emptyTitle: "등록된 정책이 없습니다",
    emptyHelp: "‘정책’ 화면에서 정책을 만들면 여기에 사용 현황이 표시됩니다.",
    emptyRelatedLink: { href: "#/policies", label: "정책 화면으로 이동" },
    searchFields: ["name"],
    searchPlaceholder: "정책 이름으로 검색",
    filters: [{ key: "unused", type: "select", label: "사용 여부", clientFilter: true, options: opt([["true", "쓰이지 않음"], ["false", "쓰이는 중"]]) }],
    columns: [
      col("name", "이름"),
      { key: "unused", label: "사용", render: (r) => React.createElement(Badge, { value: r.unused ? "쓰이지 않음" : "쓰이는 중", kind: r.unused ? "warn" : "ok" }) },
      { key: "versions", label: "버전 수", align: "right" },
      { key: "published_version", label: "발행 버전", align: "right", render: (r) => r.published_version == null ? "없음" : String(r.published_version) },
      { key: "template_refs", label: "템플릿", align: "right" },
      { key: "document_runs", label: "문서 생성", align: "right" },
    ],
    detailFields: [
      { key: "template_names", label: "참조하는 템플릿", render: (r) => (r.template_names || []).join(", ") || "없음" },
      { key: "latest_version", label: "최신 버전" },
      badgeCol("latest_status", "최신 상태"),
      dateCol("last_published_at", "마지막 발행"),
    ],
    actions: [
      { label: "이 정책 버전 보기", navigate: (r) => "#/policies?name=" + encodeURIComponent(r.name) },
    ],
    headerActions: [
      { label: "프롬프트 사용 통계", navigate: () => "#/prompt-usage" },
    ],
  },
};
