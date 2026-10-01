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
export { badgeCol, boolCol, mapCol, dateCol, jsonField, objectField, readCol, linkCol, listField, previewField, activeCol, enabledCol, truncateCol } from "../DataScreen.jsx";
export { objKo, actionKo, fmtDateTime, fmtDateTimeCompact, TYPE_KO } from "../../lib/format.js";
export { Badge } from "../../ui/kit.jsx";
import { objKo, actionKo, fmtDateTime, TYPE_KO } from "../../lib/format.js";
import { CONSOLE_OPS_ROLES, CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES } from "../../lib/roles.js";

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
/* 감사 로그 「대상」 필터의 선택지.
 *
 * **값은 백엔드가 실제로 저장하는 `object_type` 문자열과 정확히 같아야 한다** — 백엔드가
 * `==` 정확 일치로 거르므로 한 글자만 어긋나도 그 선택지는 언제나 0건이다. 그리고 닫힌
 * 선택지라면 「고를 수 있는 것」과 「기록되는 것」이 같아야 한다.
 *
 * 예전에는 둘 다 틀렸다(xe-03 실측):
 *   * 「문서」라는 이름표가 `document_generation` 에 붙어 있었다 — 그 값을 쓰는 코드는
 *     저장소에 하나도 없고, 실제 문서 기록은 `document` 다. 「문서」를 고른 관리자는
 *     문서 감사 기록 3건을 눈앞에 두고 「검색 결과가 없습니다」를 봤다.
 *   * 반대로 이 설치가 실제로 기록 중인 `board_post`·`document`·`llm_config`·`notion_task`
 *     는 목록에 아예 없어서, 주소창에 손으로 `?object_type=…` 을 적어야만 볼 수 있었다.
 *
 * 아래 목록은 `app/` 의 `record_audit*(object_type=…)` 호출 전량과 맞춘다(관측 이벤트
 * `record_usage` 는 감사 로그가 아니라 뺀다 — `object_type="ai"` 가 그것이다).
 * 마지막 묶음은 **없어진 기능의 옛 기록**이다: 새로 만들 수는 없지만 지난 기록이 남아 있어
 * 고를 수는 있어야 한다(필터는 역사도 봐야 한다). 그 사실을 이름표에 적어 둔다 — 안 적으면
 * 「골랐는데 늘 0건」이 결함으로 보인다. */
export const OBJTYPE_OPTS = [
  // 사람·권한·조직
  ["user", "사용자"], ["department", "부서"], ["job_title", "직책"], ["organization", "조직"],
  ["session", "로그인 세션"], ["approval", "승인"], ["approval_delegation", "승인 위임"],
  ["offboarding_run", "오프보딩"],
  // 업무
  ["notion_task", "티켓"], ["ticket", "티켓 연결과 보드"], ["ticket_comment", "티켓 댓글"],
  ["ticket_attachment", "티켓 첨부"], ["project", "프로젝트"], ["project_milestone", "프로젝트 마일스톤"],
  ["sprint", "스프린트"], ["sprint_decision", "스프린트 결정"],
  // 문서·지식
  ["document", "문서"], ["knowledge_document", "문서 첨부"], ["knowledge_space", "지식 공간"],
  ["document_template", "문서 서식"], ["document_comment", "문서 댓글"],
  ["document_category", "문서 분류"], ["tag", "태그"], ["notion_document", "팀 문서"],
  // 게시판·대화
  ["board_post", "게시글"], ["board_comment", "게시글 댓글"], ["board_attachment", "게시글 첨부"],
  ["chat_room", "채팅방"],
  // 시스템·운영
  ["app_setting", "설정"], ["system_setting", "서버 설정"], ["secret", "비밀 값"], ["feature_flag", "기능 플래그"],
  ["llm_config", "AI 모델 설정(옛 기능)"], ["ai_config", "AI 설정"], ["ai_quota", "AI 사용 한도"], ["announcement", "공지 배너"],
  ["prompts", "프롬프트"], ["policies", "정책"], ["ai_action_request", "AI 초안"],
  ["schedule", "스케줄"], ["schedule_run", "예약 실행"], ["job", "작업"],
  ["backup", "백업"], ["storage_provider", "파일 저장소"], ["mail_delivery", "메일 발송"],
  ["mail_settings", "메일 설정"], ["integrity_check", "조직 정합성 검사"],
  ["search_index", "검색 색인"], ["integration", "외부 연동"],
  // 첫 관리자 설정 코드(D-522). 틀린 코드로 코드가 폐기된 일이 이 이름으로 남는다.
  ["setup", "초기 설정"],
  // 없어진 기능의 옛 기록 — 새로 쌓이지 않는다.
  ["runner", "러너(옛 기능)"], ["workflow", "워크플로(옛 기능)"], ["template", "템플릿(옛 기능)"],
  ["document_generation", "문서 생성(옛 기능)"], ["user_notion_mapping", "Notion 연결(옛 기능)"],
].map((p) => ({ value: p[0], label: p[1] }));

