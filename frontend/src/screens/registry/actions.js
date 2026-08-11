/* 관리자 설정 화면들이 함께 쓰는 **액션과 폼 조립**. (E-10 로 registry.js 에서 갈라져 나왔다.)
 *
 * 여기 있는 것: 켜기/끄기 같은 공통 액션 묶음, 버전 이력 하위 목록, 헬스·테스트 결과 문구,
 * 문서/템플릿 설정을 폼 필드로 폈다 다시 접는 변환.
 * 여기 없는 것: 값의 한국어 표기와 열 정의 — 그건 shared.js 다.
 *
 * 이 파일의 함수들은 **설정 객체를 만들 뿐** 화면을 그리지 않는다. 그리는 것은 DataScreen 이다.
 * 그 경계를 넘기 시작하면 registry 가 다시 한 덩어리가 된다.
 */
import React from "react";
import { WRITE_ROLES, badgeCol, col, dateCol, opt, personField } from "./shared.js";
// enable/disable 공통 액션(활성 값에 따라 노출) — enable/disable는 쓰기 권한 필요.
// disableConfirm을 넘기면 행별로 다른 확인 문구를 쓴다(예: 워크플로의 예약 행 — 비활성화가 실제
// 서비스를 멈추는 경우 일반 "비활성화하시겠습니까?"보다 강한 경고가 필요하다).
// extraEnableWhen(r) — '활성화' 버튼을 !r.enabled 외에 추가 조건으로도 숨겨야 하는 리소스용(예:
// 스케줄의 실행 시각이 이미 지난 once형 — 눌러도 백엔드가 항상 409 'once 스케줄의 실행 시각이
// 이미 지났습니다'로 거절한다. 눌러도 항상 실패하는 버튼을 애초에 숨긴다).
export const onoff = (base, disableConfirm, extraEnableWhen) => [
  { label: "활성화", variant: "primary", roles: WRITE_ROLES, when: (r) => !r.enabled && (!extraEnableWhen || extraEnableWhen(r)), path: (r) => base + "/" + r.id + "/enable" },
  { label: "비활성화", variant: "danger", roles: WRITE_ROLES, when: (r) => r.enabled, path: (r) => base + "/" + r.id + "/disable", confirm: disableConfirm || "이 항목을 비활성화할까요?" },
];
// 승인 대기가 아닌(종료된) 상태
export const APPROVAL_DONE = ["approved", "rejected", "expired", "cancelled"];
// active 토글 공통(부서·직책) — /enable·/disable 하위경로가 없어 PATCH 본문으로 처리한다.
export const activeToggle = (base) => [
  { label: "활성화", variant: "primary", roles: WRITE_ROLES, when: (r) => !r.active, method: "PATCH", path: (r) => base + "/" + r.id, body: { active: true } },
  // r.user_count가 이미 같은 행 열에 로드돼 있으므로, 실제로 몇 명이 영향을 받는지 확인 문구에 반영한다
  // (0명이든 200명이든 똑같은 경고였다 — 사용 중인 부서/직책을 무심코 끄기 쉬웠다).
  { label: "비활성화", variant: "danger", roles: WRITE_ROLES, when: (r) => r.active, method: "PATCH", path: (r) => base + "/" + r.id, body: { active: false },
    confirm: (r) => r.user_count
      ? "비활성화하면 이 항목을 쓰는 사용자 " + r.user_count + "명이 사용자 폼에서 더 이상 새로 고를 수 없게 됩니다. 계속할까요?"
      : "비활성화하면 사용자 폼에서 새로 고를 수 없게 됩니다. 계속할까요?" },
];
// 사용 여부 필터 공통(부서·직책).
export const ACTIVE_FILTER = [{ key: "active", type: "select", label: "사용", options: opt([["true", "사용 중"], ["false", "미사용"]]) }];

/* 상위 부서 — 조직도를 실제로 만들 수 있게 하는 필드.
 *
 * 백엔드는 처음부터 parent_id 를 받았고(0024 가 departments.parent_id 를 만들었다,
 * app/org/schemas.py 도 받는다) 조직도 화면은 "상위 부서는 '부서 관리' 화면에서 지정합니다"라고
 * 안내하고 있었다. 그런데 **그 화면에 그 필드가 없었다** — 안내문이 거짓말이었고, 트리는
 * CLI 나 API 를 직접 두드려야만 만들 수 있었다.
 *
 * 후보에서 자기 자신은 뺀다(자기 부모가 될 수 없다). 하위 부서를 부모로 고르는 순환은
 * 백엔드(app/org/tree.py::validate_parent)가 거절하므로 여기서 다시 계산하지 않는다 —
 * 같은 규칙을 두 곳에 두면 반드시 어긋난다.
 */
