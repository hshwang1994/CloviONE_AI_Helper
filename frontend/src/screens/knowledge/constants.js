/* 문서 작업공간의 공용 상수 — 값의 뜻은 옛 Knowledge.jsx 가 정한 그대로다.
 * 파일을 나누면서 상수를 화면마다 다시 적으면 한쪽만 고치는 날이 온다. */

/* 한 쪽의 문서 수. `DataTable` 이 가상 스크롤을 쓰므로(§15.1) 스물다섯 줄로 조회 상한을
 * 만들 이유가 없어졌다 — 백 줄을 한 번에 받아도 화면은 보이는 줄만 그린다. */
export const PAGE_SIZE = 100;

/* 이 목록의 **정체**. 상세를 열었다 돌아오면 조건과 스크롤이 이 이름으로 되살아난다. */
export const LIST_KEY = "/knowledge";

/* 「보기」 넷. 값은 주소에 실린다 — 링크로 건네도 같은 화면이 선다.
 * `recent` 만 다른 입구를 쓴다(`/api/knowledge/recent`). */
export const VIEW = { all: "", favorites: "favorites", drafts: "drafts", recent: "recent" };

export const VIEW_OPTIONS = [
  { value: VIEW.favorites, label: "즐겨찾기" },
  { value: VIEW.drafts, label: "내 초안" },
  { value: VIEW.recent, label: "최근 열람" },
];

export const SORTS = [
  { value: "recent", label: "최근 수정순" },
  { value: "created", label: "만든 날짜순" },
  { value: "title", label: "제목순" },
];

/** 공간 목록의 표시 이름 — 프로젝트 소유는 그 이름 그대로, 조직 소유는 「공통 문서」로
 * 부른다(§11.2). "공간"이라는 낱말을 일반 사용자 화면에 쓰지 않는다. */
export function spaceDisplayName(space) {
  return space.owner_kind === "organization" ? "공통 문서" : space.name;
}