/** 감사 대상 종류의 한국어 이름표 — 위 선택지와 **같은 한 벌**이다.
 *  필터에서 고를 수 있는 이름과 표에 찍히는 이름이 갈라지면, 고른 것과 보이는 것이 다른
 *  낱말이 된다. `lib/format.js` 의 공용 사전이 먼저이고, 그 사전이 모르는 값만 여기서 받는다. */
export const OBJTYPE_KO = Object.fromEntries(OBJTYPE_OPTS.map((o) => [o.value, o.label]));
/* 상세 패널의 평문 필드. **열이 아니다** — 정렬 규칙이 없으므로 `type` 을 안 받는다.
   열을 만들 때는 아래 `col(key, label, type)` 을 쓴다. */
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
  // 사람 이름은 **읽는 것**이다 — 길이가 제각각이라 왼쪽 모서리가 맞아야 눈이 다음 줄로
  // 내려간다(`ui/columnTypes.js`). 상세 필드로 쓰일 때는 이 값이 무시된다.
  key: idKey, label, type: "name",
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
/** 감사 대상 종류를 한국어로. **필터가 쓰는 말이 먼저다** — 위 `OBJTYPE_KO` 가 아는 값은
 *  그 이름표를 쓰고, 모르는 값만 `lib/format.js` 의 공용 사전(`objKo`)으로 받는다. 둘 다
 *  모르면 원문을 그대로 둔다(정보 손실 방지). 예전에는 감사 로그의 절반 넘는 대상이
 *  `board_post` 처럼 영문 슬러그로 남았다 — 온통 한국어인 표에서 그 칸만 못 읽혔다.
 *
 *  🔴 순서가 반대였다. 공용 사전을 먼저 보면 그 사전이 아는 값에서는 **필터의 이름표가
 *  절대 이기지 못한다** — 그래서 「대상」 드롭다운과 표의 「대상」 칸이 일곱 값에서 서로
 *  다른 낱말을 말했다. 가장 나쁜 것이 `document_generation` 이다: 드롭다운은 「문서
 *  생성(옛 기능)」이라고 적어 두고 표는 「문서」라고 찍어, 진짜 `document` 행과 눈으로
 *  가를 수 없었다. 고른 이름과 보이는 이름은 같은 낱말이어야 한다. */
export const objTypeKo = (v) => {
  if (v == null || v === "") return "-";
  return OBJTYPE_KO[v] || objKo(v);
};
export const objField = (key, label) => ({ key, label, type: "enum", render: (r) => objTypeKo(r[key]) });

/* 목록 화면 설정 — 열/엔드포인트만 다르고 렌더는 DataScreen이 공통 처리한다.
 * 상태 열은 badgeCol(배지), enum 열은 mapCol/actionKo(한국어)로. 값은 서버 계약 그대로. */
// 옛 행이 raw 슬러그로 보이지 않게 이름표는 남긴다 — 이 둘을 **새로 만드는 경로는 없다**
// (S20). 그 시스템들이 제품에서 없어졌고, 고를 것이 하나뿐인 선택기는 고를 것이 없는
// 선택기라 유형 입력 자체를 내렸다. 목록의 열은 남는다: 옛 행이 그 값을 들고 있고, 열이
// 없어지면 그 행이 무엇인지 화면에서 사라진다.
export const PROVIDER = {
  http_service: "HTTP 서비스", notion: "Notion(옛 방식)", n8n: "n8n(옛 방식)",
};
export const SCHED_TYPE = { cron: "Cron 반복", once: "1회 실행" };
// 실제 enqueue되는 job_type 문자열과 정확히 일치해야 한다. 큐에 안 들어가는 것은 안 적는다
// (backup 은 큐에 없어서, document_generate·notion_mapping_sync 는 S11 이 걷어내서 — 오해 방지).
export const JOB_TYPE = { chat_message: "채팅 메시지", schedule_run: "예약 실행", mail_send: "메일 발송" };

