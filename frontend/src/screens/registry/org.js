/* 조직 — 회사·부서·직책.
 *
 * 부서와 직책은 조직의 뼈대고, 조직도(org-tree)는 그것을 한 장으로 보는 화면이라 같은
 * 자리에 둔다.
 *
 * 여기 「Notion 사용자 연결」 화면이 하나 더 있었다. 그 화면이 잇던 바깥 시스템의 사람은
 * 이 제품에 더 이상 없다(S14 가 런타임을 걷었다) — 연결을 새로 만들 수도, 그 연결이 무엇을
 * 바꾸지도 못하는 채로 사이드바에 서 있었다. S20 이 화면을 내렸다. 표(`user_notion_mappings`)
 * 는 이관 계보이자 옛 담당자 토큰의 짝이라 그대로 남는다(D-285).
 *
 * registry.js 를 쪼갠 조각이다 (E-10). 쪼갠 축은 '줄 수'가 아니라 **관리자가 한 번에
 * 함께 보는 묶음**이다 — 줄 수를 맞추려고 아무 데나 자르면 화면 하나를 고치는 데
 * 파일 셋을 열게 되어 오히려 더 나빠진다.
 *
 * 화면 설정만 있고 그리는 코드는 없다. 그리는 것은 DataScreen.jsx 하나다.
 */
import React from "react";
import { WRITE_ROLES, activeCol, col, dateCol, field, opt } from "./shared.js";
import { ACTIVE_FILTER, PARENT_DEPT_FIELD, activeToggle } from "./actions.js";

