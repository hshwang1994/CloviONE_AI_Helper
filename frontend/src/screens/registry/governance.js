/* 권한과 기록 — 승인·위임·감사·역할·대리 보기.
 *
 * '누가 무엇을 할 수 있고, 무엇을 했는가'를 보는 화면들이다. 승인과 감사는 같은 사건의
 * 앞뒤(요청과 기록)라 한쪽만 고치면 반드시 어긋난다.
 *
 * registry.js 를 쪼갠 조각이다 (E-10). 쪼갠 축은 '줄 수'가 아니라 **관리자가 한 번에
 * 함께 보는 묶음**이다 — 줄 수를 맞추려고 아무 데나 자르면 화면 하나를 고치는 데
 * 파일 셋을 열게 되어 오히려 더 나빠진다.
 *
 * 화면 설정만 있고 그리는 코드는 없다. 그리는 것은 DataScreen.jsx 하나다.
 */
import React from "react";
import Tooltip from "@mui/material/Tooltip";
import { APPROVAL_PAYLOAD_KEY_KO, Badge, OBJTYPE_OPTS, OBJ_ID_PARAM, OBJ_ROUTE, OPS_ROLES, ROLE_KO, WRITE_ROLES, actionCol, actionKo, badgeCol, canReachObjRoute, col, dateCol, field, fmtDateTime, mapCol, objCol, objRouteHref, objectField, opt, personField, truncateCol, writerEmptyHelp } from "./shared.js";
import { APPROVAL_DONE } from "./actions.js";

// RG-05: 서버(app/approvals/router.py)가 request_type/requested_by 서버 필터를 지원하는데
// 화면엔 status만 있었다 — 승인 큐는 서버 페이지네이션이라 clientFilter로는 "지금 페이지 안"까지가
// 한계다(문서/스케줄 등 다른 서버-페이지네이션 화면과 같은 이유). 실제로 등록된 5개 요청 유형은
// app/approvals/service.py의 _REQUEST_TYPE_KO(APPR-02)와 정본이 같다 — 라벨은 actionKo로 만들어
// 목록 열(actionCol("request_type", ...))과 항상 같은 말을 쓰게 한다.
const APPROVAL_REQUEST_TYPES = [
  "user.role_change", "integration.change_config", "runner.change_config",
  "schedule.enable", "document.publish",
];

/* app/core/authz.py `rbac_matrix()` 가 돌려주는 `scopes`(전체/조직/부서 + 각 설명)를
 * 사람이 읽는 한 문단으로 만든다 — role 축(이 표의 열)과 직교하는 scope 축을
 * '허용 매트릭스'에 새 열로 끼워 넣진 않는다(scope 는 capability 별이 아니라
 * admin 역할 전체에 걸리는 조건이라 칸마다 다른 값이 아니다), 대신 admin 열
 * 위에서 그 축의 존재와 각 값의 뜻을 설명한다. */
function adminScopeTooltip(scopes) {
  const lines = (scopes || []).map((s) => s.label + ": " + s.help).join(", ");
  return "admin 역할은 관리 범위로 추가로 좁혀질 수 있습니다(사용자 관리에서 설정). " + lines;
}

