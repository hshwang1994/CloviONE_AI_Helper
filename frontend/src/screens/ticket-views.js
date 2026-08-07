/* 티켓 값을 보여 주는 질의 키의 **접두사 표**. 티켓을 고친 뒤 무엇을 다시 불러야 하는지를
 * 여기 한 곳에서만 정한다 (E6).
 *
 * ## 왜 표인가
 *
 * 예전에는 티켓을 고치는 자리마다 `invalidateQueries(["tickets"])` 를 손으로 적었다. 그런데
 * 티켓을 그리는 화면은 `["tickets", …]` 만이 아니다 — 홈('오늘')은 `["home","today"]`,
 * 업무 대시보드는 `["home","work-dashboard"]`, 스프린트 회의는 `["sprint", …]` 를 쓴다.
 * 그래서 홈에서 티켓을 고치면 "저장했습니다" 토스트가 뜨는데 목록의 값은 옛것 그대로였고,
 * 사용자는 저장이 안 된 줄 알고 같은 편집을 되풀이했다.
 *
 * 무효화 키를 부르는 자리마다 나열하면 **화면이 늘 때마다 또 빠진다**. 그리고 그때 증상은
 * "값이 안 바뀐다" 라서 원인을 찾기 어렵다. 관리자 목록 화면이 같은 이유로
 * `DataScreen.jsx::CROSS_SCREEN_KEYS` 를 한 곳에 두고 있다 — 이건 티켓판이다.
 *
 * ## 접두사 규칙
 *
 * react-query 의 무효화는 **접두사 일치**다(`["home"]` 은 `["home","today"]` 와
 * `["home","work-dashboard"]` 를 함께 잡는다). 그래서 여기 적는 것은 완전한 키가 아니라
 * '티켓을 보여 주는 질의가 시작하는 마디'다. 새 화면을 만들 때 지켜야 할 규칙은 하나다:
 * **티켓 값을 그리는 질의라면 키를 아래 접두사 중 하나로 시작하라.** 새 접두사가 필요하면
 * 여기에 한 줄 더한다.
 *
 * 아래 목록은 전부 티켓 편집으로 값이 실제로 달라지는 질의다(추측으로 넣지 않는다):
 *   tickets     내 티켓·팀 티켓·프로젝트 티켓·미할당 목록 + 후보 목록(ticket-options.js)
 *   ticket      티켓 상세 (Ticket.jsx)
 *   home        오늘(/api/home/today) · 업무 대시보드(/api/home/work-dashboard)
 *   sprint      스프린트 회의(/api/sprint/summary)
 *   my-stats    내 업무량·완료 통계(/api/me/stats — 홈과 같은 티켓 로더를 쓴다)
 *   projects    프로젝트 진행률·WBS·헬스(app/projects/repository.tasks_for_project 가 티켓을 센다)
 *   dev-report  개발자 월간 리포트(DevReport.jsx, /api/admin/reports/dev-monthly)— 담당자별
 *               완료/진행/검증/계획/지연 건수와 업무량을 마감일이 그 달인 티켓에서 센다.
 *               편집 모달이 바꾸는 상태·담당자·마감·WD·난이도가 전부 이 집계에 들어간다.
 *               빠져 있으면 리포트를 이미 열어 본 뒤 다른 화면에서 티켓을 고쳐도 '새로고침'을
 *               다시 누르기 전까진 옛 집계가 남는다.
 */
export const TICKET_VIEW_KEYS = [
  ["tickets"],
  ["ticket"],
  ["home"],
  ["sprint"],
  ["my-stats"],
  ["projects"],
  ["dev-report"],
];

/* 티켓을 고친 뒤 부른다.
 *
 * `refetchType` 을 그대로 넘길 수 있게 열어 둔다. 기본값(활성 질의만 다시 부르기)은 편집처럼
 * '지금 보고 있는 화면이 바뀌면 되는' 경우에 맞고, 삭제·복원처럼 **어느 화면으로 가도**
 * 최신이어야 하는 경우는 `{ refetchType: "all" }` 로 비활성 목록까지 즉시 다시 부른다
 * (예전에 삭제 후 다른 목록이 stale 로만 남아 '자동 갱신 안 됨'처럼 보였다). */
export function invalidateTicketViews(qc, options) {
  for (const queryKey of TICKET_VIEW_KEYS) {
    qc.invalidateQueries({ queryKey, ...(options || {}) });
  }
}
