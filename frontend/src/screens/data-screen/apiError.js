// 401(세션 만료)은 다른 실패와 다르게 다뤄야 한다 — 재시도해도 항상 401이라 일반 오류 문장만
// 띄우면 사용자가 뭘 해야 하는지 모른 채 막힌다(로그인 화면으로 가는 실제 동작이 없었다). 로그인
// 화면으로 실제로 이동시킨다(UserMenu.logout()과 동일한 이동 방식).
//
// 그 밖의 실패는 **부르는 쪽이 준 자리**(`report`)에 문장으로 남긴다 — 예전에는 토스트였다. 실패는
// 사라지면 안 되는 사실이고, 목록 동작의 실패는 목록 위에 · 상세 동작의 실패는 상세 안에 선다
// (핸드오프 RULES §1 · ACCEPTANCE I3).
//
// DataScreen.jsx와 그 하위 SubListDrawer가 함께 쓴다 — 두 곳이 각자 이 판단을 손으로 반복하면
// 한쪽만 로그인 화면으로 보내고 다른 쪽은 일반 토스트만 띄우는 어긋남이 생긴다.
import { expireSession } from "../../lib/sessionRedirect.js";

export function handleApiError(e, report) {
  if (e && e.status === 401) {
    /* 안내는 토스트가 아니라 본문 자리의 오류 상태(401 갈래)다 — 짧게 머문 뒤 로그인 화면으로 간다.
       이동은 공용 계층이 한다(지시 19) — 되돌아올 곳(`next`)과 만료 표시(`expired=1`)를 싣고,
       같은 순간 다른 화면이 또 예약해 좋은 주소를 덮어쓰지 않게 1회만 예약한다. */
    expireSession();
    return;
  }
  report(e && e.message);
}