// 감사/승인 enum 한국어화는 공용 lib/format.js(objKo·actionKo)에서 온다.
/* 감사 대상 종류. **닫힌 집합**이라 `enum` 이다 — 짧고 폭이 고정된 값이라 칸 가운데에
   서면 열이 하나의 띠로 읽힌다(`ui/columnTypes.js` 의 그 규칙). */
export const objCol = (key, label, type = "enum") => ({ key, label, type, render: (r) => objTypeKo(r[key]) });
// title 속성으로 원문 action 문자열을 마우스 오버 시 보여준다 — 감사 로그의 '작업' 필터는 이
// 원문과 정확히 일치해야 하는데(정확 일치 필터), 열은 한국어 번역만 보여줘서 필터에 뭘 입력해야
// 할지 목록만 보고는 알 방법이 없었다(truncateCol이 이미 쓰는 title 힌트 패턴과 동일).
export const actionCol = (key, label, type = "enum") => ({ key, label, type, render: (r) => React.createElement("span", { title: r[key] }, actionKo(r[key])) });

/* 열 하나. **`type` 은 선택이 아니다.**
 *
 * 예전에는 `{key, label}` 만 만들었고, 그 열은 어휘의 `UNTYPED`(왼쪽 정렬 + 4.5rem 바닥)로
 * 떨어졌다. 그래서 같은 표 안에서 날짜 하나는 가운데, 다른 날짜는 왼쪽에 서는 일이 실제로
 * 있었다(`/users` 의 「생성 일자」와 「최근 로그인」). 기본값을 두면 그 실수가 조용히
 * 지나가므로 기본값을 안 준다 — `scripts/check_column_types.py` 가 빠진 자리를 잡는다. */
