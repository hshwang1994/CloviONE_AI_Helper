/* 문서 값을 보여 주는 질의 키의 **접두사 표** — `ticket-views.js`의 문서판(QA-02 후속,
 * L축 재감사에서 발견).
 *
 * 문서를 그리는 화면은 `["team-docs", …]`(목록)·`["team-doc", id]`(상세)만이 아니다 —
 * 홈('오늘')의 「최근 문서」 위젯도 `/api/home/today`를 통해 같은 자료를 보여준다
 * (`Home.jsx::useToday`, `app/home/readers.py::recent_documents`). 그런데 `home`은
 * `staleTime:30s` + 전역 `refetchOnWindowFocus:false`(`main.jsx`)라 다른 탭에서 문서를
 * trash·restore·restrict·생성·동기화해도 홈 탭을 열어 둔 채로는 갱신되지 않는다 —
 * 티켓판(`ticket-views.js` docstring)이 이미 겪은 것과 같은 증상이다.
 *
 * `TeamDocs.jsx`·`TeamDoc.jsx`·`Trash.jsx` 세 파일에 흩어져 있던 무효화 키 나열도
 * 여기 한 곳으로 모은다 — 그중 `TeamDocs.jsx`의 일괄 삭제는 지운 문서마다 개별
 * `["team-doc", id]`를 손으로 순회했는데, react-query의 무효화는 **접두사 일치**라
 * `["team-doc"]`(id 없이) 하나면 전부 잡는다(`ticket-views.js`와 같은 규칙).
 *
 * 아래 목록은 전부 문서 편집으로 값이 실제로 달라지는 질의다:
 *   team-docs   문서 목록(TeamDocs.jsx) + 필터 후보
 *   team-doc    문서 상세(TeamDoc.jsx, id별)
 *   trash       휴지통 목록(Trash.jsx) — 티켓과 공유하는 자료지만 문서 쪽 무효화 누락이 있었다
 *   home        오늘(/api/home/today)의 「최근 문서」 위젯
 */
export const DOCUMENT_VIEW_KEYS = [
  ["team-docs"],
  ["team-doc"],
  ["trash"],
  ["home"],
];

/* 문서를 고친(trash·restore·restrict·생성·동기화) 뒤 부른다. `refetchType` 은 그대로 넘길 수
 * 있게 열어 둔다 — `invalidateTicketViews` 와 같은 계약. */
export function invalidateDocumentViews(qc, options) {
  for (const queryKey of DOCUMENT_VIEW_KEYS) {
    qc.invalidateQueries({ queryKey, ...(options || {}) });
  }
}
