import { PROSE_MAX_WIDTH } from "../../ui/theme.js";
import { CHAT } from "../../ui/chat.js";

/* AI 채팅의 폭 규격 — 화면(Chat.jsx)과 조각(목록 · 메시지 · 참고 자료)이 같은 숫자를 본다.
 *
 * 틀은 채팅방과 같은 어휘다(핸드오프 RULES §9 「목록 296 · 스레드 나머지 · 두 판 다 카드」). 몇 칸이 서는지는 **카드가 놓인
 * 폭**이 정한다(`useChatLayout`) — 창 폭으로 정하면 앱 사이드바 · 확대 · 4K 루트 글자 크기(18 · 20px)에 따라 같은 창에서도
 * 칸이 모자랐다. 문턱은 rem 이라 루트 글자 크기를 따른다.
 *
 *   wide    ≥ 74rem   목록 · 스레드 · 참고 자료(그 대화에 참고 자료가 있을 때, 사람이 접을 수 있다)   1920 · 125%
 *   medium  ≥ 52rem   목록 · 스레드, 참고 자료는 답 아래 접기                                           1366
 *   narrow  ≥ 37.5rem 스레드만, 목록은 서랍                                                             1024
 *   mobile  < 37.5rem 스레드만, 목록은 전체 폭 서랍                                                    390
 */
export const CHAT_LAYOUT_REM = { wide: 74, medium: 52, mobile: 37.5 };

/* 대화 목록 칸 폭(296) — 채팅방과 같은 값이다. */
export const LIST_WIDTH = CHAT.listWidth;

/* 참고 자료 칸 폭(300). */
export const SOURCES_WIDTH = "18.75rem";

/* 스레드 기둥의 상한 — 결과 목록 · 코드 · 표가 쓰는 폭이다. 글줄은 아래 `ANSWER_TEXT_MAX` 로 더 좁다(46rem ≈ 한 줄 48자).
 * 1920 에서도 가운데 기둥이 화면을 가로지르지 않는다. */
export const THREAD_MAX = "min(100%, 52rem)";
export const ANSWER_TEXT_MAX = PROSE_MAX_WIDTH;

/* 내 말풍선의 상한 — 짧은 질문은 글만큼, 긴 질문은 스레드의 3/4 까지. */
export const USER_BUBBLE_MAX = "min(75%, 36rem)";

/* 옛 이름 — 클로비 패널과 옛 시험이 쓴다. 도우미 답은 이제 말풍선이 아니라 글 기둥이다. */
export const BUBBLE_MAX = `min(88%, ${PROSE_MAX_WIDTH})`;

/* 흐름 모드(창이 1200×600 보다 작을 때)의 판 높이 — 화면 아래까지 선다. `dvh` 라 휴대폰의 주소 막대가 접히고 펴져도 입력 칸이
 * 화면 밖으로 밀리지 않는다(키보드는 브라우저마다 달라 최선 노력이다). 채움 모드에서는 앱 틀이 높이를 준다.
 * clovi-allow-geometry: 채움 판의 높이다(`density.js::PAGE_FILL_HEIGHT` 와 같은 자리, 단위만 dvh). */
export const CHAT_FLOW_HEIGHT = "calc(100dvh - 12rem)";

/* 휴대폰(600px 미만)의 판 높이 — 페이지 머리의 「문서에서 찾기」가 제목 아래 줄로 내려가 판이 1.5rem 더 아래에서 시작한다.
   같은 12rem 을 쓰면 판 아래가 화면을 넘어 입력 칸이 잘렸다(390×844 실측 11px).
   clovi-allow-geometry: 채움 판의 높이다(위 `CHAT_FLOW_HEIGHT` 와 같은 자리). */
export const CHAT_FLOW_HEIGHT_PHONE = "calc(100dvh - 13.5rem)";

/* 대화 목록 서랍의 폭(좁음) — 휴대폰에서는 판 전체다. */
export const DRAWER_WIDTH = "min(20rem, 88%)";
