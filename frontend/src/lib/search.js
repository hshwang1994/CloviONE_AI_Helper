import { api } from "./api.js";

/* 통합 검색 클라이언트 (백엔드: GET /api/search).
 *
 * 팔레트(Ctrl+K)와 결과 화면이 **같은 함수**를 쓴다. 두 곳이 각자 fetch 를 쓰면 하나만
 * 고쳐지는 날이 오고, 그때 "팔레트에는 나오는데 결과 화면에는 없다"가 된다.
 *
 * 유형별 라벨·라우트는 서버가 응답에 실어 준다. 화면이 유형별 if 를 갖지 않는 것이 핵심이다 —
 * 새 유형이 늘 때 백엔드만 고치면 팔레트·결과 화면·빈 상태가 함께 따라온다.
 */

/* trigram 인덱스는 3자 미만을 못 만든다. 서버가 1~2자를 LIKE 폴백으로 처리하므로
 * 프런트는 **1자부터 보낸다** — 여기서 막으면 서버의 폴백이 죽은 코드가 된다. */
export const MIN_SEARCH_CHARS = 1;

/* 검색어 상한(코드포인트 수). 서버의 `MAX_QUERY_CHARS` 와 같은 값이라 화면이 보낸 글자와 서버가 쓰는 글자가 같다. */
export const MAX_QUERY_CHARS = 100;

/* ── 검색어의 두 모양 — 보여 주는 값과 대조하는 값 ──────────────────────────
 *
 * 검색어는 두 가지로 다듬고, 둘은 하는 일이 달라 한 함수로 합치지 않는다.
 *
 *   * `normalizeQuery` 는 **화면과 주소에 서는 값**이다. 앞뒤 공백을 걷고, 이어진 공백을 한 칸으로 접고,
 *     한글 표기를 완성형(NFC)으로 맞추고, 100자에서 자른다. 사람이 친 글자는 그대로 남아서 「ClovirONE」은
 *     주소에도 「ClovirONE」으로 선다. 서버의 `normalize_query` 와 같은 값을 낸다.
 *   * `foldText` 는 **맞는지 볼 때만** 쓰는 값이다. 호환 문자를 한 표기로 모으고(NFKC — 전각 글자 · 합자 ·
 *     반각 가나 · 조합형 한글), 대소문자를 없애고, 공백 · 제로폭 문자 · 소프트 하이픈을 모두 지운다.
 *     그래서 「현황 제외」와 「현황제외」가 같은 것을 찾고, 「ClovirONE」 · 「clovirone」 · 「CLOVIRONE」도
 *     같은 것을 찾는다. 접은 값은 화면에 그리지 않는다.
 *
 * **질의와 대상 양쪽을 같은 규칙으로 접는다.** 한쪽만 접으면 고친 것이 아니라 어긋나는 방향만 바뀐다 —
 * 질의에서만 공백을 지우면 제목이 「현황 제외」인 글을 「현황 제외」로 쳐도 못 찾는다. 서버도 같은 규칙으로
 * 양쪽을 접는다(`app/core/search_text.py::fold`, SQL `search_fold()`). 세 구현이 같은 값을 내는지는 공용
 * 말뭉치 `tests/fixtures/search_fold_corpus.json` 이 잰다(`search-fold.test.js`).
 *
 * **뜻을 바꾸는 퍼지는 넣지 않는다.** 오타 허용 · 형태소 분석 · 억양 무시가 없다. 「é」와 「e」는 다른 글자이고,
 * 비슷한 말까지 찾아 주는 검색은 사용자가 친 것과 다른 결과를 내놓는다. 접기가 지우는 차이는 뜻이 없는
 * 것(공백 · 대소문자 · 같은 글자의 다른 표기)뿐이다.
 */

/* 서버 `str.split()` 이 공백으로 보는 글자 그대로다. JS 의 `\s` 로 가르면 U+FEFF 를 공백으로 보고
 * U+001C~U+001F · U+0085 는 공백으로 안 봐서, 그 글자가 든 검색어는 화면과 서버가 서로 다른 값을 든다. */
