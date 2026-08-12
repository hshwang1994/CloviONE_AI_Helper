/* 조직 — 회사·부서·직책과 Notion 사용자 연결.
 *
 * 부서와 직책은 조직의 뼈대고, Notion 연결은 그 사람들을 바깥 시스템의 사람과 잇는다.
 * 조직도(org-tree)는 앞의 것들을 한 장으로 보는 화면이라 같은 자리에 둔다.
 *
 * registry.js 를 쪼갠 조각이다 (E-10). 쪼갠 축은 '줄 수'가 아니라 **관리자가 한 번에
 * 함께 보는 묶음**이다 — 줄 수를 맞추려고 아무 데나 자르면 화면 하나를 고치는 데
 * 파일 셋을 열게 되어 오히려 더 나빠진다.
 *
 * 화면 설정만 있고 그리는 코드는 없다. 그리는 것은 DataScreen.jsx 하나다.
 */
import React from "react";
import { MAP_SOURCE, OBJTYPE_OPTS, WRITE_ROLES, activeCol, badgeCol, col, dateCol, field, mapCol, opt, truncateCol } from "./shared.js";
import { ACTIVE_FILTER, PARENT_DEPT_FIELD, activeToggle } from "./actions.js";

export const ORG_SCREENS = {
  /* 조직 관리 — `organizations` 는 0022 부터 표만 있고 라우터도 화면도 없었다(시드 한 행이
     전부). 지시서 §3 이 "조직 > 부서 > 사용자" 를 요구하는데 맨 위 층이 화면에 없으면 그
     관계를 보여 줄 수가 없다. 삭제가 없는 이유: 사용자·부서가 org_id 로 이 행을 가리키고
     있어서 지우면 그 참조가 통째로 끊긴다 — 대신 '정지'로 새 사용을 막는다. */
  organizations: {
    key: "organizations", area: "사용자", title: "조직 관리",
    endpoint: "/api/admin/organizations",
    help: "회사(테넌트)를 관리합니다. 부서와 사용자는 모두 조직 하나에 속하며, 그 포함 관계는 ‘조직도’에서 한눈에 볼 수 있습니다.",
    createLabel: "+ 조직 추가",
    emptyTitle: "등록된 조직이 없습니다",
    emptyHelp: "‘+ 조직 추가’로 조직을 만들면 부서와 사용자를 그 아래에 둘 수 있습니다.",
    searchFields: ["name", "slug"],
    searchPlaceholder: "조직 이름 또는 식별자로 검색",
    // 상태 필터가 아예 없어서, 조직이 늘어나면 '정지된 곳만' 훑을 방법이 없었다.
    // GET /api/admin/organizations는 쿼리 파라미터를 하나도 받지 않고(app/org/router.py
    // list_organizations) **페이지네이션도 하지 않는다** — 응답이 곧 전체 목록이다. 그래서
    // clientFilter로 걸러도 숨는 행이 없다(paginated 화면에서 clientFilter를 쓰면 다른 페이지의
    // 일치 항목이 사라지는데, 여기는 다른 페이지 자체가 없다).
    filters: [{ key: "status", type: "select", label: "상태", clientFilter: true, options: opt([["active", "사용"], ["suspended", "정지"]]) }],
    columns: [
      col("name", "조직 이름"),
      col("slug", "식별자"),
      { key: "status", label: "상태", render: (r) => (r.status === "active" ? "사용" : "정지") },
      col("department_count", "부서"),
      col("user_count", "사용자"),
      dateCol("created_at", "생성"),
    ],
    detailFields: [
      field("id", "조직 ID"),
      field("slug", "식별자"),
      { key: "_contains", label: "포함 관계", render: (r) =>
        "부서 " + (r.department_count || 0) + "개, 사용자 " + (r.user_count || 0) + "명" },
      { key: "_delete_note", label: "삭제 안내", render: () =>
        "조직은 지울 수 없습니다. 사용자와 부서가 이 조직을 가리키고 있어 지우면 그 연결이 끊깁니다, 대신 ‘정지’로 새 사용을 막으세요." },
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
      { label: "정지", variant: "danger", roles: WRITE_ROLES, when: (r) => r.status === "active",
        method: "PATCH", path: (r) => "/api/admin/organizations/" + r.id, body: { status: "suspended" },
        confirm: (r) => "이 조직을 정지하면 소속 사용자 " + (r.user_count || 0)
          + "명이 지금 즉시 로그아웃되고, 다시 로그인할 수 없게 됩니다(시스템 관리자는 제외). "
          + "사용자와 부서 데이터 자체는 지워지지 않으며 ‘사용’으로 되돌릴 수 있습니다. 계속 정지할까요?" },
      { label: "사용", roles: WRITE_ROLES, when: (r) => r.status !== "active",
        method: "PATCH", path: (r) => "/api/admin/organizations/" + r.id, body: { status: "active" } },
      { label: "조직도에서 보기", roles: WRITE_ROLES, navigate: () => "#/org-tree" },
      { label: "감사 로그에서 보기", navigate: (r) => "#/audit?object_type=organization&object_id=" + r.id },
    ],
  },
  departments: {
    key: "departments", area: "사용자", title: "부서 관리", endpoint: "/api/admin/departments",
    help: "부서 이름을 한 곳에서 관리합니다. 사용자 폼의 '부서'는 여기 목록에서 고릅니다.", createLabel: "+ 부서 추가",
    emptyTitle: "등록된 부서가 없습니다", emptyHelp: "‘+ 부서 추가’로 부서를 만들면 사용자 폼의 '부서' 목록에 바로 나타납니다.",
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
    columns: [col("name", "부서 이름"), col("org_name", "조직"), activeCol("사용"),
      col("user_count", "소속 인원(보관 포함)"), dateCol("created_at", "생성")],
    // id는 감사 로그의 object_id와 대조할 때 쓰이므로 상세에서 노출한다.
    // 삭제 버튼은 소속 인원>0이면 아래 actions에서 통째로 숨겨진다(사용 중이면 비활성화만 가능) — 그
    // 이유가 코드 주석에만 있어 화면엔 아무 설명 없이 버튼만 사라졌었다. 상세에 이유를 남긴다.
    detailFields: [field("id", "부서 ID"), field("org_name", "조직"), field("org_id", "조직 ID"),
      field("child_department_count", "하위 부서"),
      { key: "_delete_note", label: "삭제 안내", render: (r) => r.user_count
        ? "사용 중인 부서(소속 인원 " + r.user_count + "명, 보관 계정 포함)는 삭제할 수 없습니다, 대신 ‘비활성화’를 이용하세요."
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
    key: "job-titles", area: "사용자", title: "직책 관리", endpoint: "/api/admin/job-titles",
    help: "직책 이름을 한 곳에서 관리합니다. 사용자 폼의 '직책'은 여기 목록에서 고릅니다.", createLabel: "+ 직책 추가",
    emptyTitle: "등록된 직책이 없습니다", emptyHelp: "‘+ 직책 추가’로 직책을 만들면 사용자 폼의 '직책' 목록에 바로 나타납니다.",
    // 부서→직책→사용자 온보딩 체인(사용자 생성은 직책이 있어야 가능 — Users.jsx) — 연동→러너→워크플로
    // 체인처럼 다음 단계(사용자)로 이어 준다. 단계별 안내는 canOnboard가 쓰기 역할에만 보여준다.
    emptySituation: "부서, 직책, 사용자 온보딩 체인의 한 단계입니다, 아직 직책이 하나도 없습니다.",
    emptySteps: ["‘+ 직책 추가’로 필요한 직책을 만듭니다.", "사용할 직책을 모두 등록합니다.", "사용자 화면에서 계정을 만들 때 이 직책을 배정합니다."],
    emptyExpected: "등록한 직책은 사용자 폼의 ‘직책’ 목록에 바로 나타납니다.",
    emptyRelatedLink: { href: "#/users", label: "다음: 사용자 등록으로 이동" },
    // 이 화면은 paginated가 아니라 클라이언트 검색창이 항상 뜨는데, 기본 검색은 JSON.stringify(row)
    // 전체(원시 UUID·ISO created_at 포함)를 훑는다 — 화면에 보이는 '생성' 열은 KST로 포맷된 값인데
    // 검색은 원시 UTC ISO 문자열을 매칭해, 화면에 보이는 그대로 타이핑해도 자정 경계 근처에서
    // 못 찾을 수 있었다(오탐/누락 방지를 위해 실제로 보이는 필드인 이름만 검색 대상으로 좁힌다).
    searchFields: ["name"],
    searchPlaceholder: "직책 이름으로 검색",
    filters: ACTIVE_FILTER,
    // usage_count(보유 인원)는 보관(soft-delete)된 사용자도 센다(부서와 동일한 계산 — app/org/service.py).
    // 라벨은 부서 화면과 다르게 '보유'를 쓴다 — 직책은 사람이 '보유'하는 것이지 '소속'되는 게 아니다.
    columns: [col("name", "직책 이름"), activeCol("사용"), col("user_count", "보유 인원(보관 포함)"), dateCol("created_at", "생성")],
    // 삭제 버튼은 소속 인원>0이면 아래 actions에서 통째로 숨겨진다(부서와 동일한 이유) — 상세에 이유를 남긴다.
    detailFields: [field("id", "직책 ID"),
      { key: "_delete_note", label: "삭제 안내", render: (r) => r.user_count ? "사용 중인 직책(보유 인원 " + r.user_count + "명, 보관 계정 포함)은 삭제할 수 없습니다, 대신 ‘비활성화’를 이용하세요." : "-" }],
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
    key: "org-tree", area: "사용자", title: "조직도", endpoint: "/api/admin/departments/tree",
    help: "조직 > 부서 > 사용자 순서로 소속 관계를 봅니다. 맨 윗줄이 조직이고 그 아래 들여쓴 줄이 부서입니다. 부서 줄의 ‘소속 인원’을 누르면 그 자리에서 사람 이름까지 펼쳐 볼 수 있습니다.",
    emptyTitle: "등록된 부서가 없습니다",
    emptyHelp: "‘부서 관리’에서 부서를 만들고 상위 부서를 지정하면 여기에 계층으로 표시됩니다.",
    emptyRelatedLink: { href: "#/departments", label: "부서 관리로 이동" },
    searchFields: ["name", "path"],
    searchPlaceholder: "조직 또는 부서 이름으로 검색",
    filters: ACTIVE_FILTER,
    columns: [
      // 들여쓰기가 곧 트리다 — 표 하나로 조직도를 그리기 위한 유일한 장치라 여기서만 만든다.
      // 공백 문자가 아니라 좌측 패딩(rem)이라 4K에서 루트 폰트사이즈 레버를 그대로 따라간다.
      /* 맨 위 줄은 **조직**이다(지시서 §3 "조직 > 부서 > 사용자"). 조직이 하나뿐이어도
         그 층이 화면에 없으면 사용자는 이 부서들이 어느 조직 소속인지 알 방법이 없다.
         조직 행은 굵게, 부서 행은 들여쓰기 + 갈래표시로 갈라 놓는다. */
      { key: "name", label: "조직과 부서", render: (r) => React.createElement(
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
      { key: "kind", label: "구분", render: (r) => (r.kind === "organization" ? "조직" : "부서") },
      activeCol("사용"),
      col("user_count", "소속 인원(보관 포함)"),
      col("subtree_user_count", "하위 포함 인원"),
      col("child_count", "하위 부서"),
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
          col("display_name", "이름"),
          col("title", "직책"),
          col("email", "이메일"),
          col("role", "역할"),
          { key: "active", label: "상태", render: (u) => (u.archived_at ? "보관" : u.active ? "사용" : "비활성") },
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
  "notion-mapping": {
    key: "notion-mapping", area: "사용자", title: "Notion 사용자 연결", endpoint: "/api/admin/notion-mapping",
    help: "직원 계정과 Notion 사용자를 연결합니다. 자동 매칭되며 수동 지정도 가능합니다. (‘notion-user-mapping’ 워크플로가 등록, 활성화되어 있어야 자동 동기화, 검증이 동작합니다.)",
    // 사용자 화면(Users.jsx)의 'Notion 연결 확인' 링크가 ?user_id=를 붙여 이 화면으로 온다 — 다른
    // 9개 id 딥링크 화면(runners.onQuery 등)과 동일하게 GET /{user_id}({"mapping":...} 응답,
    // app/notion_mapping/router.py get_mapping)로 그 사용자의 상세 드로어를 곧바로 연다(예전엔 필터만
    // 채워 목록에서 다시 찾아야 했다).
    onQuery: (p) => p.user_id ? { open: "select", id: p.user_id } : null,
    selectKey: "mapping",
    emptyTitle: "표시할 사용자가 없습니다",
    // 읽기 전용 역할(operator/auditor)에는 자기 권한 밖 버튼('자동 동기화' 등)을 누르라고 안내하지 않는다.
    emptyHelp: (role) => (role === "admin" || role === "system_admin")
      ? "사용자 디렉터리의 계정이 여기에 나타납니다. ‘자동 동기화’로 Notion 사용자와 매칭하거나, 행에서 검증, 수동 연결하세요. (‘notion-user-mapping’ 워크플로가 필요합니다.)"
      : "사용자 디렉터리의 계정이 여기에 나타납니다. Notion 연결은 관리자가 수행합니다.",
    paginated: true, searchable: true,
    // 서버 검색(q)은 직원 이메일/이름만 매칭한다(app/notion_mapping/router.py) — notion_email은 검색
    // 대상이 아닌데 눈에 보이는 열이라 'Notion 이메일로 찾기'를 시도하면 결과가 없어도 이유를 알 수
    // 없었다. placeholder로 검색 범위를 명시해 조용한 0건을 줄인다.
    searchPlaceholder: "검색(직원 이메일, 이름, Notion 이메일은 검색되지 않음)",
    filters: [{ key: "status", type: "select", label: "상태", options: opt([["unmapped", "미연결"], ["verified", "확인됨"], ["conflict", "충돌"]]) },
      // 사용자 상세의 딥링크(onQuery, 위 참고)가 채우는 필드 — 직접 입력도 가능하게 남겨 둔다.
      { key: "user_ids", type: "text", label: "사용자 ID" },
      // 출처는 **서버 필터**다. 백엔드가 source 쿼리 파라미터를 받아 SQL에서 거른다
      // (app/notion_mapping/router.py list_mappings — "출처 필터는 서버측에서 한다"). 이 화면은
      // paginated라, 예전처럼 clientFilter로 두면 지금 페이지 안의 일치 항목만 남고 다른 페이지의
      // 수동 매핑은 화면에서 사라진다 — 그리고 사용자는 그걸 '그런 연결이 없다'로 읽는다.
      // 백엔드는 이미 고쳐졌는데 이 줄만 옛 사실("지원하지 않는다")을 붙들고 있었다.
      { key: "source", type: "select", label: "출처", options: opt([["workflow", "워크플로 자동"], ["manual", "수동 지정"]]) }],
    columns: [col("user_email", "사용자"), col("user_display_name", "이름"), badgeCol("status", "상태"),
      // 실패로 'unmapped'로 되돌아온 행을 '한 번도 시도 안 함'과 구분한다 — 대량 트리아지 때 각 행을
      // 열지 않아도 사유를 바로 읽을 수 있게 실제 메시지를 보여준다(길면 말줄임, title 속성으로 전체 확인).
      truncateCol("error_message", "오류", 40),
      col("notion_email", "Notion 이메일"), mapCol("source", "출처", MAP_SOURCE), dateCol("last_verified_at", "마지막 검증")],
    // 충돌 해결 시 어떤 Notion 사용자 후보가 있는지 상세에서 보여준다(blind guess 방지).
    // error_message·last_verified_at은 이미 위 columns에 있다 — 드로어는 columns+detailFields를 합쳐
    // 그리므로 여기 다시 넣으면 같은 라벨이 두 번(다른 렌더로) 나온다. 여기서는 중복 제거.
    // 드로어는 columns+detailFields를 key 기준으로 합치므로(중복 시 columns가 우선) error_message를
    // 그대로 다시 넣으면 목록의 40자 truncateCol이 그대로 이어져 상세에서도 잘린다 — 진단에 필요한
    // 전체 오류 메시지를 보여줄 별도 key(다른 화면의 path_full/last_error_full과 동일 패턴)를 쓴다.
    // candidates는 '충돌 해결' 액션의 select(위 optionsFrom)가 이미 사람이 읽는 형태(이메일 — id)로
    // 보여준다 — 상세에서 같은 데이터를 원시 JSON으로 한 번 더 보여주면 같은 정보가 두 번(하나는
    // 정리된 선택지, 하나는 원시 덩어리) 나온다. 동일한 '이메일, id' 목록으로 통일한다.
    detailFields: [field("notion_user_id_masked", "Notion ID(마스킹)"),
      { key: "candidates", label: "연결 후보", render: (r) => {
        const cs = r.candidates;
        if (!cs || !cs.length) return "-";
        return React.createElement("ul", null, cs.map((c, i) => React.createElement("li", { key: i },
          (c.notion_email ? c.notion_email + ", " : "") + c.notion_user_id)));
      } }],
    // '오류(전체)' 상세 필드는 여기서 별도로 두지 않는다 — 위 columns의 truncateCol("error_message", ...)가
    // 이미 title 속성으로 전체 텍스트를 마우스 오버 시 보여주며, 드로어도 열+detailFields 합집합을
    // 그리므로 그 열이 그대로 드로어 안에도 나타난다. 예전엔 같은 내용을 자른 버전/전체 버전으로
    // 두 번(혼란스러운 near-duplicate로) 보여줬다.
    headerActions: [
      // '자동 동기화'는 POST /sync가 즉시 202로 큐잉될 뿐 30초를 기다리지 않는다(그 30초 문구는
      // 개별 '검증' 액션의 것 — verify_mapping이 실제로 동기 30초 타임아웃이다). 백그라운드 작업
      // 자체는 SYNC_TIMEOUT_SECONDS=90초까지 걸릴 수 있다(app/jobs/handlers/notion_mapping_sync.py).
      // primary:true — 백업(+ 백업 실행)·문서(+ 문서 생성) 화면과 동일하게, 이 화면의 headline
      // 액션을 EmptyState CTA로도 승격한다(그렇지 않으면 목록이 완전히 비어 있을 때 이 버튼이 안 보였다).
      { label: "자동 동기화", primary: true, roles: WRITE_ROLES, path: () => "/api/admin/notion-mapping/sync", confirm: "Notion 사용자와 자동 매칭을 다시 실행할까요? 수동으로 지정한 연결도 일치하는 후보가 없으면 해제될 수 있습니다. Notion 조회에 최대 1~2분 정도 걸릴 수 있으며, 화면은 진행 상태를 자동으로 갱신합니다.",
        // 202 큐 작업 — 완료를 단정하지 않고 실제 상태를 반영해 안내한다.
        result: (res) => {
          const running = res && (res.status === "running" || res.deduplicated);
          return { ok: true, kind: "info", msg: running
            ? "이미 동기화가 진행 중입니다. 완료되면 목록이 자동으로 갱신됩니다."
            : "동기화 작업을 시작했습니다(진행 중). 완료되면 목록이 자동으로 갱신됩니다." };
        },
        // 큐 작업이 끝날 때까지 폴링해 완료 시점에 목록을 갱신하고 결과를 알린다(화면에서 완료 피드백 제공).
        // 폴링은 최대 40초(20×2s)까지만 기다린다 — SYNC_TIMEOUT_SECONDS보다 짧게 끝나면 그 뒤로는
        // 아무도 다시 목록을 갱신하지 않는다(QueryClient가 refetchOnWindowFocus:false). '자동으로
        // 갱신됩니다'는 지키지 못할 약속이었다 — 새로고침이 필요하다고 정직하게 안내한다.
        pollJob: { getId: (res) => res && res.job_id, interval: 2000, maxTries: 20,
          doneMsg: "자동 동기화가 완료되었습니다. 목록을 갱신했습니다.",
          failMsg: "자동 동기화 작업이 실패했습니다",
          timeoutMsg: "동기화가 아직 진행 중입니다. 이 화면은 자동으로 갱신되지 않을 수 있으니, 잠시 후 새로고침해 확인하세요." } },
    ],
    // 검증·수동 연결·충돌 해결·연결 해제는 모두 상태 변경(쓰기) — 백엔드 RBAC와 일치시켜 쓰기 역할만 노출.
    actions: [
      { label: "검증", roles: WRITE_ROLES, path: (r) => "/api/admin/notion-mapping/" + r.user_id + "/verify",
        // 자동 검증은 워크플로 재소스로 매칭한다 — 수동으로 지정한 연결(source==='manual')을
        // 무일치로 덮어써 지울 수 있으므로(service.py no-match 처리) 그 경우만 별도로 경고한다.
        confirm: (r) => r.source === "manual"
          ? "이 사용자를 지금 검증할까요? 수동으로 지정한 연결입니다, 자동 검증이 일치를 못 찾으면 연결이 해제될 수 있습니다. (Notion에 직접 조회하므로 최대 30초까지 걸릴 수 있습니다.)"
          : "이 사용자를 지금 검증할까요? Notion에 직접 조회하므로 최대 30초까지 걸릴 수 있습니다.",
        result: (res) => {
          const m = (res && res.mapping) || res || {};   // res===null(빈 2xx)이면 res.mapping 접근이 throw — 널가드
          // status==='verified'인데 error_message가 새로 채워졌다면 이번 조회 자체가 실패한 것이다
          // (백엔드 verify_mapping이 n8n 조회 예외를 삼키고 상태는 건드리지 않은 채 error_message만
          // 채워 돌려준다 — 상태만 보면 '검증됨'이라 거짓 성공 토스트가 뜬다). 기존 연결은 유지되지만
          // 이번 시도는 실패로 알린다.
          if (m.status === "verified" && !m.error_message) return { ok: true, msg: "검증 완료: 연결됨" };
          if (m.status === "verified" && m.error_message) return { ok: false, kind: "warn", msg: "검증 중 오류가 발생했습니다(기존 연결은 유지됨): " + m.error_message };
          // 충돌은 실패가 아니라 '관리자 해결이 필요한' 정상 분기 — 오류 톤으로 표시하지 않는다.
          if (m.status === "conflict") return { ok: false, kind: "info", msg: "충돌 감지: 여러 Notion 사용자가 일치합니다. 아래 ‘충돌 해결’에서 지정하세요." };
          // '미연결(unmapped)'은 시스템 실패가 아니라 정상적인 검증 결과다 → 정보 톤으로 안내(오류 톤 과장 금지).
          // 백엔드 verify_mapping은 no-match에도 error_message('일치하는 Notion 사용자가 없습니다.')를 채우므로
          // error_message 유무로 갈라선 안 된다(그렇게 하면 이 정보 분기가 죽고 정상 결과가 빨간 오류로 뜬다).
          if (m.status === "unmapped") return { ok: false, kind: "info", msg: (m.error_message || "연결된 Notion 사용자를 찾지 못했습니다") + " 필요하면 ‘수동 연결’로 지정하세요." };
          // 예상 밖 상태(verified/conflict/unmapped 외)만 진짜 실패로 표시한다.
          return { ok: false, msg: "검증 실패: " + (m.error_message || m.status || "일치하는 Notion 사용자를 찾지 못했습니다") };
        } },
      { label: "수동 연결", roles: WRITE_ROLES, path: (r) => "/api/admin/notion-mapping/" + r.user_id + "/map", fields: [
        { name: "notion_user_id", label: "Notion 사용자 ID", type: "text", required: true, help: "Notion 워크스페이스의 사용자 ID(8~64자, 영문, 숫자, 하이픈)." },
        { name: "notion_email", label: "Notion 이메일(선택)", type: "text" },
      ] },
      { label: "충돌 해결", roles: WRITE_ROLES, when: (r) => r.status === "conflict", path: (r) => "/api/admin/notion-mapping/" + r.user_id + "/resolve-conflict", fields: [
        // 후보 목록에서 바로 고른다(원시 JSON에서 8~64자 id를 복사·붙여넣는 실수 방지).
        { name: "notion_user_id", label: "연결할 Notion 사용자", type: "select", required: true,
          optionsFrom: (r) => (r.candidates || []).map((c) => ({ value: c.notion_user_id, label: (c.notion_email ? c.notion_email + ", " : "") + c.notion_user_id })),
          help: "이 사용자와 충돌한 Notion 후보 중 올바른 사람을 고르세요." },
      ] },
      // 충돌 행도 해제 가능(후보가 모두 오답일 때 '미연결'로 초기화). 백엔드 unmap은 어떤 상태에서도 동작한다.
      { label: "연결 해제", variant: "danger", roles: WRITE_ROLES, when: (r) => r.status === "verified" || r.status === "conflict" || r.source === "manual", path: (r) => "/api/admin/notion-mapping/" + r.user_id + "/unmap", confirm: "이 사용자의 Notion 연결을 해제할까요?" },
      // user_notion_mapping은 감사 로그의 유효한 object_type이고(OBJTYPE_OPTS, object_id=user_id) 이
      // 화면의 검증/수동 연결/충돌 해결/해제/동기화가 모두 이 타입으로 기록된다 — 부서·직책과 동일한 딥링크.
      // operator는 이 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — 다른 화면들의 동일한 '감사 로그에서 보기'와 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=user_notion_mapping&object_id=" + r.user_id },
    ],
  },
};
