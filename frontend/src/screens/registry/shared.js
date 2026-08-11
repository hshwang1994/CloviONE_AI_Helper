/* 관리자 설정 화면들이 함께 쓰는 **어휘와 열**. (E-10 로 registry.js 2,534줄에서 갈라져 나왔다.)
 *
 * 여기 있는 것: 값을 사람의 말로 바꾸는 표(상태·역할·제공자…), 표의 열을 만드는 작은 함수,
 * 다른 화면으로 가는 경로 규칙, 역할 상수.
 * 여기 없는 것: 액션과 폼을 조립하는 것들 — 그건 actions.js 다. 둘을 한 파일에 두면 화면
 * 문구 한 줄을 고치려고 폼 조립 코드를 스크롤해서 지나가야 한다.
 *
 * 밖에서 들여오는 것(DataScreen 의 열 헬퍼, format 의 한국어 변환, kit 의 Badge)은 여기서
 * **되판다**. 도메인 모듈이 shared.js 한 곳만 보게 하려는 것이다 — 모듈마다 import 줄이
 * 네 개씩 늘면 화면을 옮길 때마다 그 네 줄을 다시 맞춰야 한다.
 */
import React from "react";
import Typography from "@mui/material/Typography";
export { badgeCol, mapCol, dateCol, jsonField, objectField, readCol, linkCol, listField, previewField, activeCol, truncateCol } from "../DataScreen.jsx";
export { objKo, actionKo, fmtDateTime, TYPE_KO } from "../../lib/format.js";
export { Badge } from "../../ui/kit.jsx";
import { objKo, actionKo, fmtDateTime, TYPE_KO } from "../../lib/format.js";

// 바이트 크기를 사람이 읽을 수 있게(백업 크기 등). null이면 '-'.
export const fmtBytes = (n) => {
  if (n == null || n === "") return "-";
  const b = Number(n);
  if (!isFinite(b)) return String(n);
  if (b < 1024) return b + " B";
  const u = ["KB", "MB", "GB", "TB"]; let v = b / 1024, i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return (Math.round(v * 10) / 10) + " " + u[i];
};

export const SCHED_RUN = { queued: "대기", running: "실행 중", succeeded: "성공", failed: "실패", skipped: "건너뜀" };
// 감사 로그 대상 필터 옵션 — 값은 백엔드가 실제로 저장하는 object_type 문자열과 정확히 일치해야 한다
// (백엔드가 == 정확 일치로 필터하므로 어긋나면 항상 0건). prompt/policy/setting/document는 복수형·접미
// 형태로 저장되고('prompts'/'policies'/'app_setting'/'document_generation'), 'role'은 저장되지 않는다.
export const OBJTYPE_OPTS = [["user", "사용자"], ["integration", "외부 연동"], ["runner", "러너"], ["workflow", "워크플로"],
  ["prompts", "프롬프트"], ["policies", "정책"], ["template", "템플릿"], ["schedule", "스케줄"], ["schedule_run", "예약 실행"],
  ["approval", "승인"], ["backup", "백업"], ["app_setting", "설정"], ["document_generation", "문서"],
  ["user_notion_mapping", "Notion 연결"], ["job", "작업"], ["department", "부서"], ["job_title", "직책"]]
  .map((p) => ({ value: p[0], label: p[1] }));
export const field = (key, label) => ({ key, label });

