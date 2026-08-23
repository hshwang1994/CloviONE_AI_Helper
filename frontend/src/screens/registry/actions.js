/* 관리자 설정 화면들이 함께 쓰는 **액션과 폼 조립**. (E-10 로 registry.js 에서 갈라져 나왔다.)
 *
 * 여기 있는 것: 켜기/끄기 같은 공통 액션 묶음, 버전 이력 하위 목록, 헬스·테스트 결과 문구,
 * 문서/템플릿 설정을 폼 필드로 폈다 다시 접는 변환.
 * 여기 없는 것: 값의 한국어 표기와 열 정의 — 그건 shared.js 다.
 *
 * 이 파일의 함수들은 **설정 객체를 만들 뿐** 화면을 그리지 않는다. 그리는 것은 DataScreen 이다.
 * 그 경계를 넘기 시작하면 registry 가 다시 한 덩어리가 된다.
 */
import React from "react";
import { WRITE_ROLES, badgeCol, col, dateCol, opt, personField } from "./shared.js";
// enable/disable 공통 액션(활성 값에 따라 노출) — enable/disable는 쓰기 권한 필요.
// disableConfirm을 넘기면 행별로 다른 확인 문구를 쓴다(예: 워크플로의 예약 행 — 비활성화가 실제
// 서비스를 멈추는 경우 일반 "비활성화하시겠습니까?"보다 강한 경고가 필요하다).
// extraEnableWhen(r) — '활성화' 버튼을 !r.enabled 외에 추가 조건으로도 숨겨야 하는 리소스용(예:
// 스케줄의 실행 시각이 이미 지난 once형 — 눌러도 백엔드가 항상 409 'once 스케줄의 실행 시각이
// 이미 지났습니다'로 거절한다. 눌러도 항상 실패하는 버튼을 애초에 숨긴다).
// PA-RC-0023: '활성화'는 primary가 아니라 default다 — 이 액션이 뜨는 상세 모달에는 이미
// '수정'(DataScreen.jsx의 canEdit 분기, 항상 primary)이 같이 떠 있다. 화면/오버레이당
// primary는 정확히 하나여야 하는데(같은 원칙으로 '비활성화'는 이미 danger), '활성화'만
// primary로 남아 있어 두 개가 동시에 채워져 있었다 — Users.jsx의 '복구'가 이미 같은
// 상황(활성화 성격 + 수정과 공존)을 default로 맞춰 둔 것과 같은 결로 통일한다.
export const onoff = (base, disableConfirm, extraEnableWhen) => [
  { label: "활성화", variant: "default", roles: WRITE_ROLES, when: (r) => !r.enabled && (!extraEnableWhen || extraEnableWhen(r)), path: (r) => base + "/" + r.id + "/enable" },
  { label: "비활성화", variant: "danger", roles: WRITE_ROLES, when: (r) => r.enabled, path: (r) => base + "/" + r.id + "/disable", confirm: disableConfirm || "이 항목을 비활성화할까요?" },
];
// 승인 대기가 아닌(종료된) 상태
export const APPROVAL_DONE = ["approved", "rejected", "expired", "cancelled"];
// active 토글 공통(부서·직책) — /enable·/disable 하위경로가 없어 PATCH 본문으로 처리한다.
// PA-RC-0023: 위 onoff()와 같은 이유로 default — '수정'이 이미 이 상세 모달의 primary다.
export const activeToggle = (base) => [
  { label: "활성화", variant: "default", roles: WRITE_ROLES, when: (r) => !r.active, method: "PATCH", path: (r) => base + "/" + r.id, body: { active: true } },
  // r.user_count가 이미 같은 행 열에 로드돼 있으므로, 실제로 몇 명이 영향을 받는지 확인 문구에 반영한다
  // (0명이든 200명이든 똑같은 경고였다 — 사용 중인 부서/직책을 무심코 끄기 쉬웠다).
  { label: "비활성화", variant: "danger", roles: WRITE_ROLES, when: (r) => r.active, method: "PATCH", path: (r) => base + "/" + r.id, body: { active: false },
    confirm: (r) => r.user_count
      ? "비활성화하면 이 항목을 쓰는 사용자 " + r.user_count + "명이 사용자 폼에서 더 이상 새로 고를 수 없게 됩니다. 계속할까요?"
      : "비활성화하면 사용자 폼에서 새로 고를 수 없게 됩니다. 계속할까요?" },
];
// 사용 여부 필터 공통(부서·직책).
export const ACTIVE_FILTER = [{ key: "active", type: "select", label: "사용", options: opt([["true", "사용 중"], ["false", "미사용"]]) }];