const DISPLAY_SPACE = /[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+/;

/* 접을 때 지우는 글자 — 공백 · 제로폭 문자 · 방향 표시 · 소프트 하이픈 · BOM · NUL. NFKC 가 전각 공백(U+3000)과
 * 여러 폭의 공백(U+2000~U+200A 등)을 먼저 보통 공백으로 바꾸므로 여기에는 NFKC 뒤에도 남는 글자만 적는다.
 * 서버의 SQL 함수와 같은 목록이다 — PG 의 `\s` 는 로케일에 따라 달라서 양쪽 다 코드포인트를 직접 적는다. */
const FOLD_REMOVE = /[\u0000\u0009-\u000D\u001C-\u0020\u0085\u00A0\u00AD\u1680\u2028\u2029\u200B-\u200F\u2060\uFEFF]+/g;

/** 글자를 공백으로 갈라 낱말 배열로 준다 — 서버의 `str.split()` 과 같은 결과다(빈 낱말은 없다).
 *
 * 검색어의 표시 모양과 태그의 정체성(`ui/TagPicker.jsx::tagSlug`)이 이 가르기를 함께 쓴다. 둘 다 서버가
 * `split()` · `\s` 로 공백을 다루는 자리라서, 공백으로 보는 글자가 화면과 서버에서 같아야 한다. */
export function splitWords(text) {
  return String(text ?? "").split(DISPLAY_SPACE).filter(Boolean);
}

/** 화면과 주소에 서는 검색어 — 앞뒤 공백 제거, 이어진 공백 한 칸, NFC, 100자 상한.
 *
 * 서버(`" ".join(text.split())`)와 같은 방법으로 낱말을 가르고 한 칸으로 잇는다. NFC 는 글자 수를 세기
 * **전에** 한다 — 조합형으로 온 두 글자는 코드포인트로 여섯이라, 먼저 세면 상한이 엉뚱한 자리에서 자른다. */
export function normalizeQuery(raw) {
  const words = splitWords(String(raw || "").normalize("NFC"));
  return Array.from(words.join(" ")).slice(0, MAX_QUERY_CHARS).join("");
}

/** 대조에만 쓰는 접은 값 — NFKC → `İ`를 `i`로 → 소문자 → `ς`를 `σ`로 → 공백 · 제로폭 문자 삭제.
 *
 * 순서에 이유가 있다. `İ`는 소문자로 내리면 `i` 뒤에 결합 점(U+0307)이 붙어 `i`로 친 검색어와 갈리므로 먼저
 * 바꾼다. 소문자는 `toLowerCase` 다 — casefold 는 PG 에 없고 `ß → ss` 처럼 글자 수가 바뀌는 대응이 양쪽에서
 * 어긋난다. 낱말 끝의 `Σ`는 소문자로 내리면 `ς`가 되고 가운데의 `Σ`는 `σ`가 되므로 둘을 `σ` 하나로 모은다. */
export function foldText(s) {
  return String(s ?? "").normalize("NFKC").replace(/\u0130/g, "i").toLowerCase().replace(/\u03C2/g, "\u03C3").replace(FOLD_REMOVE, "");
}

/** `haystack` 안에 `query` 가 있는가 — 둘 다 접어서 본다.
 *
 * `haystack` 은 글자 하나이거나 글자 배열이다. 배열이면 **칸마다 따로** 보고 하나라도 맞으면 참이다. 서버가
 * 여러 열을 `OR` 로 보는 것과 같은 뜻이다(`contains_folded`). 칸을 이어 붙여 보지 않는 이유는 이은 자리에서
 * 없던 낱말이 생기기 때문이다 — 이름 「김하나」와 부서 「개발팀」을 붙이면 「나개발」이 걸린다.
 *
 * 접은 질의가 비면 참이다. 빈 조건은 조건이 아니고, 공백이나 제로폭 문자만 친 경우도 같다. */
export function includesFolded(haystack, query) {
  const needle = foldText(query);
  if (!needle) return true;
  const fields = Array.isArray(haystack) ? haystack : [haystack];
  return fields.some((field) => foldText(field).includes(needle));
}

/** MUI Autocomplete 의 `filterOptions` — 후보 순서를 지키고 `includesFolded(stringify(후보), 입력)` 으로 거른다.
 *
 * `stringify` 는 후보 하나를 글자(또는 글자 배열)로 바꾼다. 없으면 Autocomplete 가 넘겨 주는 `getOptionLabel`
 * 을 쓴다. 이름과 보조 글자(코드 · 소속)를 함께 찾게 하려면 둘을 배열로 돌려준다 — 칸마다 따로 본다.
 *
 * MUI 기본 필터(`createFilterOptions`)를 쓰지 않는 이유는 둘이다. 그 필터는 억양을 무시해서 「é」로 「e」를
 * 찾는다 — 뜻이 바뀌는 일치다. 그리고 그 억양 제거가 한글을 자모로 풀어서, 입력을 조합하는 도중의 「하」가
 * 「한국」의 앞머리에 걸린다. 그 일치는 조합이 끝나면 사라지는 순간의 일치라 검색어의 뜻이 아니다. 대신 서버와
 * 같은 접기로 공백 · 대소문자 · 전각 차이를 없앤다.
 *
 * 늘 새 배열을 돌려준다. 부르는 쪽(`TagPicker` 의 「추가」 후보)이 결과에 줄을 더해도 받은 후보 목록이 안 바뀐다. */
export function foldedFilterOptions({ stringify } = {}) {
  return (options, state) => {
    const input = (state && state.inputValue) || "";
    const list = Array.isArray(options) ? options : [];
    if (!foldText(input)) return list.slice();
    const textOf = stringify || ((option) => (state && state.getOptionLabel ? state.getOptionLabel(option) : option));
    return list.filter((option) => includesFolded(textOf(option), input));
  };
}

/* 서버로 보낼 만한 검색어인가 — **접은 길이**로 센다. 공백이나 제로폭 문자만 친 검색어는 서버가 조건 없음으로
 * 읽으므로(`pattern_for` 가 `None`) 화면도 보내지 않는다. */
export function isSearchable(raw) {
  return foldText(raw).length >= MIN_SEARCH_CHARS;
}

export function searchApi(q, { limit } = {}) {
  const params = new URLSearchParams({ q: normalizeQuery(q) });
  if (limit) params.set("limit", String(limit));
  return api("/api/search?" + params.toString());
}

/* 그룹 배열을 평평한 목록으로. 팔레트의 위/아래 키 이동이 그룹을 넘나들어야 한다. */
export function flattenGroups(groups) {
  return (groups || []).flatMap((g) =>
    (g.items || []).map((item) => ({ ...item, groupLabel: g.label })),
  );
}

export function totalOf(result) {
  return (result && Number(result.total)) || 0;
}

/* 결과 한 줄을 눌렀을 때 갈 곳. 서버가 준 route 를 쓰되, 비어 있으면 이동하지 않는다
 * (없는 곳으로 보내는 것보다 안 움직이는 편이 낫다 — '되는 척'을 만들지 않는다). */
export function routeOf(item) {
  const route = item && item.route;
  return typeof route === "string" && route.startsWith("/") ? route : null;
}

/* 결과 화면 주소. 팔레트의 '모든 결과 보기'와 상단바 입력이 같은 곳으로 간다. */
export function searchResultsPath(q) {
  return "/search?q=" + encodeURIComponent(normalizeQuery(q));
}
