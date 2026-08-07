import { PROSE_MAX_WIDTH } from "../../ui/theme.js";

/* AI 채팅 그리드의 폭 상수 — Chat.jsx와 그 아래로 쪼갠 화면 조각(사이드바·메시지·결과 레일)이
 * 전부 같은 숫자를 봐야 한다. 레일이 있는지 없는지, 말풍선이 몇 글자에서 줄바꿈하는지가
 * 파일마다 갈라지면 조각마다 다른 폭을 그리게 된다.
 *
 * 열 폭은 rem이다 — 루트 폰트사이즈 레버(styles/root.css)가 4K에서 18/20px로 올라가면 목록과
 * 레일도 같은 비율로 넓어진다. px로 박아 두면 3840에서 목록이 실처럼 가늘어진다(앱 셸이 겪은 문제). */
export const COLUMNS = {
  xs: "minmax(0,1fr)",
  xl: "19rem minmax(0,1fr)",
  xxl: "21rem minmax(0,1fr) 26rem",
  uhd: "23rem minmax(0,1fr) 30rem",
};

/* 스레드 열 자체의 상한. 말풍선 안 글줄은 따로 PROSE_MAX_WIDTH로 더 좁게 잡는다 — 이 값은
 * 카드·구분선이 화면 가운데 기둥처럼 서 있게 하는 바깥 틀일 뿐이다. */
export const THREAD_MAX = "min(100%, 76rem)";

// 말풍선 글줄 상한. 남는 폭은 세 번째 열로 가고 줄은 절대 길어지지 않는다.
export const BUBBLE_MAX = `min(88%, ${PROSE_MAX_WIDTH})`;