export const col = (key, label, type) => ({ key, label, type });
export const opt = (pairs) => pairs.map((p) => ({ value: p[0], label: p[1] }));
// 백엔드 허용값과 정확히 일치해야 한다(none/bearer/api_key_header) — 옛 header/basic은 422였다.
export const AUTH_OPTS = opt([["none", "없음"], ["bearer", "Bearer 토큰"], ["api_key_header", "API 키(헤더)"]]);
// 워크플로 백엔드는 POST/GET만 허용한다(WorkflowConfig._method_known).
export const SCHEDT_OPTS = opt([["cron", "Cron 반복"], ["once", "1회 실행"]]);
// 간편 주기 — 고르면 백엔드가 Cron 식을 생성한다(cron.PRESETS). 빈 값은 '직접 입력'.
export const SCHED_PRESET_OPTS = opt([["", "사용 안 함(직접 입력)"], ["daily", "매일"], ["weekly", "매주"], ["monthly", "매월"]]);
// 스케줄 고급 정책 — 백엔드 허용값과 정확히 일치(misfire: skip/run_once, concurrency: skip/allow).
export const MISFIRE_OPTS = opt([["skip", "건너뛰기(skip)"], ["run_once", "한 번만 실행(run_once)"]]);
export const CONCURRENCY_OPTS = opt([["skip", "건너뛰기(skip)"], ["allow", "동시 실행 허용(allow)"]]);
// 대상은 시스템 하나뿐이다 — 워크플로 대상은 S11 이 n8n 과 함께 걷어냈다.
export const SCHED_TARGET_OPTS = opt([["system", "시스템"]]);
// 상태 변경(쓰기) 액션 role 게이트 — 백엔드 RBAC와 일치시켜 읽기 전용 역할(operator/auditor)에게
// 항상 403이 되는 버튼을 애초에 숨긴다(DataScreen canDo가 a.roles로 필터).
export const WRITE_ROLES = CONSOLE_WRITE_ROLES;                  // 생성/수정/onoff/발행/롤백/승인·거절/동기화 등
export const OPS_ROLES = CONSOLE_OPS_ROLES;                      // 운영성 액션(헬스/테스트/지금 실행/작업 재시도·취소 등)
// 관리 콘솔 역할(일반 사용자 role=user 제외) — 알림의 '관련 항목 보기'처럼 관리자 해시 경로로만
// 이동하는 액션을 일반 사용자에게 숨긴다(일반 사용자가 누르면 채팅으로 튕겨 나간다).
export const ADMIN_VIEW_ROLES = CONSOLE_READ_ROLES;
// 생성 권한이 없는 역할(operator/auditor)에게는 렌더되지도 않는 '추가' 버튼을 누르라고 안내하지 않는다.
// 쓰기 역할(admin/system_admin)에겐 CTA 안내를, 그 외엔 읽기 전용 안내를 준다(schedules/backup 패턴).
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
  // `integration: "#/integrations"` 가 있었다 — 그 화면을 걷으면서 함께 지운다.
  // 남은 감사 기록은 그대로 보이고, 「관련 목록 열기」 단추만 안 붙는다.
  prompts: "#/prompts", policies: "#/policies",
  schedule: "#/schedules", schedule_run: "#/schedules", approval: "#/approvals",
  backup: "#/backup",
  job: "#/jobs",
  department: "#/departments", job_title: "#/job-titles", user: "#/users",
  app_setting: "#/settings", organization: "#/organizations", feature_flag: "#/feature-flags",
  // organization/feature_flag와 같은 부류(F15) — 백엔드는 이미 이 object_type들로 감사 기록을
  // 남기는데(app/quotas/router.py, app/approvals/router.py의 delegations_router,
  // app/announcements/router.py, app/offboarding/router.py) 이 표에 없어 그 행들만 '관련 항목
  // 보기'/'관련 목록 열기' 버튼이 항상 숨겨졌다(MEGA CYCLE G 조사). 넷 다 단건 GET 엔드포인트가
  // 없어 목록으로만 보낸다(schedule_run과 같은 패턴 — OBJ_ID_PARAM에 없음).
  ai_quota: "#/ai-quotas", approval_delegation: "#/approval-delegations",
  announcement: "#/announcements", offboarding_run: "#/offboarding",
  /* 감사 기록은 남는데 돌아갈 화면이 없던 셋(xe-10). 셋 다 관리 콘솔에 실재하는 주소다 —
     설정은 탭이 `?tab=` 이고(AdminRoutes 의 옛 주소 리다이렉트가 같은 값을 쓴다), 메일은
     자기 화면이 있다. 단건 딥링크는 없으므로 `OBJ_ID_PARAM` 에는 안 넣는다(목록까지만
     보낸다 — `schedule_run` 과 같은 대접).
     🔴 「화면 역할이 `CONSOLE_READ` 라 게이트가 필요 없다」고 적혀 있었는데 그것은 `#/mail`
     에만 맞다. 설정 화면은 `CONSOLE_READ` 지만 **탭이 더 좁다** — `SettingsShell.jsx` 의
     `storage`·`ai` 탭은 `system_admin` 전용이라, 감사자·운영자·일반 관리자가 그 주소로
     가면 「대시보드로 이동」만 있는 거부 화면을 본다. 좁은 것은 화면이 아니라 탭이므로
     아래 `OBJ_ROUTE_ROLES` 에 그 둘을 적는다. */
  storage_provider: "#/settings?tab=storage", llm_config: "#/ai-connection", ai_config: "#/ai-connection",
  mail_delivery: "#/mail", mail_settings: "#/mail",
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
// job 은 읽기(`GET /api/admin/jobs*`)가 `CONSOLE_READ_ROLES` 라 감사자도 딥링크가 산다 —
// 재시도·취소 단추는 그 화면의 액션이 따로 `OPS_ROLES` 로 막는다(automation.js).
// storage_provider·llm_config — 좁은 것이 **화면이 아니라 탭**이다. 설정 화면 자체는
// `CONSOLE_READ` 지만 `SettingsShell.jsx` 의 `storage`·`ai` 탭은 `system_admin` 전용이라,
// 그 밖의 역할이 이 딥링크를 누르면 탭 대신 거부 안내를 본다(department/job_title 과
// 같은 막다른 링크다). 서버도 같은 자리에서 좁힌다 — `STORAGE_CONFIGURE` 는
// `SYSTEM_ADMIN_ONLY` 다(app/authz/permissions.py).
export const OBJ_ROUTE_ROLES = { user: WRITE_ROLES, department: WRITE_ROLES, job_title: WRITE_ROLES, job: ADMIN_VIEW_ROLES, organization: WRITE_ROLES, offboarding_run: WRITE_ROLES,
  storage_provider: ["system_admin"], llm_config: ["system_admin"], ai_config: ["system_admin"] };
