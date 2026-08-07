import { keyframes } from "@mui/system";

/* 게임방 화면 전반에서 쓰는 상태/역할 라벨, 모션 키프레임, 공용 sx, 가위바위보 라벨.
 * GameRoom.jsx 구조 분리(2026-08)로 값 변경 없이 이 파일로 옮겼다. 원래 GameRoom() 함수 안에
 * 있던 지역 RPS_LABELS/RPS_EMOJI와 RpsTournamentLive가 쓰던 T_RPS_LABELS/T_RPS_EMOJI는 완전히
 * 같은 값(["가위","바위","보"] / ["✌️","✊","✋"])이었다 — 옮기며 하나로 합쳤다. */

export const STATUS_LABELS = { waiting: "대기 중", playing: "진행 중", finished: "결과 확인 중" };
export const STATUS_KIND = { waiting: "info", playing: "warn", finished: "ok" };
export const ROLE_LABELS = { host: "방장", player: "참여", spectator: "관전" };

export const pop = keyframes`
  0% { transform: scale(.5); opacity: 0; }
  55% { transform: scale(1.14); }
  75% { transform: scale(.96); }
  100% { transform: scale(1); opacity: 1; }
`;
export const rise = keyframes`
  from { transform: translateY(12px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
`;
export const draw = keyframes`to { stroke-dashoffset: 0; }`;
export const pulse = keyframes`
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.12); }
`;

export const bracketListSx = { listStyle: "none", m: 0, p: 0, display: "grid", gap: 1, width: "100%", maxWidth: "30rem" };
export const stageColumnSx = { display: "grid", gap: 1.5, justifyItems: "center", width: "100%" };

export const RPS_LABELS = ["가위", "바위", "보"];
export const RPS_EMOJI = ["✌️", "✊", "✋"];
export function rpsEmoji(label) {
  return RPS_EMOJI[RPS_LABELS.indexOf(label)] || "";
}
