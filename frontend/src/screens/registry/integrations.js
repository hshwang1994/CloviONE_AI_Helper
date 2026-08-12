/* 외부 연동 배관 — 연동·러너·워크플로.
 *
 * 이 셋은 한 덩어리다. 워크플로는 러너와 연동을 가리키고, '연결 확인'·'테스트' 결과 문구도
 * 같은 어휘를 쓴다. 하나를 고치면 대개 나머지도 함께 본다.
 *
 * registry.js 를 쪼갠 조각이다 (E-10). 쪼갠 축은 '줄 수'가 아니라 **관리자가 한 번에
 * 함께 보는 묶음**이다 — 줄 수를 맞추려고 아무 데나 자르면 화면 하나를 고치는 데
 * 파일 셋을 열게 되어 오히려 더 나빠진다.
 *
 * 화면 설정만 있고 그리는 코드는 없다. 그리는 것은 DataScreen.jsx 하나다.
 */
import React from "react";
import { AUTH_OPTS, Badge, HTTP_OPTS, OPS_ROLES, PROVIDER, PROVIDER_OPTS, RESERVED_WORKFLOW_NOTES, RUNNER_MAINT_OPTS, WFMODE_OPTS, WF_MODE, WRITE_ROLES, badgeCol, col, dateCol, field, mapCol, opt, reservedDisableConfirm, truncateCol, writerEmptyHelp } from "./shared.js";
import { healthResult, onoff, reachResult, snapCol, testResult, versionsAction } from "./actions.js";
import { serviceLabel } from "../ops/opsHelpers.js";

