/* 조직 콘솔의 질의와 무효화 한 벌.
 *
 * 🔴 queryKey 뿌리(`["org-tree"]`·`["departments"]`·`["organizations"]`·`["users"]`)는
 * 계약이다 — Users.jsx 의 저장 후 무효화(Users.jsx::refresh)와 `CROSS_SCREEN_KEYS` 가
 * 이 이름으로 이 화면을 갱신한다. 뿌리를 바꾸면 「사용자 화면에서 부서를 바꿨는데
 * 조직도가 옛 모습」이 된다(옛 `["org-console","people"]` 키가 실제로 그랬다 — Users 의
 * `["users"]` 무효화가 못 닿는 이름이라 소속 인원 판이 낡은 채 남는 잠복 결함이었다). */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api.js";
import { CROSS_SCREEN_KEYS } from "../data-screen/crossScreenKeys.js";

export const TREE_ENDPOINT = "/api/admin/departments/tree";

/** 조직도 트리 — 전량 응답이다. 조직 관리 작업 공간은 `active` 없이 하나만 받고 「사용 중만」을 화면에서 거른다(조상을 남긴다,
 * `orgTreeModel.js`). 서버 거르기(`?active=`)는 걸러진 부모의 자식을 맨 위로 끌어올려 계층을 틀었다 — 인자는 다른 소비처를 위해 남긴다. */
export function useOrgTreeQuery(active) {
  return useQuery({
    queryKey: ["org-tree", active || ""],
    queryFn: () => api(TREE_ENDPOINT + (active ? "?active=" + active : "")),
    retry: false,
  });
}

/** 조직 목록 — 파라미터도 페이지네이션도 없는 전량 응답(app/org/router.py). 상세 판은
 * 여기서 id 로 찾는다: 행 수가 곧 전체라 단건 질의를 따로 두면 왕복만 는다. */
export function useOrganizations() {
  return useQuery({
    queryKey: ["organizations"],
    queryFn: () => api("/api/admin/organizations"),
    retry: false,
  });
}

/** 부서 단건 — 응답이 `{department: {...}}` 봉투다(app/org/router.py::get_org_item).
 * 봉투째 sel 로 삼으면 id 가 undefined 가 되는 함정을 DataScreen 이 selectKey 로 풀었었다. */
export function useDepartmentItem(id) {
  return useQuery({
    queryKey: ["departments", "item", id],
    queryFn: () => api("/api/admin/departments/" + encodeURIComponent(id)),
    select: (data) => (data && data.department) || data,
    enabled: Boolean(id),
    retry: false,
  });
}

/** 부서를 지우거나 비활성화하면 무엇이 달라지는가(D-533) — 창이 **열려 있을 때만** 묻는다. 뿌리가 `departments` 라
 * 조직 · 부서를 고친 뒤의 무효화(`invalidateOrgCaches`)가 함께 닿는다. */
export function useDeptImpact(id, enabled) {
  return useQuery({
    queryKey: ["departments", "impact", id],
    queryFn: () => api("/api/admin/departments/" + encodeURIComponent(id) + "/impact"),
    enabled: Boolean(id) && Boolean(enabled),
    retry: false,
    staleTime: 0,
  });
}

/** 조직을 비활성화하면 누가 로그아웃되는가(D-533) — 창이 열려 있을 때만 묻는다. */
export function useOrgImpact(id, enabled) {
  return useQuery({
    queryKey: ["organizations", "impact", id],
    queryFn: () => api("/api/admin/organizations/" + encodeURIComponent(id) + "/impact"),
    enabled: Boolean(id) && Boolean(enabled),
    retry: false,
    staleTime: 0,
  });
}

/** 상위 부서 후보 — **조건 무관 전량**이어야 한다. 목록에 걸린 필터가 후보를 좁히면
 * 「미사용 부서만 상위로 고를 수 있는」 폼이 된다(PARENT_DEPT_FIELD 원칙).
 * Users.jsx 의 useNameOptions 와 같은 엔드포인트·같은 캐시 뿌리다. */
export function useDepartmentOptions() {
  return useQuery({
    queryKey: ["departments"],
    queryFn: () => api("/api/admin/departments"),
    retry: false,
  });
}

/** 조직·부서를 고친 뒤 낡는 것 전부 — DataScreen 의 refresh 와 동등한 계약을 로컬로
 * 재현한다. `CROSS_SCREEN_KEYS` 를 import 해서 쓴다(두 벌 금지) — 티켓 담당자 드롭다운이
 * 부서·조직 이름을 싣고 있어(`["tickets"]`) 그 축까지 함께 낡는다. */
export function invalidateOrgCaches(qc) {
  qc.invalidateQueries({ queryKey: ["organizations"] });
  qc.invalidateQueries({ queryKey: ["departments"] });
  qc.invalidateQueries({ queryKey: ["org-tree"] });
  for (const key of CROSS_SCREEN_KEYS.organizations) qc.invalidateQueries({ queryKey: key });
  for (const key of CROSS_SCREEN_KEYS.departments) qc.invalidateQueries({ queryKey: key });
}

export function useInvalidateOrgCaches() {
  const qc = useQueryClient();
  return () => invalidateOrgCaches(qc);
}
