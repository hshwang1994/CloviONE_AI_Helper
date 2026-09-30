/* AI 저작물 — 프롬프트·정책과 그 사용 통계.
 *
 * 버전을 만들고(초안 → 발행 → 보관, D-518) 되돌리는 화면들이 같은 액션 묶음을 공유한다.
 * 사용 통계 두 화면은 그 저작물이 실제로 어디서 쓰였는지를 보는 반대편 창이라 함께 둔다.
 *
 * registry.js 를 쪼갠 조각이다 (E-10). 쪼갠 축은 '줄 수'가 아니라 **관리자가 한 번에
 * 함께 보는 묶음**이다 — 줄 수를 맞추려고 아무 데나 자르면 화면 하나를 고치는 데
 * 파일 셋을 열게 되어 오히려 더 나빠진다.
 *
 * 화면 설정만 있고 그리는 코드는 없다. 그리는 것은 DataScreen.jsx 하나다.
 */
import React from "react";
import Link from "@mui/material/Link";
import { Badge, OBJTYPE_OPTS, WRITE_ROLES, badgeCol, col, dateCol, field, jsonField, opt, truncateCol, writerEmptyHelp } from "./shared.js";
import { nameVersionsAction } from "./actions.js";

// 호출 기록의 결과 배지(D-517). 막힘은 실패와 다른 사실이다 - 제공자에 닿지 않았다.
const USAGE_STATUS_KIND = { ok: "ok", error: "danger", blocked_quota: "warn", blocked_policy: "warn" };

/* 프롬프트 한 줄의 상태 배지(D-518). 발행은 「이 사용처에서 지금 쓴다」는 뜻이라 「사용 중」으로 읽힌다. 기본 제공
   행은 같은 사용처에 발행본이 있으면 쉬고 있다(「대체됨」). */
const PROMPT_STATUS = {
  draft: ["초안", "neutral"], published: ["사용 중", "ok"], archived: ["보관", "neutral"],
};
function promptStatus(r) {
  if (r.status === "builtin") return r.in_use ? ["사용 중", "ok"] : ["대체됨", "neutral"];
  return PROMPT_STATUS[r.status] || [r.status, "neutral"];
}
const PROMPT_SOURCE = { builtin: "기본 제공", admin: "관리자 작성" };
const isBuiltinRow = (r) => r.source === "builtin";
const promptPath = (r) => "/api/admin/prompts/" + r.id;