export const INTEGRATION_SCREENS = {
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
    columns: [
      // WF1 R2 재검증(admin_integration-detail) — name은 discovery.py의 idempotency 조회 키
      // 겸 systemd 유닛 이름이라(예: "claude-request-interpreter") 슬러그 그대로 저장된다 —
      // 저장된 값 자체는 안 바꾼다(다른 로직이 그 값으로 조회한다). ops 화면(Diagnostics.jsx 등,
      // ops/opsHelpers.js::serviceLabel)은 이미 알려진 4종 슬러그를 전부 사람이 읽는 이름으로
      // 바꿔 보여주는데(SERVICE_LABELS), 이 화면만 그 규칙을 안 썼다 — 목록과 상세 드로어 제목
      // (declaredRowName이 이 rowName을 그대로 쓴다) 모두에 원시 슬러그가 그대로 샜다.
      // 관리자가 직접 등록한(§4종 밖) 연동 이름은 serviceLabel의 kebab/snake 자동 정리
      // 폴백만 타므로 자유 텍스트를 훼손하지 않는다.
      { key: "name", label: "이름", render: (r) => serviceLabel(r.name), rowName: (r) => serviceLabel(r.name) },
      mapCol("provider_type", "유형", PROVIDER), badgeCol("enabled", "활성"),
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
    // RN-10/RN-11: 예전엔 이 문구가 "실제 업무(티켓 처리, 요청 해석)를 수행하는 실행기"라고 단정했다.
    // 그런데 app/jobs/handlers/의 어떤 잡 핸들러도 RunnerHttpProvider.invoke를 부르지 않는다(부르는
    // 곳은 관리 콘솔의 수동 '테스트' 버튼뿐이다) — 채팅·문서 생성 같은 실제 업무는 이 러너가 아니라
    // '외부 연동' 화면의 n8n 경로(업무 자동화 흐름/워크플로)로 나간다. 등록·헬스체크 레지스트리라는
    // 사실만 말하고, 실제 처리가 어디로 가는지는 그 화면으로 안내한다(app/setup/probes.py::probe_llm
    // 의 같은 정정과 짝).
    help: (role) => "등록, 헬스체크, 수동 테스트 대상 레지스트리입니다(실제 채팅, 문서 생성 처리는 ‘외부 연동’의 n8n 경로가 맡습니다). 상태 확인 후 켜세요. 성능 저하, 차단된 러너는 헬스 체크가 한 번 성공하면 자동 복구됩니다."
      + ((role === "admin" || role === "system_admin") ? " 강제로 멈추려면 ‘점검 상태 변경’을 누르세요." : ""),
    emptyTitle: "등록된 러너가 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 러너 추가’로 실행기를 등록하고 상태 확인 후 켜세요(등록, 헬스체크 대상입니다).", "러너는 관리자가 등록합니다. 등록되면 여기에 표시됩니다."),
    // 첫 화면 진입 시 단계별 안내(§9) — 연동→러너→워크플로 체인의 두 번째 단계.
    emptySituation: "등록된 러너가 아직 하나도 없습니다.",
    emptyPrerequisite: "이 러너가 사용할 서버 주소(Base URL)를 미리 확인하세요(SSRF allowlist에 있어야 합니다). 외부 연동과 묶을 계획이면 그 연동을 먼저 등록해 두세요.",
    emptySteps: ["‘+ 러너 추가’로 이름과 서버 주소를 입력합니다.", "저장 후 ‘헬스’, ‘테스트’로 연결을 확인합니다.", "정상이면 ‘활성화’로 등록을 마칩니다."],
    // 프롬프트의 '러너 ID'는 이미 참고용 메타데이터로만 안내되고(authoring.js: "이 값만으로
    // 실행되지는 않습니다"), 템플릿도 신규로는 러너를 대상 워크플로로 지정할 수 없다(registry/
    // shared.js TARGET_OPTS, app/templates/router.py의 동일 검증) — 여기서 "지정할 수 있다"고
    // 안내하면 두 화면 모두와 어긋난다.
    emptyExpected: "등록한 러너는 목록에 상태, 점검 상태와 함께 표시됩니다.",
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
    // 담당자까지 편집 가능하게 명시적 edit 폼(PATCH)을 둔다.
    // (capabilities/tags/retry_policy 는 런타임에 아무 영향이 없는 메타데이터라 폼에서 제거 — 러너
    //  호출 경로엔 재시도 로직이 없고 기능/태그로 결정되는 동작도 없다. 혼란만 주던 JSON 입력을 없앤다.)
    // CONC-02: maintenance_state는 여기 없다 — 서킷 브레이커가 연속 실패/성공에 따라 같은 필드를
    // 자동으로 쓴다(정상↔성능 저하). 이 일반 편집 폼에 남겨 두면 diffFields(CONC-01)로도 못 막는
    // 충돌이 남는다: 관리자가 이 필드를 "의도적으로" 바꾼 값과 그 사이 자동 판정이 다시 바꾼 값이
    // 겹치면 여전히 나중에 저장한 쪽이 이긴다(예: 관리자가 '점검'으로 내려 배분을 멈췄는데, 낡은
    // 폼을 아직 열어 둔 다른 관리자가 무관한 필드만 고쳐 저장해도 diff엔 안 걸리지만, 그 관리자가
    // *이 필드도* 만졌다가 되돌리면 자동 판정과 정면으로 충돌한다). 아래 전용 액션으로 분리해
    // 매번 명시적 확인을 받는다.
    editMethod: "PATCH", edit: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text" },
      { name: "base_url", label: "서버 주소(Base URL)", type: "text" },
      { name: "health_url", label: "상태 확인 주소(Health URL)", type: "text" },
      { name: "auth_type", label: "인증", type: "select", options: AUTH_OPTS },
      { name: "secret_ref", label: "인증 정보 이름(Secret)", type: "text", help: "‘없음’이 아닌 인증이면 반드시 지정하세요." },
      { name: "timeout_seconds", label: "타임아웃(초)", type: "number" },
      { name: "concurrency_limit", label: "동시 실행 수", type: "number" },
      { name: "owner", label: "담당자", type: "text" },
      { name: "version", label: "러너 버전", type: "text" },
      { name: "description", label: "설명", type: "textarea" },
    ] },
    actions: [
      ...onoff("/api/admin/runners"),
      // CONC-02: 점검 상태 전용 액션 — 위 edit.fields 주석 참고. activeToggle(actions.js)과 같은
      // "단일 필드 전용 PATCH" 패턴이지만 값이 셋(정상/성능 저하/점검)이라 고정 body 대신 작은
      // 입력 폼(fields) 하나로 고른다. confirm은 fields보다 먼저 뜬다(DataScreen.jsx runAction).
      { label: "점검 상태 변경", roles: WRITE_ROLES, method: "PATCH", path: (r) => "/api/admin/runners/" + r.id,
        confirm: (r) => "현재 점검 상태는 ‘" + ((RUNNER_MAINT_OPTS.find((o) => o.value === r.maintenance_state) || {}).label || r.maintenance_state) + "’입니다. ‘점검’으로 바꾸면 새 작업 배분이 즉시 멈추고, ‘정상’으로 바꾸면 성능 저하 여부와 무관하게 새 작업을 다시 받습니다. 바꿀까요?",
        fields: [{ name: "maintenance_state", label: "점검 상태", type: "select", options: RUNNER_MAINT_OPTS, required: true }] },
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
        },
        // RG-07: 워크플로의 /versions만 created_by_name/_email을 실제로 준다(연동·러너는 안 준다).
        true),
      // operator는 워크플로 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=workflow&object_id=" + r.id },
    ],
  },
};