/* 관리 콘솔의 사람 후보 목록 — 승인·위임·감사·대리 보기·AI 상한이 같은 것을 쓴다.
 *
 * 경로가 `/api/admin/people` 인 이유: 그 다섯 화면은 운영자·감사자도 여는데 `/api/admin/users`
 * 는 사용자 관리 권한(admin 이상)이라, 그 역할은 화면을 열 때마다 403 을 맞고 사람 필터가
 * 비어 있었다. `people` 은 신원 조각(id·이름·이메일·활성·보관·부서명)만 싣는 읽기 전용
 * 경로다(`app/users/people_router.py`). 보관된 사람도 실려 온다 — 감사 로그와 승인 이력은
 * 퇴사한 사람을 계속 가리키므로 후보에서 빼면 옛 기록을 고를 수 없다. */
export const PEOPLE_REF_LIST = { key: "people", endpoint: "/api/admin/people", labelKey: "display_name", secondaryKey: "email" };
/* **만드는 폼**의 사람 후보 — 보관된 계정은 뺀다 (xb-10).
 *
 * 위 `PEOPLE_REF_LIST` 가 보관된 사람까지 싣는 이유는 옛 기록을 **거르기** 위해서다(감사
 * 로그의 행위자, 대리 보기 이력). 앞으로 일어날 일을 **만드는** 자리는 반대다: 퇴사해서
 * 보관한 계정에 AI 사용 상한을 걸거나 그 사람에게 결재를 위임하는 것은 아무 뜻이 없고,
 * 위임은 서버가 422 로 거절하기까지 한다 — 폼이 반드시 실패하는 선택지를 권한 셈이다.
 * 서버가 그 축을 이미 받는다(`app/users/people_router.py` 의 `include_archived`).
 *
 * 필터와 폼이 한 화면에서 서로 다른 후보를 봐야 하는 화면(대리 보기)은 아직 이 목록을
 * 안 쓴다 — `refLists` 는 화면당 한 벌이고, 그 화면은 필터가 옛 기록을 가리키기 때문이다. */
export const PEOPLE_ACTIVE_REF_LIST = { key: "people", endpoint: "/api/admin/people?include_archived=false", labelKey: "display_name", secondaryKey: "email" };
export const canReachObjRoute = (objType, role) => !OBJ_ROUTE_ROLES[objType] || (role != null && OBJ_ROUTE_ROLES[objType].includes(role));
// 대상 화면 중 일부는 이제 id 기반 딥링크(onQuery: p.<param> → 상세 드로어를 곧바로 연다)를 지원한다
// (jobs: ?job_id= — object_id가 곧 그 파라미터 값).
// integration/schedule도 각 화면이 ?id= 딥링크(onQuery)를 지원해 여기 있다(백엔드 GET .../{id}
// 단건 조회가 이미 존재한다). 여기 없는 object_type은 대상 화면에 그런 딥링크가 없어 여전히
// 목록 전체로만 이동한다.
export const OBJ_ID_PARAM = { job: "job_id",
  integration: "id", schedule: "id", approval: "id",
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
// 백업 오류는 SQLite/파일시스템 원시 예외 문자열을 그대로 담아 온다 — 알려진 사유 코드만 한국어로
// 치환하고, 그 외(원시 예외 등)는 원문을 그대로 보여준다(정보 손실 방지).
export const BACKUP_REASON_KO = { file_missing: "백업 파일 없음", checksum_mismatch: "체크섬 불일치", database_error: "데이터베이스 오류", integrity_check: "무결성 검사 실패", set_missing: "백업 세트를 찾을 수 없음", checksums_missing: "체크섬 파일 없음", set_modified: "백업 세트가 만든 뒤에 바뀜", file_removed: "서버에서 삭제한 백업" };
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
  target_email: "대상 이메일", target_user_id: "대상 사용자 ID",
  config: "설정", definition: "정의",
  period: "기간", mode: "모드", reason: "사유", comment: "메모" };