/* ── 식별자를 화면에 어떻게 낼 것인가 (E-4 "UUID 노출") ──────────────────────────
 *
 * 관리자 상세 패널이 사람 자리를 UUID 로 채우고 있었다. 운영자는 `9f2c…-…` 를 보고
 * "이게 누구냐" 를 알 수 없어 사용자 화면을 따로 열어 id 를 검색해야 했다.
 *
 * 그렇다고 id 를 전부 지우면 **지금 되던 일이 안 된다.** 그래서 두 갈래로 나눈다.
 *
 * ## 사람이 읽을 값으로 바꾸는 자리 — `personField`
 * 서버가 이미 이름을 함께 주는 자리다. 이름을 앞에 세우고 id 는 그 아래 작은 글씨로
 * 남긴다(지우지 않는다 — 동명이인이면 그때는 id 가 유일한 구분자다).
 *
 * ## 원시 id 를 그대로 남기는 자리 — 그리고 그 이유
 *   1) **다른 화면의 폼이 이 값을 요구한다.** 러너·워크플로·프롬프트·정책·템플릿·연동 ID 가
 *      그렇다. 생성/수정 폼의 도움말이 문자로 "‘러너’ 화면에서 ID를 확인해 입력하세요" 라고
 *      적혀 있다 — 여기서 지우면 그 폼을 채울 방법이 사라진다.
 *   2) **지원팀이 물어보는 값이다.** 감사 로그의 기록 ID 와 문의 번호(request_id), 사용자
 *      상세의 계정 ID. "화면이 안 나와요" 라는 문의에 이 값 하나면 서버 로그에서 그 요청을
 *      바로 찾는다. 이것들을 이름으로 바꾸면 문의 대응이 다시 추측이 된다.
 *   3) **일부러 이름을 안 싣는 자리.** 작업(잡) 큐의 요청자 id 가 그렇다. 서버가 요청자
 *      이메일·이름을 **의도적으로 응답에서 뺀다**(app/jobs/router.py `_job_view` 참고 —
 *      큐 화면이 대화 내용의 우회 열람 통로가 되지 않게). 화면에 이름을 그리려면 그 원칙을
 *      먼저 깨야 한다. 그래서 여기서는 id 로 남기고, 라벨로 그 뜻을 밝힌다.
 */
export const personField = (idKey, label, nameKey, emailKey) => ({
  key: idKey, label,
  render: (r) => {
    const name = r[nameKey];
    const email = emailKey ? r[emailKey] : null;
    const id = r[idKey];
    // 이름도 id 도 없으면 '아무도 아님'이다 — 예약·시스템이 돌린 것이 여기 해당한다.
    if (!name && !email && !id) return "자동 실행(사람 아님)";
    if (!name && !email) return React.createElement("span", null, String(id));
    return React.createElement("span", null,
      name || email,
      email && name ? React.createElement("span", { style: { color: "var(--color-muted)" } }, " " + email) : null,
      id ? React.createElement(Typography, { component: "div", variant: "caption", color: "text.disabled" }, "ID " + id) : null,
    );
  },
});               // 상세 전용 평문 필드
export const objField = (key, label) => ({ key, label, render: (r) => objKo(r[key]) });

/* 목록 화면 설정 — 열/엔드포인트만 다르고 렌더는 DataScreen이 공통 처리한다.
 * 상태 열은 badgeCol(배지), enum 열은 mapCol/actionKo(한국어)로. 값은 서버 계약 그대로. */
export const PROVIDER = { n8n: "n8n", http_service: "HTTP 서비스", notion_via_n8n: "Notion(n8n 경유)" };
export const WF_MODE = { read: "읽기", write: "쓰기" };
export const SCHED_TYPE = { cron: "Cron 반복", once: "1회 실행" };
export const DOC_MODE = { preview_then_approve: "미리보기 후 승인", preview_only: "미리보기만", auto_publish: "자동 발행" };
export const MAP_SOURCE = { workflow: "워크플로 자동", manual: "수동 지정" };
// 실제 enqueue되는 job_type 문자열과 정확히 일치해야 한다(chat_message·document_generate·notion_mapping_sync).
// 실제 enqueue되는 job_type만 매핑한다(backup은 큐에 없어 제거 — 오해 방지).
export const JOB_TYPE = { chat_message: "채팅 메시지", document_generate: "문서 생성", notion_mapping_sync: "Notion 동기화", schedule_run: "예약 실행" };
export const RUNNER_MAINT_OPTS = [["normal", "정상"], ["degraded", "성능 저하"], ["maintenance", "점검"]].map((p) => ({ value: p[0], label: p[1] }));

