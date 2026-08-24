/* 생성물이다. 손으로 고치지 마라.
 *
 *   python scripts/gen_mascot_bounds.py
 *
 * 정본은 `app/static/brand/mascot/mascot-bounds.json` 이고 그 값을 만든 정의는
 * `scripts/gen_mascot_bounds.py` 머리말에 있다 — 알파 ≥ 128 인 픽셀의 bbox,
 * 단 불투명 픽셀이 반대 차원의 0.5% 미만인 행/열은 버린다.
 *
 * `hfrac` 은 «자산 세로 가운데 캐릭터가 실제로 차지하는 비율» 이다. 화면이 «보이는 크기»
 * 를 말하면 `Mascot.jsx` 가 이 값으로 나눠 CSS 박스를 만든다 — 그래서 여백이 다른 자산끼리
 * 같은 크기로 보인다. 이 파일이 낡으면 `scripts/static_checks.sh` 가 잡는다.
 */

export const MASCOT_BOUNDS = {
  "clovi-avatar.png": { hfrac: 0.84, wfrac: 0.8, size: [1024, 1024] },
  "clovi-button.png": { hfrac: 0.666, wfrac: 0.891, size: [1024, 1024] },
  "clovi-error.png": { hfrac: 0.727, wfrac: 0.68, size: [1024, 1024] },
  "clovi-happy.png": { hfrac: 0.793, wfrac: 0.813, size: [1024, 1024] },
  "clovi-idle-blink.png": { hfrac: 0.85, wfrac: 0.781, size: [1024, 1024] },
  "clovi-idle.png": { hfrac: 0.798, wfrac: 0.73, size: [1024, 1024] },
  "clovi-love.png": { hfrac: 0.808, wfrac: 0.75, size: [1024, 1024] },
  "clovi-sleep.png": { hfrac: 0.745, wfrac: 0.747, size: [1024, 1024] },
  "clovi-talking.png": { hfrac: 0.817, wfrac: 0.943, size: [1024, 1024] },
  "clovi-think.png": { hfrac: 0.772, wfrac: 0.705, size: [1024, 1024] },
  "clovi-wave.png": { hfrac: 0.715, wfrac: 0.811, size: [1024, 1024] },
  "clovi-canonical-avatar.png": { hfrac: 0.953, wfrac: 1.0, size: [256, 256] },
  "clovi-canonical-eye-base.png": { hfrac: 0.784, wfrac: 0.883, size: [1024, 1024] },
  "clovi-canonical-eyes-layer.png": { hfrac: 0.055, wfrac: 0.161, size: [1024, 1024] },
  "clovi-canonical-hero.png": { hfrac: 0.784, wfrac: 0.883, size: [1024, 1024] },
  "empty-board.png": { hfrac: 0.706, wfrac: 0.839, size: [1024, 1024] },
  "empty-chat.png": { hfrac: 0.762, wfrac: 0.754, size: [1024, 1024] },
  "empty-docs.png": { hfrac: 0.724, wfrac: 0.806, size: [1024, 1024] },
  "empty-notify.png": { hfrac: 0.842, wfrac: 0.793, size: [1024, 1024] },
  "empty-search.png": { hfrac: 0.789, wfrac: 0.647, size: [1024, 1024] },
  "empty-tickets.png": { hfrac: 0.622, wfrac: 0.844, size: [1024, 1024] },
  "empty-trash.png": { hfrac: 0.74, wfrac: 0.682, size: [1024, 1024] },
  "state-404.png": { hfrac: 0.704, wfrac: 0.592, size: [1024, 1024] },
  "state-500.png": { hfrac: 0.771, wfrac: 0.8, size: [1024, 1024] },
  "state-no-permission.png": { hfrac: 0.7, wfrac: 0.834, size: [1024, 1024] },
  "state-offline.png": { hfrac: 0.655, wfrac: 0.784, size: [1024, 1024] },
  "state-session-expired.png": { hfrac: 0.677, wfrac: 0.783, size: [1024, 1024] },
  "state-success.png": { hfrac: 0.777, wfrac: 0.713, size: [1024, 1024] },
};

/** 자산 경로(또는 파일 이름) → 세로 잉크 비율. 모르는 자산이면 1(= 여백 없음)로 본다. */
export function hfracOf(src) {
  const name = String(src || "").split("/").pop();
  const entry = MASCOT_BOUNDS[name];
  return entry ? entry.hfrac : 1;
}
