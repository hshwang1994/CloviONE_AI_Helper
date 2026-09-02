/* 문서 작업공간의 질의 한 벌.
 *
 * 🔴 모든 queryKey 는 `["knowledge", ...]` 로 시작해야 한다 — 휴지통 복원·영구삭제의
 * 무효화 표(`screens/document-views.js`)가 접두사 일치로 동작하고, 키가 안 따라온 것이
 * D-313 의 사고였다. 새 질의를 더할 때도 같은 접두사를 쓴다. */

import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api.js";
import { offsetEnvelope, useInfiniteList } from "../../lib/useInfiniteList.js";
import { PAGE_SIZE, VIEW } from "./constants.js";

export function useTree(spaceId) {
  return useQuery({
    queryKey: ["knowledge", "tree", spaceId],
    queryFn: () => api(`/api/knowledge/spaces/${spaceId}/tree`),
    enabled: Boolean(spaceId),
  });
}

/* 옛 문서 화면의 「문서 종류·업무 분야·기술 태그」 세 필터는 대신하지 않는다 — 그 셋은
 * `document_cache` 의 고정 상수 축이고 이관에서 태그로 손실 없이 들어왔다(S14 결정 D6). */
export function useTags() {
  return useQuery({ queryKey: ["knowledge", "tags"], queryFn: () => api("/api/knowledge/tags") });
}

/* 카테고리 — 조직이 스스로 만드는 분류 어휘(0026). 필터 고르개와 분류 관리가 함께 쓴다. */
export function useCategories() {
  return useQuery({
    queryKey: ["knowledge", "categories"],
    queryFn: () => api("/api/knowledge/categories"),
  });
}

export function useSummary() {
  return useQuery({
    queryKey: ["knowledge", "summary"],
    queryFn: () => api("/api/knowledge/summary"),
  });
}

export function useTemplates() {
  return useQuery({
    queryKey: ["knowledge", "templates"],
    queryFn: () => api("/api/knowledge/templates"),
    staleTime: 600000,
  });
}

export function useRecent() {
  return useQuery({
    queryKey: ["knowledge", "recent"],
    queryFn: () => api("/api/knowledge/recent?limit=8"),
  });
}

/* 문서 목록 — **쪽이 아니라 묶음**이다.
 *
 * 갈래가 둘인 이유: 「최근 열람」은 다른 입구(`/api/knowledge/recent`)를 쓰고 쪽 자체가
 * 없다. 사람마다 다르고 길지 않아서 나눌 것이 없다 — 없는 쪽 나누기를 흉내 내지 않는다.
 * 그 갈래만 평범한 질의이고, 아래에서 무한 목록과 **같은 모양**으로 펴서 돌려준다.
 * 화면은 둘을 구별하지 않는다.
 *
 * 훅 둘을 언제나 부르고 `enabled` 로 끈다 — 갈래에 따라 훅 수가 달라지면 React 가
 * 상태를 잘못 짝짓는다. */
export function useDocuments(params) {
  const { view, spaceId, folderId, q, tags, category, author, sort, resume } = params;
  const isRecent = view === VIEW.recent;

  const recentQ = useQuery({
    queryKey: ["knowledge", "documents", "recent"],
    queryFn: () => api("/api/knowledge/recent?limit=50"),
    enabled: isRecent,
  });

  const tagKey = (tags || []).join("\u0000");
  const list = useInfiniteList({
    key: ["knowledge", "documents", view, spaceId, folderId, q, tagKey, category, author, sort],
    envelope: offsetEnvelope,
    size: PAGE_SIZE,
    /* offset 페이징은 그 사이 문서가 생기거나 지워지면 경계에서 같은 행을 두 번 준다.
       이어 붙이는 화면에서는 한 화면 안에 같은 문서 둘이 된다 — id 로 거른다. */
    rowId: (d) => d.id,
    enabled: !isRecent,
    resume,
    fetch: ({ limit, offset }) => {
      const search = new URLSearchParams();
      if (spaceId) search.set("space_id", spaceId);
      if (folderId) search.set("folder_id", folderId);
      if (q) search.set("q", q);
      // 다중 태그는 AND 다(app/knowledge/service.py::list_documents) — 서버가 같은
      // 이름의 반복 파라미터를 배열로 받는다.
      (tags || []).forEach((t) => search.append("tags", t));
      if (category) search.set("category_id", category);
      if (author) search.set("created_by", author);
      if (sort) search.set("sort", sort);
      if (view === VIEW.favorites) search.set("favorites", "true");
      if (view === VIEW.drafts) { search.set("mine", "true"); search.set("drafts", "true"); }
      search.set("limit", String(limit));
      search.set("offset", String(offset));
      return api(`/api/knowledge/documents?${search.toString()}`);
    },
  });

  if (!isRecent) return list;
  const items = (recentQ.data && recentQ.data.items) || [];
  return {
    rows: items,
    total: items.length,
    loaded: items.length,
    first: recentQ.data || null,
    hasNext: false,
    fetchNext: () => {},
    isFetchingNext: false,
    isLoading: recentQ.isPending,
    isError: recentQ.isError,
    error: recentQ.error,
    refetch: recentQ.refetch,
  };
}