// 감사/승인 enum 한국어화는 공용 lib/format.js(objKo·actionKo)에서 온다.
export const objCol = (key, label) => ({ key, label, render: (r) => objKo(r[key]) });
// title 속성으로 원문 action 문자열을 마우스 오버 시 보여준다 — 감사 로그의 '작업' 필터는 이
// 원문과 정확히 일치해야 하는데(정확 일치 필터), 열은 한국어 번역만 보여줘서 필터에 뭘 입력해야
// 할지 목록만 보고는 알 방법이 없었다(truncateCol이 이미 쓰는 title 힌트 패턴과 동일).
export const actionCol = (key, label) => ({ key, label, render: (r) => React.createElement("span", { title: r[key] }, actionKo(r[key])) });

export const col = (key, label) => ({ key, label });
export const opt = (pairs) => pairs.map((p) => ({ value: p[0], label: p[1] }));
// 백엔드 허용값과 정확히 일치해야 한다(none/bearer/api_key_header) — 옛 header/basic은 422였다.
export const AUTH_OPTS = opt([["none", "없음"], ["bearer", "Bearer 토큰"], ["api_key_header", "API 키(헤더)"]]);
export const PROVIDER_OPTS = opt([["http_service", "HTTP 서비스"], ["n8n", "n8n"], ["notion_via_n8n", "Notion(n8n 경유)"]]);
export const WFMODE_OPTS = opt([["read", "읽기"], ["write", "쓰기"]]);
// 워크플로 백엔드는 POST/GET만 허용한다(WorkflowConfig._method_known).
export const HTTP_OPTS = opt([["POST", "POST"], ["GET", "GET"]]);
export const SCHEDT_OPTS = opt([["cron", "Cron 반복"], ["once", "1회 실행"]]);
// 간편 주기 — 고르면 백엔드가 Cron 식을 생성한다(cron.PRESETS). 빈 값은 '직접 입력'.
export const SCHED_PRESET_OPTS = opt([["", "사용 안 함(직접 입력)"], ["daily", "매일"], ["weekly", "매주"], ["monthly", "매월"]]);
// 스케줄 고급 정책 — 백엔드 허용값과 정확히 일치(misfire: skip/run_once, concurrency: skip/allow).
export const MISFIRE_OPTS = opt([["skip", "건너뛰기(skip)"], ["run_once", "한 번만 실행(run_once)"]]);
export const CONCURRENCY_OPTS = opt([["skip", "건너뛰기(skip)"], ["allow", "동시 실행 허용(allow)"]]);
// 'runner' 대상은 target_ref가 가리키는 워크플로 실행 경로만 백엔드가 소비하지 않는다
// (apply_template_bindings의 워크플로 재지정은 target_type===workflow일 때만 동작 —
// app/documents/service.py). 반면 prompt_id/policy_id/input_schema/approval_policy 바인딩은
// target_type과 무관하게 config.template_id로 여전히 적용된다 — '아무 효과 없음'이 아니라
// '대상 워크플로 재지정만' 안 되는 것이다. 그래도 이 화면의 '이 템플릿으로 문서 생성' 버튼은 대상
// 워크플로가 필요하므로(templates.actions 참고) 신규 생성은 워크플로만 선택 가능하게 한다.
export const TARGET_OPTS = opt([["workflow", "워크플로"]]);
// 백엔드는 템플릿의 target_type=runner도 검증·저장은 해 주고(app/templates/router.py), 실제로
// prompt/policy/입력 스키마/승인 정책 바인딩도 target_type과 무관하게 계속 적용한다(위 주석 참고) —
// 다만 apply_template_bindings의 대상 워크플로 재지정만 target_type==workflow일 때만 동작한다.
// '이 템플릿으로 문서 생성' 버튼이 대상 워크플로를 필요로 하므로, 신규 생성은 워크플로만 선택
// 가능하게 한다(기존 러너 대상 행은 detailFields의 _runner_target_note로 별도 안내).
export const TEMPLATE_TARGET_OPTS = TARGET_OPTS;
export const SCHED_TARGET_OPTS = opt([["workflow", "워크플로"], ["system", "시스템"]]);
// 상태 변경(쓰기) 액션 role 게이트 — 백엔드 RBAC와 일치시켜 읽기 전용 역할(operator/auditor)에게
// 항상 403이 되는 버튼을 애초에 숨긴다(DataScreen canDo가 a.roles로 필터).
export const WRITE_ROLES = ["admin", "system_admin"];            // 생성/수정/onoff/발행/롤백/승인·거절/동기화 등
export const OPS_ROLES = ["operator", "admin", "system_admin"];  // 운영성 액션(헬스/테스트/지금 실행/작업 재시도·취소 등)
// 관리 콘솔 역할(일반 사용자 role=user 제외) — 알림의 '관련 항목 보기'처럼 관리자 해시 경로로만
// 이동하는 액션을 일반 사용자에게 숨긴다(일반 사용자가 누르면 채팅으로 튕겨 나간다).
export const ADMIN_VIEW_ROLES = ["operator", "admin", "system_admin", "auditor"];
// 생성 권한이 없는 역할(operator/auditor)에게는 렌더되지도 않는 '+ 추가' 버튼을 누르라고 안내하지 않는다.
// 쓰기 역할(admin/system_admin)에겐 CTA 안내를, 그 외엔 읽기 전용 안내를 준다(schedules/documents/backup 패턴).
export const writerEmptyHelp = (writerMsg, readerMsg) => (role) => (role === "admin" || role === "system_admin") ? writerMsg : readerMsg;
// 알림의 관련 대상(related_object_type) → 해당 관리 화면 해시 경로(문서 화면 navigate 방식과 동일).
// 값은 REGISTRY 키(App.jsx가 "/"+key로 라우팅) 및 별도 화면(users/settings) 경로와 일치해야 한다.
// organization·feature_flag — governance.js audit 화면의 object_type 필터 드롭다운은 이미 이 둘을
// 보강해 뒀지만(OBJTYPE_OPTS에 없던 값, F15와 동일 부류), 이 맵엔 없어서 그 두 object_type의 감사
// 로그 행은 '관련 항목 보기'/'관련 목록 열기' 버튼이 항상 숨겨졌다. org.js('조직 관리')와
// platform.js('기능 플래그')는 이미 "감사 로그에서 보기"로 ?object_type=organization /
// ?object_type=feature_flag 딥링크를 감사 화면으로 걸어 두고 있어(org.js organizations.actions,
// platform.js feature-flags.actions) 한쪽 방향 링크만 있고 되돌아오는 버튼이 없었다.
export const OBJ_ROUTE = {
  integration: "#/integrations", runner: "#/runners", workflow: "#/workflows",
  prompts: "#/prompts", policies: "#/policies", template: "#/templates",
  schedule: "#/schedules", schedule_run: "#/schedules", approval: "#/approvals",
  backup: "#/backup", document_generation: "#/documents", document: "#/documents",
  user_notion_mapping: "#/notion-mapping", job: "#/jobs",
  department: "#/departments", job_title: "#/job-titles", user: "#/users",
  app_setting: "#/settings", organization: "#/organizations", feature_flag: "#/feature-flags",
  // organization/feature_flag와 같은 부류(F15) — 백엔드는 이미 이 object_type들로 감사 기록을
  // 남기는데(app/quotas/router.py, app/approvals/router.py의 delegations_router,
  // app/announcements/router.py, app/offboarding/router.py) 이 표에 없어 그 행들만 '관련 항목
  // 보기'/'관련 목록 열기' 버튼이 항상 숨겨졌다(MEGA CYCLE G 조사). 넷 다 단건 GET 엔드포인트가
  // 없어 목록으로만 보낸다(schedule_run과 같은 패턴 — OBJ_ID_PARAM에 없음).
  ai_quota: "#/ai-quotas", approval_delegation: "#/approval-delegations",
  announcement: "#/announcements", offboarding_run: "#/offboarding",
};
// OBJ_ROUTE 대상 화면 중 일부는 App.jsx의 SCREEN_ROLES로 더 좁게 제한된다(예: 사용자·부서·직책은
// admin/system_admin만, 작업 큐는 operator/admin/system_admin만 — auditor 제외). '관련 항목 보기'가
// 그 화면에 못 들어가는 역할에게도 똑같이 노출되면 클릭 즉시 403 막다른 길이 된다 — 여기 없는
// object_type은 대상 화면이 role 제한이 없어(App.jsx SCREEN_ROLES 미지정) 그대로 둔다.
// organization — navConfig.js SCREEN_ROLES.organizations는 admin/system_admin만 허용한다(auditor
// 제외). audit/notifications 화면은 auditor도 들어오므로, 그 게이트 없이는 auditor에게도 '관련
// 목록 열기'가 보여 눌러도 늘 403인 막다른 링크가 된다(위 department/job_title과 동일한 이유).
// feature_flag는 여기 없다 — navConfig.js SCREEN_ROLES["feature-flags"]가 operator/admin/
// system_admin/auditor를 모두 허용해(audit에 들어올 수 있는 역할의 상위집합) 추가 제한이 필요 없다.
// offboarding_run — navConfig.js SCREEN_ROLES.offboarding은 admin/system_admin만 허용한다
// (auditor 제외) — audit 화면(admin/system_admin/auditor)에 들어온 auditor에게도 이 게이트 없이는
// '관련 목록 열기'가 보여 늘 403인 막다른 링크가 된다(department/job_title과 동일한 이유).
export const OBJ_ROUTE_ROLES = { user: WRITE_ROLES, department: WRITE_ROLES, job_title: WRITE_ROLES, job: OPS_ROLES, organization: WRITE_ROLES, offboarding_run: WRITE_ROLES };
export const canReachObjRoute = (objType, role) => !OBJ_ROUTE_ROLES[objType] || (role != null && OBJ_ROUTE_ROLES[objType].includes(role));
// 대상 화면 중 일부는 이제 id 기반 딥링크(onQuery: p.<param> → 상세 드로어를 곧바로 연다)를 지원한다
// (runners: ?id=, jobs: ?job_id=, notion-mapping: ?user_id= — 이 셋은 object_id가 곧 그 파라미터 값).
// workflow/integration/schedule/document_generation도 각 화면이 이제 ?id= 딥링크(onQuery)를 지원해
// 여기 추가한다(runners와 동일한 패턴 — 백엔드 GET .../{id} 단건 조회가 이미 존재함).
// 여기 없는 object_type은 대상 화면에 그런 딥링크가 없어 여전히 목록 전체로만 이동한다.
// document_generation과 document는 둘 다 OBJ_ROUTE에서 같은 문서 화면(#/documents)을 가리키는
// object_type 별칭이다(감사/알림은 'document_generation', 승인의 object_type은 'document') — 문서
// 화면의 onQuery가 둘 다 ?id=를 같은 방식으로 소비하므로 두 별칭 모두 등록해 어느 쪽에서 와도 동작한다.
export const OBJ_ID_PARAM = { runner: "id", job: "job_id", user_notion_mapping: "user_id",
  workflow: "id", integration: "id", schedule: "id", document_generation: "id", document: "id",
  approval: "id", template: "id",
  // prompts/policies는 이름 기준 버전 관리 화면이지만 각 버전 행의 id로도 상세를 곧바로 연다
  // (onQuery: { open: 'select', id }가 GET /{id}로 단건 조회 — nameVersionsAction과 별개 경로).
  // 감사/알림의 '관련 항목 보기'가 이 두 object_type만 빠져 있어 늘 '관련 목록 열기'로 격하됐었다.
  prompts: "id", policies: "id",
  // user — Users.jsx가 NOTI-04R로 ?id= 딥링크(onQuery와 같은 계약: 단건 GET, 목록에 없어도
  // 열림, 실패 시 이유를 알림)를 갖췄다. OBJ_ROUTE_ROLES.user(WRITE_ROLES)가 이미 admin+만
  // 이 경로를 볼 수 있게 막아 둔다.
  user: "id" };
