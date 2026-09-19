/* 채팅 전용 시각 규격 — 핸드오프 README §C · RULES §9 (소유자 확정, 2026-09-14).
 *
 * ## 왜 공통 토큰이 아니라 여기인가
 *
 * 채팅방은 판·표·폼과 **다른 읽기 방식**을 가진 화면이다. 말풍선 모서리 12 와 연결 모서리 4,
 * 상대 아바타 34, 머리 참여자 스택 26(−8 겹침), 입력창 모서리 10 은 공통 토큰의 가장 가까운 값
 * (8 · 30 · 6)으로 접으면 채팅이 판처럼 보인다 — 소유자가 「가장 가까운 공통 값으로 바꾸지
 * 마라」로 확정했다. 그래서 값을 화면 파일에 흩지 않고 **이 한 곳**에 두고, 채팅방과 AI 도우미가
 * 여기서 가져간다(`COMPONENT_LEDGER.md` 「채팅 전용 규격」 절에 근거).
 *
 * 새 CSS 시스템이 아니다. MUI `sx` 가 그대로 받는 값이고, 색은 전부 테마 토큰이다.
 *
 * ## 소비처
 *
 *   채팅방(`/chat-rooms`)   전부(`ChatRooms` 목록 폭 · `ChatRoom` 머리 스택 · `ChatPane` 말풍선 · 입력)
 *   AI 도우미(`/chat`)       `bubbleRadius` · `bubbleJoinRadius` · `composerRadius` · `tool` 과 공통 날짜
 *                            구분선(`ChatDaySeparator` 의 `daySeparatorWidth`)만 쓴다(P-26 · UI 3차 C-6 — 열 폭과
 *                            말풍선 최대 폭은 그 화면의 계약이다)
 *   부품 갤러리              「채팅 규격」 절
 */
import { CONTROL, RADIUS } from "./theme.js";

export const CHAT = {
  /* 말풍선 모서리. AI 도우미의 말풍선도 같은 값을 쓴다. */
  bubbleRadius: 12,
  /* 이어지는 말풍선이 모이는 모서리 — 상대는 묶음 첫 말풍선의 시작 모서리, 나는 마지막 말풍선의 끝 모서리. */
  bubbleJoinRadius: RADIUS.xs,
  /* 말풍선 최대 폭 — 한 줄이 스레드를 가로질러 읽기 어려워지지 않고, 좌우 자리로 화자가 갈린다. */
  bubbleMaxWidth: "68%",
  /* 대화 목록 칸 폭(296). */
  listWidth: "18.5rem",
  /* 상대 얼굴(34) — 이름 줄과 첫 말풍선 두 줄에 걸친다. */
  avatar: "2.125rem",
  /* 방 머리 참여자 얼굴 스택(26)과 겹침(−8). 얼굴 둘레 흰 선이 겹친 경계를 가른다. */
  stackAvatar: "1.625rem",
  stackOverlap: "-0.5rem",
  /* 입력 상자 모서리(10) — 판(8)과 입력칸(6) 사이의 값이다. 공통 토큰으로 접으면 입력이 판처럼 보인다. */
  composerRadius: 10,
  /* 입력 도구 · 보내기 단추(30) — 작은 단추 토큰 그대로다. */
  tool: CONTROL.buttonSm,
  /* 말풍선 밖 시각 글자(0.6875rem) — 본문(0.9375rem)과 이름(0.875rem)보다 두 단 작다. */
  timeText: "0.6875rem",
  /* 날짜 구분선의 폭(28rem) — 스레드 가운데에 선다(UI 3차 조합 계약 C-6). 스레드 전폭으로 그으면 1920 에서 선 두 줄이
     말풍선보다 길게 달려 대화를 칸막이로 자른다. 채팅방과 AI 도우미가 같은 구분선(`ui/ChatDaySeparator.jsx`)을 쓴다. */
  daySeparatorWidth: "28rem",
};
