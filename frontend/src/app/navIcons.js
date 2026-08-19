/* 아이콘 키 → 컴포넌트, **한 계열**로 (지시 79 · R-48 · R-79).
 *
 * ## 계열
 *
 * 계열은 `@mui/icons-material` 의 `*Outlined` 하나다. 예전에는 이 파일만 Lucide 를 썼고
 * 그 근거였던 기준 목업은 지시 64 로 없앴다(D-142). 채운 실루엣은 작은 크기에서 글자보다
 * 무겁다 — 몇 개가 `*Rounded` 인 것은 그 이름에 Outlined 변형이 없는 경우이고 전부 선 도형이다.
 * 개별 경로로 import 한다(배럴을 쓰면 아이콘 수천 개가 번들 그래프에 들어온다 — 정적 검사가
 * 같은 규칙을 강제한다).
 *
 * ## 왜 표가 37개에서 4개로 줄었나 — 자식 아이콘 규칙 (W3)
 *
 * PLAN «Icon System» 의 규칙은 하나다: **그룹이 아이콘을 가지면 그 자식들은 아이콘을 갖지
 * 않는다. 그룹 없는 최상위 항목은 아이콘을 갖는다.** 두 사이드바의 모든 항목이 그룹 안에
 * 있고 모든 그룹이 아이콘을 가지므로, 결과는 **랜드마크 그룹당 글리프 하나 + 한 줄에 정렬된
 * 라벨들**이다. 그룹 글리프는 `navConfig.js` 가 컴포넌트로 직접 들고 있다(키를 거치지 않는다).
 *
 * 그 전에는 항목마다 키가 붙어 있었고, 그 결과가 R-48 이 금지한 바로 그 상태였다 —
 * `ticket` 4곳 · `report` 4곳 · `docs` 3곳 · `policy` 3곳 · `users` 3곳처럼 **같은 그림이 여러
 * 메뉴에서 반복**되어 훑을 때 두 항목이 한 덩어리로 보였고, 41개 글리프가 라벨 시작선을
 * 그룹 60px / 자식 64px 로 갈라 놓았다(F-W1R-18 픽셀 실측). 쓰지 않는 키를 남겨 두면 다음
 * 사람이 그것을 근거로 다시 붙인다 — 그래서 지운다.
 *
 * ## 남은 넷이 하는 일
 *
 * Command Palette 의 **결과 유형** 표시다(지시 14: "최근 방문, 메뉴, 티켓, 문서 등 검색 결과
 * 유형을 쉽게 구분"). 서버가 유형별로 묶어 주는 결과 줄 앞에 그 유형의 그림을 놓는다 —
 * 줄마다 유형을 글자로 다시 적으면 구역 제목과 같은 말을 두 번 한다(지시 44). 사이드바
 * 항목 줄에는 이 표가 쓰이지 않는다.
 *
 * 사용자 rail 이 flat 해지는 날(W11, R-58)에는 그 최상위 항목들이 다시 글리프를 갖는다 —
 * 그때 이 표가 자란다. 규칙이 바뀌는 게 아니라 구조가 바뀌는 것이다.
 */

import Ticket from "@mui/icons-material/ConfirmationNumberOutlined";
import FileText from "@mui/icons-material/DescriptionOutlined";
import ClipboardList from "@mui/icons-material/AssignmentOutlined";
import User from "@mui/icons-material/PersonOutlineRounded";

/* 아이콘 키 → 컴포넌트. 없는 키를 쓰면 아무것도 그리지 않고 조용히 넘어간다 —
 * 서버가 결과 유형을 늘려도 화면이 죽지 않고, 구역 제목이 유형을 계속 말한다. */
export const NAV_ICONS = {
  ticket: Ticket,
  docs: FileText,
  board: ClipboardList,
  profile: User,
};

export function navIcon(key) {
  return (key && NAV_ICONS[key]) || null;
}
