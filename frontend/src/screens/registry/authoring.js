/* AI 저작물 — 프롬프트·정책과 그 사용 통계.
 *
 * 버전을 만들고(초안 → 테스트 → 검토 → 발행) 되돌리는 세 화면이 같은 액션 묶음을 공유한다.
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

export const AUTHORING_SCREENS = {
  prompts: {
    key: "prompts", area: "AI", title: "프롬프트", endpoint: "/api/admin/prompts",
    // 상태 전이 버튼이 내용 검증을 뜻하지 않는다는 점을 밝힌다(전이는 순수 상태 기록일
    // 뿐 — app/prompts/service.py).
    help: "AI에게 주는 지시문을 버전으로 관리합니다. ‘테스트로’, ‘검토로’, ‘발행’은 상태만 바꿀 뿐, 실제로 실행하거나 내용을 검증하지 않습니다. 내용 검증은 화면 밖에서 직접 확인하세요.",
    emptyTitle: "추가된 프롬프트가 없습니다",
    // 읽기 전용 역할(operator/auditor)에는 렌더되지 않는 '추가' 버튼을 누르라고 안내하지 않는다.
    // 안내 문구의 생명주기는 실제 강제되는 전이(draft→test→review→published)에 맞춘다('테스트' 단계 포함).
    emptyHelp: writerEmptyHelp("‘+ 프롬프트 추가’로 AI에게 줄 지시문을 넣고, 초안→테스트→검토→발행 순으로 올리세요.", "프롬프트는 관리자가 추가합니다. 추가되면 버전이 여기에 표시됩니다."),
    // 다른 온보딩 화면(연동/러너)처럼 단계별 안내를 준다(생명주기: 초안→테스트→검토→발행).
    emptySituation: "AI에게 줄 지시문(프롬프트)이 아직 하나도 없습니다.",
    emptySteps: ["‘+ 프롬프트 추가’로 초안을 추가합니다.", "‘테스트로 → 검토로’ 순으로 상태를 올립니다.", "‘발행’하면 그 시점부터 이 이름의 발행본이 이 버전이 됩니다."],
    emptyExpected: "발행된 버전이 실제 사용되며, 같은 이름의 이전 발행본은 자동으로 보관됩니다.",
    createLabel: "프롬프트 추가",
    // 다른 화면이 ?id=로 넘겨주는 딥링크를 소비해 그 프롬프트의 상세 드로어를
    // 곧바로 연다(단건 GET). 이 라우터의 GET /{row_id}는 {"item":...} 모양으로 응답한다
    // (app/prompts/router.py get_one) — job 과 selectKey 가 다르다.
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
    // purpose는 최대 2000자에 create/edit 폼도 여러 줄 textarea라 자르지 않으면 표가 옆으로 밀린다
    // (list_field 상세는 여전히 truncateCol의 title 속성으로 전체 확인 가능 — 오류 열과 동일 패턴).
    columns: [{ ...col("name", "이름"), identifier: true }, truncateCol("purpose", "용도", 60),
      col("version", "버전"), badgeCol("status", "상태"), dateCol("created_at", "추가")],
    // 상세에서 실제 지시문(발행본 포함)을 읽을 수 있게 — 편집은 초안만이라 그 외엔 읽기 전용으로 노출.
    // purpose는 이제 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    detailFields: [field("id", "프롬프트 ID"),
      { key: "created_by", label: "작성자", render: (r) => r.created_by_name || r.created_by_email || r.created_by || "-" },
      // 초안이 아니면 '수정' 버튼이 통째로 사라진다(editWhen 아래) — policies와 동일한 이유로 편집
      // 안내를 남긴다(registry.js policies의 _edit_note와 동일 패턴).
      { key: "_edit_note", label: "수정 안내", render: (r) => r.status !== "draft" ? "이 버전은 초안이 아니라 수정할 수 없습니다. 아래 ‘새 버전’으로 수정 가능한 초안을 추가하세요." : "-" },
      dateCol("published_at", "발행 시각"), jsonField("content", "프롬프트 내용")],
    // purpose는 서버에서 최대 2000자까지 허용한다(app/prompts/router.py) — 한 줄 text 입력은 좁아서
    // textarea로(워크플로의 purpose 필드와 동일한 대우).
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "purpose", label: "용도", type: "textarea" },
      { name: "content", label: "프롬프트 내용", type: "textarea", required: true, help: "AI에게 주는 지시문입니다. 무엇을, 어떤 형식으로 만들지 구체적으로 적으세요. 예: ‘아래 티켓 목록을 프로젝트별로 묶어 주간 보고서를 마크다운 표로 요약해줘. 완료, 지연 건수를 강조할 것.’ 발행하면 이 이름의 발행본이 그 시점부터 쓰입니다." },
    ] },
    // 수정은 ContentUpdateRequest(PATCH) 계약: 내용·용도만(이름은 새 버전으로만 바뀜). 초안일 때만 편집 가능(그 외 409).
    editMethod: "PATCH", editWhen: (r) => r.status === "draft", edit: { roles: WRITE_ROLES, fields: [
      { name: "content", label: "프롬프트 내용", type: "textarea", required: true, help: "AI에게 주는 지시문입니다. 무엇을, 어떤 형식으로 만들지 구체적으로 적으세요. 예: ‘아래 티켓 목록을 프로젝트별로 묶어 주간 보고서를 마크다운 표로 요약해줘. 완료, 지연 건수를 강조할 것.’ 발행하면 이 이름의 발행본이 그 시점부터 쓰입니다." },
      { name: "purpose", label: "용도", type: "textarea" },
    ] },
    actions: [
      { label: "테스트로", roles: WRITE_ROLES, when: (r) => r.status === "draft", path: (r) => "/api/admin/prompts/" + r.id + "/transition", body: { status: "test" }, confirm: "이 버전을 테스트 단계로 옮길까요? 상태만 바뀔 뿐, 러너로 실제 실행되거나 내용이 검증되지는 않습니다." },
      { label: "검토로", roles: WRITE_ROLES, when: (r) => r.status === "test", path: (r) => "/api/admin/prompts/" + r.id + "/transition", body: { status: "review" }, confirm: "이 버전을 검토 단계로 옮길까요? 상태만 바뀔 뿐 내용이 검증되지는 않습니다." },
      { label: "초안으로 되돌리기", roles: WRITE_ROLES, when: (r) => r.status === "test" || r.status === "review", path: (r) => "/api/admin/prompts/" + r.id + "/transition", body: { status: "draft" }, confirm: "이 버전을 초안으로 되돌려 다시 수정할까요?" },
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
    /* C2 «Filter Surface 가 정당한가» — 이 화면은 **행 수가 유한하고 작다**(정책 2 ·
       기능 플래그 11 · 통합 4 · RBAC 13 실측). R-88 이 "25행" 을 기계 규칙으로 쓰지 말라고
       못박으므로 숫자가 아니라 **판단**을 남긴다: 조건 조합을 이름 붙여 재사용할 만큼
       탐색이 반복되지 않는다. 그래서 저장된 뷰를 그리지 않는다 — 기능이 아니라 소음이다. */
    smallSet: true,
    key: "policies", area: "AI", title: "정책", endpoint: "/api/admin/policies",
    // '테스트로'·'검토로'·'발행'·'보관'은 상태만 바꿀 뿐 JSON 내용을 검증하지 않는다
    // (프롬프트와 동일).
    help: "업무 규칙(정책)을 관리합니다. ‘테스트로’, ‘검토로’, ‘발행’, ‘보관’은 상태만 바꿀 뿐, 내용(JSON)을 검증하지 않습니다. 내용 검증은 화면 밖에서 직접 확인하세요. 발행하면 그 시점부터 이 이름의 발행본이 새 버전이 됩니다.",
    // 발행은 그 순간부터 이 이름의 발행본을 바꾼다 — 프롬프트보다 파급이 크다는 판단은
    // 그대로다. 배너를 일반 안내와 같은 톤으로 두면 그 경고가 안 읽힌다.
    helpTone: "warn",
    emptyTitle: "추가된 정책이 없습니다",
    // 정책도 프롬프트와 동일하게 4단계 생명주기(초안→테스트→검토→발행)를 강제한다 — '등록하고
    // 발행하세요'는 마치 한 단계로 끝나는 것처럼 읽혀, 새 관리자가 초안 행에서 비활성 '발행' 버튼을
    // 만나고 이유를 못 찾았다(프롬프트 registry.js:404와 동일 문구로 맞춘다).
    emptyHelp: writerEmptyHelp("‘+ 정책 추가’로 업무 규칙(JSON)을 넣고, 초안→테스트→검토→발행 순으로 올리세요.", "정책은 관리자가 추가합니다. 추가되면 버전이 여기에 표시됩니다."),
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
    // name 필터는 백엔드가 정확 일치만 지원한다(model.name == name) — 이름을 미리 몰라도 시도할
    // 수 있게, 이미 불러온 현재 페이지에서 뽑은 이름으로 자동완성 제안(datalist)을 준다.
    filters: [{ key: "name", type: "text", label: "이름(정확히)", datalistFrom: (items) => items.map((r) => r.name) },
      { key: "status", type: "select", label: "상태", value: "published", options: opt([["draft", "초안"], ["test", "테스트"], ["review", "검토"], ["published", "발행됨"], ["archived", "보관됨"]]) }],
    // WF1 단독 결함 — purpose는 이제 Policy에도 있다(app/prompts/models.py::Policy.purpose,
    // 마이그레이션 0058). 프롬프트와 동일하게 목록 열로 노출한다 — 여러 버전이 쌓인 목록에서
    // 각 정책이 '무엇을 강제하는지' 행마다 열어보지 않고는 알 수 없었다. purpose는 최대 2000자라
    // truncateCol로 자른다(프롬프트 registry.js:53-54와 동일 패턴, 전체는 title 속성으로 확인).
    columns: [{ ...col("name", "이름"), identifier: true }, truncateCol("purpose", "용도", 60), col("version", "버전"), badgeCol("status", "상태"), dateCol("created_at", "추가")],
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
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      // purpose는 서버에서 최대 2000자까지 허용한다(app/prompts/router.py) — 한 줄 text 입력은
      // 좁아서 textarea로(프롬프트 registry.js:70-71과 동일 대우).
      { name: "purpose", label: "용도", type: "textarea" },
      // 서버 기본값("{}")과 맞춘다(app/prompts/router.py PolicyCreateRequest.content) — 값 없이는
      // 다른 registry create 필드처럼 즉시 제출 가능해야 한다(예전엔 최소 "{}"라도 직접 타이핑해야 했다).
      { name: "content", label: "규칙(JSON)", type: "json", required: true, value: '{\n  "required_fields": ["title"]\n}', help: '업무 규칙을 JSON 객체로 적습니다. 위 기본값은 "제목은 필수"라는 뜻의 예시입니다. 필요에 맞게 바꾸세요(예: {"required_fields":["title","owner"],"min_length":10}).' },
    ] },
    editMethod: "PATCH", editWhen: (r) => r.status === "draft", edit: { roles: WRITE_ROLES, fields: [
      { name: "content", label: "규칙(JSON)", type: "json", required: true, help: '예: {"required_fields":["title"]}' },
      { name: "purpose", label: "용도", type: "textarea" },
    ] },
    actions: [
      { label: "테스트로", roles: WRITE_ROLES, when: (r) => r.status === "draft", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "test" }, confirm: "이 버전을 테스트 단계로 옮길까요? 상태만 바뀔 뿐, 러너로 실제 실행되거나 내용(JSON)이 검증되지는 않습니다." },
      { label: "검토로", roles: WRITE_ROLES, when: (r) => r.status === "test", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "review" }, confirm: "이 버전을 검토 단계로 옮길까요? 상태만 바뀔 뿐 내용(JSON)은 검증되지 않습니다." },
      { label: "초안으로 되돌리기", roles: WRITE_ROLES, when: (r) => r.status === "test" || r.status === "review", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "draft" }, confirm: "이 버전을 초안으로 되돌려 다시 수정할까요?" },
      { label: "발행", variant: "primary", roles: WRITE_ROLES, when: (r) => r.status === "review", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "published" }, confirm: "이 버전을 발행할까요? 발행되면 실제 사용되며, 현재 발행 중인 같은 이름의 버전은 자동으로 보관(archive)됩니다." },
      // keepSelection — 새 버전을 만드는 목적이 '바로 이어서 편집'이므로(내용은 초안일 때만 편집
      // 가능), 프롬프트의 '새 버전'과 동일하게 드로어를 닫지 않고 새 초안으로 갱신한다.
      { label: "새 버전", roles: WRITE_ROLES, when: (r) => r.status !== "draft", path: (r) => "/api/admin/policies/" + r.id + "/new-version", keepSelection: true },
      // 정책도 프롬프트와 동일하게 버전 기록 + 롤백 + 비교(diff)를 노출한다(잘못 발행된 규칙 복원 경로).
      nameVersionsAction("/api/admin/policies", "정책 버전 기록"),
      { label: "보관", variant: "danger", roles: WRITE_ROLES, when: (r) => r.status !== "archived", path: (r) => "/api/admin/policies/" + r.id + "/transition", body: { status: "archived" }, confirm: "이 버전을 보관할까요? 보관하면 더 이상 발행, 사용되지 않지만 이력으로는 목록에 남습니다." },
      // policies는 감사 로그의 유효한 object_type이고(OBJTYPE_OPTS) 모든 쓰기 액션이 이 타입으로
      // 기록된다 — 부서·직책과 동일한 딥링크를 추가한다.
      // operator는 정책 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=policies&object_id=" + r.id },
    ],
  },
  "prompt-usage": {
    key: "prompt-usage", area: "AI", title: "프롬프트 사용 통계",
    endpoint: "/api/admin/prompts/usage/stats",
    help: "프롬프트가 실제로 쓰이고 있는지 이름별로 봅니다. ‘쓰이지 않음’은 이 이름을 참조하는 스케줄이 없다는 뜻입니다. 정리 대상을 고를 때 씁니다. 버전 비교와 되돌리기는 ‘프롬프트’ 화면의 ‘버전 기록’에서 합니다.",
    emptyTitle: "추가된 프롬프트가 없습니다",
    emptyHelp: "‘프롬프트’ 화면에서 프롬프트를 추가하면 사용 현황이 여기에 표시됩니다.",
    emptyRelatedLink: { href: "#/prompts", label: "프롬프트 화면으로 이동" },
    searchFields: ["name"],
    searchPlaceholder: "프롬프트 이름으로 검색",
    filters: [{ key: "unused", type: "select", label: "사용 여부", clientFilter: true, options: opt([["true", "쓰이지 않음"], ["false", "쓰이는 중"]]) }],
    // 열을 접지 않는다 — 접을 이유가 실측으로 확인되지 않았다. 900px 아래에서는 DataTable이
    // 표가 아니라 카드 목록으로 그린다(kit.jsx TABLE_CARD_BREAKPOINT) — 좁은 화면에서 잘리는
    // 게 아니라 라벨과 값이 세로로 쌓인다. 그 위 폭에서는 TableContainer가 스스로 가로
    // 스크롤하므로 페이지에 가로 스크롤이 생기지도 않는다.
    columns: [
      { ...col("name", "이름"), identifier: true },
      { key: "unused", label: "사용", render: (r) => React.createElement(Badge, { value: r.unused ? "쓰이지 않음" : "쓰이는 중", kind: r.unused ? "warn" : "ok" }) },
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
      { label: "이 프롬프트 버전 보기", navigate: (r) => "#/prompts?name=" + encodeURIComponent(r.name) },
    ],
    headerActions: [
      { label: "정책 사용 통계", navigate: () => "#/policy-usage" },
    ],
  },
  "policy-usage": {
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
      { key: "unused", label: "사용", render: (r) => React.createElement(Badge, { value: r.unused ? "쓰이지 않음" : "쓰이는 중", kind: r.unused ? "warn" : "ok" }) },
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
    headerActions: [
      { label: "프롬프트 사용 통계", navigate: () => "#/prompt-usage" },
    ],
  },
};
