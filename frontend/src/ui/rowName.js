/* 표의 한 행이 '무엇인가'를 한 마디로 답하는 값.
 *
 * 왜 필요한가: 행 단위 컨트롤(선택 체크박스, 상세 열기 버튼)은 행마다 **다른** 접근 이름을
 * 가져야 한다. 스크린리더로 목록을 훑을 때 "이 항목 선택" 이 스무 번 들리면 무엇을 고르는지
 * 알 방법이 없고, 그러면 선택해서 일괄 처리하는 흐름 자체를 못 쓴다.
 *
 * 왜 화면이 아니라 **열 정의**가 정하는가: 행을 구별하는 값은 화면마다 다르다(티켓은 제목,
 * 사용자는 이메일, 문서는 제목). 그렇다고 화면마다 라벨 문자열을 손으로 적게 하면 다음에
 * 만드는 화면에서 반드시 빠지고, 빠졌다는 사실은 **화면을 보는 사람에게는 안 보인다**.
 * 그래서 이미 화면마다 한 벌씩 있는 열 정의(screens/registry.js 와 각 화면의 columns)에
 * 표식 하나로 선언하게 한다.
 *
 * 열 정의에 적는 법:
 *   { key: "title", label: "제목", rowName: true }         // 그 열의 원시 값을 쓴다
 *   { key: "title", label: "제목", rowName: (r) => ... }   // 값을 다듬어 쓴다(빈 제목 대체 등)
 *   { key: "_sel",  label: "",     rowName: false }        // 이 열은 절대 이름의 출처가 아니다
 *
 * 아무 열에도 표식이 없으면 render() 없이 값을 그대로 그리는 첫 열로 떨어진다. render() 가
 * 있는 열을 폴백에서 빼는 이유: 그 열이 화면에 그리는 것은 원시 값이 아니라 배지나 링크라서
 * (예: 상태 코드 'failed' → 배지 '실패') 낭독되는 이름이 화면과 어긋날 수 있다.
 */

function textOf(col, row) {
  if (typeof col.rowName === "function") {
    try {
      const v = col.rowName(row);
      return v == null ? "" : String(v).trim();
    } catch (e) {
      // 한 열의 실수가 표 전체를 못 그리게 만들지 않는다 - 이름만 포기한다.
      return "";
    }
  }
  const v = row ? row[col.key] : null;
  return v == null ? "" : String(v).trim();
}

function candidates(columns) {
  return (Array.isArray(columns) ? columns : [])
    .filter((c) => c && c.rowName !== false && !c.open);
}

/** 열 정의가 **명시적으로** 지정한 이름. 표식이 없으면 "". */
export function declaredRowName(columns, row) {
  const marked = candidates(columns).find((c) => c.rowName);
  return marked ? textOf(marked, row) : "";
}

/** 행을 구별하는 값. 표식이 없으면 값을 그대로 쓰는 첫 열로 떨어진다. 없으면 "". */
export function rowNameOf(columns, row) {
  const declared = declaredRowName(columns, row);
  if (declared) return declared;
  const plain = candidates(columns).find((c) => !c.render && textOf(c, row));
  return plain ? textOf(plain, row) : "";
}
