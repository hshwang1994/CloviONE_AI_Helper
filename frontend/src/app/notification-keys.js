/* 알림 캐시 키 — **한 뿌리 아래 모은다** (PF9).
 *
 * ## 무슨 일이 있었나
 *
 * 같은 알림을 보는 캐시가 서로 다른 세 네임스페이스에 흩어져 있었다.
 *   `["noti-unread"]`  벨 배지 · 사이드바 배지
 *   `["noti-list", …]` 벨 팝오버 목록
 *   `["notifications", …]` 전체 알림 화면(DataScreen)
 * 셋은 접두어가 달라서 **한 번의 무효화로 함께 갱신할 방법이 없었다.** 그래서 읽음 처리를
 * 하는 자리마다 세 줄을 손으로 적었고, 한 곳이라도 빠지면 "목록에서 읽었는데 벨 숫자가
 * 그대로" 같은 상태가 됐다. 실제로 코드 주석이 그 결함을 예고해 놓은 채 남아 있었다.
 * 반대로 어떤 자리는 필요 없는 것까지 무효화해 알림과 무관한 재조회를 만들었다.
 *
 * ## 지금 규칙
 *
 * 모든 알림 캐시는 `["noti", …]` 로 시작한다. react-query 의 무효화는 접두어 일치이므로
 * **`invalidateNotifications(qc)` 한 번이 셋 다 갱신한다.** 새 알림 화면을 붙이는 사람은
 * 여기서 키를 받아 쓰기만 하면 되고, 무효화 목록을 어디에 더 적을지 고민할 일이 없다.
 *
 * 키를 문자열로 손수 적는 자리를 남기지 않는다 — 그 순간 다시 네 번째 네임스페이스가 생긴다.
 * `src/app/notification-keys.test.js` 가 그것을 감시한다.
 */

/** 모든 알림 캐시의 뿌리. 무효화는 이것 하나면 된다. */
export const NOTI_ROOT = ["noti"];

/** 안 읽음 개수(벨 배지 + 사이드바 배지가 같은 캐시를 본다).
 *
 * 0060 부터 **audience 별로 다른 캐시**다. 사용자 알림과 관리자 알림은 다른 화면·다른
 * 경로이고 숫자도 달라야 하는데, 한 키를 공유하면 콘솔을 옮길 때마다 상대 콘솔의 숫자가
 * 잠깐 보였다가 바뀐다. 뿌리(`["noti"]`)는 같으므로 무효화 한 번은 여전히 셋 다 갱신한다.
 */
export function notiUnreadKey(audience) {
  return ["noti", "unread", audience];
}

/** 접두어 — audience 와 무관하게 안 읽음 캐시 전체를 가리킬 때. */
export const NOTI_UNREAD = ["noti", "unread"];

/** 벨 팝오버 목록. 변형(`unread`/`recent`)은 실제 캐시 키의 일부다. */
export function notiListKey(variant, audience = "user") {
  return ["noti", "list", audience, variant];
}

/** 접두어 — 변형과 무관하게 목록 전체를 가리킬 때. */
export const NOTI_LIST = ["noti", "list"];

/** 전체 알림 화면(DataScreen)이 쓰는 뿌리. 화면 키("notifications")와 **일부러 다르다** —
 *  화면 키는 경로·저장된 뷰의 이름이고, 이것은 캐시 주소다. 둘을 같은 문자열로 묶으면
 *  경로 이름을 바꾸는 순간 캐시 네임스페이스가 조용히 갈라진다. */
export const NOTI_SCREEN = ["noti", "screen"];

/** 알림과 관련된 모든 캐시를 한 번에 갱신한다. */
export function invalidateNotifications(qc) {
  qc.invalidateQueries({ queryKey: NOTI_ROOT });
}
