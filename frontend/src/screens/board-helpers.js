/* 자유게시판 순수 헬퍼 — 컴포넌트에서 분리해 단위 테스트한다(레포의 *-helpers 관례). */

// 정렬 화이트리스트. 'likes' 는 공감(👍) 많은 순 — 제안 게시판의 기본이다.
const SORTS = new Set(["recent", "views", "likes"]);

/* 목록 쿼리스트링. 빈 카테고리/검색은 넣지 않고, 정렬은 화이트리스트로 고정한다.
 *
 * `kind` 는 자유게시판일 때 **아예 안 싣는다.** 서버 기본값이 자유라, 안 싣는 쪽이
 * 예전 주소·북마크(`/api/board/posts?sort=recent`)와 글자 그대로 같은 요청이 된다.
 * `status` 도 마찬가지로 고른 것이 있을 때만 붙는다 — 주소만 보고 "지금 필터가 걸려
 * 있나"를 알 수 있어야 한다. */
export function buildPostsQuery({ category, q, sort, kind, status } = {}) {
  const p = new URLSearchParams();
  if (kind && kind !== "free") p.set("kind", kind);
  if (category) p.set("category", category);
  if (q) p.set("q", q);
  p.set("sort", SORTS.has(sort) ? sort : "recent");
  if (status) p.set("status", status);
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