export const PARENT_DEPT_FIELD = {
  name: "parent_id",
  label: "상위 부서",
  type: "select",
  value: "",
  help: "비우면 최상위 부서가 됩니다. 하위 부서를 상위로 고르면 순환이 되어 저장되지 않습니다.",
  optionsFrom: (row, rows) => opt([
    ["", "(최상위)"],
    ...(rows || [])
      .filter((d) => !row || d.id !== row.id)
      .map((d) => [d.id, d.name]),
  ]),
};
// 버전 스냅샷 열 — 각 버전 행의 config 스냅샷(r.snapshot)에서 값을 읽어 보여준다(롤백 전 내용 확인).
export const snapCol = (key, label, map) => ({ key: "snap_" + key, label, render: (r) => {
  const v = r.snapshot ? r.snapshot[key] : undefined;
  if (v == null || v === "") return "-";
  return map ? (map[v] || String(v)) : String(v);
} });
// 버전 기록·롤백 공통 액션(config-versioned 리소스: 연동·러너·워크플로).
// extraCols: 스냅샷에서 뽑아 보여줄 추가 열(base_url/auth_type/enabled 등) — 블라인드 롤백 방지.
// confirmFn(sub, parent) — 기본 확인 문구를 행별로 강화해야 하는 리소스(예: 워크플로의 예약 행)를
// 위한 선택적 오버라이드. DataScreen.jsx의 SubListDrawer.act()가 confirm을 (하위 행, 부모 행) 두
// 인자로 호출하므로 parent(부모 행)를 읽어 경고 문구를 만들 수 있다.
// namedCreator — RG-07: 셋 다 "변경자"를 쓰지만 이름을 실제로 주는 건 워크플로뿐이다(연동·러너의
// /versions는 정말 이름을 안 준다, app/{integrations,runners}/router.py 확인함) — 그래서
// personField를 기본으로 못 켠다. 이름을 주는 쪽만 true로 켠다.
export const versionsAction = (base, extraCols, confirmFn, namedCreator) => ({
  label: "버전 기록",
  subList: {
    title: "버전 기록",
    endpoint: (r) => base + "/" + r.id + "/versions",
    columns: [col("version", "버전"),
      namedCreator ? personField("created_by", "변경자", "created_by_name", "created_by_email") : col("created_by", "변경자 ID"),
      dateCol("created_at", "시각"), ...(extraCols || [])],
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
export const nameVersionsAction = (base, title) => ({
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
export const healthResult = (res) => ({ ok: res.status === "up", msg: (res.status === "up" ? "정상" + (res.latency_ms != null ? ` (${res.latency_ms}ms)` : "") : "중단: " + (res.detail || "확인 실패")) + (res.checked_url ? " (" + res.checked_url + ")" : "") });
// '테스트'는 연결 확인일 뿐, 러너가 실제로 작업을 받을 수 있는지(can_dispatch)와는 별개다 —
// 백엔드가 의도적으로 비활성/점검 상태 러너도 테스트만은 통과시킨다(새 러너를 켜기 전에 미리
// 확인할 수 있게). 통과 문구가 '작업이 실제로 배분된다'는 뜻으로 오해되지 않게 구분해 둔다.
// 백엔드 POST /{id}/test(app/runners/router.py)는 {ok, status_code}만 돌려주고 status 필드는 절대
// 주지 않는다 — res.status 검사는 항상 undefined라 사실상 죽은 코드였다. res.ok만으로 판정한다.
export const testResult = (res) => ({ ok: res.ok !== false, msg: (res.ok !== false) ? "테스트 통과(연결 확인됨), 비활성/점검 상태면 실제 작업은 배분되지 않습니다." : "테스트 실패: " + (res.detail || ("HTTP " + (res.status_code || "?"))) });
// 워크플로 '테스트'는 GET 도달성만 확인한다(실제 실행/POST 검증 아님) — 통과를 과장하지 않게 문구를 분리한다.
// 백엔드 provider_n8n.test()는 'reachable'/'unreachable'만 반환한다(ok/failed 필드 없음) — healthResult처럼
// 정확 일치로 판정해야 timeout/connection_refused('unreachable')가 올바로 '연결 실패'로 표시된다.
export const reachResult = (res) => { const ok = res.status === "reachable"; return { ok, msg: ok ? "연결 확인됨(도달 가능)" : "연결 실패: " + (res.detail || res.status || ("HTTP " + (res.status_code || "?"))) }; };

// 문서 생성 폼 필드 — '+ 문서 생성' 헤더 작업과 실패/품질미달 행의 '재시도' 행 작업이 공유한다
// (재시도는 같은 폼을 워크플로/모드/설정은 물려받고 기간만 비운 채로 다시 연다).
// 문서 생성 폼 — 예전엔 config 전체를 raw JSON으로 손수 적게 해 무슨 키를 넣어야 할지 알기 어려웠다.
// 실제로 백엔드(app/documents/service.py)가 읽는 키를 명명 입력으로 펼치고, 그 외 드문 키만 '고급(JSON)'
// 하나로 남긴다. 제출 시 docConfigTransform이 이들을 다시 config dict로 조립한다(백엔드 계약 유지).
export const DOC_GENERATE_FIELDS = [
  // DGEN-01: 자유 텍스트 ID 받아쓰기 대신 이름으로 고른다 — documents 화면의 config.refLists
  // (registry/automation.js)가 이 화면에 로드된 워크플로/템플릿 목록을 DataScreen.jsx의
  // withOptionsFrom을 통해 select 옵션으로 준다.
  { name: "workflow_id", label: "워크플로", type: "select", required: true, optionsFromRefList: "workflows", help: "생성을 실행할 워크플로. ‘업무 자동화 흐름(워크플로)’ 화면에서 등록·활성화합니다." },
  { name: "period", label: "기간", type: "text", required: true, help: "예: 2026-07 또는 2026-W29 (문서가 다룰 기간)" },
  { name: "mode", label: "모드", type: "select", value: "preview_then_approve", options: opt([["preview_then_approve", "미리보기 후 승인"], ["preview_only", "미리보기만"], ["auto_publish", "자동 발행"]]), help: "‘자동 발행’이라도 대상 워크플로/템플릿이 승인을 요구하면 미리보기 후 승인 흐름으로 전환됩니다." },
  { name: "template_id", label: "템플릿(선택)", type: "select", optionsFromRefList: "templates", extraOptions: [{ value: "", label: "(템플릿 없음)" }], help: "고르면 그 템플릿의 프롬프트, 정책, 기본값이 함께 적용됩니다." },
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
export const _DOC_STR_KEYS = ["template_id", "source_database", "output_format", "title_rule", "target_parent_page", "target_database"];
export function docConfigTransform(body) {
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
export function docConfigInitial({ workflow_id = "", mode = "preview_then_approve", config = {}, period = "" } = {}) {
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
export const docGenerateResult = () => ({ ok: true, msg: "문서 생성을 요청했습니다(진행 중). 잠시 후 목록이 자동으로 새로고침됩니다." });

// 템플릿의 '문서 생성 기본값(input_schema)'도 raw JSON이었다 — 문서 생성 폼과 같은 방식으로 명명
// 필드로 펼친다(템플릿은 재사용 기본값이라 template_id·기간·모드는 없다). toApiBody/fromRow가 input_schema
// dict와 상호 변환한다.
export const _TPL_STR_KEYS = ["source_database", "output_format", "title_rule", "target_parent_page", "target_database"];
export const TEMPLATE_SCHEMA_FIELDS = [
  { name: "source_database", label: "원본 Notion DB(선택)", type: "text", help: "이 템플릿으로 만드는 문서가 데이터를 읽어올 Notion 데이터베이스 ID(또는 이름). 문서 생성 시 기본값으로 채워집니다." },
  { name: "output_format", label: "출력 형식", type: "select", value: "", options: opt([["", "(기본: 마크다운)"], ["markdown", "마크다운"], ["html", "HTML"]]) },
  { name: "title_rule", label: "제목 규칙(선택)", type: "text", help: "생성 문서 제목 규칙. 예: 주간 보고서 {week}" },
  { name: "target_parent_page", label: "발행 위치: 상위 페이지 ID(선택)", type: "text", help: "생성된 문서를 붙일 Notion 상위 페이지 ID." },
  { name: "target_database", label: "발행 위치: DB ID(선택)", type: "text", help: "생성된 문서를 추가할 Notion 데이터베이스 ID." },
  { name: "input_schema_extra", label: "고급 기본값(JSON, 선택)", type: "json", jsonObject: true, help: '위에 없는 키(filter, grouping, prompt_template 등)를 직접 넣습니다. 같은 키가 있으면 이 값이 우선합니다.' },
];
export function assembleInputSchema(body) {
  const named = { source_database: body.source_database, output_format: body.output_format, title_rule: body.title_rule, target_parent_page: body.target_parent_page, target_database: body.target_database };
  const schema = {};
  _TPL_STR_KEYS.forEach((k) => { const v = named[k]; if (v != null && String(v).trim() !== "") schema[k] = v; });
  if (body.input_schema_extra && typeof body.input_schema_extra === "object" && !Array.isArray(body.input_schema_extra)) Object.assign(schema, body.input_schema_extra);
  return schema;
}
export function disassembleInputSchema(is) {
  const s = is || {};
  const extra = {};
  Object.keys(s).forEach((k) => { if (!_TPL_STR_KEYS.includes(k)) extra[k] = s[k]; });
  const out = { source_database: s.source_database || "", output_format: s.output_format || "", title_rule: s.title_rule || "", target_parent_page: s.target_parent_page || "", target_database: s.target_database || "" };
  if (Object.keys(extra).length) out.input_schema_extra = extra;
  return out;
}