export const GOVERNANCE_SCREENS = {
  approvals: {
    key: "approvals", area: "자동화", title: "승인", endpoint: "/api/admin/approvals",
    // self_approval_allowed는 서버 설정 파일에만 있고(app/core/feature_flags.py) 이 관리 콘솔에는
    // 그 값을 보거나 바꿀 화면이 없다 — '정책 설정에 따라 달라질 수 있어요'는 마치 이 화면 어딘가에
    // 바꿀 수 있는 정책 설정이 있는 것처럼 읽혀 없는 컨트롤을 찾게 만들었다. 서버 쪽 설정임을 명시한다.
    help: "위험할 수 있는 작업의 승인 요청을 처리합니다. 본인 요청은 기본적으로 본인이 승인할 수 없습니다(서버 설정 파일로만 조정되며, 이 화면에서는 바꿀 수 없습니다). 승인 요청은 72시간(기본값)이 지나면 자동으로 만료됩니다. 처리하지 않고 두면 다음에 다시 열었을 때 '만료'로 바뀌어 있을 수 있습니다.",
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
    filters: [
      { key: "status", type: "select", label: "상태", value: "pending", options: opt([["pending", "대기"], ["approved", "승인됨"], ["rejected", "거절됨"], ["expired", "만료"], ["cancelled", "취소됨"]]) },
      { key: "request_type", type: "select", label: "유형", options: opt(APPROVAL_REQUEST_TYPES.map((t) => [t, actionKo(t)])) },
      // requested_by는 요청자 ID(UUID) 그대로 받는다 — 다른 화면의 관용(impersonation의
      // actor_user_id/target_user_id)과 같은 자유 텍스트 ID 필터, 이름 검색이 아니다.
      { key: "requested_by", type: "text", label: "요청자 ID" },
    ],
    // 만료 시각은 대기(pending)일 때만 의미가 있다 — 종료된 행은 원래 만료 시각을 계속 보여주면 오해를 낳으므로 '-'.
    // 요청자 열 — router.py가 배치로 requester_name/requester_email을 미리 붙여 주므로(누가 요청했는지
    // 목록에서 바로 보이게), 각 행을 열어보지 않고도 트리아지할 수 있게 노출한다.
    // SEM-01: 이 화면 첫 열(유형)이 actionCol(render 있음)이라 표식 없이는 100건이 전부
    // "상세 보기"로 읽혔다 — 요청자까지 합쳐 행마다 실제로 다른 이름을 만든다(둘 다 이미
    // 목록에 보이는 값). requester_name 폴백은 바로 아래 요청자 열과 동일한 우선순위.
    columns: [{ ...actionCol("request_type", "유형"), rowName: (r) => actionKo(r.request_type) + " / " + (r.requester_name || r.requester_email || (r.requested_by === "system" ? "시스템(자동)" : r.requested_by) || "-") }, objCol("object_type", "대상"),
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
          ? React.createElement(Badge, { value: "기한 초과, " + text, kind: "danger" })
          : text;
      } },
      { key: "expires_at", label: "만료", render: (r) => APPROVAL_DONE.includes(r.status) ? "-" : fmtDateTime(r.expires_at) }],
    // 승인 전에 '무엇을 적용하는지'를 반드시 보여준다(내용 없이 승인 금지). request_payload가 핵심.
    // 요청자는 위 columns에서 이름/이메일로 이미 보여주므로 여기선 원시 ID만(대조용). 결정자는
    // approval_view가 requester_name과 마찬가지로 approver_name/approver_email을 함께 돌려준다
    // (app/approvals/service.py) — 원시 UUID 대신 그 이름을 보여준다.
    // request_payload를 원시 JSON 한 덩어리(예: document.publish의 {"generation_id":...})가 아니라 최상위
    // 키/값 행으로 펼쳐 승인 전에 '무엇을 적용하는지' 읽기 쉽게 보여준다(내용 없이 승인 금지). 중첩은 JSON.
    detailFields: [field("object_id", "대상 ID"),
      // 요청자는 서버가 이름/이메일을 함께 준다(app/approvals/service.py approval_view).
      // 예전에는 목록에만 이름을 쓰고 상세는 UUID 만 남겼는데, 상세는 **결재하기 직전에
      // 보는 화면**이라 거기서 누구인지 못 읽으면 목록으로 되돌아가야 했다.
      personField("requested_by", "요청자", "requester_name", "requester_email"),
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
    // 승인/거절 권한은 role 하나로 못 정한다(FN-11) — 위임받은 대리 결재자는 admin/system_admin이
    // 아니어도 결재할 수 있다(app/approvals/delegation.py). 그래서 여기 static roles: 게이트를
    // 안 쓰고, 서버가 role+위임을 이미 합쳐 계산해 준 r.can_decide를 그대로 믿는다(approval_view의
    // overdue와 같은 원칙 — 판단은 서버 한 곳에서만). 취소는 위임과 무관한 별개 권한이라(백엔드도
    // require_roles로 고정) 아래 static roles: OPS_ROLES를 그대로 둔다.
    actions: [
      // 자기 요청은 자기 승인·거절이 백엔드에서 금지된다(403) → 본인 요청 행에서는 두 버튼을 숨긴다(취소만 남긴다).
      { label: "승인", variant: "primary", when: (r, ctx) => !APPROVAL_DONE.includes(r.status) && (!ctx || r.requested_by !== ctx.userId) && !!r.can_decide, path: (r) => "/api/admin/approvals/" + r.id + "/approve",
        fields: [{ name: "comment", label: "승인 메모(선택)", type: "textarea", help: "승인 사유, 조건 등을 남기면 감사 기록에 함께 저장됩니다." }] },
      // 거절은 되돌릴 수 없다 — 한 번 결정된 요청은 백엔드가 어떤 재결정도 409로 막는다
      // ("이미 처리된 승인 요청입니다", app/approvals/service.py). 사유 입력 폼은 '무엇을 적을지'만
      // 묻지 '무슨 일이 일어나는지'는 말하지 않았다 — 같은 저장소의 다른 되돌릴 수 없는 액션(공지
      // 삭제·상한 삭제)처럼 확인을 먼저 받는다. document.publish 거절은 대상 문서 생성까지 실패로
      // 확정한다(_fail_pending_document_publish) — 그 파급을 요청 유형별로 밝힌다.
      { label: "거절", variant: "danger", when: (r, ctx) => !APPROVAL_DONE.includes(r.status) && (!ctx || r.requested_by !== ctx.userId) && !!r.can_decide, path: (r) => "/api/admin/approvals/" + r.id + "/reject",
        confirm: (r) => "이 요청을 거절하면 되돌릴 수 없습니다. 같은 건을 다시 승인할 방법이 없고 요청자가 새로 요청해야 합니다."
          + (r.request_type === "document.publish" ? " 이 요청은 문서 발행 건이라, 거절하면 대상 문서 생성도 실패로 확정됩니다." : "")
          + " 계속 거절할까요?",
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
  "approval-delegations": {
    key: "approval-delegations", area: "자동화", title: "승인 위임",
    endpoint: "/api/admin/approval-delegations",
    help: "결재자가 자리를 비우는 동안 다른 사람이 대신 승인할 수 있게 합니다. 위임을 받은 사람은 평소 승인 권한이 없어도 위임 기간에만 결재할 수 있고, 그 결재에는 누구를 대신했는지가 함께 기록됩니다. 기간이 지나면 저절로 닫힙니다.",
    emptyTitle: "추가된 위임이 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 위임 추가’로 부재 기간과 대리 승인자를 지정하세요.", "위임은 관리자가 추가합니다."),
    emptySituation: "결재자가 휴가를 가면 승인 큐가 그동안 멈춥니다.",
    emptyPrerequisite: "위임하는 사람(승인 권한이 있는 계정)과 대신할 사람의 사용자 ID가 필요합니다.",
    emptySteps: ["‘+ 위임 추가’에 두 사람의 ID와 기간을 적습니다.", "기간이 시작되면 상태가 ‘진행 중’이 됩니다.", "일찍 끝내려면 ‘위임 거두기’를 누릅니다."],
    emptyExpected: "위임 기간에는 대리 승인자가 승인, 거절을 할 수 있고, 결재 기록에 대신한 사람이 남습니다.",
    createLabel: "+ 위임 추가",
    searchFields: ["delegator_name", "delegate_name", "reason"],
    searchPlaceholder: "이름으로 검색",
    filters: [{ key: "state", type: "select", label: "상태", options: opt([["active", "진행 중"], ["scheduled", "예정"], ["ended", "종료"], ["revoked", "거둠"]]) }],
    columns: [
      // SEM-01: 첫 열이 render라 표식 없이는 모든 위임이 "상세 보기"로 동일했다 — 위임한
      // 사람→대리 승인자를 합쳐 실제로 구별되는 이름을 만든다.
      { key: "delegator_name", label: "위임한 사람", render: (r) => r.delegator_name || r.delegator_user_id, rowName: (r) => (r.delegator_name || r.delegator_user_id) + " → " + (r.delegate_name || r.delegate_user_id) },
      { key: "delegate_name", label: "대리 승인자", render: (r) => r.delegate_name || r.delegate_user_id },
      { key: "state", label: "상태", render: (r) => React.createElement(Badge, {
        value: ({ active: "진행 중", scheduled: "예정", ended: "종료", revoked: "거둠" })[r.state] || r.state,
        kind: r.state === "active" ? "ok" : r.state === "scheduled" ? "info" : "neutral",
      }) },
      dateCol("starts_at", "시작"),
      // SEC-05 — 거둔(revoked) 위임은 원래 예정됐던 ends_at을 그대로 보여주면 "그날까지 아직
      // 진행 중"으로 오해하게 만든다(실제로는 revoked_at에 이미 끝났다). 승인 화면의 만료
      // 열이 같은 이유로 종료된 행엔 원래 시각을 안 보여주는 것(위 expires_at 열 주석)과
      // 같은 판단 — 여기는 대체할 실제 종료 시각(revoked_at)이 있으므로 그걸 보여준다.
      { key: "ends_at", label: "종료", render: (r) => fmtDateTime(r.state === "revoked" ? r.revoked_at : r.ends_at) },
      truncateCol("reason", "사유", 40),
    ],
    detailFields: [field("id", "위임 ID"), field("delegator_email", "위임한 사람 이메일"),
      field("delegate_email", "대리 승인자 이메일"), dateCol("revoked_at", "거둔 시각"), dateCol("created_at", "추가")],
    create: { roles: WRITE_ROLES, fields: [
      { name: "delegator_user_id", label: "위임하는 사람(사용자 ID)", type: "text", required: true, help: "승인 권한이 있는 계정이어야 합니다(관리자, 시스템 관리자). ‘사용자’ 화면에서 ID를 복사하세요." },
      { name: "delegate_user_id", label: "대리 승인자(사용자 ID)", type: "text", required: true, help: "이 사람은 위임 기간에만 승인, 거절을 할 수 있습니다." },
      { name: "starts_at", label: "시작", type: "datetime-local", required: true },
      { name: "ends_at", label: "종료", type: "datetime-local", required: true, help: "최대 90일. 기간이 지나면 권한이 저절로 닫힙니다." },
      { name: "reason", label: "사유", type: "text", help: "예: 7/20~7/25 휴가" },
    ] },
    actions: [
      { label: "위임 거두기", variant: "danger", roles: WRITE_ROLES, when: (r) => r.state === "active" || r.state === "scheduled",
        path: (r) => "/api/admin/approval-delegations/" + r.id + "/revoke",
        confirm: "이 위임을 지금 거둘까요? 대리 승인자는 즉시 결재할 수 없게 됩니다." },
      { label: "승인 큐 보기", navigate: () => "#/approvals" },
      // approval_delegation은 감사 로그의 유효한 object_type이고(app/approvals/router.py
      // delegations_router) 이제 OBJ_ROUTE에도 있다 — 다른 쓰기 화면들과 동일한 딥링크를
      // 추가한다(MEGA CYCLE G).
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=approval_delegation&object_id=" + r.id },
    ],
  },
  audit: {
    key: "audit", area: "감사", title: "감사 로그", endpoint: "/api/admin/audit",
    // PA-RC-0024: /audit/:id 라우트가 AdminRoutes.jsx에 등록돼 있다 — DataScreen이 이
    // 플래그를 보고 sel(상세 선택)을 그 경로와 동기화한다(직접 진입·새로고침·뒤로가기).
    // 이 플래그가 없는 다른 registry 화면은 :id 라우트 자체가 없으므로 절대 켜면 안 된다
    // (없는 경로로 navigate하면 방금 연 상세가 "찾을 수 없음"으로 잘못 보인다).
    hasIdRoute: true,
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
    // result 도 받는다 — 이상 징후의 '실패만 보기'가 `?user_id=…&result=failure` 로 보내는데,
    // 여기에 없으면 그 조건이 조용히 버려져 **그 사람의 로그 전체**가 열렸다(F7). 반만 걸러진
    // 화면을 '실패만'이라고 믿는 것은 아무것도 안 거른 것보다 나쁘다.
    // action 도 받는다 — 임퍼소네이션 화면의 '감사 로그에서 보기'가 `?action=impersonation.start`로
    // 보내는데(governance.js impersonation.headerActions), 이 화면의 filters엔 action이 이미 있어
    // 첫 진입(parseView)은 정상 동작하지만 여기(onQuery)엔 없어서, 감사 화면을 이미 열어 둔 채
    // (라우트가 그대로라 리마운트되지 않는다) 같은 링크를 다시 타면 그 조건만 조용히 버려져
    // **감사 로그 전체**가 열렸다(result와 동일한 F7 부류의 결함).
    onQuery: (p) => (p.object_type || p.object_id || p.user_id || p.result || p.action)
      ? { open: "filter", values: { object_type: p.object_type, object_id: p.object_id, user_id: p.user_id, result: p.result, action: p.action } }
      : null,
    paginated: true,
    // 백엔드 최대 100(app/core/pagination.py MAX_PAGE_SIZE)까지 지원하는데 기본값 20에 머물러 있었다
    // — 감사·조사 화면 특성상(넓은 기간을 훑어야 함) 페이지당 더 많이 받아 클릭 수를 줄인다.
    pageSize: 100,
    // VIS-58: 한 페이지 100행이면 표가 6,014px까지 늘어나 "언제·누가·무엇을·결과"를 대조하는
    // 이 화면의 목적 자체가 스크롤 30행쯤부터 무너진다(열 제목이 사라짐). DataTable의
    // stickyHeader(kit.jsx, MUI Table stickyHeader 위임)로 스크롤 중에도 열 제목이 고정되게 한다.
    stickyHeader: true,
    filters: [
      // OBJTYPE_OPTS(shared.js)에는 organization·feature_flag가 빠져 있었다 — 둘 다 백엔드가
      // 실제로 기록하는 object_type이고(app/org/router.py, app/admin/feature_flags.py), 이
      // 화면과 같은 파일(governance.js)의 organizations·feature-flags가 아니라 org.js/platform.js가
      // "감사 로그에서 보기"로 각각 ?object_type=organization / ?object_type=feature_flag 딥링크를
      // 이미 건다(org.js:76, platform.js:288) — 그런데 이 드롭다운엔 그 값을 고를 옵션이 없어서
      // 딥링크로 들어오면 필터는 서버에 그대로 실려 정상 작동하지만(값 자체는 select 컴포넌트가
      // 검증하지 않는다) 드롭다운은 어떤 옵션과도 맞지 않아 빈 채로 보이고, 사용자가 직접 '조직'
      // 이나 '기능 플래그' 대상만 골라 보려 해도 목록에 없어 고를 수 없었다(F15와 동일한 부류 —
      // 감사 대상 옵션 누락). shared.js의 OBJTYPE_OPTS 자체는 이 작업의 편집 범위 밖이라(governance.js
      // 만 손볼 수 있다) 이 화면이 실제로 쓰는 옵션 목록에서 두 값을 보강한다.
      // ai_quota/approval_delegation/announcement/offboarding_run도 organization/feature_flag와
      // 같은 이유(F15 부류)로 여기 보강한다 — shared.js의 OBJ_ROUTE에는 이제 있지만 OBJTYPE_OPTS
      // 자체는 여전히 이 작업의 편집 범위 밖이다(MEGA CYCLE G).
      { key: "object_type", type: "select", label: "대상", options: [...OBJTYPE_OPTS,
        { value: "organization", label: "조직" }, { value: "feature_flag", label: "기능 플래그" },
        { value: "ai_quota", label: "AI 사용 상한" }, { value: "approval_delegation", label: "승인 위임" },
        { value: "announcement", label: "공지 배너" }, { value: "offboarding_run", label: "오프보딩" }] },
      // 특정 엔티티에 일어난 모든 사건을 추적한다(상세의 '대상 ID'·부서/직책 상세 id를 붙여넣는다).
      { key: "object_id", type: "text", label: "대상 ID" },
      // 감사 action은 백엔드가 정확 일치(==)로 필터한다(router: AuditLog.action == action). 실제 값은
      // '대상.동작'을 조합한 열린 네임스페이스라(예: user.update, prompts.update_content, cli.user.enable,
      // user.role_change_requested) 유한한 select로 담으면 유효한 값을 가려 버린다 — 정확한 문자열을
      // 그대로 입력받는 자유 입력을 유지하되, 라벨로 정확 일치임을 분명히 한다.
      // '작업'은 정확 일치 자유 입력인데, 목록의 '작업' 열은 한국어 번역만 보여줘(원문은 hover title뿐)
      // 필터에 뭘 입력해야 할지 알 방법이 없었다 — 현재 페이지의 실제 action 문자열로 자동완성 제안을 준다.
      { key: "action", type: "text", label: "작업(정확히, 예: user.update)", datalistFrom: (items) => items.map((r) => r.action) },
      // VIS-59: 로그인/로그아웃이 같은 대상 ID로 수십 행씩 연속돼 실제로 봐야 할 사건
      // (실패·설정 변경 등)이 그 사이에 묻힌다. action(하나만 골라 좁히는 정확 일치)과는
      // 반대 방향이 필요해서 별도 필터로 둔다 — exclude_actions는 이것만 빼고 전부 보여준다
      // (백엔드 app/audit/router.py, 쉼표로 구분된 action 목록을 받는다).
      { key: "exclude_actions", type: "select", label: "표시 범위",
        options: [{ value: "user.login,user.logout", label: "로그인/로그아웃 제외" }] },
      { key: "user_id", type: "text", label: "행위자 ID" },
      // 실패만 격리하는 것은 보안 감사에서 가장 자주 필요한 질의다(로그인 실패·비밀번호 변경
      // 실패). 백엔드는 예전부터 이 조건을 받고 있었고(app/audit/router.py `_filtered_stmt`,
      // 목록과 CSV 내보내기가 같은 질의를 쓴다) 화면도 '결과' 열을 보여 주면서, 정작 그 값으로
      // 좁힐 방법만 없었다. 값은 서버 계약 그대로다(AuditLog.result 는 success/failure 뿐).
      { key: "result", type: "select", label: "결과", options: opt([["success", "성공"], ["failure", "실패"]]) },
      // 상관 id 로 찾기 (Z8). 이 값은 상세 패널에 **보이기만 했고 그것으로 찾을 수가 없었다**.
      // 사용자가 오류 화면의 '문의 번호'를 불러 주면 그대로 붙여넣어 그 요청 하나를 짚는다 —
      // 새벽 3시에 "화면이 안 나와요" 를 받았을 때 경로와 상태 코드 말고 쓸 것이 생긴다.
      { key: "request_id", type: "text", label: "문의 번호(요청 ID)" },
      // 백엔드 _parse_boundary(app/audit/router.py)는 하루 단위가 아니라 시각(오프셋 포함 ISO-8601)까지
      // 정밀하게 필터할 수 있는데, <input type="date">로는 하루 경계만 만들 수 있어 그 정밀도가
      // 화면에서 닿지 않았다 — datetime-local로 바꿔 시:분까지 지정하고 KST(+09:00)로 변환해 보낸다.
      { key: "since", type: "datetime-local", label: "시작 시각(KST)" },
      { key: "until", type: "datetime-local", label: "종료 시각(KST)" },
    ],
    // 행위자는 이름 → 이메일 → (UUID) 순으로 표시하고, user_id가 없으면 시스템/CLI 동작이므로 '시스템'.
    // SEM-01: 첫 열(시각)이 dateCol(render 있음)이라 표식 없이는 페이지 100건이 전부 "상세
    // 보기"였다 — 작업·행위자·시각을 합쳐 실제로 구별되는 이름을 만든다(마지막 요소인
    // 행위자 판정은 바로 아래 '행위자' 열과 동일한 우선순위: 이름 → 이메일 → 시스템).
    columns: [{ ...dateCol("created_at", "시각"), rowName: (r) => actionKo(r.action) + " / " + (r.actor_name || r.actor_email || (r.user_id ? r.user_id : "시스템")) + " / " + fmtDateTime(r.created_at) }, actionCol("action", "작업"), objCol("object_type", "대상"),
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
      // 대상 유형이 OBJ_ID_PARAM에 있으면(workflow/integration/schedule/runner/job/user_notion_mapping/
      // document_generation) 그 화면이 ?id= 딥링크를 지원하므로 목록이 아니라 그 행 하나를 직접 연다
      // — 라벨도 실제 동작대로 '관련 항목 보기'로 구분한다(예전엔 이 딥링크 인프라가 있는데도 아무
      // 곳에서도 쓰지 않아, jobs.onQuery의 '감사 로그/알림에서 딥링크' 주석이 거짓이었다).
      { label: "관련 항목 보기", when: (r, ctx) => !!OBJ_ROUTE[r.object_type] && !!OBJ_ID_PARAM[r.object_type] && !!r.object_id && canReachObjRoute(r.object_type, ctx && ctx.role), navigate: (r) => objRouteHref(r.object_type, r.object_id) },
      // 그 외(딥링크 미지원 대상 유형, 또는 object_id 없음)는 여전히 목록 전체로만 이동한다 — 라벨을
      // 실제 동작대로 정직하게 맞춘다. schedule_run도 포함한다 — '#/schedules'로 보내도 특정 실행
      // 행을 찾아 주지는 못하지만(스케줄 화면에 그런 딥링크가 없다), 목록 전체로라도 보내는 게 아무
      // 동작도 없는 것보다는 낫다(알림 화면 registry/notifications.js가 이미 같은 이유로 schedule_run을
      // 포함하도록 고쳐졌다 — 이 화면만 옛 제외를 그대로 두고 있었다).
      { label: "관련 목록 열기", when: (r, ctx) => !!OBJ_ROUTE[r.object_type] && !(OBJ_ID_PARAM[r.object_type] && r.object_id) && canReachObjRoute(r.object_type, ctx && ctx.role), navigate: (r) => OBJ_ROUTE[r.object_type] },
    ],
  },
  "audit-anomalies": {
    key: "audit-anomalies", area: "감사", title: "감사 이상 징후",
    endpoint: "/api/admin/audit/anomalies",
    help: "감사 로그에서 눈여겨볼 만한 것을 규칙으로 골라냅니다. 통계 모델이나 AI가 아니라 셀 수 있는 사실만 봅니다. 그래서 같은 데이터면 언제 열어도 같은 결과가 나오고, 각 항목에 왜 걸렸는지(근거, 임계값)가 함께 표시됩니다. 여기 걸렸다고 곧바로 문제인 것은 아니며, 확인할 대상을 좁혀 주는 목록입니다.",
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
        critical_action: "권한, 계정 변경", new_actor_action: "처음 하는 동작",
      }),
      { key: "actor_name", label: "행위자", render: (r) => r.actor_name || r.actor_id || "시스템" },
      /* SEM-01: 첫 열(중요도)이 render라 표식 없이는 전부 "상세 보기"였다 — 처음엔 서버가
       * 만들어 주는 요약 문장(title)을 그대로 rowName으로 썼는데(app/audit/anomalies.py의
       * _finding), 그 title이 실제로는 **kind별 고정 문자열**이라는 것을 WF1 R1 재검증 중
       * 발견했다("실패가 몰려 있습니다" 등, 행위자·건수와 무관하게 항상 같다) — 같은 kind로
       * 두 사람이 함께 걸리면(흔한 일이다, 예: 같은 날 두 관리자가 각자 실패 급증) 두 행의
       * rowName이 완전히 같아져 SEM-01이 이 화면에서는 실제로 안 고쳐진 것과 같았다. 화면에
       * 이미 있는 행위자로 보강해 행마다 실제로 구별되게 한다 — 동시에 요약 열이 유형 열과
       * 같은 말만 반복하던 것(WF1 High 발견)도 함께 없어진다. */
      { key: "title", label: "요약", render: (r) => (r.title || "이상 징후") + " / " + (r.actor_name || r.actor_id || "시스템"),
        rowName: (r) => (r.title || "이상 징후") + " / " + (r.actor_name || r.actor_id || "시스템") },
      { key: "count", label: "건수", align: "right" },
      dateCol("last_at", "마지막"),
    ],
    detailFields: [
      field("detail", "설명"),
      { key: "evidence", label: "근거", render: (r) => (r.evidence || []).join(", ") || "-" },
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
  rbac: {
    key: "rbac", area: "사용자와 권한", title: "권한 매트릭스", endpoint: "/api/admin/rbac-matrix",
    // 이 표는 역할(role) 축 하나만 보여준다 — role=admin 은 admin_scope(전체/조직/부서)로
    // 추가로 좁혀질 수 있는데(app/core/scope.py), 그 축이 이 매트릭스 어디에도 안 보이면
    // "부서 관리자가 왜 남의 부서를 못 보는지" 이 화면만 봐서는 알 수 없다. 그 범위 설정
    // 자체는 사용자 관리(admin_scope 필드)에서 하므로 여기서는 안내만 한다.
    help: "누가 무엇을 할 수 있는지 한 화면에서 봅니다. 이 표는 서버의 권한 정의(app/core/authz.py) 하나에서 그대로 옵니다. 화면이 따로 들고 있는 사본이 없으므로 규칙을 고치면 이 표도 함께 바뀝니다. "
      + "이 표는 역할(role) 기준이며, admin 역할은 관리 범위(전체/조직/부서)로 추가로 좁혀질 수 있습니다. 범위는 여기가 아니라 '사용자 관리'의 대상 사용자 수정에서 설정합니다. '관리자' 열에 마우스를 올리면 범위별 설명을 볼 수 있습니다.",
    emptyTitle: "권한 정의를 불러오지 못했습니다", emptyHelp: "잠시 후 다시 시도해 주세요.",
    // 열이 곧 역할이라 서버 응답에서 만든다 — 여기에 역할 배열을 적으면 두 벌이 되고,
    // 백엔드에서 규칙을 고쳐도 이 표만 옛 열을 계속 보여 준다(tests/security/test_rbac_matrix.py가 고정).
    columnsFrom: (data) => [
      col("capability", "할 수 있는 일"),
      col("area", "영역"),
      ...((data && data.roles) || []).map((role) => ({
        key: "role_" + role.value,
        // 범위(scope)가 걸리는 열에만, 서버가 실제로 돌려준 scopes(app/core/authz.py
        // SCOPE_LABELS)로 툴팁을 붙인다 — 어느 역할인지도 data.scoped_role 로 서버가 알려준다
        // (역할 이름을 여기 손으로 적으면 tests/security/test_rbac_matrix.py 가 잡는다).
        // 고정 문구가 아니라 응답 데이터를 그대로 읽으므로 백엔드에서 범위 설명이 바뀌면
        // 이 툴팁도 따라 바뀐다. 열의 접근 가능한 이름(role.label, 예: "관리자")은 그대로
        // 둔다 — describeChild:true 라야 Tooltip이 title을 aria-describedby(설명)로만 붙이고
        // aria-label로 accessible name 자체를 덮어쓰지 않는다(기본값은 반대다, MUI
        // Tooltip.js: describeChild 기본 false면 title이 aria-label이 되어 "관리자"라는
        // 이름이 사라진다) — tests/…/rbac-matrix.test.jsx의 열 이름 단정과 공존해야 한다.
        label: data && role.value === data.scoped_role && Array.isArray(data.scopes) && data.scopes.length
          ? React.createElement(
              Tooltip,
              { title: adminScopeTooltip(data.scopes), describeChild: true },
              React.createElement("span", null, role.label),
            )
          : role.label,
        align: "center",
        render: (r) => (r.allowed || []).includes(role.value)
          ? React.createElement(Badge, { value: "허용", kind: "ok" })
          : React.createElement("span", { "aria-label": "허용 안 됨" }, "—")  // clovi-allow-glyph: 권한 매트릭스의 '허용 안 됨' 표시. 글리프 자체가 내용이다,
      })),
    ],
    // 이 화면에는 필터를 두지 않는다(전수조사가 '필터 0개'로 지목했지만 의도한 0개다).
    // 표는 app/core/authz.py의 CAPABILITIES 열 줄이 전부이고, 페이지네이션도 없다 —
    // '길어지면 못 찾는다'가 성립하지 않는 크기다. 그리고 '영역' 필터를 만들려면 그 영역
    // 목록을 여기 한 벌 더 적어야 하는데, 그 순간 이 파일의 대전제(역할, 영역은 authz.py
    // 한 곳에서만 정한다 — 위 columnsFrom 주석)가 깨진다. 좁혀 볼 필요는 검색이 받는다.
    // 검색은 '할 수 있는 일'과 '영역'만 대상으로 — 기본(JSON.stringify)이면 allowed 배열의
    // 원시 역할 값('system_admin')까지 매칭해 화면에 안 보이는 값으로 결과가 걸린다.
    searchFields: ["capability", "area", "note"],
    searchPlaceholder: "권한 이름으로 검색",
    detailFields: [field("id", "권한 키"), field("note", "설명"),
      { key: "allowed", label: "허용 역할", render: (r) => (r.allowed || []).join(", ") || "-" }],
  },
  /* ── 관리자 백로그 잔여 (PLAN Phase 6, 마이그레이션 0033) ───────────────────
   *
   * 아래 여덟 화면은 전부 DataScreen 계약에 맞췄다. 새 화면 컴포넌트를 만들지 않은 이유:
   * 목록 + 필터 + 상세 드로어 + 액션이라는 모양이 이미 이 계약 그대로이고, 손으로 쓰면
   * 401 처리·페이지네이션·"검색 결과 없음"과 "데이터 없음" 구분을 화면마다 다시 유도해야
   * 한다(그리고 매번 조금씩 다르게 된다). 달력(스케줄러)만 표로 표현할 수 없어 별도 화면이다.
   */
  impersonation: {
    key: "impersonation", area: "사용자와 권한", title: "임퍼소네이션(대리 보기)",
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
    emptyExpected: "시작, 종료가 이 목록과 감사 로그에 남고, 그동안의 쓰기 시도는 전부 차단되며 횟수가 기록됩니다.",
    paginated: true,
    // actor_user_id/target_user_id는 백엔드가 이미 받는 서버 필터다(app/impersonation/router.py
    // list_sessions) — 그런데 이 배열에 없으면 DataScreen.buildUrl()이 config.filters에 있는 키만
    // 서버로 보내므로(serverFilterDefs), 아래 '이 관리자의 기록만' 액션과 onQuery 딥링크가 filters
    // 상태에 넣는 값이 실제 요청에는 실리지 않는다 — 열린 화면은 전체 기록인데 '이 관리자만
    // 걸러 준 화면'으로 오인하게 된다(감사 이상 징후의 result 필터 F7과 동일한 부류의 결함).
    filters: [
      { key: "active", type: "select", label: "진행 중", options: opt([["true", "진행 중"], ["false", "종료됨"]]) },
      { key: "actor_user_id", type: "text", label: "관리자 ID" },
      { key: "target_user_id", type: "text", label: "대상 사용자 ID" },
    ],
    columns: [
      // SEM-01: 첫 열이 render라 표식 없이는 모든 기록이 "상세 보기"로 동일했다 — 관리자→
      // 대상을 합쳐 실제로 구별되는 이름을 만든다(delegations와 동일한 패턴).
      { key: "actor_name", label: "관리자", render: (r) => r.actor_name || r.actor_user_id, rowName: (r) => (r.actor_name || r.actor_user_id) + " → " + (r.target_name || r.target_user_id) },
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
        result: () => ({ ok: true, msg: "대리 보기를 시작했습니다. 화면을 다시 불러옵니다. 위쪽 띠에서 종료할 수 있습니다." }) },
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
};
