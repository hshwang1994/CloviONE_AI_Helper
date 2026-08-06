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

export function useAssigneeOptions(enabled) {
  return useQuery({
    queryKey: ["tickets", "assignees"], queryFn: () => api("/api/tickets/assignees"),
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

/** 응답의 목록. 서버는 `items` 를 정본으로 주고 `tickets` 는 옛 화면 호환용 별칭이다. */
export function ticketRows(data) {
  const d = data || {};
  const rows = Array.isArray(d.items) ? d.items : d.tickets;
  return Array.isArray(rows) ? rows : [];
}
