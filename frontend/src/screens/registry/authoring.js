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

/* 정책(계획 3.9, D-519). 종류마다 규칙 칸이 정해져 있고, 폼은 JSON 대신 그 칸을 보인다. 서버가 같은 규칙으로 다시
   검사한다(`app/ai/policy/schemas.py`) - 화면은 칸을 모아 보낼 뿐이다. */
const POLICY_KINDS = [["approval", "쓰기 승인"], ["data_protection", "개인정보 가리기"], ["content", "응답 제한"]];
const POLICY_KIND_LABEL = { approval: "쓰기 승인", data_protection: "개인정보 가리기", content: "응답 제한", legacy: "옛 형식" };
// 서버의 액션 이름과 같은 표다(`app/ai/actions.py`). 쓰기 승인은 결과가 저장되는 기능에만 건다.
const POLICY_TARGETS = [["*", "모든 기능"], ["chat.answer", "채팅 답변"], ["workspace.ask", "작업 공간 질문"],
  ["workspace.draft", "작업 공간 문서 초안"], ["report.weekly_summary", "프로젝트 주간 요약"], ["home.narrative", "홈 문장 요약"],
  ["game.quiz", "게임 퀴즈 만들기"]];
const WRITE_TARGETS = [["workspace.draft", "작업 공간 문서 초안"]];
const AUTO_ROLES = [["auto_system_admin", "system_admin", "시스템 관리자는 승인 없이 저장합니다"],
  ["auto_admin", "admin", "관리자는 승인 없이 저장합니다"], ["auto_operator", "operator", "운영자는 승인 없이 저장합니다"]];
const RULE_FIELDS = {
  approval: [
    { name: "write_requires_approval", type: "checkbox", label: "승인", checkLabel: "문서로 저장하기 전에 승인을 받습니다", value: true },
    ...AUTO_ROLES.map(([name, , checkLabel]) => ({ name, type: "checkbox", label: "승인 없이 저장", checkLabel })),
  ],
  data_protection: [
    { name: "mask_phone_numbers", type: "checkbox", label: "전화번호", checkLabel: "전화번호를 가립니다", value: true },
    { name: "mask_resident_registration_numbers", type: "checkbox", label: "주민등록번호", checkLabel: "주민등록번호를 가립니다", value: true },
    { name: "mask_emails", type: "checkbox", label: "이메일", checkLabel: "이메일 주소를 가립니다" },
  ],
  content: [
    { name: "max_output_chars", type: "number", label: "답의 최대 글자 수", help: "비우면 기능마다 정해진 길이를 씁니다. 퀴즈처럼 JSON 으로 답하는 기능은 넘으면 자르지 않고 실패합니다." },
    { name: "block_external_links", type: "checkbox", label: "제품 밖 링크", checkLabel: "제품 밖 링크를 누를 수 없게 바꿉니다" },
  ],
};
const ruleKindOf = (body) => body.kind || Object.keys(RULE_FIELDS).find((k) => RULE_FIELDS[k].some((f) => f.name in body));
function policyApiBody(body) {
  const kind = ruleKindOf(body);
  const out = {};
  for (const key of ["name", "purpose", "kind"]) if (key in body) out[key] = body[key];
  const target = kind === "approval" ? body.target_write : body.target;
  if (target !== undefined) out.applies_to = target;
  if (kind === "approval") {
    out.content = { write_requires_approval: !!body.write_requires_approval, auto_approve_roles: AUTO_ROLES.filter(([name]) => body[name]).map(([, role]) => role) };
  } else if (kind === "data_protection") {
    out.content = { mask_phone_numbers: !!body.mask_phone_numbers, mask_resident_registration_numbers: !!body.mask_resident_registration_numbers, mask_emails: !!body.mask_emails };
  } else if (kind === "content") {
    const cap = body.max_output_chars;
    out.content = { max_output_chars: cap === "" || cap == null ? null : Number(cap), block_external_links: !!body.block_external_links };
  }
  return out;
}
/* 수정 폼의 처음 값. **그 종류의 칸만** 담는다 - 모든 종류의 칸을 담으면 `policyApiBody` 가 종류를 잘못 알아보고,
   바뀐 칸만 보내는 비교(`diffFields`)가 늘 「바뀜」으로 읽는다. */
