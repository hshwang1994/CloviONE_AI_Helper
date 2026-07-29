/* 값별 배지 색 매핑. 게시판 카테고리·문서 종류를 값에 따라 서로 다른 배지 색으로 구분한다
 * (장식용 — 시맨틱 아님). 색은 kit.css의 .k-badge--* 클래스(토큰 기반, 라이트/다크 대비 확보).
 * 알 수 없는 값은 neutral(회색)로 떨어진다. */

const BOARD_CATEGORY_KIND = {
  "공지": "danger",   // 공지는 눈에 띄게(빨강)
  "질문": "info",
  "정보공유": "ok",
  "맛집": "warn",
  "자유": "purple",
};

// 문서 종류 8종은 서로 다른 색으로(빨강은 '오류'로 읽혀 문서엔 쓰지 않는다).
const DOC_TYPE_KIND = {
  "회의록": "info",
  "기획서": "purple",
  "설계서": "teal",
  "작업 계획서": "warn",
  "매뉴얼": "ok",
  "보고서": "indigo",
  "참고자료": "pink",
  "기타": "neutral",
};

export function boardCategoryKind(category) {
  return BOARD_CATEGORY_KIND[category] || "neutral";
}

export function docTypeKind(docType) {
  return DOC_TYPE_KIND[docType] || "neutral";
}
