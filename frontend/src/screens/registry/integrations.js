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
import Link from "@mui/material/Link";
import { AUTH_OPTS, OPS_ROLES, PROVIDER, PROVIDER_OPTS, WRITE_ROLES, badgeCol, col, dateCol, enabledCol, field, mapCol, opt, truncateCol, writerEmptyHelp } from "./shared.js";
import { healthResult, onoff, snapCol, versionsAction } from "./actions.js";
import { serviceLabel } from "../ops/opsHelpers.js";

export const INTEGRATION_SCREENS = {
  integrations: {
    /* C2 «Filter Surface 가 정당한가» — 이 화면은 **행 수가 유한하고 작다**(정책 2 ·
       기능 플래그 11 · 통합 4 · RBAC 13 실측). R-88 이 "25행" 을 기계 규칙으로 쓰지 말라고
       못박으므로 숫자가 아니라 **판단**을 남긴다: 조건 조합을 이름 붙여 재사용할 만큼
       탐색이 반복되지 않는다. 그래서 저장된 뷰를 그리지 않는다 — 기능이 아니라 소음이다. */
    smallSet: true,
    key: "integrations", area: "자동화와 연동", title: "외부 연동", endpoint: "/api/admin/integrations",
    help: "이 시스템이 불러다 쓰는 외부 서비스를 추가하고 점검합니다. 비활성화하면 그 서비스로 나가는 호출을 막습니다.",
    emptyTitle: "추가된 외부 연동이 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 외부 연동 추가’로 외부 서비스를 추가하고 상태를 점검하세요.", "외부 연동은 관리자가 추가합니다. 추가되면 여기에 상태와 함께 표시됩니다."),
    // 첫 화면 진입 시 단계별 안내(§9) — 연동→러너→워크플로 체인의 첫 단계라 다음 화면으로 가는
    // relatedLink도 함께 준다.
    emptySituation: "이 관리 콘솔이 아직 외부 서비스를 하나도 모릅니다.",
    emptyPrerequisite: "추가할 서비스의 서버 주소(Base URL)를 미리 확인하세요(SSRF allowlist에 있어야 합니다).",
    emptySteps: ["‘+ 외부 연동 추가’로 이름과 서버 주소를 입력합니다.", "저장 후 ‘헬스체크’로 연결을 확인합니다.", "정상이면 ‘활성화’로 실제 사용을 시작합니다."],
    emptyExpected: "추가한 연동은 목록에 상태와 함께 표시되고, 헬스체크 결과가 함께 보입니다.",
    createLabel: "외부 연동 추가",
    // 알림·감사의 '관련 항목 보기'가 ?id= 로 넘겨주는 딥링크를 소비해 그 연동의 상세
    // 드로어를 곧바로 연다(단건 GET).
    onQuery: (p) => p.id ? { open: "select", id: p.id } : null,
    selectKey: "integration",
    // GET /api/admin/integrations는 쿼리 파라미터를 받지 않는다(app/integrations/router.py) —
    // clientFilter:true로 이미 받아 온 전체 목록을 화면에서 직접 거른다(같은
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
      { key: "name", label: "이름", identifier: true, render: (r) => serviceLabel(r.name), rowName: (r) => serviceLabel(r.name) },
      mapCol("provider_type", "유형", PROVIDER), enabledCol("활성"),
      /* 지시 37: `http://127.0.0.1:8788` 은 이 연동이 무엇인지가 아니라 **어디에 있는지**다.
         SSRF allowlist 때문에 어차피 전부 서버-로컬 주소라 행끼리 비교할 값도 아니다 —
         목록의 자리는 "지금 통하는가"와 "언제 확인했는가"가 갖고, 주소는 상세로 내린다. */
      badgeCol("last_health_status", "상태 확인"), dateCol("last_health_at", "마지막 확인"),
      col("config_version", "버전")],
    // admin은 auth_type='none'인 연동만 새로 만들 수 있다(백엔드 _guard_secret_binding_create가 그 외
    // 값을 403). 예전엔 옵션을 그대로 다 보여주고 help 문구만으로 고르지 말라고 부탁했다 — 골라도
    // 항상 403이 되는 선택지를 애초에 못 고르게, system_admin이 아니면 옵션 자체를 '없음'만 준다
    // (같은 registry 의 다른 화면들이 쓰는 role-분기 패턴과 같은 발상).
    create: { roles: WRITE_ROLES, fields: (role) => [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "provider_type", label: "유형", type: "select", value: "http_service", options: PROVIDER_OPTS },
      { name: "base_url", label: "서버 주소(Base URL)", type: "text", required: true, help: "allowlist에 있어야 합니다." },
      { name: "health_url", label: "상태 확인 주소(Health URL)", type: "text", help: "비우면 Base URL로 헬스체크" },
      { name: "auth_type", label: "인증", type: "select", value: "none",
        options: role === "system_admin" ? AUTH_OPTS : AUTH_OPTS.filter((o) => o.value === "none"),
        help: role === "system_admin" ? undefined : "admin은 인증 없는(‘없음’) 연동만 새로 만듭니다. Bearer, API 키가 필요하면 system_admin에게 요청하세요." },
      { name: "secret_ref", label: "인증 정보 이름(Secret)", type: "text", help: "서버 secrets 파일 이름(값 아님). ‘없음’이 아닌 인증이면 반드시 지정하세요." },
      { name: "description", label: "설명", type: "textarea" },
      { name: "enabled", label: "활성", type: "checkbox", value: false, checkLabel: "활성(비활성 상태로 추가만 하고 헬스체크 후 활성화할 수 있음)" },
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
    // provider_type은 이미 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    // base_url 은 목록에서 상세로 내려왔다(지시 37) — 여기서는 주요 정보가 아니라 확인용이다.
    // id는 러너 create의 integration_id 입력에 쓰이므로 상세에서 확인·복사할 수 있게 노출.
    detailFields: [field("id", "연동 ID"), truncateCol("base_url", "서버 주소", 80),
      truncateCol("health_url", "상태 확인 주소", 80), mapCol("auth_type", "인증", { none: "없음", bearer: "Bearer 토큰", api_key_header: "API 키(헤더)" }), field("secret_ref", "인증 정보 이름"),
      // auth_type이 '없음'이면 secret_status는 null이다(원래 정상) — 일반 Badge는 null을 '알 수 없음'으로
      // 오해하게 표시하므로, 인증 자체가 필요 없는 경우엔 '해당 없음'으로 구분한다(그 외엔 기존 배지 재사용).
      { key: "secret_status", label: "인증 정보 상태", render: (r) => r.auth_type === "none" ? "해당 없음" : badgeCol("secret_status", "인증 정보 상태").render(r) },
      field("description", "설명"), dateCol("created_at", "추가"), dateCol("updated_at", "수정")],
  },
};
