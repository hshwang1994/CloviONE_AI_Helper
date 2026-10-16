/* AI 저작물 — 프롬프트 · 정책과 호출 기록.
 *
 * 세 화면은 목적과 정보 구조가 다르다(계획 A4 ~ A6): 프롬프트는 「AI 기능마다 따르는 지시문」(기능마다 한 줄 → 서랍),
 * 정책은 「AI 동작에 거는 제한과 보호 규칙」(종류별 구획), 사용 통계는 「실제 사용량 분석」(조건 · 기간 → 지표 한 줄 → 나눔 표,
 * 그 화면은 `screens/ai/AiUsageStats.jsx` 가 따로 그린다). 상태 어휘는 셋이 같다 — 초안 · 적용 중 · 보관(D-541).
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
import { nameVersionsAction, slotVersionsAction } from "./actions.js";

// 호출 기록의 결과 배지(D-517). 막힘은 실패와 다른 사실이다 - 제공자에 닿지 않았다.
const USAGE_STATUS_KIND = { ok: "ok", error: "danger", blocked_quota: "warn", blocked_policy: "warn" };

/* 생명주기 어휘는 하나다 — 초안 · 적용 중 · 보관(D-541). 예전 프롬프트는 「사용 중」, 정책은 「발행됨 · 보관됨」이라 같은 일을
   두 말로 했고, 「사용 중」은 실제 호출과 무관했다. */
const LIFECYCLE = { draft: ["초안", "neutral"], published: ["적용 중", "ok"], archived: ["보관", "neutral"] };
const lifecycle = (status) => LIFECYCLE[status] || [status, "neutral"];
/* 기능 상태(D-541) — 「최근 30일 요청 0」의 까닭을 이 칸이 말한다. */
const FEATURE_STATE_KIND = { on: "ok", off: "neutral", ai_unavailable: "warn" };
const featurePath = (r) => "/api/admin/prompts/features/" + r.slot;

/* 정책(계획 3.9, D-519). 종류마다 규칙 칸이 정해져 있고, 폼은 JSON 대신 그 칸을 보인다. 서버가 같은 규칙으로 다시
   검사한다(`app/ai/policy/schemas.py`) - 화면은 칸을 모아 보낼 뿐이다. */
const POLICY_KINDS = [["approval", "쓰기 승인"], ["data_protection", "개인정보 가리기"], ["content", "응답 제한"]];
const POLICY_KIND_LABEL = { approval: "쓰기 승인", data_protection: "개인정보 가리기", content: "응답 제한", legacy: "옛 형식" };
// 서버의 액션 이름과 같은 표다(`app/ai/actions.py`). 쓰기 승인은 결과가 저장되는 기능에만 건다.
// 은퇴한 기능(이전 방식의 질문 답변 · 작업 공간 묻기)은 고를 수 없다(D-542) — 서버가 거절한다.
const POLICY_TARGETS = [["*", "모든 기능"], ["assistant.chat", "AI 도우미"],
  ["workspace.draft", "작업 공간 문서 초안"], ["report.weekly_summary", "프로젝트 주간 요약"], ["home.narrative", "홈 문장 요약"],
  ["game.quiz", "게임 퀴즈 만들기"]];
/* 정책 화면의 종류별 구획(D-542). 구획 머리는 종류 이름과 그 종류가 런타임에서 하는 일 한 문장이다. */
const POLICY_GROUPS = {
  approval: { key: "approval", label: "승인 필요", note: "AI가 만든 결과를 사람이 승인한 뒤에 씁니다." },
  data_protection: { key: "data_protection", label: "개인정보 가리기", note: "모델에 보내기 전에 개인정보를 가립니다." },
  content: { key: "content", label: "응답 제한", note: "응답 길이와 링크를 제한합니다." },
};
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
    { name: "max_output_chars", type: "number", label: "답의 최대 글자 수", help: "비우면 기능마다 정해진 길이를 씁니다. 퀴즈처럼 JSON으로 답하는 기능은 넘으면 자르지 않고 실패합니다." },
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
    return parts.length ? parts.join(", ") + " 항목을 가립니다." : "가리는 항목이 없습니다.";
  }
  if (r.kind === "content") {
    const cap = c.max_output_chars ? "답을 " + c.max_output_chars + "자로 제한합니다." : "기능마다 정해진 길이를 씁니다.";
    return cap + (c.block_external_links ? " 제품 밖 링크는 누를 수 없게 바꿉니다." : "");
  }
  return "옛 형식이라 적용하지 않습니다.";
}
const policyPath = (r) => "/api/admin/policies/" + r.id;