function policyFormValues(row) {
  const c = row.content || {};
  const target = (row.applies_to || [])[0];
  const roles = c.auto_approve_roles || [];
  const base = { purpose: row.purpose };
  if (row.kind === "approval") {
    return { ...base, target_write: target || "workspace.draft", write_requires_approval: c.write_requires_approval !== false,
      ...Object.fromEntries(AUTO_ROLES.map(([name, role]) => [name, roles.includes(role)])) };
  }
  if (row.kind === "data_protection") {
    return { ...base, target: target || "*", mask_phone_numbers: !!c.mask_phone_numbers,
      mask_resident_registration_numbers: !!c.mask_resident_registration_numbers, mask_emails: !!c.mask_emails };
  }
  if (row.kind === "content") {
    return { ...base, target: target || "*", max_output_chars: c.max_output_chars == null ? "" : c.max_output_chars,
      block_external_links: !!c.block_external_links };
  }
  return base;
}
const targetField = (kind) => (kind === "approval"
  ? { name: "target_write", label: "적용할 기능", type: "select", required: true, value: "workspace.draft", options: opt(WRITE_TARGETS) }
  : { name: "target", label: "적용할 기능", type: "select", required: true, value: "*", options: opt(POLICY_TARGETS), help: "기능을 지정한 정책이 모든 기능 정책보다 먼저 걸립니다." });
