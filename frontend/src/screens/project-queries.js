import React from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { useAuth } from "../app/auth.jsx";

/* 프로젝트 화면들이 쓰는 질의 한 벌. **경로와 질의 키를 여기 한 곳에만 둔다.**
 *
 * 화면마다 `api("/api/projects/" + id + "/health")` 를 직접 쓰면 키가 조금씩 달라지고,
 * 그러면 같은 데이터를 두 번 받거나(요청 두 배) 한쪽만 갱신되어 두 화면이 다른 숫자를
 * 말한다. 티켓 화면이 같은 이유로 `ticket-options.js` 를 따로 두고 있다.
 *
 * `enabled` 를 받는 이유: 상세는 탭 화면이라 지금 안 보이는 탭의 자료까지 받아 올 이유가
 * 없다. 첫 진입에 왕복 여섯 번을 붙이면 느린 것은 사용자가 실제로 보는 탭이다.
 */

const LONG = 5 * 60 * 1000;

/** 목록 한 페이지. `qs` 는 화면이 조립한 질의 문자열이다(조건이 늘어도 키를 안 고쳐도 된다). */
export function useProjectList(qs) {
  return useQuery({
    queryKey: ["projects", "list", qs],
    queryFn: () => api(qs ? "/api/projects?" + qs : "/api/projects"),
    retry: false,
    // 페이지를 넘길 때마다 카드가 통째로 스켈레톤으로 깜빡이면 목록이 어디로 갔는지 알 수 없다.
    placeholderData: keepPreviousData,
  });
}

export function useProject(id) {
  return useQuery({
    queryKey: ["projects", "one", id],
    queryFn: () => api("/api/projects/" + encodeURIComponent(id)),
    enabled: !!id,
    retry: false,
  });
}

function detail(id, suffix, enabled, extra) {
  return {
    queryKey: ["projects", "one", id, suffix, extra || ""],
    queryFn: () => api(
      "/api/projects/" + encodeURIComponent(id) + "/" + suffix + (extra ? "?" + extra : ""),
    ),
    enabled: !!id && enabled !== false,
    retry: false,
  };
}

export function useProjectProgress(id, enabled) {
  return useQuery(detail(id, "progress", enabled));
}

export function useProjectHealth(id, enabled) {
  return useQuery(detail(id, "health", enabled));
}

export function useProjectWbs(id, enabled) {
  return useQuery(detail(id, "wbs", enabled));
}

export function useProjectMilestones(id, enabled) {
  return useQuery(detail(id, "milestones", enabled));
}

/** 주간 리포트. `week` 는 주 중 아무 날이고, 비면 서버가 이번 주로 정한다. */
export function useProjectWeekly(id, week, enabled) {
  return useQuery(detail(id, "weekly-report", enabled, week ? "week=" + encodeURIComponent(week) : ""));
}

/* 부서 id → 이름.
 *
 * 프로젝트 API 는 `dept_id` 만 준다. 이름을 주는 경로는 `/api/admin/departments` 하나뿐이고
 * **관리자군만** 부를 수 있다(app/org/router.py 의 CONSOLE_WRITE_ROLES). 그래서 역할을 보고
 * 부를 수 있을 때만 부른다 - 모두가 부르게 두면 일반 사용자의 프로젝트 화면마다 403 이
 * 한 번씩 나가고, 그건 화면에 아무 도움도 안 되면서 로그만 더럽힌다.
 *
 * 이름을 모르는 사람에게는 부서 자리를 아예 안 그린다(project-format.js::deptLabel).
 */
const DEPT_ROLES = ["admin", "system_admin"];

export function useDeptNames() {
  const auth = useAuth();
  const role = (auth.data && auth.data.role) || "";
  const q = useQuery({
    queryKey: ["departments", "names"],
    queryFn: () => api("/api/admin/departments"),
    enabled: DEPT_ROLES.includes(role),
    retry: false,
    staleTime: LONG,
  });
  const rows = (q.data && q.data.items) || null;
  return React.useMemo(() => {
    const out = {};
    for (const row of rows || []) out[row.id] = row.name;
    return out;
  }, [rows]);
}
