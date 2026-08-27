/* 문서 값을 보여 주는 질의 키의 **접두사 표** — `ticket-views.js`의 문서판(QA-02 후속,
 * L축 재감사에서 발견).
 *
 * 문서를 그리는 화면은 문서 목록·상세만이 아니다 — 홈('오늘')의 「최근 문서」 위젯도
 * `/api/home/today`를 통해 같은 자료를 보여준다(`Home.jsx::useToday`,
 * `app/home/readers.py::recent_documents`). 그런데 `home`은 `staleTime:30s` + 전역
 * `refetchOnWindowFocus:false`(`main.jsx`)라 다른 탭에서 문서를 지우거나 되살려도 홈 탭을
 * 열어 둔 채로는 갱신되지 않는다 — 티켓판(`ticket-views.js` docstring)이 이미 겪은 증상이다.
 *
 * ## 🔴 이 표는 한 번 **없는 키를 가리키고 있었다** (D-313)
 *
 * 처음 만들 때 적은 접두사는 `["team-docs"]`(옛 목록)·`["team-doc"]`(옛 상세)였다. S14 가
 * 문서 축을 정본(`/api/knowledge/*`)으로 옮기면서 화면의 질의 키가 `["knowledge", …]` 로
 * 바뀌었는데 **이 표는 안 따라왔다.** 그래서 휴지통에서 문서를 복원·영구 삭제한 뒤
 * `invalidateDocumentViews` 가 도는데도 지우는 대상이 하나도 없었다 — 없는 키를 무효화하는
 * 것은 오류가 아니라 **아무 일도 안 하는 것**이라 화면에도 콘솔에도 흔적이 없다.
 *
 * 증상은 이랬다: 문서를 복원하고 `/knowledge` 로 가면 최대 staleTime 동안 그 문서가 여전히
 * 없고, 영구 삭제한 문서의 상세는 그 시간 동안 멀쩡히 열린다. 두 경우 다 사용자는 자기가
 * 누른 것이 안 먹혔다고 읽는다.
 *
 * ## 접두사 규칙
 *
 * react-query 의 무효화는 **접두사 일치**다(`["knowledge"]` 하나가 목록·상세·판·차이·트리를
 * 함께 잡는다). 그래서 여기 적는 것은 완전한 키가 아니라 '문서를 보여 주는 질의가 시작하는
 * 마디'다. 새 화면을 만들 때 지켜야 할 규칙은 하나다: **문서 값을 그리는 질의라면 키를 아래
 * 접두사 중 하나로 시작하라.**
 *
 * 아래 목록은 전부 문서를 지우거나 되살리면 값이 실제로 달라지는 질의다:
 *   knowledge   문서 목록·상세·판 이력·차이·폴더 트리·태그 (Knowledge.jsx · KnowledgeDoc.jsx)
 *   trash       휴지통 목록(Trash.jsx) — 티켓과 공유하는 자료지만 문서 쪽 무효화 누락이 있었다
 *   home        오늘(/api/home/today)의 「최근 문서」 위젯
 */
export const DOCUMENT_VIEW_KEYS = [
  ["knowledge"],
  ["trash"],
  ["home"],
];

/* 문서를 고친(휴지통 이동·복원·영구 삭제·생성) 뒤 부른다. `refetchType` 은 그대로 넘길 수
 * 있게 열어 둔다 — `invalidateTicketViews` 와 같은 계약. */
export function invalidateDocumentViews(qc, options) {
  for (const queryKey of DOCUMENT_VIEW_KEYS) {
    qc.invalidateQueries({ queryKey, ...(options || {}) });
  }
}


/* 태그 상자에 이름 하나를 더한다. 이미 있으면 그대로 둔다 — 같은 태그가 두 번 적히면
 * 서버가 하나로 접지만, 사용자는 자기가 두 번 눌렀다고 읽는다.
 *
 * **여기 있는 이유**: 목록 화면과 상세 화면이 둘 다 태그 상자를 갖는다. 한쪽에서 다른 쪽을
 * import 하면 늦게 싣기로 한 두 청크가 하나로 붙는다(문서를 안 여는 사람이 편집 화면을
 * 함께 받는다). 화면 둘이 나눠 쓰는 작은 함수는 이런 모듈이 갖는다.
 */
export function appendTag(value, name) {
  const parts = String(value || "").split(",").map((t) => t.trim()).filter(Boolean);
  if (parts.some((t) => t.toLowerCase() === String(name).toLowerCase())) return parts.join(", ");
  parts.push(name);
  return parts.join(", ");
}
