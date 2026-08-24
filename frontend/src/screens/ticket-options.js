import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { api } from "../lib/api.js";

/* 티켓 화면들이 함께 쓰는 **후보 목록** 질의(진행상태·우선순위·난이도 / 프로젝트 / 담당자).
 *
 * 예전에는 내 티켓 화면 안에 모듈 비공개로 있었다. 공용 필터 부품이 같은 목록을 필요로
 * 하면서 밖으로 뺐다 — 필터 부품이 내 티켓 화면을 import 하면 화면이 부품을 import 하는
 * 것과 맞물려 순환이 된다. 질의 키가 같으므로 여러 화면이 동시에 불러도 요청은 한 번이다.
 *
 * `enabled` 를 받는 이유: 편집 모달은 열릴 때만 후보가 필요하고, 필터 줄은 그 조건을
 * 실제로 그릴 때만 필요하다. 목록 화면의 첫 로드에 쓸데없는 왕복을 붙이지 않는다. */

export function useAssigneeOptions(enabled, projectId) {
  /* `projectId` 를 주면 **그 프로젝트에 닿을 수 있는 사람만** 후보가 된다 (0060 §14).
   *
   * 담당자와 프로젝트 ACL 이 어긋나면 그 사람은 **자기가 담당한 티켓을 못 여는** 상태가
   * 된다(목록에도 안 뜬다). 고를 수 없게 막는 편이 그 상태를 만들고 나서 설명하는 것보다
   * 낫다 — 서버도 같은 판정을 하므로(app/tickets/service.py) 화면이 유일한 방어는 아니다.
   *
   * 프로젝트가 아직 안 정해졌으면 후보를 묻지 않는다. 전체 명부를 먼저 보여 줬다가 프로젝트를
   * 고르는 순간 절반이 사라지면, 사용자는 방금 고른 사람이 왜 없어졌는지 알 수 없다.
   */
  return useQuery({
    queryKey: ["tickets", "assignees", projectId || ""],
    queryFn: () =>
      api("/api/tickets/assignees" + (projectId ? `?project_id=${encodeURIComponent(projectId)}` : "")),
    enabled: !!enabled, retry: false, staleTime: 60000,
  });
}

export function useTicketMeta(enabled) {
  return useQuery({
    queryKey: ["tickets", "meta"], queryFn: () => api("/api/tickets/meta"),
    enabled: !!enabled, retry: false, staleTime: 300000,
  });
}

export function useTicketProjects(enabled) {
  return useQuery({
    queryKey: ["tickets", "projects"], queryFn: () => api("/api/tickets/projects"),
    enabled: !!enabled, retry: false, staleTime: 300000,
  });
}

/* 목록 한 페이지. `qs` 는 화면이 조립한 질의 문자열(TicketFilterBar.ticketQueryParams)이다.
 *
 * 질의 키에 `qs` 를 통째로 넣는다 — 조건 하나가 늘 때마다 키 배열을 같이 고쳐야 하면
 * 언젠가 안 고치고, 그때 증상은 "필터를 바꿨는데 목록이 그대로"(캐시가 안 갈린다)다.
 *
 * `placeholderData` 로 이전 페이지를 남긴다. 필터·페이지를 바꿀 때마다 표가 통째로
 * 스켈레톤으로 깜빡이면 목록이 어디로 갔는지 알 수 없다(문서 목록·관리자 목록도 같다). */
export function useTicketList(path, qs) {
  return useQuery({
    queryKey: ["tickets", path, qs],
    queryFn: () => api(qs ? `${path}?${qs}` : path),
    retry: false,
    placeholderData: keepPreviousData,
  });
}

/* 티켓 한 건의 **프로젝트 축**. 행이 두 자리로 실어 오기 때문에 여기 한 곳에서만 고른다.
 *
 *   `project_uid`  해석된 Portal 프로젝트 id — 화면이 고르는 값과 **같은 축**이다
 *                  (`/api/tickets/projects` 가 주는 것이 `projects.id` 다).
 *   `project_ids`  이관해 온 티켓이 아직 달고 있는 옛 소스의 relation id 목록.
 *
 * 옛 축만 읽으면 화면은 **자기가 준 적 없는 값**을 들고 있게 된다. 그 값은 어느 후보와도
 * 안 맞으므로, 필터는 언제나 0건이 되고 편집 폼의 프로젝트 칸은 언제나 비어 보인다 —
 * 둘 다 오류를 안 내고 「이 프로젝트엔 티켓이 없다」·「이 티켓엔 프로젝트가 없다」로
 * 읽힌다. 서버는 이미 두 축을 함께 본다(`app/tickets/query.py::filter_clauses`).
 */
export function ticketProjectId(ticket) {
  const t = ticket || {};
  if (t.project_uid) return t.project_uid;
  const legacy = Array.isArray(t.project_ids) ? t.project_ids : [];
  return legacy[0] || "";
}

/** 응답의 목록. 서버는 `items` 를 정본으로 주고 `tickets` 는 옛 화면 호환용 별칭이다. */
export function ticketRows(data) {
  const d = data || {};
  const rows = Array.isArray(d.items) ? d.items : d.tickets;
  return Array.isArray(rows) ? rows : [];
}
