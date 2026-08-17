/* AI 저작물 — 프롬프트·정책·템플릿과 그 사용 통계.
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
import { Badge, OBJTYPE_OPTS, TEMPLATE_TARGET_OPTS, WRITE_ROLES, badgeCol, col, dateCol, field, jsonField, mapCol, opt, truncateCol, writerEmptyHelp } from "./shared.js";
import { TEMPLATE_SCHEMA_FIELDS, assembleInputSchema, disassembleInputSchema, nameVersionsAction, onoff } from "./actions.js";

export const AUTHORING_SCREENS = {
  prompts: {
    key: "prompts", area: "연동", title: "프롬프트", endpoint: "/api/admin/prompts",
    // 워크플로 화면의 '테스트'가 실제 실행이 아니라 도달성만 확인한다고 밝히듯, 여기도 상태 전이
    // 버튼이 내용 검증을 뜻하지 않는다는 점을 밝힌다(전이는 순수 상태 기록일 뿐 — app/prompts/service.py).
    help: "AI에게 주는 지시문을 버전으로 관리합니다. ‘테스트로’, ‘검토로’, ‘발행’은 상태만 바꿀 뿐, 러너로 실제 실행하거나 내용을 검증하지 않습니다. 내용 검증은 화면 밖에서 직접 확인하세요. 발행하면 이 프롬프트 이름을 참조하는 템플릿이 다음 문서 생성부터 이 버전을 사용하게 됩니다.",
    emptyTitle: "추가된 프롬프트가 없습니다",
    // 읽기 전용 역할(operator/auditor)에는 렌더되지 않는 '+ 추가' 버튼을 누르라고 안내하지 않는다.
    // 안내 문구의 생명주기는 실제 강제되는 전이(draft→test→review→published)에 맞춘다('테스트' 단계 포함).
    emptyHelp: writerEmptyHelp("‘+ 프롬프트 추가’로 AI에게 줄 지시문을 추가해 초안→테스트→검토→발행 순으로 버전 관리하세요.", "프롬프트는 관리자가 추가합니다. 추가되면 버전이 여기에 표시됩니다."),
    // 다른 온보딩 화면(연동/러너)처럼 단계별 안내를 준다(생명주기: 초안→테스트→검토→발행).
    emptySituation: "AI에게 줄 지시문(프롬프트)이 아직 하나도 없습니다.",
    emptySteps: ["‘+ 프롬프트 추가’로 초안을 추가합니다.", "‘테스트로 → 검토로’ 순으로 상태를 올립니다.", "‘발행’하면 이 이름을 참조하는 템플릿이 다음 문서 생성부터 이 버전을 사용합니다."],
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
      { key: "runner_id", label: "러너 ID", render: (r) => r.runner_id ? React.createElement(Link, { underline: "hover", href: "#/runners?id=" + encodeURIComponent(r.runner_id) }, r.runner_id) : "-" },
      col("version", "버전"), badgeCol("status", "상태"), dateCol("created_at", "추가")],
    // 상세에서 실제 지시문(발행본 포함)을 읽을 수 있게 — 편집은 초안만이라 그 외엔 읽기 전용으로 노출.
    // purpose·runner_id는 이제 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
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
      { name: "runner_id", label: "러너 ID(선택)", type: "text", help: "이 프롬프트와 연관지을 러너의 ID(참고용 메타데이터, 이 값만으로 실행되지는 않습니다). ‘러너’ 화면에서 확인." },
      { name: "content", label: "프롬프트 내용", type: "textarea", required: true, help: "AI에게 주는 지시문입니다. 무엇을, 어떤 형식으로 만들지 구체적으로 적으세요. 예: ‘아래 티켓 목록을 프로젝트별로 묶어 주간 보고서를 마크다운 표로 요약해줘. 완료, 지연 건수를 강조할 것.’ 이 이름을 참조하는 템플릿이 문서 생성 시 이 내용을 사용합니다." },
    ] },
    // 수정은 ContentUpdateRequest(PATCH) 계약: 내용·용도만(이름은 새 버전으로만 바뀜). 초안일 때만 편집 가능(그 외 409).
    // '비우면 연결 해제'는 **거짓이었다.** kit.jsx FormModal은 값이 있던 텍스트 칸을 비우면 null을
    // 보내는데(submit의 hadValue 분기), 백엔드 PATCH는 `if payload.runner_id is not None:` 가드라
    // 그 null을 '안 보냄'과 구별하지 못하고 통째로 무시한다(app/prompts/router.py). 저장은 성공하고
    // 값은 그대로 남는다 — 화면만 해제됐다고 믿는, 가장 나쁜 종류의 거짓말이다.
    // 문구를 고치고 동작은 그대로 둔 이유: 서버 가드를 model_fields_set 기준으로 바꾸면 같은 블록의
    // purpose까지 의미가 함께 바뀌는 백엔드 계약 변경이고, 그 판정은 백엔드 테스트가 지켜야 한다.
    // 이 작업의 소유 범위는 registry.js와 그 부품이므로 서버는 손대지 않는다(노트에 남긴다).
    // 화면은 자기가 지키지 못하는 약속을 하지 않는다.
    editMethod: "PATCH", editWhen: (r) => r.status === "draft", edit: { roles: WRITE_ROLES, fields: [
      { name: "content", label: "프롬프트 내용", type: "textarea", required: true, help: "AI에게 주는 지시문입니다. 무엇을, 어떤 형식으로 만들지 구체적으로 적으세요. 예: ‘아래 티켓 목록을 프로젝트별로 묶어 주간 보고서를 마크다운 표로 요약해줘. 완료, 지연 건수를 강조할 것.’ 이 이름을 참조하는 템플릿이 문서 생성 시 이 내용을 사용합니다." },
      { name: "purpose", label: "용도", type: "textarea" },
      { name: "runner_id", label: "러너 ID(선택)", type: "text", help: "이 프롬프트와 연관지을 러너의 ID(참고용 메타데이터, 이 값만으로 실행되지는 않습니다). ‘러너’ 화면에서 확인. 비워도 기존 연결은 지워지지 않습니다. 바꾸려면 다른 러너 ID를 넣으세요." },
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
    key: "policies", area: "연동", title: "정책", endpoint: "/api/admin/policies",
    // 정책은 프롬프트보다 실제 파급력이 크다 — 발행하면 app/documents/service.py apply_template_bindings()/
    // _resolve_published_binding()가 이 정책 '이름'을 참조하는 모든 Template에 그 순간부터 현재 발행
    // 버전의 JSON을 그대로 n8n 페이로드에 inline한다(문서 생성이 다시 일어날 때마다). '테스트로'·
    // '검토로'·'발행'·'보관'은 상태만 바꿀 뿐 JSON 내용을 검증하지 않는다(프롬프트와 동일).
    help: "업무 규칙(정책)을 관리합니다. ‘테스트로’, ‘검토로’, ‘발행’, ‘보관’은 상태만 바꿀 뿐, 내용(JSON)을 검증하지 않습니다. 내용 검증은 화면 밖에서 직접 확인하세요. 발행하면 이 정책 이름을 참조하는 모든 템플릿이 그 즉시(다음 문서 생성부터) 새 버전의 JSON을 그대로 사용하게 됩니다. 프롬프트보다 실제 파급력이 큽니다.",
    // WF1 단독 결함 — 위 문장이 스스로 "프롬프트보다 실제 파급력이 크다"고 말하면서도, 배너
    // 자체는 프롬프트 화면의 일반 안내와 똑같은 기본(info) 톤이었다(DataScreen.jsx의 capWarning
    // 등 다른 배너는 이미 tone="warn"을 쓴다 — 능력은 있고 이 배너에는 안 쓰였다). warn으로 맞춘다.
    helpTone: "warn",
    emptyTitle: "추가된 정책이 없습니다",
    // 정책도 프롬프트와 동일하게 4단계 생명주기(초안→테스트→검토→발행)를 강제한다 — '등록하고
    // 발행하세요'는 마치 한 단계로 끝나는 것처럼 읽혀, 새 관리자가 초안 행에서 비활성 '발행' 버튼을
    // 만나고 이유를 못 찾았다(프롬프트 registry.js:404와 동일 문구로 맞춘다).
    emptyHelp: writerEmptyHelp("‘+ 정책 추가’로 업무 규칙(JSON)을 추가해 초안→테스트→검토→발행 순으로 버전 관리하세요.", "정책은 관리자가 추가합니다. 추가되면 버전이 여기에 표시됩니다."),
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
    // WF1 단독 결함 — purpose는 이제 Policy에도 있다(app/prompts/models.py::Policy.purpose,
    // 마이그레이션 0058). 프롬프트와 동일하게 목록 열로 노출한다 — 여러 버전이 쌓인 목록에서
    // 각 정책이 '무엇을 강제하는지' 행마다 열어보지 않고는 알 수 없었다. purpose는 최대 2000자라
    // truncateCol로 자른다(프롬프트 registry.js:53-54와 동일 패턴, 전체는 title 속성으로 확인).
    columns: [col("name", "이름"), truncateCol("purpose", "용도", 60), col("version", "버전"), badgeCol("status", "상태"), dateCol("created_at", "추가")],
    // id는 템플릿의 policy_id 입력에 쓰이므로 상세에서 확인할 수 있게 노출한다(라벨은 프롬프트의
    // '프롬프트 ID'와 맞춰 어느 화면 상세를 보고 있는지 분명히 한다 — 템플릿의 policy_id 도움말이
    // '정책 화면 상세의 ID를 입력'이라 안내한다).
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
      { name: "content", label: "규칙(JSON)", type: "json", required: true, value: '{\n  "required_fields": ["title"]\n}', help: '이 정책 이름을 참조하는 템플릿이 문서를 만들 때 n8n 페이로드에 그대로 실립니다. 업무 규칙을 JSON 객체로 적습니다. 위 기본값은 "제목은 필수"라는 뜻의 예시입니다. 필요에 맞게 바꾸세요(예: {"required_fields":["title","owner"],"min_length":10}).' },
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
    key: "templates", area: "연동", title: "템플릿", endpoint: "/api/admin/templates",
    help: "자주 하는 자동화를 템플릿으로 저장합니다. 추가 직후에는 비활성 상태이며, 비활성 템플릿은 프롬프트, 정책, 입력값 바인딩과 승인 정책이 모두 적용되지 않습니다(승인 정책만이 아닙니다), 활성화해야 전부 적용됩니다.",
    emptyTitle: "추가된 템플릿이 없습니다",
    emptyHelp: writerEmptyHelp("자주 쓰는 자동화를 템플릿으로 저장하려면 ‘+ 템플릿 추가’를 누르세요. 대상 워크플로/러너와 연결됩니다. 추가 직후에는 비활성 상태이므로 활성화해야 적용됩니다.", "템플릿은 관리자가 추가합니다. 추가되면 여기에 표시됩니다."),
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
        if (r.target_type === "workflow") return React.createElement(Link, { underline: "hover", href: "#/workflows?id=" + encodeURIComponent(r.target_ref) }, r.target_ref);
        // 러너 화면은 이제 ?id=로 특정 러너 상세를 곧바로 여는 딥링크(onQuery)를 지원한다 — 무필터
        // 전체 목록에만 떨어지던 죽은 앵커가 아니라 실제로 그 러너로 데려간다.
        if (r.target_type === "runner") return React.createElement(Link, { underline: "hover", href: "#/runners?id=" + encodeURIComponent(r.target_ref) }, r.target_ref);
        return r.target_ref;
      } },
      // badgeCol("enabled", ...)이던 시절엔 원시 불리언이 statusText를 타 "예"/"아니오"로
      // 떴다 — 바로 위 filters의 '활성'/'비활성' 어휘와 어긋났고, 비활성(생성 직후 기본값 —
      // 이 상태면 프롬프트·정책·입력값 바인딩·승인 정책이 전부 적용되지 않는다, 위 help 참고)이
      // 중립(회색) 톤이라 훑어보다 놓치기 쉬웠다. org-tree의 activeCol과 같은 이유로 이 화면의
      // 필터와 같은 어휘 + 비활성=주의 톤을 쓴다.
      { key: "enabled", label: "활성", render: (r) => React.createElement(Badge, { value: r.enabled ? "활성" : "비활성", kind: r.enabled ? "ok" : "warn" }) },
      dateCol("created_at", "추가")],
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
        ? "이 템플릿의 대상 유형은 '러너'입니다. 대상 워크플로 재지정(자동 문서 생성의 워크플로 호출)만 적용되지 않습니다. 프롬프트, 정책, 입력 스키마, 승인 정책 바인딩은 여전히 config.template_id를 통해 정상 적용됩니다."
        : "-" },
      // 프롬프트/정책 화면이 이제 ?id=로 특정 행 상세를 곧바로 여는 딥링크(onQuery)를 지원한다 —
      // 무필터 전체 목록에만 떨어지던 죽은 앵커가 아니라 실제로 그 프롬프트/정책으로 데려간다.
      { key: "prompt_id", label: "프롬프트 ID", render: (r) => r.prompt_id ? React.createElement(Link, { underline: "hover", href: "#/prompts?id=" + encodeURIComponent(r.prompt_id) }, r.prompt_id) : "-" },
      { key: "policy_id", label: "정책 ID", render: (r) => r.policy_id ? React.createElement(Link, { underline: "hover", href: "#/policies?id=" + encodeURIComponent(r.policy_id) }, r.policy_id) : "-" },
      // 비활성 템플릿은 '이 템플릿으로 문서 생성' CTA가 숨겨진다(enabled && workflow일 때만) — 왜
      // 그 버튼이 없는지 상세에서 바로 설명한다(RESERVED_WORKFLOW_NOTES와 동일한 '혼란 지점 안내' 패턴).
      { key: "_inactive_note", label: "[주의] 활성 상태", render: (r) => r.enabled ? "-" : "이 템플릿은 비활성 상태입니다. 활성화해야 문서 생성에 사용되고 프롬프트, 정책, 입력 스키마, 승인 정책 바인딩이 적용됩니다." },
      field("created_by", "작성자 ID"), jsonField("input_schema", "입력 스키마"),
      // approval_policy는 폼에선 체크박스('발행 전 승인 필요')로 다루면서 상세에선 raw JSON({"required":true})을
      // 보여줘 계약 형태가 새고 폼 어휘와 어긋났다 — 폼과 같은 어휘로 예/아니오만 보여준다.
      { key: "approval_policy", label: "승인 정책", render: (r) => "발행 전 승인 필요: " + ((r.approval_policy && r.approval_policy.required) ? "예" : "아니오") },
      dateCol("updated_at", "수정")],
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "description", label: "설명", type: "textarea" },
      { name: "target_type", label: "대상 유형", type: "select", value: "workflow", options: TEMPLATE_TARGET_OPTS },
      { name: "target_ref", label: "대상 ID", type: "text", required: true, help: "대상 유형이 워크플로면 ‘업무 자동화 흐름’ 화면에서, 러너면 ‘자동화 작업 실행기’ 화면에서 대상의 ID를 확인해 입력하세요." },
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
      { name: "target_ref", label: "대상 ID", type: "text", required: true, help: "대상 유형이 워크플로면 ‘업무 자동화 흐름’ 화면에서, 러너면 ‘자동화 작업 실행기’ 화면에서 대상의 ID를 확인해 입력하세요." },
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
  "prompt-usage": {
    key: "prompt-usage", area: "감사", title: "프롬프트 사용 통계",
    endpoint: "/api/admin/prompts/usage/stats",
    help: "프롬프트가 실제로 쓰이고 있는지 이름별로 봅니다. ‘쓰이지 않음’은 이 이름을 참조하는 템플릿, 스케줄이 없고 문서 생성에도 쓰인 적이 없다는 뜻입니다. 정리 대상을 고를 때 씁니다. 버전 비교와 되돌리기는 ‘프롬프트’ 화면의 ‘버전 기록’에서 합니다.",
    emptyTitle: "추가된 프롬프트가 없습니다",
    emptyHelp: "‘프롬프트’ 화면에서 프롬프트를 추가하면 여기에 사용 현황이 표시됩니다.",
    emptyRelatedLink: { href: "#/prompts", label: "프롬프트 화면으로 이동" },
    searchFields: ["name"],
    searchPlaceholder: "프롬프트 이름으로 검색",
    filters: [{ key: "unused", type: "select", label: "사용 여부", clientFilter: true, options: opt([["true", "쓰이지 않음"], ["false", "쓰이는 중"]]) }],
    // 열을 접지 않는다 — 접을 이유가 실측으로 확인되지 않았다. 이 표는 일곱 열이고(전수조사
    // 메모의 '아홉'은 세다 틀린 것이다), 900px 아래에서는 DataTable이 표가 아니라 카드 목록으로
    // 그린다(kit.jsx TABLE_CARD_BREAKPOINT) — 좁은 화면에서 잘리는 게 아니라 라벨과 값이 세로로
    // 쌓인다. 그 위 폭에서는 TableContainer가 스스로 가로 스크롤하므로 페이지에 가로 스크롤이
    // 생기지도 않는다. 즉 여기서 열을 숨기면 좁은 화면에서 이미 잘 보이던 값을 없애는 셈이다.
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
    key: "policy-usage", area: "감사", title: "정책 사용 통계",
    endpoint: "/api/admin/policies/usage/stats",
    help: "정책이 실제로 쓰이고 있는지 이름별로 봅니다. 정책은 발행하는 순간 그 이름을 참조하는 모든 템플릿이 다음 문서 생성부터 새 내용을 쓰므로, 어디서 쓰이는지를 먼저 확인하고 발행하세요.",
    emptyTitle: "추가된 정책이 없습니다",
    emptyHelp: "‘정책’ 화면에서 정책을 추가하면 여기에 사용 현황이 표시됩니다.",
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
