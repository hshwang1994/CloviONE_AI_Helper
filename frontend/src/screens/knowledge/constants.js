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

/* 프로젝트 축의 「공통 문서」 값 — 서버 `service.PROJECT_FILTER_NONE` 과의 값 계약이다.
 * 주소(`?project=none`)·필터 파라미터·생성 선택지가 전부 이 한 값으로 왕복한다. */
export const PROJECT_NONE = "none";

/** 공간 하나를 프로젝트 축 값으로 옮긴다 — 프로젝트 공간이면 그 프로젝트 id, 아니면 공통. */
export function axisValueOf(space) {
  return space && space.owner_kind === "project" && space.owner_project_id
    ? space.owner_project_id
    : PROJECT_NONE;
}

/** 프로젝트 축 값이 가리키는 공간. 공간이 아직 없는 프로젝트(서버가 첫 문서에서 만든다 —
 * §14.2)와, 공통이 유일하게 정해지지 않는 배치에서는 null 이다. */
export function spaceForAxis(spaces, value) {
  const list = spaces || [];
  if (!value) return null;
  if (value === PROJECT_NONE) {
    const common = list.filter((s) => s.owner_kind !== "project");
    return common.length === 1 ? common[0] : null;
  }
  return (
    list.find((s) => s.owner_kind === "project" && s.owner_project_id === value) || null
  );
}

/** 좌측 내비·필터의 프로젝트 축 선택지.
 *
 * 🔴 소스가 **프로젝트 목록**이다(공간 목록이 아니다). 공간은 문서가 하나라도 붙는
 * 프로젝트에만 생기므로(§14.2), 공간 목록으로 만들면 문서 0건 프로젝트가 좌측·필터에서
 * 통째로 사라진다 — 새 문서 모달(전체 프로젝트를 읽는 ProjectPicker)과 어긋나
 * 「만들어진 프로젝트가 안 보인다」가 됐다. 값은 프로젝트 id(축 값)라 주소·서버
 * 파라미터와 무변환 왕복하고, 문서 0건 프로젝트를 골라도 서버가 빈 목록을 주며
 * 화면이 「첫 문서 만들기」를 안내한다.
 *
 * 「공통 문서」(비프로젝트 공간)는 공간 쪽에서만 알 수 있으므로 `hasCommon` 으로 받는다. */
export function navEntriesFrom(projects, { hasCommon = false } = {}) {
  const rows = (projects || []).map((p) => ({ value: p.id, label: p.name }));
  return hasCommon ? [{ value: PROJECT_NONE, label: "공통 문서" }, ...rows] : rows;
}
