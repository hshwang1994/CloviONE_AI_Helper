/* 방의 신원 스냅샷 (G5) — 「누가 누구인가」의 정본 하나.
 *
 * `leave_room` 은 구성원 행을 지운다(`app/games/service.py`). 그래서 끝난 뒤 나간 사람의 얼굴 · 이름을 `members` 로는 못 푼다 —
 * 서버가 시작할 때 구성원 전원의 신원을 상태에 박고(`state.people`), 응답은 그것과 지금 있는 구성원을 합쳐 최상위 `people` 로
 * 준다(지금 있는 사람이 이긴다 — 새 사진의 `?v=`). 화면의 모든 얼굴은 `personOf(people, user_id)` 로 푼다. */

/** 응답의 `people` 과 `members` 를 한 지도로. 구성원이 스냅샷보다 새 값이다. */
export function buildPeople(data) {
  const out = {};
  const snap = data && data.people && typeof data.people === "object" ? data.people : {};
  for (const [uid, p] of Object.entries(snap)) {
    if (uid && p && typeof p === "object") out[uid] = { user_id: uid, ...p };
  }
  for (const m of (data && data.members) || []) {
    if (m && m.user_id) out[m.user_id] = { ...(out[m.user_id] || {}), user_id: m.user_id, name: m.name, avatar_url: m.avatar_url, avatar_default_key: m.avatar_default_key };
  }
  return out;
}

/** 신원 하나. 모르는 사람은 `null` — 지어내지 않는다(부르는 쪽이 이름만으로 그린다). */
export function personOf(people, userId) {
  if (!userId || !people) return null;
  return people[userId] || null;
}

/** 이름의 첫 글자 — 얼굴이 없는 자유 이름(구슬)의 색 원에 쓴다. */
export function initialOf(name) {
  const s = String(name || "").trim();
  return s ? Array.from(s)[0] : "?";
}
