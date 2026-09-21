/* 조직 — 직책.
 *
 * 옛날 이 파일은 조직·부서·조직도 화면 설정까지 들었다. 그 셋은 조직 콘솔
 * (screens/OrgConsole.jsx + screens/org/)이 **선택 반응형 상세 판**으로 재구성되면서
 * registry 를 떠났다 — 콘솔이 폼·확인 문구·질의를 자기 파일로 들고, 여기 남겨 두면
 * 어떤 렌더 경로에도 닿지 않는 죽은 설정이 된다(실제로 org-tree 의 열·액션 절반이
 * 그렇게 죽어 있었다). 직책만 평범한 목록 화면이라 DataScreen 설정으로 남는다.
 *
 * registry.js 를 쪼갠 조각이다 (E-10). 화면 설정만 있고 그리는 코드는 없다 — 그리는
 * 것은 DataScreen.jsx 하나다.
 */
import { WRITE_ROLES, activeCol, col, dateCol, field } from "./shared.js";
import { ACTIVE_FILTER, activeToggle } from "./actions.js";

export const ORG_SCREENS = {
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
    // 「직책 이름」이 그 행의 이름이라 제목 열이다(D-501) — 홀로 왼쪽에 서고 남는 폭을 갖는다. 예전에는 네 열이
    // 1,600px 을 똑같이 나눠 「선임」 두 글자가 400px 칸 가운데에 떠 있었다. 남는 폭을 제목이 가져가면 나머지는
    // 자기 바닥으로 서므로, 머리 이름이 긴 「보유 인원(보관 포함)」은 그 이름이 한 줄로 서는 바닥을 든다.
    columns: [col("name", "직책 이름", "title"), activeCol("사용"),
      { ...col("user_count", "보유 인원(보관 포함)"), type: "count", minWidth: "10rem" }, dateCol("created_at", "생성 일자")],
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
};
