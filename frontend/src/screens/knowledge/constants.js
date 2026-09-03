/* 문서 작업공간의 공용 상수 — 값의 뜻은 옛 Knowledge.jsx 가 정한 그대로다.
 * 파일을 나누면서 상수를 화면마다 다시 적으면 한쪽만 고치는 날이 온다. */

/* 한 쪽의 문서 수. `DataTable` 이 가상 스크롤을 쓰므로(§15.1) 스물다섯 줄로 조회 상한을
 * 만들 이유가 없어졌다 — 백 줄을 한 번에 받아도 화면은 보이는 줄만 그린다. */
export const PAGE_SIZE = 100;

/* 이 목록의 **정체**. 상세를 열었다 돌아오면 조건과 스크롤이 이 이름으로 되살아난다. */
export const LIST_KEY = "/knowledge";

/* 「보기」. 값은 주소에 실린다 — 링크로 건네도 같은 화면이 선다.
 * `recent`(최근 열람)만 다른 입구를 쓴다(`/api/knowledge/recent`).
 *
 * `updated24` 는 「최근 24시간 안에 고친 문서」다. 예전 「최근 수정」 타일은 `sort=recent`
 * 만 걸어 **전체를 정렬만** 했다 — 이름은 24시간을 말하는데 목록에는 작년 문서가 계속
 * 있었다. 지금은 서버가 실제로 창을 자른다(`updated_within_hours=24`). */
export const VIEW = {
  all: "",
  updated24: "updated24",
  favorites: "favorites",
  drafts: "drafts",
  recent: "recent",
};

/* 「최근 24시간」이 서버에 보내는 시간. 화면 문구와 이 수가 갈라지면 안 되므로 한 자리다. */
export const RECENT_WINDOW_HOURS = 24;

export const VIEW_OPTIONS = [
  { value: VIEW.updated24, label: "최근 24시간" },
  { value: VIEW.favorites, label: "즐겨찾기" },
  { value: VIEW.drafts, label: "내 초안" },
  /* 「최근 열람」은 위 셋과 성격이 다르다 — 문서가 아니라 **내 발자국**을 본다.
   * 목록 메뉴 넷에는 없지만 이 고르개에는 남는다(사용자 결정). */
  { value: VIEW.recent, label: "최근 열람" },
];

export const SORTS = [
  { value: "recent", label: "최근 수정순" },
  { value: "created", label: "만든 날짜순" },
  { value: "title", label: "제목순" },
];

/** 축의 이름은 **프로젝트** 하나다.
 *
 * 🔴 예전에는 「문서 범위」였다. 그 낱말이 생긴 이유는 이 고르개의 후보에 프로젝트가
 * 아닌 값(「공통 문서」)이 섞여 있어서 제목이 내용에 대해 거짓말을 했기 때문이다(D-415).
 * 지금은 그 값을 「프로젝트 미지정」으로 부르므로 **프로젝트 축의 정직한 값**이 되고,
 * 「문서 범위」라는 이름이 있어야 할 이유가 사라졌다. 폴더 축이 화면에서 걷힌 것도 같은
 * 회차다 — 「범위 안의 폴더」라는 계층 자체가 없어졌다.
 *
 * 주소·API 매개변수(`?project=`, `project_id`, `"none"`)는 **안 바꿨다.** 북마크와 목록
 * 복귀 기억과 서버 계약 셋이 그 값을 이미 쓰고 있다. */
export const PROJECT_UNASSIGNED_LABEL = "프로젝트 미지정";

/** 공간 목록의 표시 이름 — 프로젝트 소유는 그 이름 그대로, 그 밖은 「프로젝트 미지정」이다.
 * "공간"이라는 낱말을 일반 사용자 화면에 쓰지 않는다. */
export function spaceDisplayName(space) {
  return space.owner_kind === "project" ? space.name : PROJECT_UNASSIGNED_LABEL;
}

/* 프로젝트 축의 「미지정」 값 — 서버 `service.PROJECT_FILTER_NONE` 과의 값 계약이다.
 * 주소(`?project=none`)·필터 파라미터·생성 선택지가 전부 이 한 값으로 왕복한다. */
export const PROJECT_NONE = "none";

/** 공간 하나를 프로젝트 축 값으로 옮긴다 — 프로젝트 공간이면 그 프로젝트 id, 아니면 공통. */
export function axisValueOf(space) {
  return space && space.owner_kind === "project" && space.owner_project_id
    ? space.owner_project_id
    : PROJECT_NONE;
}

/** 프로젝트 축 값이 가리키는 공간. 공간이 아직 없는 프로젝트(서버가 첫 문서에서 만든다 —
 * §14.2)와, 공통이 유일하게 정해지지 않는 배치에서는 null 이다.
 *
 * 🔴 새 문서를 만들 때는 **이제 이 함수가 필요 없다.** 프로젝트를 안 고르면 서버가
 * 공통 공간을 찾거나 만든다(`service.resolve_or_create_common_space`). 예전에는 화면이
 * 공간 목록을 뒤져 `space_id` 를 만들어 보내야 했고, 목록이 비었거나 둘 이상이면
 * `null` 이 되어 「어느 프로젝트의 문서인지 골라 주세요」로 끝났다. */
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
 * 🔴 「프로젝트 미지정」은 **언제나 선다.** 예전에는 공간 목록에 비프로젝트 공간이 있을
 * 때만(`hasCommon`) 세웠는데, 프로젝트가 선택이 된 지금은 미지정 문서가 아무 때나 생길
 * 수 있다. 공간 질의가 도착하기 전에는 후보가 없다가 도착하면 생기는 고르개는, 쓰는
 * 사람에게 「방금 있던 선택지가 사라졌다」로 보인다. 그리고 서버의 센티널은 원래
 * 조건 없이 늘 받는다 — 각 프로젝트 + 미지정 = 전체라는 분할 완전성이 그 근거다. */
export function navEntriesFrom(projects) {
  const rows = (projects || []).map((p) => ({ value: p.id, label: p.name }));
  return [{ value: PROJECT_NONE, label: PROJECT_UNASSIGNED_LABEL }, ...rows];
}