export const AUTHORING_SCREENS = {
  prompts: {
    smallSet: true, // 기능 수만큼의 줄이라 저장된 뷰가 소음이다(D-506)
    searchable: false, // 기능 다섯 줄이 한 화면에 다 선다 — 찾을 것이 없는 검색 칸을 세우지 않는다
    key: "prompts", area: "AI", title: "프롬프트", endpoint: "/api/admin/prompts/features",
    /* 관리자는 행(버전)이 아니라 기능으로 생각한다(D-541) — 기능마다 한 줄이고, 행을 열면 지금 지시문 · 고정 틀 · 초안 ·
       버전 기록이 한 서랍에 있다. 0 회의 까닭은 「기능 상태」 칸이 말한다. */
    help: "AI 기능마다 따르는 지시문을 고칩니다. 발행한 지시문은 다음 AI 호출부터 쓰입니다.",
    emptyTitle: "AI 기능이 없습니다.",
    emptyHelp: "지시문을 고칠 수 있는 기능은 제품이 정합니다. 목록이 비었다면 서버 응답을 확인하세요.",
    // 옛 딥링크(`?id=<버전 id>` · `builtin:<기능>`)도 그 기능의 서랍을 연다 — 서버가 기능으로 풀어 준다.
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "item",
    columns: [
      { key: "label", label: "기능", type: "name", rowLink: true, rowName: (r) => r.label },
      { key: "current", label: "지금 쓰는 지시문", type: "name", render: (r) => (r.current ? r.current.label : "-") },
      { key: "feature_state", label: "기능 상태", type: "status", render: (r) => React.createElement(Badge, { value: r.feature_state_label || r.feature_state, kind: FEATURE_STATE_KIND[r.feature_state] || "neutral" }) },
      /* `value` 는 그리는 글과 같은 글이다 — 열 배분은 `render` 결과를 재지 않아서(`ui/columnPlan.js::columnValueText`) 없으면 바닥 폭으로 서고 긴 초안 이름이 잘린다. */
      { key: "draft", label: "초안", type: "code", value: (r) => (r.draft ? r.draft.label : "-"), render: (r) => (r.draft ? r.draft.label : "-") },
      { key: "calls_30d", label: "최근 30일 요청", type: "count" },
      { key: "failure_rate", label: "실패율", type: "percent", render: (r) => (r.failure_rate == null ? "-" : r.failure_rate + "%") },
      dateCol("last_used_at", "마지막 사용"),
    ],
    detailFields: [
      field("description", "설명"),
      { key: "_state", label: "기능 상태", render: (r) => r.feature_note || "활성화되어 있습니다." },
      { key: "_current", label: "지금 쓰는 지시문", render: (r) => (r.current ? r.current.instruction : "-") },
      { key: "_draft", label: "초안", render: (r) => (r.draft ? r.draft.content : "초안이 없습니다. ‘수정’을 누르면 지금 지시문에서 초안을 만듭니다.") },
      { key: "_role", label: "역할 문장(고정)", render: (r) => (r.frame ? r.frame.role : "-") },
      { key: "_format", label: "출력 형식(고정)", render: (r) => (r.frame ? r.frame.format_line : "-") },
      { key: "_grounding", label: "안전 규칙(고정)", render: (r) => (r.frame ? r.frame.grounding : "-") },
    ],
    /* 「수정」은 그 기능의 초안을 고친다 — 초안이 없으면 지금 지시문을 복사해 만든다(서버, D-541). 발행 전에는 호출에 쓰이지
       않는다. 프롬프트는 부서로 나뉘는 자원이 아니라 쓰기는 전역 범위 관리자만 한다. */
    editMethod: "PATCH", editWhen: () => true, edit: { roles: WRITE_ROLES, requiresGlobalScope: true, fields: [
      { name: "content", label: "지시문", type: "textarea", required: true, help: "초안에 저장합니다. 발행하기 전에는 AI 호출에 쓰이지 않습니다. 안전 규칙과 출력 형식은 따로 붙습니다." },
    ] },
    actions: [
      { label: "초안 발행", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => !!r.draft, path: (r) => featurePath(r) + "/publish", keepSelection: true, confirm: "초안을 발행할까요? 다음 AI 호출부터 이 기능은 이 지시문을 씁니다." },
      { label: "초안 버리기", variant: "danger", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => !!r.draft, path: (r) => featurePath(r) + "/discard", keepSelection: true, confirm: "초안을 버릴까요? 버전 기록에 보관으로 남습니다." },
      { label: "기본 제공으로 되돌리기", variant: "danger", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => r.current && r.current.source === "admin", path: (r) => featurePath(r) + "/reset", keepSelection: true, confirm: "기본 제공 지시문으로 되돌릴까요? 다음 AI 호출부터 기본 제공 지시문을 씁니다." },
      slotVersionsAction(),
    ],
  },
  policies: {
    /* C2 «Filter Surface 가 정당한가» — 이 화면은 행 수가 유한하고 작다. 조건 조합을 이름 붙여 재사용할 만큼
       탐색이 반복되지 않으므로 저장된 뷰를 그리지 않는다. */
    smallSet: true,
    key: "policies", area: "AI", title: "정책", endpoint: "/api/admin/policies",
    // 발행은 그 순간부터 전사 AI 요청에 걸린다 — 배너를 일반 안내와 같은 톤으로 두면 그 경고가 안 읽힌다.
    helpTone: "warn",
    help: "AI 동작에 거는 제한과 보호 규칙입니다. 발행한 정책은 다음 AI 요청부터 걸리고, 기능을 지정한 정책이 모든 기능 정책보다 먼저 걸립니다.",
    /* 한 줄 요약과 옮긴 초안 안내(D-542). 종류별 수는 아래 표의 구획 머리가 세므로 숫자 칸을 따로 늘어놓지 않는다 —
       서버가 쓴 한 문장(「적용 중인 규칙 N개가 AI 기능 M개에 걸려 있습니다.」)만 선다. 한 번뿐인 업그레이드 알림
       (`ai_policy_migrated`)을 옮긴 초안 안내가 대신한다. */
    summary: {
      endpoint: "/api/admin/policies/summary",
      kind: "sentence",
      sentence: (d) => d.sentence || "",
      notes: (d) => (d.migrated_drafts ? ["업그레이드가 옛 정책에서 옮긴 초안 " + d.migrated_drafts + "건이 아직 적용되지 않았습니다. 검토하고 발행해야 걸립니다."] : []),
    },
    /* 종류별 구획(D-542) — 같은 표 안에 종류마다 머리행이 서고 그 종류가 하는 일을 한 문장으로 말한다. */
    groupRows: (r) => POLICY_GROUPS[r.kind] || { key: r.kind, label: r.kind_label || r.kind },
    groupOrder: ["approval", "data_protection", "content"],
    // 규칙이 없는 종류도 머리와 한 줄로 선다 — 「승인 필요 규칙이 없다」를 화면이 말한다(D-542).
    groupSlots: ["approval", "data_protection", "content"].map((k) => ({ ...POLICY_GROUPS[k], emptyText: "이 종류의 규칙이 없습니다." })),
    emptyTitle: "등록된 정책이 없습니다.",
    emptyHelp: writerEmptyHelp("‘정책 추가’로 종류와 적용할 기능을 고르고 초안에서 발행하세요. 발행한 정책이 없으면 AI 요청에 아무 규칙도 걸리지 않습니다.", "정책은 관리자가 추가합니다. 추가되면 버전이 여기에 표시됩니다."),
    createLabel: "정책 추가",
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "item",
    paginated: true,
    capWarning: 500,
    /* 기본 조건이 없다(D-542) — 예전 기본값 「발행됨」은 업그레이드가 옮긴 검토 초안까지 숨겼다. 종류는 구획이 대신한다.
       옛 형식 원본은 서버가 기본 목록에서 뺀다. */
    filters: [
      { key: "status", type: "select", label: "상태", options: opt([["draft", "초안"], ["published", "적용 중"], ["archived", "보관"]]) },
    ],
    columns: [
      {
        ...col("name", "이름", "name"), rowLink: true, rowName: (r) => r.name + " v" + r.version,
        value: (r) => r.name + " v" + r.version, render: (r) => r.name + " v" + r.version,
      },
      /* 그린 글자를 `value` 로도 말한다 — 열 배분이 값 폭을 알아야 「모든 기능」처럼 짧은 값 옆의 빈 폭을 이름 열에 내준다(D-529 보정). */
      {
        key: "applies_to_labels", label: "적용 기능", type: "text",
        value: (r) => (r.applies_to_labels || []).join(", ") || "-", render: (r) => (r.applies_to_labels || []).join(", ") || "-",
      },
      { key: "status", label: "상태", type: "status", render: (r) => { const [value, kind] = lifecycle(r.status); return React.createElement(Badge, { value, kind }); } },
      { key: "applied_30d", label: "최근 30일 적용", type: "count" },
      dateCol("last_applied_at", "최근 적용"),
    ],
    detailFields: [
      field("purpose", "설명"),
      { key: "_rules", label: "규칙", render: (r) => policyRuleSummary(r) },
      { key: "_kind", label: "종류", render: (r) => r.kind_label || POLICY_KIND_LABEL[r.kind] || r.kind },
      { key: "_applied", label: "최근 30일 적용", render: (r) => (r.applied_30d ? r.applied_30d + "건(성공한 요청과 이 정책이 막은 요청)" : "아직 걸린 요청이 없습니다.") },
      { key: "_migrated", label: "옮긴 정책", render: (r) => (r.migrated_from_id ? "업그레이드가 옛 정책에서 옮긴 초안입니다. 검토하고 발행해야 걸립니다." : "-") },
      { key: "created_by", label: "작성자", render: (r) => r.created_by_name || r.created_by_email || r.created_by || "-" },
      { key: "_edit_note", label: "수정 안내", render: (r) => (r.status !== "draft" ? "이 버전은 초안이 아니라 수정할 수 없습니다. ‘새 버전’으로 초안을 추가하세요." : "-") },
      dateCol("published_at", "발행 시각"),
      jsonField("content", "규칙(JSON)"),
      field("id", "정책 ID"),
    ],
    /* 정책은 부서로 나뉘는 자원이 아니다 - 발행본이 전사 AI 요청에 걸린다. 서버가 쓰기를 전역 범위 관리자로 한정한다. */
    create: { roles: WRITE_ROLES, requiresGlobalScope: true, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "kind", label: "종류", type: "select", required: true, value: "data_protection", options: opt(POLICY_KINDS), help: "종류는 추가한 뒤에 바꿀 수 없습니다." },
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
  "ai-usage-records": {
    key: "ai-usage-records", area: "AI", title: "호출 기록",
    endpoint: "/api/admin/ai/usage/records",
    help: "AI 호출 한 번이 한 줄입니다. 누가, 언제, 어떤 기능으로, 어느 모델에 얼마나 썼고 어떻게 끝났는지만 남기고 질문과 답의 본문은 남기지 않습니다. 기록은 180일 동안 둡니다.",
    emptyTitle: "아직 AI 호출 기록이 없습니다.",
    emptyHelp: "AI 연결을 먼저 설정하세요. AI 기능을 쓰면 여기에 기록이 쌓입니다.",
    emptyRelatedLink: { href: "#/ai-connection", label: "AI 연결 열기" },
    paginated: true, pageSize: 50,
    // 검색은 서버가 한다(D-543) — 보이는 범위 안 사람의 이름 · 이메일과 기능 이름. 받은 쪽의 행 JSON 을 훑지 않는다.
    searchable: true, searchPlaceholder: "사용자 이름, 이메일, 기능으로 검색",
    filters: [
      { key: "status", type: "select", label: "결과", options: opt([["ok", "성공"], ["error", "실패"], ["blocked_policy", "정책 차단"], ["blocked_quota", "한도 초과"]]) },
      /* 기능은 분류 축이다 — 키 이름(`action`)이 그룹 표에 없어 「기타」로 떨어지면 기간 칸 뒤에 섰다(좁히는 순서: 분류 → 결과 → 기간).
         은퇴한 기능은 지난 기록을 볼 때만 쓴다 — 이름에 「(이전 방식)」이 붙는다(서버의 기능 이름과 같다). */
      { key: "action", type: "select", label: "기능", group: "category", options: opt([["assistant.chat", "AI 도우미"], ["workspace.draft", "작업 공간 문서 초안"], ["report.weekly_summary", "프로젝트 주간 요약"], ["home.narrative", "홈 문장 요약"], ["game.quiz", "게임 퀴즈 만들기"], ["system.connection_test", "연결 확인"], ["chat.answer", "채팅 답변(이전 방식)"], ["workspace.ask", "작업 공간 질문(이전 방식)"]]) },
      { key: "from", endKey: "to", type: "period", label: "기간", presets: ["today", "7d", "30d", "thisMonth", "lastMonth"], emptyPreset: "30d" },
    ],
    serverSort: { keys: ["action_key", "created_at", "input_tokens", "latency_ms", "model", "output_tokens", "status"], default: { key: "created_at", dir: "desc" } },
    columns: [
      { ...dateCol("created_at", "시각"), sortable: true, rowName: (r) => (r.action_label || r.action_key) + " / " + (r.user_name || "") },
      { key: "user_name", label: "사용자", type: "name", render: (r) => r.user_name || "-" },
      { key: "action_key", label: "기능", type: "enum", sortable: true, render: (r) => r.action_label || r.action_key },
      { key: "model", label: "모델", type: "identifier", sortable: true, render: (r) => r.model || "-" },
      // AI 도우미 한 차례가 쓴 도구(D-537) — 사람의 낱말로(「사내 문서 검색, 내 업무(2회)」). 인자와 결과는 없다.
      { key: "tools_label", label: "도구", type: "text", tier: "secondary", render: (r) => r.tools_label || "-" },
      { key: "status", label: "결과", type: "status", sortable: true, render: (r) => React.createElement(Badge, { value: r.status_label || r.status, kind: USAGE_STATUS_KIND[r.status] || "neutral" }) },
      { key: "input_tokens", label: "입력 토큰", type: "count", sortable: true, render: (r) => (r.input_tokens == null ? "-" : String(r.input_tokens)) },
      { key: "output_tokens", label: "출력 토큰", type: "count", sortable: true, render: (r) => (r.output_tokens == null ? "-" : String(r.output_tokens)) },
      { key: "latency_ms", label: "응답(ms)", type: "number", sortable: true, render: (r) => (r.latency_ms == null ? "-" : String(r.latency_ms)) },
    ],
    detailFields: [
      field("user_email", "이메일"), field("department_name", "부서"), field("provider", "제공자"),
      field("error_code", "실패 코드"), { key: "truncated", label: "잘림", render: (r) => (r.truncated ? "입력이나 출력을 한도에 맞춰 잘랐습니다." : "자르지 않았습니다.") },
      { key: "_rounds", label: "라운드", render: (r) => (r.rounds ? r.rounds + "번" : "-") },
      { key: "_mode", label: "모드", render: (r) => (r.mode === "search_only" ? "도구 없이 검색 결과로만 답했습니다." : r.mode === "tools" ? "도구를 썼습니다." : "-") },
      { key: "_prompt", label: "지시문 버전", render: (r) => (r.prompt_version ? "v" + r.prompt_version : "기본 제공") },
      field("id", "기록 ID"),
    ],
  },
};
