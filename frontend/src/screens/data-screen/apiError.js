// 401(세션 만료)은 다른 실패와 다르게 다뤄야 한다 — 재시도해도 항상 401이라 일반 오류 토스트만
// 띄우면 사용자가 뭘 해야 하는지 모른 채 막힌다(로그인 화면으로 가는 실제 동작이 없었다). 로그인
// 화면으로 실제로 이동시킨다(UserMenu.logout()과 동일한 이동 방식).
//
// DataScreen.jsx와 그 하위 SubListDrawer가 함께 쓴다 — 두 곳이 각자 이 판단을 손으로 반복하면
// 한쪽만 로그인 화면으로 보내고 다른 쪽은 일반 토스트만 띄우는 어긋남이 생긴다.
import { redirectToLogin } from "../../lib/sessionRedirect.js";

export function handleApiError(e, toast) {
  if (e && e.status === 401) {
    toast("로그인이 필요합니다. 로그인 화면으로 이동합니다.", "error");
    // 토스트를 띄운 바로 다음 줄에서 즉시 전체 페이지 이동을 하면 브라우저가 언로드를 시작하면서
    // 방금 띄운 토스트가 사용자가 읽기도 전에 사라질 수 있다(리액트 상태 업데이트가 언마운트로
    // 잘려나감) — 짧게 지연해 안내 문구를 실제로 볼 수 있는 시간을 준다.
    // 이동은 공용 계층이 한다(지시 19) — 되돌아올 곳(`next`)과 만료 표시(`expired=1`)를
    // 싣고, 같은 순간 다른 화면이 또 예약해 좋은 주소를 덮어쓰지 않게 1회만 예약한다.
    redirectToLogin({ delayMs: 1200 });
    return;
  }
  toast(e.message, "error");
}
