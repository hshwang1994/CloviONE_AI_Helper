/* 자유게시판 순수 헬퍼 — 컴포넌트에서 분리해 단위 테스트한다(레포의 *-helpers 관례). */

// 목록 쿼리스트링. 빈 카테고리/검색은 넣지 않고, 정렬은 화이트리스트로 고정한다.
export function buildPostsQuery({ category, q, sort } = {}) {
  const p = new URLSearchParams();
  if (category) p.set("category", category);
  if (q) p.set("q", q);
  p.set("sort", sort === "views" ? "views" : "recent");
  return p.toString();
}

// 반응 배열 → {이모지: {count, mine}} 맵(토글 판정·표시에 쓴다).
export function reactionMap(reactions) {
  const m = {};
  (reactions || []).forEach((r) => {
    if (r && r.emoji) m[r.emoji] = { count: r.count || 0, mine: !!r.mine };
  });
  return m;
}

// 댓글 배열 → {tops, repliesByParent}. 최상위 댓글과 그 답글(한 단계)을 나눈다.
export function splitComments(comments) {
  const list = Array.isArray(comments) ? comments : [];
  const tops = list.filter((c) => !c.parent_comment_id);
  const repliesByParent = {};
  list.forEach((c) => {
    if (c.parent_comment_id) {
      (repliesByParent[c.parent_comment_id] =
        repliesByParent[c.parent_comment_id] || []).push(c);
    }
  });
  return { tops, repliesByParent };
}