export const AUTHORING_SCREENS = {
  prompts: {
    smallSet: true, // 저장된 뷰 기준(서버 페이지 + 조건 셋 이상)에 못 미친다(D-506)
    key: "prompts", area: "AI", title: "프롬프트", endpoint: "/api/admin/prompts",
    /* 런타임이 실제로 읽는다(D-518) - 예전 도움말은 「상태만 바꿀 뿐」이라고 적었다. 목록 첫머리가 사용처마다
       기본 제공 지시문이고, 같은 사용처에 발행한 프롬프트가 있으면 다음 호출부터 그것을 쓴다. */
    help: "AI가 기능마다 따르는 지시문입니다. 사용처마다 기본 제공 지시문이 있고, 같은 사용처에 프롬프트를 발행하면 다음 AI 호출부터 발행한 지시문을 씁니다. 안전 규칙과 출력 형식은 따로 붙으므로 바꿀 수 없습니다.",
    emptyTitle: "조건에 맞는 프롬프트가 없습니다",
    emptyHelp: "조건을 지우면 사용처마다 기본 제공 지시문이 보입니다.",
    createLabel: "프롬프트 추가",
    // 다른 화면이 ?id=로 넘겨주는 딥링크를 소비해 그 프롬프트의 상세 드로어를 곧바로 연다(단건 GET).
    // 기본 제공 행의 id(`builtin:answer`)도 같은 문으로 연다(app/prompts/router.py get_one).
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "item",
    // 사용처 수만큼의 기본 제공 행과 관리자가 쓴 버전들이다 - 한 번에 받는다(서버 기본 500건, 그 상한을 알린다).
    capWarning: 500,
    refLists: [{ key: "promptSlots", endpoint: "/api/admin/prompts/slots", valueKey: "key", labelKey: "label" }],
    filters: [
      { key: "slot", type: "select", label: "사용처", optionsFromRefList: "promptSlots" },
      { key: "source", type: "select", label: "출처", options: opt([["builtin", "기본 제공"], ["admin", "관리자 작성"]]) },
      { key: "status", type: "select", label: "상태", options: opt([["draft", "초안"], ["published", "사용 중"], ["archived", "보관"]]) },
    ],
    columns: [
      { ...col("name", "이름", "title"), rowName: (r) => r.name + (r.version ? " v" + r.version : "") },
      { key: "slot_label", label: "사용처", type: "enum", render: (r) => r.slot_label || "정하지 않음" },
      { key: "source", label: "출처", type: "enum", render: (r) => PROMPT_SOURCE[r.source] || r.source },
      { key: "version", label: "버전", type: "code", render: (r) => (r.version == null ? "-" : "v" + r.version) },
      { key: "status", label: "상태", type: "status", render: (r) => { const [value, kind] = promptStatus(r); return React.createElement(Badge, { value, kind }); } },
      { key: "calls_30d", label: "30일 호출", type: "count" },
      dateCol("last_used_at", "마지막 사용"),
    ],
    // 상세에서 지시문과 사용처가 고정한 틀을 함께 읽는다 - 관리자가 바꾸는 것은 지시문 하나다.
    detailFields: [
      field("purpose", "설명"),
      { key: "content", label: "지시문", render: (r) => r.content || "-" },
      { key: "_frame_role", label: "역할 문장(고정)", render: (r) => (r.frame ? r.frame.role : "사용처를 고르면 보입니다.") },
      { key: "_frame_format", label: "출력 형식(고정)", render: (r) => (r.frame ? r.frame.format_line : "사용처를 고르면 보입니다.") },
      { key: "created_by", label: "작성자", render: (r) => (isBuiltinRow(r) ? "기본 제공" : (r.created_by_name || r.created_by_email || r.created_by || "-")) },
      { key: "_edit_note", label: "수정 안내", render: (r) => (isBuiltinRow(r) ? "기본 제공 지시문은 고칠 수 없습니다. ‘복제해서 수정’으로 초안을 만드세요." : (r.status !== "draft" ? "이 버전은 초안이 아니라 고칠 수 없습니다. ‘새 버전’으로 초안을 만드세요." : "-")) },
      dateCol("published_at", "발행 시각"),
      field("id", "프롬프트 ID"),
    ],
    /* 프롬프트는 부서로 나뉘는 자원이 아니다 — 사용처 하나의 발행본을 전 부서가 함께 쓴다. 서버가 생성·수정·발행·
       새 버전·롤백·복제를 전부 전역 범위 관리자로 한정한다(`app/prompts/router.py::_require_global`). */
    create: { roles: WRITE_ROLES, requiresGlobalScope: true, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "slot", label: "사용처", type: "select", required: true, optionsFromRefList: "promptSlots", help: "이 지시문을 쓸 기능입니다. 연결 확인은 고를 수 없습니다." },
      { name: "purpose", label: "설명", type: "textarea" },
      { name: "content", label: "지시문", type: "textarea", required: true, help: "모델에게 주는 지시입니다. 기본 제공 지시문에서 시작하려면 목록의 기본 제공 행에서 ‘복제해서 수정’을 누르세요. 안전 규칙과 출력 형식은 따로 붙습니다." },
    ] },
    // 수정은 초안일 때만 된다(그 밖은 409). 사용처도 초안에서 바꿀 수 있다.
    editMethod: "PATCH", editWhen: (r) => !isBuiltinRow(r) && r.status === "draft", edit: { roles: WRITE_ROLES, requiresGlobalScope: true, fields: [
      { name: "content", label: "지시문", type: "textarea", required: true },
      { name: "slot", label: "사용처", type: "select", required: true, optionsFromRefList: "promptSlots" },
      { name: "purpose", label: "설명", type: "textarea" },
    ] },
    actions: [
      { label: "복제해서 수정", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => isBuiltinRow(r) && r.editable !== false, path: (r) => "/api/admin/prompts/builtin/" + r.slot + "/copy", keepSelection: true },
      { label: "발행", variant: "primary", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => !isBuiltinRow(r) && r.status === "draft", path: (r) => promptPath(r) + "/transition", body: { status: "published" }, confirm: "이 버전을 발행할까요? 다음 AI 호출부터 이 사용처는 이 지시문을 쓰고, 지금 쓰는 발행본은 보관됩니다." },
      // 새 버전은 어떤 상태에서든 새 초안으로 갈라진다. 드로어를 새 초안으로 바꿔 곧바로 고칠 수 있게 한다.
      { label: "새 버전", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => !isBuiltinRow(r) && r.status !== "draft", path: (r) => promptPath(r) + "/new-version", keepSelection: true },
      { ...nameVersionsAction("/api/admin/prompts", "프롬프트 버전 기록"), when: (r) => !isBuiltinRow(r) },
      { label: "보관", variant: "danger", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => !isBuiltinRow(r) && r.status !== "archived", path: (r) => promptPath(r) + "/transition", body: { status: "archived" }, confirm: "이 버전을 보관할까요? 사용 중이던 버전이면 다음 AI 호출부터 기본 제공 지시문을 씁니다." },
      // operator는 프롬프트 화면엔 들어오지만 /audit 화면엔 못 들어간다 — admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], when: (r) => !isBuiltinRow(r), navigate: (r) => "#/audit?object_type=prompts&object_id=" + r.id },
    ],
  },
  policies: {
    /* C2 «Filter Surface 가 정당한가» — 이 화면은 **행 수가 유한하고 작다**(정책 2 ·
       기능 플래그 11 · 통합 4 · RBAC 13 실측). R-88 이 "25행" 을 기계 규칙으로 쓰지 말라고
       못박으므로 숫자가 아니라 **판단**을 남긴다: 조건 조합을 이름 붙여 재사용할 만큼
       탐색이 반복되지 않는다. 그래서 저장된 뷰를 그리지 않는다 — 기능이 아니라 소음이다. */
    smallSet: true,
    key: "policies", area: "AI", title: "정책", endpoint: "/api/admin/policies",
    // 생명주기는 초안 → 발행 → 보관이다(D-518). 발행은 JSON 모양만 검사한다.
    help: "업무 규칙(정책)을 버전으로 관리합니다. 발행하면 이 이름의 발행본이 새 버전으로 바뀌고, 발행할 때는 JSON 모양만 검사합니다.",
    // 발행은 그 순간부터 이 이름의 발행본을 바꾼다 — 프롬프트보다 파급이 크다는 판단은
    // 그대로다. 배너를 일반 안내와 같은 톤으로 두면 그 경고가 안 읽힌다.
    helpTone: "warn",
    emptyTitle: "추가된 정책이 없습니다",
    // 정책도 프롬프트와 동일하게 4단계 생명주기(초안→테스트→검토→발행)를 강제한다 — '등록하고
    // 발행하세요'는 마치 한 단계로 끝나는 것처럼 읽혀, 새 관리자가 초안 행에서 비활성 '발행' 버튼을
    // 만나고 이유를 못 찾았다(프롬프트 registry.js:404와 동일 문구로 맞춘다).
    emptyHelp: writerEmptyHelp("‘+ 정책 추가’로 업무 규칙(JSON)을 넣고 초안에서 발행하세요.", "정책은 관리자가 추가합니다. 추가되면 버전이 여기에 표시됩니다."),
    createLabel: "정책 추가",
    // 다른 화면이 ?id=로 넘겨주는 딥링크를 소비해 그 정책의 상세 드로어를 곧바로
    // 연다(단건 GET). 이 라우터의 GET /{row_id}는 {"item":...} 모양으로
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
    // 🔴 이름 후보는 프롬프트와 **같은 이유로** 받아 둔 행이 아니라 전량 엔드포인트에서 온다
    // (위 프롬프트 항목의 긴 주석 참고 — 서버 필터가 정확 일치라 후보를 못 보면 못 쓰는
    // 필터이고, `/usage/stats` 가 이름당 한 행을 같은 게이트로 무페이징 제공한다).
    refLists: [{ key: "policyNames", endpoint: "/api/admin/policies/usage/stats", valueKey: "name", labelKey: "name" }],
    filters: [{ key: "name", type: "select", kind: "entity", label: "이름", optionsFromRefList: "policyNames" },
      { key: "status", type: "select", label: "상태", value: "published", options: opt([["draft", "초안"], ["published", "발행됨"], ["archived", "보관됨"]]) }],
    // WF1 단독 결함 — purpose는 이제 Policy에도 있다(app/prompts/models.py::Policy.purpose,
    // 마이그레이션 0058). 프롬프트와 동일하게 목록 열로 노출한다 — 여러 버전이 쌓인 목록에서
    // 각 정책이 '무엇을 강제하는지' 행마다 열어보지 않고는 알 수 없었다. purpose는 최대 2000자라
    // truncateCol로 자른다(프롬프트 registry.js:53-54와 동일 패턴, 전체는 title 속성으로 확인).
    columns: [{ ...col("name", "이름"), identifier: true }, truncateCol("purpose", "용도", 60), col("version", "버전", "code"), badgeCol("status", "상태"), dateCol("created_at", "생성 일자")],
    // id는 상세에서 확인할 수 있게 노출한다(라벨은 프롬프트의 '프롬프트 ID'와 맞춰
    // 어느 화면 상세를 보고 있는지 분명히 한다).
    // created_by는 _policy_view가 감사 로그의 actor_name과 동일한 패턴으로 created_by_name/
    // created_by_email을 이미 계산해 돌려준다 — 원시 UUID 대신 그 이름을 보여준다(프롬프트 상세와 동일 패턴).
    // purpose는 이제 목록 열이라 상세에서 중복 제거(프롬프트 registry.js:63과 동일 판단).
    detailFields: [field("id", "정책 ID"),
      { key: "created_by", label: "작성자", render: (r) => r.created_by_name || r.created_by_email || r.created_by || "-" },
      // 초안이 아니면 '수정' 버튼이 통째로 사라진다(editWhen 아래) — 이유를 밝히지 않으면 이 화면을
      // 처음 보는 관리자는 왜 버튼이 없는지 알 방법이 없다. '새 버전'이 실제 대안이라고 안내한다.
      { key: "_edit_note", label: "수정 안내", render: (r) => r.status !== "draft" ? "이 버전은 초안이 아니라 수정할 수 없습니다. 아래 ‘새 버전’으로 수정 가능한 초안을 추가하세요." : "-" },
      dateCol("published_at", "발행 시각"), jsonField("content", "규칙(JSON)")],
    /* 정책도 프롬프트와 같은 문을 지난다(위 프롬프트 create 주석) —
       한 번의 롤백으로 전사 규칙이 바뀌는 자원이라 서버가 쓰기를 전역 범위로 한정한다. */
    create: { roles: WRITE_ROLES, requiresGlobalScope: true, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      // purpose는 서버에서 최대 2000자까지 허용한다(app/prompts/router.py) — 한 줄 text 입력은
      // 좁아서 textarea로(프롬프트 registry.js:70-71과 동일 대우).
      { name: "purpose", label: "용도", type: "textarea" },
      // 서버 기본값("{}")과 맞춘다(app/prompts/router.py PolicyCreateRequest.content) — 값 없이는
      // 다른 registry create 필드처럼 즉시 제출 가능해야 한다(예전엔 최소 "{}"라도 직접 타이핑해야 했다).
      { name: "content", label: "규칙(JSON)", type: "json", required: true, value: '{\n  "required_fields": ["title"]\n}', help: '업무 규칙을 JSON 객체로 적습니다. 위 기본값은 "제목은 필수"라는 뜻의 예시입니다. 필요에 맞게 바꾸세요(예: {"required_fields":["title","owner"],"min_length":10}).' },
    ] },
    editMethod: "PATCH", editWhen: (r) => r.status === "draft", edit: { roles: WRITE_ROLES, requiresGlobalScope: true, fields: [
      { name: "content", label: "규칙(JSON)", type: "json", required: true, help: '예: {"required_fields":["title"]}' },
      { name: "purpose", label: "용도", type: "textarea" },
    ] },
    actions: [
      { label: "발행", variant: "primary", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => r.status === "draft", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "published" }, confirm: "이 버전을 발행할까요? 같은 이름으로 발행돼 있던 버전은 보관됩니다." },
      // keepSelection — 새 버전을 만드는 목적이 '바로 이어서 편집'이므로(내용은 초안일 때만 편집
      // 가능), 프롬프트의 '새 버전'과 동일하게 드로어를 닫지 않고 새 초안으로 갱신한다.
      { label: "새 버전", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => r.status !== "draft", path: (r) => "/api/admin/policies/" + r.id + "/new-version", keepSelection: true },
      // 정책도 프롬프트와 동일하게 버전 기록 + 롤백 + 비교(diff)를 노출한다(잘못 발행된 규칙 복원 경로).
      nameVersionsAction("/api/admin/policies", "정책 버전 기록"),
      { label: "보관", variant: "danger", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => r.status !== "archived", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "archived" }, confirm: "이 버전을 보관할까요? 보관하면 더 이상 발행, 사용되지 않지만 이력으로는 목록에 남습니다." },
      // policies는 감사 로그의 유효한 object_type이고(OBJTYPE_OPTS) 모든 쓰기 액션이 이 타입으로
      // 기록된다 — 부서·직책과 동일한 딥링크를 추가한다.
      // operator는 정책 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=policies&object_id=" + r.id },
    ],
  },
  "prompt-usage": {
    smallSet: true, // 사용처 수만큼의 줄이라 저장된 뷰가 소음이다(D-506)
    key: "prompt-usage", area: "AI", title: "프롬프트 사용 통계",
    endpoint: "/api/admin/prompts/usage/stats",
    /* 예전에는 「이 이름을 참조하는 스케줄이 있는가」를 셌고 언제나 「쓰이지 않음」이었다. 이제 AI 호출 기록에서
       사용처마다 최근 30일을 센다(D-518). */
    help: "사용처마다 지금 쓰는 지시문과 최근 30일의 AI 호출 수, 실패율, 마지막 사용을 봅니다. 수는 AI 호출 기록에서 셉니다.",
    emptyTitle: "사용처가 없습니다",
    emptyHelp: "프롬프트 사용처는 제품이 정합니다. 목록이 비었다면 서버 응답을 확인하세요.",
    columns: [
      { key: "label", label: "사용처", type: "title" },
      { key: "current_name", label: "지금 쓰는 지시문", type: "name", render: (r) => (r.current_source === "admin" ? r.current_name + " v" + r.current_version : "기본 제공") },
      { key: "calls", label: "30일 호출", type: "count" },
      { key: "failure_rate", label: "실패율", type: "percent", render: (r) => (r.failure_rate == null ? "-" : r.failure_rate + "%") },
      dateCol("last_used_at", "마지막 사용"),
    ],
    detailFields: [field("description", "설명"), field("errors", "실패 호출"), field("slot", "사용처 키")],
    actions: [
      { label: "지금 쓰는 지시문 보기", navigate: (r) => "#/prompts?id=" + encodeURIComponent(r.current_id) },
    ],
  },
  "policy-usage": {
    smallSet: true, // 저장된 뷰 기준(서버 페이지 + 조건 셋 이상)에 못 미친다(D-506)
    key: "policy-usage", area: "AI", title: "정책 사용 통계",
    endpoint: "/api/admin/policies/usage/stats",
    help: "정책이 실제로 쓰이고 있는지 이름별로 봅니다. ‘쓰이지 않음’은 이 이름을 참조하는 스케줄이 없다는 뜻입니다.",
    emptyTitle: "추가된 정책이 없습니다",
    emptyHelp: "‘정책’ 화면에서 정책을 추가하면 사용 현황이 여기에 표시됩니다.",
    emptyRelatedLink: { href: "#/policies", label: "정책 화면으로 이동" },
    searchFields: ["name"],
    searchPlaceholder: "정책 이름으로 검색",
    filters: [{ key: "unused", type: "select", label: "사용 여부", clientFilter: true, options: opt([["true", "쓰이지 않음"], ["false", "쓰이는 중"]]) }],
    columns: [
      { ...col("name", "이름"), identifier: true },
      { key: "unused", label: "사용", type: "count", render: (r) => React.createElement(Badge, { value: r.unused ? "쓰이지 않음" : "쓰이는 중", kind: r.unused ? "warn" : "ok" }) },
      { key: "versions", label: "버전 수", type: "count" },
      { key: "published_version", label: "발행 버전", type: "count", render: (r) => r.published_version == null ? "없음" : String(r.published_version) },
      { key: "schedule_refs", label: "스케줄", type: "count" },
    ],
    detailFields: [
      { key: "schedule_names", label: "참조하는 스케줄", render: (r) => (r.schedule_names || []).join(", ") || "없음" },
      { key: "latest_version", label: "최신 버전" },
      badgeCol("latest_status", "최신 상태"),
      dateCol("last_published_at", "마지막 발행"),
    ],
    actions: [
      { label: "이 정책 버전 보기", navigate: (r) => "#/policies?name=" + encodeURIComponent(r.name) },
    ],
    /* 「프롬프트 사용 통계」 머리 단추를 걷었다(D-501) — 이 화면은 언제나 「AI 사용 통계」 그릇의 탭이라 바로 옆
       「프롬프트」 탭이 같은 곳으로 간다. */
  },
  /* AI 사용 통계(계획 3.11, D-517). 예전 「사용 통계」는 이름을 참조하는 스케줄이 있는가를 보여 주는 설정 개요였다 -
     실제 호출은 어디에도 없었다. 이제 AI 런타임이 호출마다 남기는 기록(`ai_usage_records`)을 묶어 본다. 부서 범위
     관리자는 자기 범위 사람의 호출만 본다(서버가 거른다). 본문은 기록되지 않는다. */
  "ai-usage-stats": {
    smallSet: true, // 묶음 결과는 행이 몇 줄이라 저장된 뷰가 소음이다(D-506)
    key: "ai-usage-stats", area: "AI", title: "사용 통계",
    endpoint: "/api/admin/ai/usage/stats",
    help: "기간 안의 AI 호출을 기능, 사용자, 부서, 제공자, 모델, 결과, 날짜로 묶어 봅니다. 성공률은 제공자까지 간 호출 가운데 성공한 비율이고, 한도나 정책으로 막힌 호출은 따로 셉니다.",
    emptyTitle: "아직 AI 호출 기록이 없습니다",
    emptyHelp: "AI 연결을 먼저 설정하세요. 채팅이나 작업 공간에서 AI 를 쓰면 여기에 기록이 쌓입니다.",
    emptyRelatedLink: { href: "#/settings?tab=ai", label: "AI 설정으로 이동" },
    filters: [
      { key: "group_by", type: "select", label: "묶음", value: "action", options: opt([["action", "기능"], ["user", "사용자"], ["department", "부서"], ["provider", "제공자"], ["model", "모델"], ["status", "결과"], ["day", "날짜"]]) },
      { key: "status", type: "select", label: "결과", options: opt([["ok", "성공"], ["error", "실패"], ["blocked_quota", "한도로 막힘"], ["blocked_policy", "정책으로 막힘"]]) },
      { key: "from", type: "date", label: "시작일", group: "other" },
      { key: "to", type: "date", label: "종료일", group: "other" },
    ],
    columns: [
      { key: "label", label: "묶음", type: "title", render: (r) => (r.email ? r.label + " (" + r.email + ")" : r.label) },
      { key: "calls", label: "호출", type: "count" },
      { key: "success_rate", label: "성공률", type: "percent", render: (r) => (r.success_rate == null ? "-" : r.success_rate + "%") },
      { key: "blocked", label: "막힘", type: "count" },
      { key: "input_tokens", label: "입력 토큰", type: "count" },
      { key: "output_tokens", label: "출력 토큰", type: "count" },
      { key: "avg_latency_ms", label: "평균 응답(ms)", type: "number", render: (r) => (r.avg_latency_ms == null ? "-" : String(r.avg_latency_ms)) },
      dateCol("last_at", "마지막 호출"),
    ],
    detailFields: [field("ok", "성공"), field("errors", "실패"), field("blocked", "막힘"), field("key", "묶음 값")],
  },
  "ai-usage-records": {
    key: "ai-usage-records", area: "AI", title: "호출 기록",
    endpoint: "/api/admin/ai/usage/records",
    help: "AI 호출 한 번이 한 줄입니다. 누가, 언제, 어떤 기능으로, 어느 모델에 얼마나 썼고 어떻게 끝났는지만 남기고 질문과 답의 본문은 남기지 않습니다. 기록은 180일 동안 둡니다.",
    emptyTitle: "아직 AI 호출 기록이 없습니다",
    emptyHelp: "AI 연결을 먼저 설정하세요. 채팅이나 작업 공간에서 AI 를 쓰면 여기에 기록이 쌓입니다.",
    emptyRelatedLink: { href: "#/settings?tab=ai", label: "AI 설정으로 이동" },
    paginated: true, pageSize: 50,
    filters: [
      { key: "status", type: "select", label: "결과", options: opt([["ok", "성공"], ["error", "실패"], ["blocked_quota", "한도로 막힘"], ["blocked_policy", "정책으로 막힘"]]) },
      { key: "action", type: "select", label: "기능", options: opt([["chat.answer", "채팅 답변"], ["workspace.ask", "작업 공간 질문"], ["workspace.draft", "작업 공간 문서 초안"], ["report.weekly_summary", "프로젝트 주간 요약"], ["home.narrative", "홈 문장 요약"], ["game.quiz", "게임 퀴즈 만들기"], ["system.connection_test", "연결 확인"]]) },
      { key: "from", type: "date", label: "시작일", group: "other" },
      { key: "to", type: "date", label: "종료일", group: "other" },
    ],
    serverSort: { keys: ["action_key", "created_at", "input_tokens", "latency_ms", "model", "output_tokens", "status"], default: { key: "created_at", dir: "desc" } },
    columns: [
      { ...dateCol("created_at", "시각"), sortable: true, rowName: (r) => (r.action_label || r.action_key) + " / " + (r.user_name || "") },
      { key: "user_name", label: "사용자", type: "name", render: (r) => r.user_name || "-" },
      { key: "action_key", label: "기능", type: "enum", sortable: true, render: (r) => r.action_label || r.action_key },
      { key: "model", label: "모델", type: "identifier", sortable: true, render: (r) => r.model || "-" },
      { key: "status", label: "결과", type: "status", sortable: true, render: (r) => React.createElement(Badge, { value: r.status_label || r.status, kind: USAGE_STATUS_KIND[r.status] || "neutral" }) },
      { key: "input_tokens", label: "입력 토큰", type: "count", sortable: true, render: (r) => (r.input_tokens == null ? "-" : String(r.input_tokens)) },
      { key: "output_tokens", label: "출력 토큰", type: "count", sortable: true, render: (r) => (r.output_tokens == null ? "-" : String(r.output_tokens)) },
      { key: "latency_ms", label: "응답(ms)", type: "number", sortable: true, render: (r) => (r.latency_ms == null ? "-" : String(r.latency_ms)) },
    ],
    detailFields: [
      field("user_email", "이메일"), field("department_name", "부서"), field("provider", "제공자"),
      field("error_code", "실패 코드"), { key: "truncated", label: "잘림", render: (r) => (r.truncated ? "입력이나 출력을 한도에 맞춰 잘랐습니다." : "자르지 않았습니다.") },
      field("id", "기록 ID"),
    ],
  },
};
