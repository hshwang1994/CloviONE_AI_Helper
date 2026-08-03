import { api } from "./api.js";

/* 통합 검색 클라이언트 (백엔드: GET /api/search).
 *
 * 팔레트(Ctrl+K)와 결과 화면이 **같은 함수**를 쓴다. 두 곳이 각자 fetch 를 쓰면 하나만
 * 고쳐지는 날이 오고, 그때 "팔레트에는 나오는데 결과 화면에는 없다"가 된다.
 *
 * 유형별 라벨·라우트는 서버가 응답에 실어 준다. 화면이 유형별 if 를 갖지 않는 것이 핵심이다 —
 * 새 유형이 늘 때 백엔드만 고치면 팔레트·결과 화면·빈 상태가 함께 따라온다.
 */

/* trigram 인덱스는 3자 미만을 못 만든다. 서버가 1~2자를 LIKE 폴백으로 처리하므로
 * 프런트는 **1자부터 보낸다** — 여기서 막으면 서버의 폴백이 죽은 코드가 된다. */
export const MIN_SEARCH_CHARS = 1;

export function normalizeQuery(raw) {
  return String(raw || "").trim().replace(/\s+/g, " ");
}

export function isSearchable(raw) {
  return normalizeQuery(raw).length >= MIN_SEARCH_CHARS;
}

export function searchApi(q, { limit } = {}) {
  const params = new URLSearchParams({ q: normalizeQuery(q) });
  if (limit) params.set("limit", String(limit));
  return api("/api/search?" + params.toString());
}

/* 그룹 배열을 평평한 목록으로. 팔레트의 위/아래 키 이동이 그룹을 넘나들어야 한다. */
export function flattenGroups(groups) {
  return (groups || []).flatMap((g) =>
    (g.items || []).map((item) => ({ ...item, groupLabel: g.label })),
  );
}

export function totalOf(result) {
  return (result && Number(result.total)) || 0;
}

/* 결과 한 줄을 눌렀을 때 갈 곳. 서버가 준 route 를 쓰되, 비어 있으면 이동하지 않는다
 * (없는 곳으로 보내는 것보다 안 움직이는 편이 낫다 — '되는 척'을 만들지 않는다). */
export function routeOf(item) {
  const route = item && item.route;
  return typeof route === "string" && route.startsWith("/") ? route : null;
}

/* 결과 화면 주소. 팔레트의 '모든 결과 보기'와 상단바 입력이 같은 곳으로 간다. */
export function searchResultsPath(q) {
  return "/search?q=" + encodeURIComponent(normalizeQuery(q));
}
