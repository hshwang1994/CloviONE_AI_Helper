import React from "react";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
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

/* 목록 맨 위의 요약. **집계는 서버가 한다.**
 *
 * 화면에서 `items` 를 세면 안 된다 - 목록은 20건씩 잘려 나가므로 "총 22건인데 요약은
 * 20건 기준" 이 된다(app/projects/service.py::project_dashboard 가 같은 판단을 기록한다).
 * 그래서 이 훅은 목록 질의와 **별개의 경로**를 부르고, 조건(qs)을 싣지 않는다 - 요약은
 * 보고 있는 페이지가 아니라 범위 전체를 말한다.
 */
export function useProjectDashboard() {
  return useQuery({
    queryKey: ["projects", "dashboard"],
    queryFn: () => api("/api/projects/dashboard"),
    retry: false,
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

// FN-06: 백엔드는 이미 주 단위 이력을 쌓고 있었다(worker_main.py 의 시간당 스윕) — 화면만
// 그걸 부를 방법이 없었다.
export function useProjectHealthHistory(id, enabled) {
  return useQuery(detail(id, "health/history", enabled));
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

/* ── 쓰기 ────────────────────────────────────────────────────────────────────
 *
 * 백엔드에는 처음부터 생성·수정·마일스톤 CRUD 가 다 있었는데(app/projects/router.py) 화면에
 * 그 버튼이 하나도 없었다. 사용자가 지적한 것이 바로 그 상태다: "노션에서 설정 및 추가를
 * 못 한다고 생각해라" - 포털에서 만들고 고칠 수 있어야 한다.
 */

/** 이 프로젝트를 그리는 **모든 캐시**를 무효화한다.
 *
 * 🔴 목록·요약·상세를 **전부** 건드리는 것이 요점이다. 하나만 하면 저장은 됐는데 다른
 * 화면이 옛 값을 계속 보여 준다 - 이 저장소가 E6 에서 정확히 그 실수를 겪었다. 특히 요약
 * (dashboard)을 빠뜨리기 쉽다: 상태를 '완료' 로 바꿨는데 맨 위 '진행 12건' 이 그대로다.
 *
 * `refetchType: "all"` 인 이유: 기본값은 지금 화면에 붙어 있는 질의만 다시 부른다. 상세에서
 * 고치고 목록으로 돌아가면 목록 질의는 그때 비활성이라 옛 값이 그대로 남는다.
 */
function invalidateProject(qc, id) {
  qc.invalidateQueries({ queryKey: ["projects", "list"], refetchType: "all" });
  qc.invalidateQueries({ queryKey: ["projects", "dashboard"], refetchType: "all" });
  if (id) qc.invalidateQueries({ queryKey: ["projects", "one", id], refetchType: "all" });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => api("/api/projects", { method: "POST", body }),
    // 새 프로젝트는 아직 상세를 열고 있지 않으므로 id 를 넘길 필요가 없다. 목록과 요약은
    // 반드시 다시 받아야 한다 - 안 하면 방금 만든 것이 목록에 없다.
    onSuccess: () => invalidateProject(qc, null),
  });
}

export function useUpdateProject(id) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => api("/api/projects/" + encodeURIComponent(id), {
      method: "PATCH", body,
    }),
    onSuccess: () => invalidateProject(qc, id),
  });
}

// FN-04: 백엔드(DELETE /api/projects/{id})는 보관(soft delete)이고 화면엔 "보관됨" 배지·
// "보관한 프로젝트 포함" 체크박스까지 있었는데, 그 상태로 보내는 버튼 자체가 없었다.
export function useArchiveProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api("/api/projects/" + encodeURIComponent(id), { method: "DELETE" }),
    onSuccess: (_data, id) => invalidateProject(qc, id),
  });
}

// FN-06: progress_pct/health_score는 이미 백그라운드가 채워 준다(sync.py의 동기화 후
// recompute_progress 호출, worker_main.py의 시간당 record_health_snapshots 스윕) — 이
// 두 뮤테이션은 그 값이 틀렸다는 뜻이 아니라, 방금 티켓/마일스톤을 고친 사람이 다음 스윕까지
// 기다리지 않고 지금 당장 반영시킬 수 있게 하는 수동 트리거다.
export function useRecomputeProgress(id) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/api/projects/" + encodeURIComponent(id) + "/progress/recompute", {
      method: "POST",
    }),
    onSuccess: () => invalidateProject(qc, id),
  });
}

export function useSnapshotHealth(id) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/api/projects/" + encodeURIComponent(id) + "/health/snapshot", {
      method: "POST",
    }),
    onSuccess: () => invalidateProject(qc, id),
  });
}

/* 마일스톤 세 개는 경로만 다르고 무효화 대상이 같다. 마일스톤이 바뀌면 Health 판정("기한
 * 지난 마일스톤")과 요약의 '지연 마일스톤' 이 함께 달라지므로 프로젝트 캐시 전체를 턴다. */
function milestonePath(projectId, milestoneId) {
  return "/api/projects/" + encodeURIComponent(projectId) + "/milestones"
    + (milestoneId ? "/" + encodeURIComponent(milestoneId) : "");
}

export function useCreateMilestone(projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => api(milestonePath(projectId), { method: "POST", body }),
    onSuccess: () => invalidateProject(qc, projectId),
  });
}

export function useUpdateMilestone(projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => api(milestonePath(projectId, id), {
      method: "PATCH", body,
    }),
    onSuccess: () => invalidateProject(qc, projectId),
  });
}

export function useDeleteMilestone(projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => api(milestonePath(projectId, id), { method: "DELETE" }),
    onSuccess: () => invalidateProject(qc, projectId),
  });
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