function policyRuleSummary(r) {
  const c = r.content || {};
  if (r.kind === "approval") {
    const who = (c.auto_approve_roles || []).map((x) => ({ system_admin: "시스템 관리자", admin: "관리자", operator: "운영자", user: "사용자" })[x] || x);
    if (!c.write_requires_approval) return "승인을 요구하지 않습니다.";
    return who.length ? who.join(", ") + "만 승인 없이 저장하고 나머지는 승인을 받습니다." : "모든 사람이 문서로 저장하기 전에 승인을 받습니다.";
  }
  if (r.kind === "data_protection") {
    const parts = [c.mask_phone_numbers ? "전화번호" : null, c.mask_resident_registration_numbers ? "주민등록번호" : null, c.mask_emails ? "이메일" : null].filter(Boolean);
    return parts.length ? parts.join(", ") + "를 가립니다." : "가리는 항목이 없습니다.";
  }
  if (r.kind === "content") {
    const cap = c.max_output_chars ? "답을 " + c.max_output_chars + "자까지 싣습니다." : "기능마다 정해진 길이를 씁니다.";
    return cap + (c.block_external_links ? " 제품 밖 링크는 누를 수 없게 바꿉니다." : "");
  }
  return "옛 형식이라 적용하지 않습니다.";
}
const policyPath = (r) => "/api/admin/policies/" + r.id;

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
      // 초안에서는 고정 「수정」이 채움 단추다 - 「발행」까지 채우면 한 영역에 둘이 된다(PA-RC-0023).
      { label: "발행", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => !isBuiltinRow(r) && r.status === "draft", path: (r) => promptPath(r) + "/transition", body: { status: "published" }, confirm: "이 버전을 발행할까요? 다음 AI 호출부터 이 사용처는 이 지시문을 쓰고, 지금 쓰는 발행본은 보관됩니다." },
      // 새 버전은 어떤 상태에서든 새 초안으로 갈라진다. 드로어를 새 초안으로 바꿔 곧바로 고칠 수 있게 한다.
      { label: "새 버전", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => !isBuiltinRow(r) && r.status !== "draft", path: (r) => promptPath(r) + "/new-version", keepSelection: true },
      { ...nameVersionsAction("/api/admin/prompts", "프롬프트 버전 기록"), when: (r) => !isBuiltinRow(r) },
      { label: "보관", variant: "danger", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => !isBuiltinRow(r) && r.status !== "archived", path: (r) => promptPath(r) + "/transition", body: { status: "archived" }, confirm: "이 버전을 보관할까요? 사용 중이던 버전이면 다음 AI 호출부터 기본 제공 지시문을 씁니다." },
      // operator는 프롬프트 화면엔 들어오지만 /audit 화면엔 못 들어간다 — admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], when: (r) => !isBuiltinRow(r), navigate: (r) => "#/audit?object_type=prompts&object_id=" + r.id },
    ],
  },
  policies: {
    /* C2 «Filter Surface 가 정당한가» — 이 화면은 행 수가 유한하고 작다. 조건 조합을 이름 붙여 재사용할 만큼
       탐색이 반복되지 않으므로 저장된 뷰를 그리지 않는다. */
    smallSet: true,
    key: "policies", area: "AI", title: "정책", endpoint: "/api/admin/policies",
    // 발행은 그 순간부터 전사 AI 요청에 걸린다 — 배너를 일반 안내와 같은 톤으로 두면 그 경고가 안 읽힌다.
    helpTone: "warn",
    help: "AI 요청에 거는 규칙입니다. 발행한 정책은 다음 AI 요청부터 걸리고, 기능을 지정한 정책이 모든 기능 정책보다 먼저 걸립니다. 같은 기능에 같은 종류의 정책은 하나만 발행할 수 있고, 업그레이드로 옮긴 옛 정책은 초안이라 발행해야 걸립니다.",
    emptyTitle: "조건에 맞는 정책이 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 정책 추가’로 종류와 적용할 기능을 고르고 초안에서 발행하세요. 발행한 정책이 없으면 AI 요청에 아무 규칙도 걸리지 않습니다.", "정책은 관리자가 추가합니다. 추가되면 버전이 여기에 표시됩니다."),
    createLabel: "정책 추가",
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "item",
    paginated: true,
    capWarning: 500,
    filters: [
      { key: "kind", type: "select", label: "종류", options: opt([...POLICY_KINDS, ["legacy", "옛 형식"]]) },
      { key: "status", type: "select", label: "상태", value: "published", options: opt([["draft", "초안"], ["published", "발행됨"], ["archived", "보관됨"]]) },
    ],
    columns: [
      { ...col("name", "이름", "title"), rowName: (r) => r.name + " v" + r.version },
      // 가장 긴 종류 이름(「개인정보 가리기」, 여덟 글자)이 한 줄에 서는 폭이다. enum 의 바닥 폭(6.5rem)에서는 잘렸다.
      { key: "kind", label: "종류", type: "enum", width: "9rem", render: (r) => r.kind_label || POLICY_KIND_LABEL[r.kind] || r.kind },
      { key: "applies_to_labels", label: "적용할 기능", type: "text", render: (r) => (r.applies_to_labels || []).join(", ") || "-" },
      { key: "version", label: "버전", type: "code", render: (r) => "v" + r.version },
      badgeCol("status", "상태"),
      { key: "calls_30d", label: "30일 적용", type: "count" },
    ],
    detailFields: [
      field("purpose", "설명"),
      { key: "_rules", label: "규칙", render: (r) => policyRuleSummary(r) },
      { key: "_migrated", label: "옮긴 정책", render: (r) => (r.migrated_from_id ? "업그레이드가 옛 정책에서 옮긴 초안입니다. 검토하고 발행해야 걸립니다." : "-") },
      { key: "created_by", label: "작성자", render: (r) => r.created_by_name || r.created_by_email || r.created_by || "-" },
      { key: "_edit_note", label: "수정 안내", render: (r) => (r.status !== "draft" ? "이 버전은 초안이 아니라 고칠 수 없습니다. ‘새 버전’으로 초안을 만드세요." : "-") },
      dateCol("published_at", "발행 시각"),
      jsonField("content", "규칙(JSON)"),
      field("id", "정책 ID"),
    ],
    /* 정책은 부서로 나뉘는 자원이 아니다 - 발행본이 전사 AI 요청에 걸린다. 서버가 쓰기를 전역 범위 관리자로 한정한다. */
    create: { roles: WRITE_ROLES, requiresGlobalScope: true, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "kind", label: "종류", type: "select", required: true, value: "data_protection", options: opt(POLICY_KINDS), help: "종류는 만든 뒤에 바꿀 수 없습니다." },
      { ...targetField("approval"), showIf: (v) => v.kind === "approval" },
      { ...targetField("other"), showIf: (v) => v.kind !== "approval" },
      ...Object.entries(RULE_FIELDS).flatMap(([kind, fields]) => fields.map((f) => ({ ...f, showIf: (v) => v.kind === kind }))),
      { name: "purpose", label: "설명", type: "textarea" },
    ] },
    toApiBody: policyApiBody,
    fromRow: policyFormValues,
    // 수정은 초안일 때만 된다. 종류는 바꾸지 않으므로 그 종류의 칸만 보인다.
    editMethod: "PATCH", editWhen: (r) => r.status === "draft" && r.kind !== "legacy",
    edit: { roles: WRITE_ROLES, requiresGlobalScope: true, fields: (role, row) => [
      targetField(row && row.kind),
      ...((row && RULE_FIELDS[row.kind]) || []),
      { name: "purpose", label: "설명", type: "textarea" },
    ] },
    actions: [
      // 초안에서는 고정 「수정」이 채움 단추다 - 「발행」까지 채우면 한 영역에 둘이 된다(PA-RC-0023).
      { label: "발행", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => r.status === "draft" && r.kind !== "legacy", path: (r) => policyPath(r) + "/transition", body: { status: "published" }, confirm: "이 버전을 발행할까요? 다음 AI 요청부터 이 정책이 걸리고, 같은 이름으로 발행돼 있던 버전은 보관됩니다." },
      { label: "새 버전", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => r.status !== "draft" && r.kind !== "legacy", path: (r) => policyPath(r) + "/new-version", keepSelection: true },
      nameVersionsAction("/api/admin/policies", "정책 버전 기록"),
      { label: "보관", variant: "danger", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => r.status !== "archived", path: (r) => policyPath(r) + "/transition", body: { status: "archived" }, confirm: "이 버전을 보관할까요? 발행돼 있던 버전이면 다음 AI 요청부터 이 정책이 걸리지 않습니다." },
      // operator는 정책 화면엔 들어오지만 /audit 화면엔 못 들어간다 — admin/system_admin/auditor에만 노출한다.
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
    smallSet: true, // 정책 이름 수만큼의 줄이라 저장된 뷰가 소음이다(D-506)
    key: "policy-usage", area: "AI", title: "정책 사용 통계",
    endpoint: "/api/admin/policies/usage/stats",
    /* 예전에는 스케줄이 이름을 참조하는가를 셌고 언제나 「쓰이지 않음」이었다. 이제 AI 호출 기록에서 그 정책이 걸린
       호출을 센다(D-519). */
    help: "정책마다 지금 발행된 버전과 최근 30일에 그 정책이 걸린 AI 호출 수를 봅니다. 수는 AI 호출 기록에서 셉니다.",
    emptyTitle: "추가된 정책이 없습니다",
    emptyHelp: "‘정책’ 화면에서 정책을 만들고 발행하면 적용 현황이 여기에 표시됩니다.",
    emptyRelatedLink: { href: "#/policies", label: "정책 화면으로 이동" },
    searchFields: ["name"],
    searchPlaceholder: "정책 이름으로 검색",
    columns: [
      { key: "name", label: "이름", type: "title" },
      // 가장 긴 종류 이름(「개인정보 가리기」, 여덟 글자)이 한 줄에 서는 폭이다. enum 의 바닥 폭(6.5rem)에서는 잘렸다.
      { key: "kind", label: "종류", type: "enum", width: "9rem", render: (r) => r.kind_label || POLICY_KIND_LABEL[r.kind] || r.kind },
      { key: "applies_to_labels", label: "적용할 기능", type: "text", render: (r) => (r.applies_to_labels || []).join(", ") || "-" },
      { key: "published_version", label: "발행 버전", type: "code", render: (r) => (r.published_version == null ? "발행 안 함" : "v" + r.published_version) },
      { key: "applied", label: "30일 적용", type: "count" },
      dateCol("last_applied_at", "마지막 적용"),
    ],
    detailFields: [field("versions", "버전 수"), badgeCol("latest_status", "최신 상태")],
    actions: [
      { label: "정책 보기", navigate: (r) => "#/policies?id=" + encodeURIComponent(r.id) },
    ],
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
