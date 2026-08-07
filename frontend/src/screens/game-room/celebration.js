import confetti from "canvas-confetti";
import { prefersReducedMotion } from "../../ui/motion.js";

/* 승자 공개 축포 — GameRoom.jsx 구조 분리(2026-08)로 값 변경 없이 이 파일로 옮겼다.
 * canvas-confetti는 캔버스를 CSSOM 개별 속성으로 스타일링하고 기본은 워커 미사용이라
 * CSP(style-src 'self', worker 미허용)에 안전하다.
 * 동작 최소화는 두 겹으로 막는다: (1) 여기서 아예 호출하지 않는다 — JS로 켜는 연출은 전역 CSS
 * 규칙이 닿지 않으므로 우리가 직접 판단해야 한다. (2) 그래도 라이브러리 옵션을 남겨 둔다. */
export function celebrate() {
  if (prefersReducedMotion()) return;
  const base = { spread: 74, startVelocity: 45, ticks: 200, origin: { y: 0.55 }, disableForReducedMotion: true };
  confetti({ ...base, particleCount: 90 });
  window.setTimeout(() => confetti({ ...base, particleCount: 55, angle: 60, origin: { x: 0, y: 0.62 } }), 140);
  window.setTimeout(() => confetti({ ...base, particleCount: 55, angle: 120, origin: { x: 1, y: 0.62 } }), 260);
}

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
  return sig ? data.room.id + sig : null;
}