/* 상위 부서 — 조직도를 실제로 만들 수 있게 하는 필드.
 *
 * 백엔드는 처음부터 parent_id 를 받았고(0024 가 departments.parent_id 를 만들었다,
 * app/org/schemas.py 도 받는다) 조직도 화면은 "상위 부서는 '부서 관리' 화면에서 지정합니다"라고
 * 안내하고 있었다. 그런데 **그 화면에 그 필드가 없었다** — 안내문이 거짓말이었고, 트리는
 * CLI 나 API 를 직접 두드려야만 만들 수 있었다.
 *
 * 후보에서 자기 자신은 뺀다(자기 부모가 될 수 없다). 하위 부서를 부모로 고르는 순환은
 * 백엔드(app/org/tree.py::validate_parent)가 거절하므로 여기서 다시 계산하지 않는다 —
 * 같은 규칙을 두 곳에 두면 반드시 어긋난다.
 */
export const PARENT_DEPT_FIELD = {
  name: "parent_id",
  label: "상위 부서",
  type: "select",
  value: "",
  help: "비우면 최상위 부서가 됩니다. 하위 부서를 상위로 고르면 순환이 되어 저장되지 않습니다.",
  optionsFrom: (row, rows) => opt([
    ["", "(최상위)"],
    ...(rows || [])
      .filter((d) => !row || d.id !== row.id)
      .map((d) => [d.id, d.name]),
  ]),
};
// 버전 스냅샷 열 — 각 버전 행의 config 스냅샷(r.snapshot)에서 값을 읽어 보여준다(롤백 전 내용 확인).
export const snapCol = (key, label, map) => ({ key: "snap_" + key, label, render: (r) => {
  const v = r.snapshot ? r.snapshot[key] : undefined;
  if (v == null || v === "") return "-";
  return map ? (map[v] || String(v)) : String(v);
} });
// 버전 기록·롤백 공통 액션(config-versioned 리소스: 연동·러너·워크플로).
// extraCols: 스냅샷에서 뽑아 보여줄 추가 열(base_url/auth_type/enabled 등) — 블라인드 롤백 방지.
// confirmFn(sub, parent) — 기본 확인 문구를 행별로 강화해야 하는 리소스(예: 워크플로의 예약 행)를
// 위한 선택적 오버라이드. DataScreen.jsx의 SubListDrawer.act()가 confirm을 (하위 행, 부모 행) 두
// 인자로 호출하므로 parent(부모 행)를 읽어 경고 문구를 만들 수 있다.
// namedCreator — RG-07: 셋 다 "변경자"를 쓰지만 이름을 실제로 주는 건 워크플로뿐이다(연동·러너의
// /versions는 정말 이름을 안 준다, app/integrations/router.py 확인함) — 그래서
// personField를 기본으로 못 켠다. 이름을 주는 쪽만 true로 켠다.
export const versionsAction = (base, extraCols, confirmFn, namedCreator) => ({
  label: "버전 기록",
  subList: {
    title: "버전 기록",
    endpoint: (r) => base + "/" + r.id + "/versions",
    columns: [col("version", "버전"),
      namedCreator ? personField("created_by", "변경자", "created_by_name", "created_by_email") : col("created_by", "변경자 ID"),
      dateCol("created_at", "시각"), ...(extraCols || [])],
    emptyTitle: "버전 기록이 없습니다",
    rowAction: {
      label: "이 버전으로 롤백", variant: "danger", roles: WRITE_ROLES,
      path: (sub, r) => base + "/" + r.id + "/rollback",
      body: (sub) => ({ version: sub.version }),
      confirm: confirmFn || ((sub) => "버전 " + sub.version + "(으)로 롤백할까요? 현재 설정을 이 버전으로 되돌립니다."),
    },
  },
});
// 이름 기준 버전 관리 리소스(프롬프트·정책)의 '버전 기록' 액션 — 같은 이름의 모든 버전을 모아
// 롤백(그 버전을 새 발행본으로 복원)과 버전 비교(현재 행 버전과의 통합 diff)를 하위 행에서 바로 건다.
// 상태와 무관하게 노출한다(백엔드는 롤백·조회에 상태 전제조건이 없다).
export const nameVersionsAction = (base, title) => ({
  label: "버전 기록",
  subList: {
    title,
    // '비교' 액션은 명시적 from/to 선택기가 없다 — from은 클릭한 하위 행, to는 지금 열려 있는
    // 버전(부모 행)으로 암묵적으로 정해진다. 무엇을 비교하는지 미리 알려준다.
    hint: "비교 기준은 지금 열려 있는 버전입니다.",
    // 이 하위 목록은 부모 목록과 동일한 GET(page_size 상한 500, app/prompts/router.py)을 쓴다 —
    // 부모(prompts/policies)의 paginated:true+capWarning:500 처리와 맞춰, 500건을 넘는 이름은
    // 뒷페이지를 계속 볼 수 있게 한다(예전엔 첫 페이지 500건만 오고 더 볼 방법이 없었다).
    paginated: true,
    endpoint: (r, p) => base + "?name=" + encodeURIComponent(r.name) + "&page=" + ((p && p.page) || 1),
    // _prompt_view/_policy_view가 감사 로그의 actor_name과 동일한 패턴으로 created_by_name/
    // created_by_email을 이미 계산해 돌려준다 — 원시 UUID 대신 그 이름을 보여준다.
    columns: [col("version", "버전"), badgeCol("status", "상태"),
      { key: "created_by", label: "작성자", render: (r) => r.created_by_name || r.created_by_email || r.created_by || "-" },
      dateCol("created_at", "생성")],
    emptyTitle: "버전 기록이 없습니다",
    rowActions: [
      { label: "이 버전으로 롤백", variant: "danger", roles: WRITE_ROLES,
        path: () => base + "/rollback",
        body: (sub) => ({ name: sub.name, version: sub.version }),
        confirm: (sub) => "버전 " + sub.version + "(으)로 롤백할까요? 그 버전 내용을 새 발행본으로 복원합니다." },
      // 비교는 조회형(GET) — 통합 diff 문자열을 안내 모달로 보여준다(같은 버전끼리는 숨김).
      { label: "비교", method: "GET",
        when: (sub, parent) => parent && sub.version !== parent.version,
        path: (sub, parent) => base + "/diff/view?name=" + encodeURIComponent(sub.name) + "&from=" + sub.version + "&to=" + parent.version,
        info: (res) => (res && res.diff && String(res.diff).trim()) ? String(res.diff) : "선택한 버전과 기준(현재) 버전의 내용이 동일합니다." },
      // 이 버전 목록을 가져오는 GET base?name=... 응답이 이미 각 버전의 전체 content를 포함한다
      // (app/prompts/router.py _prompt_view) — 그런데 이 하위 목록은 version/status/작성자/생성일만
      // 보여주고 실제 지시문 내용은 어디서도 읽을 방법이 없었다. 이미 불러온 데이터를 그대로(네트워크
      // 호출 없이) 안내 모달로 보여준다(schedules 실행 이력의 '전체 보기'와 동일한 localInfo 패턴).
      // content는 프롬프트(텍스트)·정책(JSON 객체) 둘 다에 쓰이는 공용 helper라 타입을 가려 표시한다.
      { label: "내용 보기", localInfo: (sub) => {
        const c = sub.content;
        if (c == null || c === "") return "(내용 없음)";
        return typeof c === "string" ? c : JSON.stringify(c, null, 2);
      } },
    ],
  },
});
// 헬스/테스트 결과 정직 표시 공통(up/ok면 성공, 아니면 원인 포함 오류).
// checked_url — 실제로 어느 주소를 찔렀는지(health_url, 비었으면 base_url로 대체) 함께 보여준다.
// health_url을 잘못 설정했거나 비워 뒀을 때, 토스트만 보고는 실제 대체(base_url)가 일어났는지
// 알 수 없었다(app/integrations/service.py run_health_check가 이미 checked_url을 돌려주는데도 버려졌었다).
export const healthResult = (res) => ({ ok: res.status === "up", msg: (res.status === "up" ? "정상" + (res.latency_ms != null ? ` (${res.latency_ms}ms)` : "") : "중단: " + (res.detail || "확인 실패")) + (res.checked_url ? " (" + res.checked_url + ")" : "") });