export const ORG_SCREENS = {
  /* 조직 관리 — `organizations` 는 0022 부터 표만 있고 라우터도 화면도 없었다(시드 한 행이
     전부). 지시서 §3 이 "조직 > 부서 > 사용자" 를 요구하는데 맨 위 층이 화면에 없으면 그
     관계를 보여 줄 수가 없다. 삭제가 없는 이유: 사용자·부서가 org_id 로 이 행을 가리키고
     있어서 지우면 그 참조가 통째로 끊긴다 — 대신 '정지'로 새 사용을 막는다. */
  organizations: {
    key: "organizations", area: "사용자와 권한", title: "조직 관리",
    endpoint: "/api/admin/organizations",
    help: "회사(테넌트)를 관리합니다. 부서와 사용자는 모두 조직 하나에 속하며, 그 포함 관계는 ‘조직도’에서 한눈에 볼 수 있습니다.",
    createLabel: "조직 추가",
    emptyTitle: "추가된 조직이 없습니다",
    emptyHelp: "‘+ 조직 추가’로 조직을 추가하면 부서와 사용자를 그 아래에 둘 수 있습니다.",
    searchFields: ["name", "slug"],
    searchPlaceholder: "조직 이름 또는 식별자로 검색",
    // 상태 필터가 아예 없어서, 조직이 늘어나면 '정지된 곳만' 훑을 방법이 없었다.
    // GET /api/admin/organizations는 쿼리 파라미터를 하나도 받지 않고(app/org/router.py
    // list_organizations) **페이지네이션도 하지 않는다** — 응답이 곧 전체 목록이다. 그래서
    // clientFilter로 걸러도 숨는 행이 없다(paginated 화면에서 clientFilter를 쓰면 다른 페이지의
    // 일치 항목이 사라지는데, 여기는 다른 페이지 자체가 없다).
    filters: [{ key: "status", type: "select", label: "상태", clientFilter: true, options: opt([["active", "사용 중"], ["suspended", "미사용"]]) }],
    columns: [
      { ...col("name", "조직 이름", "name"), identifier: true },
      /* 식별자형이다 (S18 · C3). 타입이 없으면 바닥폭 4.5rem 에 잘림 처리라, 분할 뷰의
         가운데 판처럼 좁은 자리에서 `default` 가 «defa…» 로 잘렸다 — 화면의 46% 가 비어
         있는데 식별자만 잘리는 상태였다. `identifier` 는 12.5rem 을 바닥으로 갖고
         글자 단위로 끊는다(코드·UUID 부류). */
      { ...col("slug", "식별자", "identifier") },
      { key: "status", label: "상태", type: "status", render: (r) => (r.status === "active" ? "사용 중" : "미사용") },
      // 개수는 **자릿수를 고정하고 가운데**다 — 세로로 훑으며 비교하는 값이다.
      col("department_count", "부서", "count"),
      col("user_count", "사용자", "count"),
      dateCol("created_at", "생성 일자"),
    ],
    detailFields: [
      field("id", "조직 ID"),
      field("slug", "식별자"),
      { key: "_contains", label: "포함 관계", render: (r) =>
        "부서 " + (r.department_count || 0) + "개, 사용자 " + (r.user_count || 0) + "명" },
      { key: "_delete_note", label: "삭제 안내", render: () =>
        "조직은 지울 수 없습니다. 사용자와 부서가 이 조직을 가리키고 있어 지우면 그 연결이 끊깁니다, 대신 ‘비활성화’로 새 사용을 막으세요." },
    ],
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "조직 이름", type: "text", required: true, help: "화면에 보이는 이름입니다." },
      { name: "slug", label: "식별자", type: "text", required: true,
        help: "영문 소문자, 숫자, 붙임표만 씁니다. 만든 뒤에는 바꿀 수 없습니다." },
    ] },
    edit: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "조직 이름", type: "text", required: true, help: "이 조직에 속한 모든 화면에 즉시 반영됩니다." },
    ] },
    actions: [
      // 예전 확인 문구는 "기존 사용자와 부서는 그대로 남습니다"뿐이었다 — 데이터는 그대로 남는 게
      // 맞지만, 그 문장은 **아무 일도 일어나지 않는 것처럼** 읽힌다. 실제로는 이 버튼 하나가
      // 그 조직 전원을 즉시 밖으로 내보낸다: app/org/router.py::_revoke_org_sessions가 살아 있는
      // 세션을 전부 끊고(system_admin 제외), 그 뒤로는 로그인 자체가 막힌다
      // (is_blocked_by_org_suspension을 auth/router.py와 core/deps.py가 함께 본다).
      // 몇 명이 끊기는지는 이미 같은 행에 실려 있다(user_count) — 부서/직책 비활성화가 인원수를
      // 확인 문구에 넣는 것과 같은 이유로, 0명과 200명이 같은 경고를 받지 않게 한다.
      { label: "비활성화", variant: "danger", roles: WRITE_ROLES, when: (r) => r.status === "active",
        method: "PATCH", path: (r) => "/api/admin/organizations/" + r.id, body: { status: "suspended" },
        confirm: (r) => "이 조직을 비활성화하면 소속 사용자 " + (r.user_count || 0)
          + "명이 지금 즉시 로그아웃되고, 다시 로그인할 수 없게 됩니다(시스템 관리자는 제외). "
          + "사용자와 부서 데이터 자체는 지워지지 않으며 ‘활성화’로 되돌릴 수 있습니다. 계속 비활성화할까요?" },
      { label: "활성화", roles: WRITE_ROLES, when: (r) => r.status !== "active",
        method: "PATCH", path: (r) => "/api/admin/organizations/" + r.id, body: { status: "active" } },
      { label: "조직도에서 보기", roles: WRITE_ROLES, navigate: () => "#/org-tree" },
      { label: "감사 로그에서 보기", navigate: (r) => "#/audit?object_type=organization&object_id=" + r.id },
    ],
  },
  departments: {
    key: "departments", area: "사용자와 권한", title: "부서 관리", endpoint: "/api/admin/departments",
    // PA-RC-0024: /departments/:id 라우트가 AdminRoutes.jsx에 등록돼 있다(organizations는
    // 아니다 — Handoff 실측 범위 밖). DataScreen이 이 플래그로 sel을 그 경로와 동기화한다.
    hasIdRoute: true,
    // 단건 조회(app/org/router.py::get_org_item)는 {"department": {...}}로 감싸서 온다
    // (body_key="department", :210). selectKey 없이는 DataScreen이 이 봉투 객체 자체를
    // sel로 삼아 sel.id가 undefined가 되고, 그 값으로 다시 GET /departments/undefined를
    // 불러 404 토스트가 뜬다 — TEST SERVER 실측으로 잡은 결함, users-scope-form.test.jsx류의
    // 목(mock)은 애초에 감싸지 않은 응답을 흉내 내서 이 문제를 못 잡았다.
    selectKey: "department",
    /* 상위 부서 후보는 **조건과 무관한 전량**이어야 한다 — 목록에 걸린 필터가 후보를 좁히면
       「미사용 부서만 상위로 고를 수 있는」 폼이 된다(`registry/actions.js::PARENT_DEPT_FIELD`). */
    refLists: [{ key: "allDepartments", endpoint: "/api/admin/departments" }],
    help: "부서 이름을 한 곳에서 관리합니다. 사용자 폼의 '부서'는 여기 목록에서 고릅니다.", createLabel: "부서 추가",
    emptyTitle: "추가된 부서가 없습니다", emptyHelp: "‘+ 부서 추가’로 부서를 추가하면 사용자 폼의 ‘부서’ 목록에 바로 나타납니다.",
    // 이 화면은 paginated가 아니라 클라이언트 검색창이 항상 뜨는데, searchFields가 없으면 기본 검색이
    // JSON.stringify(row) 전체(원시 UUID·boolean·UTC-ISO created_at)를 훑어 화면에 보이는 값과 무관하게
    // 매칭했다(예: KST 생성일을 그대로 쳐도 자정 경계 근처에서 못 찾음) — 이름만 검색 대상으로 좁힌다(직책 화면과 동일).
    searchFields: ["name"],
    searchPlaceholder: "부서 이름으로 검색",
    filters: ACTIVE_FILTER,
    // usage_count(소속 인원)는 보관(soft-delete)된 사용자도 센다(app/org/service.py 주석: '보관된
    // 사용자도 센다') — 열 라벨에서 바로 그 사실을 알려, 활성 인원만으로 오해해 삭제 가능 여부를
    // 잘못 판단하지 않게 한다.
    // '조직' 열 — 사용자 지적 P5("부서 추가하면 부서랑 조직을 연결하는 것이 없음").
    // 서버가 이제 부서 응답에 org_id/org_name 을 싣는다. 연결을 만들어 놓고 화면에 안 보이면
    // 같은 말을 다시 듣는다. 조직이 하나뿐인 지금도 "이 부서가 어느 조직 것인지" 가 보인다.
    columns: [{ ...col("name", "부서 이름", "name"), identifier: true }, col("org_name", "조직", "name"), activeCol("사용"),
      // 개수 열은 **우정렬 + 자릿수 고정**이다(columnTypes.js `count`). S22 캡처가 이 두
      // 열(부서·직책)만 좌정렬·비고정으로 남아 있는 것을 잡았다 — 세로로 훑으며 비교할 수
      // 없는 상태였다. 폭·정렬·자릿수는 어휘가 정한다.
      { ...col("user_count", "소속 인원(보관 포함)", "count") }, dateCol("created_at", "생성 일자")],
    // id는 감사 로그의 object_id와 대조할 때 쓰이므로 상세에서 노출한다.
    // 삭제 버튼은 소속 인원>0이면 아래 actions에서 통째로 숨겨진다(사용 중이면 비활성화만 가능) — 그
    // 이유가 코드 주석에만 있어 화면엔 아무 설명 없이 버튼만 사라졌었다. 상세에 이유를 남긴다.
    detailFields: [field("id", "부서 ID"), field("org_name", "조직"), field("org_id", "조직 ID"),
      field("child_department_count", "하위 부서"),
      { key: "_delete_note", label: "삭제 안내", render: (r) => r.user_count
        ? "사용 중인 부서(소속 인원 " + r.user_count + "명, 보관 계정 포함)는 삭제할 수 없습니다. 대신 ‘비활성화’를 이용하세요."
        : r.child_department_count
          ? "삭제하면 하위 부서 " + r.child_department_count + "개가 최상위 부서로 올라갑니다(하위 부서 자체는 지워지지 않습니다)."
          : "-" }],
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "부서 이름", type: "text", required: true, help: "사용자 폼의 '부서' 목록에 바로 나타납니다." },
      PARENT_DEPT_FIELD,
    ] },
    // 활성 토글은 확인 문구가 붙은 아래 활성/비활성 액션으로만 처리한다(수정 폼의 무경고 체크박스 제거).
    // required:true — 비워서 제출하면 FormModal이 {"name": null}을 보내 백엔드가 '값이 없어졌다'로
    // 해석하고 조용히 무시(no-op)한다(성공 토스트까지 뜬다). 클라이언트에서 먼저 막아 이 거짓
    // 성공 피드백을 없앤다(create 필드는 이미 required였는데 edit만 빠져 있었다).
    edit: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "부서 이름", type: "text", required: true, help: "이름을 바꾸면 이 부서를 쓰는 모든 사용자(소속 인원)에게 즉시 반영됩니다." },
      PARENT_DEPT_FIELD,
    ] },
    actions: [
      ...activeToggle("/api/admin/departments"),
      // 사용 중(소속 인원>0)인 부서는 삭제가 항상 409 → 미사용일 때만 노출한다(대신 '비활성화').
      // UA-20R: 이전 확인 문구("되돌릴 수 없습니다")는 하위 부서가 있어도 아무 말이 없었다 —
      // parent_id가 ondelete="SET NULL"이라 데이터가 지워지진 않지만(하위 부서는 최상위로
      // 올라온다), 3단 트리가 클릭 한 번에 평탄해지는 것을 지우기 전에 알아야 한다. 조직
      // '정지' 확인 문구(위 organizations.actions)와 같은 원칙 — 영향받는 수를 숫자로 말한다.
      { label: "삭제", variant: "danger", roles: WRITE_ROLES, when: (r) => !r.user_count, method: "DELETE", path: (r) => "/api/admin/departments/" + r.id,
        confirm: (r) => (r.child_department_count
          ? "이 부서를 지우면 하위 부서 " + r.child_department_count + "개가 최상위 부서로 올라갑니다"
            + "(하위 부서와 그 소속 인원은 지워지지 않습니다). 되돌릴 수 없습니다. 계속할까요?"
          : "이 부서를 지울까요? 되돌릴 수 없습니다.") },
      // 사용자 상세의 '감사 로그에서 보기'(Users.jsx)와 동일한 딥링크 — department는 OBJTYPE_OPTS에
      // 이미 있고 감사 화면 onQuery가 object_type/object_id를 소비하므로 클릭 한 번으로 이 부서에
      // 일어난 변경 이력을 볼 수 있다.
      { label: "감사 로그에서 보기", navigate: (r) => "#/audit?object_type=department&object_id=" + r.id },
    ],
  },
  "job-titles": {
    key: "job-titles", area: "사용자와 권한", title: "직책 관리", endpoint: "/api/admin/job-titles",
    help: "직책 이름을 한 곳에서 관리합니다. 사용자 폼의 '직책'은 여기 목록에서 고릅니다.", createLabel: "직책 추가",
    emptyTitle: "추가된 직책이 없습니다", emptyHelp: "‘+ 직책 추가’로 직책을 추가하면 사용자 폼의 ‘직책’ 목록에 바로 나타납니다.",
    // 부서→직책→사용자 온보딩 체인(사용자 생성은 직책이 있어야 가능 — Users.jsx) — 연동→러너→워크플로
    // 체인처럼 다음 단계(사용자)로 이어 준다. 단계별 안내는 canOnboard가 쓰기 역할에만 보여준다.
    emptySituation: "부서, 직책, 사용자 온보딩 체인의 한 단계입니다. 아직 직책이 하나도 없습니다.",
    emptySteps: ["‘+ 직책 추가’로 필요한 직책을 추가합니다.", "사용할 직책을 모두 추가합니다.", "사용자 화면에서 계정을 추가할 때 이 직책을 배정합니다."],
    emptyExpected: "추가한 직책은 사용자 폼의 ‘직책’ 목록에 바로 나타납니다.",
    emptyRelatedLink: { href: "#/users", label: "다음: 사용자 추가로 이동" },
    // 이 화면은 paginated가 아니라 클라이언트 검색창이 항상 뜨는데, 기본 검색은 JSON.stringify(row)
    // 전체(원시 UUID·ISO created_at 포함)를 훑는다 — 화면에 보이는 '생성' 열은 KST로 포맷된 값인데
    // 검색은 원시 UTC ISO 문자열을 매칭해, 화면에 보이는 그대로 타이핑해도 자정 경계 근처에서
    // 못 찾을 수 있었다(오탐/누락 방지를 위해 실제로 보이는 필드인 이름만 검색 대상으로 좁힌다).
    searchFields: ["name"],
    searchPlaceholder: "직책 이름으로 검색",
    filters: ACTIVE_FILTER,
    // usage_count(보유 인원)는 보관(soft-delete)된 사용자도 센다(부서와 동일한 계산 — app/org/service.py).
    // 라벨은 부서 화면과 다르게 '보유'를 쓴다 — 직책은 사람이 '보유'하는 것이지 '소속'되는 게 아니다.
    columns: [{ ...col("name", "직책 이름"), identifier: true }, activeCol("사용"),
      { ...col("user_count", "보유 인원(보관 포함)"), type: "count" }, dateCol("created_at", "생성 일자")],
    // 삭제 버튼은 소속 인원>0이면 아래 actions에서 통째로 숨겨진다(부서와 동일한 이유) — 상세에 이유를 남긴다.
    detailFields: [field("id", "직책 ID"),
      { key: "_delete_note", label: "삭제 안내", render: (r) => r.user_count ? "사용 중인 직책(보유 인원 " + r.user_count + "명, 보관 계정 포함)은 삭제할 수 없습니다. 대신 ‘비활성화’를 이용하세요." : "-" }],
    create: { roles: WRITE_ROLES, fields: [{ name: "name", label: "직책 이름", type: "text", required: true, help: "사용자 폼의 '직책' 목록에 바로 나타납니다." }] },
    // 활성 토글은 확인 문구가 붙은 아래 활성/비활성 액션으로만 처리한다(수정 폼의 무경고 체크박스 제거).
    // required:true — 부서와 동일한 이유(비워서 제출하면 조용한 no-op + 거짓 성공 토스트가 됐다).
    edit: { roles: WRITE_ROLES, fields: [{ name: "name", label: "직책 이름", type: "text", required: true, help: "이름을 바꾸면 이 직책을 쓰는 모든 사용자(보유 인원)에게 즉시 반영됩니다." }] },
    actions: [
      ...activeToggle("/api/admin/job-titles"),
      // 사용 중(소속 인원>0)인 직책은 삭제가 항상 409 → 미사용일 때만 노출한다(대신 '비활성화').
      { label: "삭제", variant: "danger", roles: WRITE_ROLES, when: (r) => !r.user_count, method: "DELETE", path: (r) => "/api/admin/job-titles/" + r.id, confirm: "이 직책을 지울까요? 되돌릴 수 없습니다." },
      // job_title은 OBJTYPE_OPTS에 이미 있고 이 id를 감사 로그에서 대조할 수 있게 상세에 노출해
      // 두었다(위 detailFields 주석 참고) — 그런데 실제로 눌러서 갈 방법이 없었다. Users.jsx의
      // '감사 로그에서 보기' 버튼과 동일한 딥링크를 추가한다.
      { label: "감사 로그에서 보기", navigate: (r) => "#/audit?object_type=job_title&object_id=" + r.id },
    ],
  },
  "org-tree": {
    key: "org-tree", area: "사용자와 권한", title: "조직도", endpoint: "/api/admin/departments/tree",
    help: "조직 > 부서 > 사용자 순서로 소속 관계를 봅니다. 맨 윗줄이 조직이고 그 아래 들여쓴 줄이 부서입니다. 부서 줄의 ‘소속 인원’을 누르면 그 자리에서 사람 이름까지 펼쳐 볼 수 있습니다.",
    emptyTitle: "추가된 부서가 없습니다",
    emptyHelp: "‘부서 관리’에서 부서를 추가하고 상위 부서를 지정하면 여기에 계층으로 표시됩니다.",
    emptyRelatedLink: { href: "#/departments", label: "부서 관리로 이동" },
    /* `slug` 가 여기 있는 이유 (S18): 조직 콘솔의 오른쪽 판에는 자기 검색 상자가 있었고,
       한 화면에 같은 엔티티를 찾는 상자가 둘이었다(계획서가 그 화면의 결함으로 지목).
       분할 뷰의 검색은 navigator 하나이므로 그 상자를 내렸는데, **식별자로 찾는 축은 그쪽
       상자에만 있었다** — 축을 함께 잃지 않도록 트리 검색이 그것까지 본다. */
    searchFields: ["name", "path", "slug"],
    searchPlaceholder: "조직 또는 부서를 이름이나 식별자로 검색",
    filters: ACTIVE_FILTER,
    columns: [
      // 들여쓰기가 곧 트리다 — 표 하나로 조직도를 그리기 위한 유일한 장치라 여기서만 만든다.
      // 공백 문자가 아니라 좌측 패딩(rem)이라 4K에서 루트 폰트사이즈 레버를 그대로 따라간다.
      /* 맨 위 줄은 **조직**이다(지시서 §3 "조직 > 부서 > 사용자"). 조직이 하나뿐이어도
         그 층이 화면에 없으면 사용자는 이 부서들이 어느 조직 소속인지 알 방법이 없다.
         조직 행은 굵게, 부서 행은 들여쓰기 + 갈래표시로 갈라 놓는다. */
      { key: "name", label: "조직과 부서", identifier: true, render: (r) => React.createElement(
        "span",
        {
          style: {
            paddingInlineStart: (r.depth || 0) * 1.25 + "rem",
            fontWeight: r.kind === "organization" ? 800 : 400,
          },
          title: r.path,
        },
        (r.kind === "organization" ? "" : "└ ")
          + r.name + (r.cycle ? " (상위 관계 오류)" : ""),
      ),
      // SEM-01: 이 열이 render(들여쓰기 트리)라 표식 없이는 전부 "상세 보기"였다 — 조직/
      // 부서 구분 + 이름으로 실제로 구별되는 이름을 만든다.
      rowName: (r) => (r.kind === "organization" ? "조직 " : "부서 ") + r.name },
      { key: "kind", label: "구분", type: "enum", render: (r) => (r.kind === "organization" ? "조직" : "부서") },
      activeCol("사용"),
      col("user_count", "소속 인원(보관 포함)", "count"),
      col("subtree_user_count", "하위 포함 인원", "count"),
      col("child_count", "하위 부서", "count"),
    ],
    detailFields: [field("id", "부서 ID"), field("path", "전체 경로"),
      { key: "parent_name", label: "상위 부서", render: (r) => r.parent_name || "(최상위)" },
      { key: "cycle", label: "상위 관계 오류", render: (r) => r.cycle
        ? "이 부서는 상위 관계가 고리를 이루고 있어 최상위로 끌어올려 표시했습니다. ‘부서 관리’에서 상위 부서를 다시 지정하세요."
        : "-" }],
    actions: [
      /* 사용자 지시 §3: "조직도, 부서 관리, 사용자 관리 페이지에 들어갔을 때 전체 조직, 부서와
         사용자의 소속 관계를 한눈에 확인할 수 있는 구조가 먼저 보여야 한다."
         예전에는 '소속 인원 보기'가 다른 화면으로 **떠나보내기만** 했다 — 조직도에서는 부서와
         숫자만 보이고 사람 이름은 하나도 안 보였으니, 관계를 한눈에 본다고 할 수 없었다.
         이제 그 자리에서 펼쳐 본다(떠나는 링크도 남긴다 — 걸러 보고 싶을 때가 있다). */
      { label: "소속 인원", roles: WRITE_ROLES, when: (r) => r.kind !== "organization", subList: {
        title: "소속 인원",
        hint: "이 부서에 직접 속한 사람입니다(하위 부서는 그 부서 줄에서 펼쳐 보세요).",
        endpoint: (r) => "/api/admin/users?department_id=" + r.id + "&page_size=100",
        columns: [
          col("display_name", "이름", "name"),
          col("title", "직책", "enum"),
          col("email", "이메일", "identifier"),
          col("role", "역할", "enum"),
          { key: "active", label: "상태", type: "status", render: (u) => (u.archived_at ? "보관" : u.active ? "사용" : "비활성") },
        ],
        emptyTitle: "이 부서에 직접 속한 사람이 없습니다",
        emptyHelp: "하위 부서에 사람이 있을 수 있습니다. ‘하위 포함 인원’ 숫자를 확인하세요.",
      } },
      { label: "사용자 화면에서 보기", roles: WRITE_ROLES, when: (r) => r.kind !== "organization",
        navigate: (r) => "#/users?department_id=" + r.id },
      { label: "조직 관리에서 열기", roles: WRITE_ROLES, when: (r) => r.kind === "organization",
        navigate: () => "#/organizations" },
      { label: "부서 관리에서 열기", roles: WRITE_ROLES, when: (r) => r.kind !== "organization",
        navigate: () => "#/departments" },
    ],
  },
};
