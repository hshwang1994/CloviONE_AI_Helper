/* 놀이의 축포 — 값과 구현은 `ui/celebrate.js` 한 곳이다.
 *
 * 예전에는 축포 구현이 이 파일에만 있었고, 그래서 이 제품에서 축포가 터질 수 있는 자리가
 * 「게임방 승자 공개」 하나뿐이었다. 업무를 끝낸 자리(회차 닫기·내 티켓 비우기·승인 비우기)
 * 에도 같은 축하를 주려고 구현을 공용으로 옮겼다 — 두 축포가 다른 모양이면 같은 제품이
 * 두 가지 축하를 갖게 된다. 이 파일에는 **게임에만 있는 것**(승자 지문)만 남는다. */
export { celebrate } from "../../ui/celebrate.js";

// 결과에 '승자'가 있으면 방별 고유 문자열(축포 트리거 키)을, 없으면 null. 값이 바뀔 때만 축포.
export function deriveCelebrateKey(data) {
  if (!data || !data.room || data.room.status !== "finished") return null;
  const gt = data.room.game_type;
  const res = (data.state && data.state.result) || null;
  if (!res) return null;
  let sig = null;
  if (gt === "random_draw" && Array.isArray(res) && res.length) sig = "d:" + res.map((w) => w.user_id).join(",");
  else if (gt === "quick_vote" && (res.winners || []).length) sig = "v:" + res.winners.join(",");
  else if (gt === "number" && res.winner) sig = "n:" + res.winner.user_id;
  else if (gt === "rps" && res.mode === "tournament" && res.champion) sig = "t:" + res.champion.user_id;
  else if (gt === "rps" && res.outcome === "win") sig = "r:" + (res.winners || []).map((w) => w.user_id).join(",");
  else if (gt === "quiz" && (res.winners || []).length) sig = "q:" + res.winners.join(",");
  else if (gt === "marble_race" && data.state.announceable && (res.winners || []).length) sig = "m:" + res.winners.join(",");
  return sig ? data.room.id + sig : null;
}

/* 발표 열쇠(D-563) — 방 id + 결과 번호(`result_seq`). 승자가 없는 결과(팀 나누기 · 사다리 · 무승부)도 발표는 하므로
 * `deriveCelebrateKey` 와 다르다(그쪽은 축포의 조건). 구슬 레이스는 서버가 확정해 발표해도 되는 결과(`announceable`)만.
 * 결과 번호가 없는 옛 응답은 승자 지문으로 대신한다. */
export function deriveResultKey(data) {
  if (!data || !data.room || data.room.status !== "finished") return null;
  const res = data.state && data.state.result;
  if (data.room.game_type === "marble_race") {
    if (!res || !data.state.announceable) return null;
  } else if (!res || (Array.isArray(res) && !res.length)) {
    return null;
  }
  const seq = data.result_seq != null ? data.result_seq : (deriveCelebrateKey(data) || "r");
  return `${data.room.id}:${seq}`;
}