export const objRouteHref = (objType, objId) => {
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
export const RESERVED_EDIT_HINT = " ‘수정’에서 수신 주소, 용도, 담당자, 태그, 모드는 바꿀 수 있지만, 이름(다른 모듈이 계약으로 찾는 식별자)은 이 화면에서 바꿀 수 없습니다, 이름 변경이 꼭 필요하면 시스템 관리자에게 문의하세요.";
export const RESERVED_WORKFLOW_NOTES = {
  "ClovirONE AI 업무 도우미": "이 행은 실제 채팅이 사용하는 수신 주소입니다, 여기서 수신 주소를 바꾸거나 비활성화하면 전 사용자의 채팅이 즉시 멈춥니다(미시딩된 새 설치에서만 서버 기본값으로 대체됩니다). 변경, 비활성화는 반드시 확인 후 진행하세요." + RESERVED_EDIT_HINT,
  "notion-user-mapping": "이 이름은 'Notion 사용자 연결' 화면의 자동 동기화, 검증이 정확히 일치시켜 찾는 식별자입니다. 이름을 바꾸거나 비활성화하면 전 사용자의 Notion 매핑 조회가 조용히 멈추고(오류: 'Notion 매핑 Workflow가 구성/활성화되지 않았습니다'), 자동 동기화도 이 워크플로를 더 이상 찾지 못합니다." + RESERVED_EDIT_HINT,
};
// 위 예약 워크플로는 비활성화가 실제 서비스를 멈춘다 — onoff() 공통 확인 문구 대신 행별 강한 경고를 준다.
export const reservedDisableConfirm = (r) => RESERVED_WORKFLOW_NOTES[r.name]
  ? RESERVED_WORKFLOW_NOTES[r.name] + "\n\n정말 비활성화하시겠습니까?"
  : "비활성화하시겠습니까?";
// 백업 오류는 SQLite/파일시스템 원시 예외 문자열을 그대로 담아 온다 — 알려진 사유 코드만 한국어로
// 치환하고, 그 외(원시 예외 등)는 원문을 그대로 보여준다(정보 손실 방지).
export const BACKUP_REASON_KO = { file_missing: "백업 파일 없음", checksum_mismatch: "체크섬 불일치", database_error: "데이터베이스 오류", integrity_check: "무결성 검사 실패" };
export const backupReasonText = (raw) => {
  if (raw == null || raw === "") return "";
  const s = String(raw);
  const key = Object.keys(BACKUP_REASON_KO).find((k) => s === k || s.startsWith(k + ":") || s.startsWith(k + "="));
  return key ? BACKUP_REASON_KO[key] : s;
};
// 스케줄 실행이 건너뛰어질 때(app/schedules/scheduler.py _record_skip) error_message에 알려진 사유
// 코드를 그대로 담아 온다 — backupReasonText와 동일한 패턴으로 한국어로 치환하고, 그 외(실제 예외
// 메시지 등)는 원문을 그대로 보여준다(정보 손실 방지).
export const SCHED_SKIP_REASON_KO = { misfire_skip: "누락(정책: 건너뛰기)", concurrent_run_active: "이미 실행 중이라 건너뜀" };
export const schedSkipReasonText = (raw) => {
  if (raw == null || raw === "") return "-";
  const s = String(raw);
  return SCHED_SKIP_REASON_KO[s] || s;
};
// 사용자 화면(Users.jsx)의 ROLE_KO와 동일한 5개 역할 라벨 — 승인 화면이 user.role_change 요청의
// request_payload(role/previous_role)를 렌더할 때 raw 값이 아니라 이 라벨을 보여주는 데 쓴다.
export const ROLE_KO = { user: "일반 사용자", operator: "운영자", auditor: "감사자", admin: "관리자", system_admin: "시스템 관리자" };
// 승인 요청 내용(request_payload)의 최상위 키를 한국어로 — 나머지는 온통 한국어인 콘솔에서 이
// 값들만 raw 영어 식별자로 남아 있었다. 알 수 없는 키는 원문 그대로 보여준다(정보 손실 방지).
export const APPROVAL_PAYLOAD_KEY_KO = { role: "역할", previous_role: "이전 역할", target_name: "대상 이름",
  target_email: "대상 이메일", target_user_id: "대상 사용자 ID", source_row_count: "원본 행 수",
  target_parent_page: "대상 페이지", generation_id: "문서 생성 ID", config: "설정", definition: "정의",
  period: "기간", mode: "모드", reason: "사유", comment: "메모" };
