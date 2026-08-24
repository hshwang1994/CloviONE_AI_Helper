/* 표의 열이 **무엇인가**를 말하는 어휘 (C3 · 지시 18·19·74·75·77).
 *
 * ## 왜 이 파일이 생겼나
 *
 * 열은 그동안 자기 폭을 **숫자로** 말했다 — `width: "6rem"`, `minWidth: "12.5rem"`,
 * `align: "right"`. 그 숫자들은 화면마다 따로 정해졌고, 그래서 같은 뜻의 값이 화면마다
 * 다른 폭과 다른 정렬로 나왔다. 실측이 그것을 그대로 보여 준다: `/board` 의 「조회」와
 * `/my-stats` 의 「배정·완료」는 셋 다 개수인데 우정렬만 있고 **자릿수 고정이 없어서**
 * 세로로 자릿수가 안 맞았다(`numeric_alignment` 8건). 폭과 정렬을 열마다 손으로 적는 한
 * 그 여덟은 고쳐도 아홉 번째가 다시 생긴다.
 *
 * 그래서 열이 폭 대신 **의미**를 말한다. 폭·정렬·자릿수 고정·넘침 처리는 그 의미에서
 * 파생한다 — 한 자리에서.
 *
 * ## 이 표를 바꾸면 216개 열이 함께 움직인다
 *
 * 그것이 목적이다. 화면 파일 28개를 안 건드리고 표의 규칙을 고치려면 규칙이 한 곳에
 * 있어야 한다. 대신 **호출부의 명시 값이 언제나 이긴다** — `type` 을 안 준 열은 예전과
 * 정확히 같이 그려진다(회귀 0). 새 어휘는 더하는 것이지 덮는 것이 아니다.
 *
 * ## 폭을 `max-content` 라고 적지 않는 이유
 *
 * `DataTable` 은 CSS 격자가 아니라 `<table>` 이다(`tableLayout: auto`). auto 배치에서
 * 「내용만큼만」은 `width: 1%` + `whiteSpace: nowrap` 이 실제로 동작하는 표현이다 —
 * 브라우저가 1% 를 하한으로 읽고 내용 폭까지 늘린다. `max-content` 를 그대로 적으면
 * 엔진마다 다르게 해석한다. 뜻은 `SHRINK` 라는 이름으로 남긴다.
 */

/** auto 배치 표에서 「내용 폭만큼」을 뜻하는 값. 위 주석 참고. */
export const SHRINK = "1%";

/* 글자 단위로 끊는 유일한 자리 — **식별자형 열**(이메일·UUID·코드·URL).
 *
 * 한글 산문은 낱말을 지켜야 하고(`root.css` 의 `keep-all`), 그 규칙을 화면이 제멋대로
 * 덮지 않는지는 `ko-wordbreak.test.jsx` 가 파일 단위로 감시한다. 예전에는 화면마다 이
 * 선언을 손으로 적어서 그 감시 목록이 파일 이름으로 늘어났다 — 이제 **어느 열이 그런
 * 열인가**가 어휘로 정해지므로, 선언은 이 한 줄이고 감시도 이 한 줄만 보면 된다. */
export const ANYWHERE_BREAK = { overflowWrap: "anywhere" };

/* 열이 안 정해 주면 이 바닥값이 붙는다. 없으면 좁은 컨테이너에서 `overflowWrap:anywhere`
 * 가 열 폭을 '한 글자'까지 줄여 제목이 세로로 무너진다(DS-06 · VIS-73). */
export const DEFAULT_COL_MIN_WIDTH = "4.5rem";

/** 행을 식별하는 열(이메일·항목명·코드)은 폭이 모자랄 때 **가장 먼저 보호**된다. */
export const IDENTIFIER_COL_MIN_WIDTH = "12.5rem";

/* 넘침 처리 어휘.
 *   `ellipsis`  한 줄로 자르고 `title` 로 전체를 남긴다
 *   `nowrap`    자르지 않고 접지도 않는다(값이 짧다는 전제 — 배지·개수·날짜)
 *   `anywhere`  긴 토큰(JSON·UUID·코드)을 글자 단위로 끊는다. 한글 산문에는 쓰지 않는다
 *   `word`      한글 낱말을 지키며 접는다(`KO_WORD_BREAK`)
 */
export const OVERFLOW = { ellipsis: "ellipsis", nowrap: "nowrap", anywhere: "anywhere", word: "word" };

/* ── 어휘표 ────────────────────────────────────────────────────────────────
 *
 * `identifying` 은 «이 열이 그 행이 무엇인지 말한다» 는 뜻이고, 그런 열은 **절대 빼지
 * 않는다**(§collapse). 열 정의의 `rowName`(rowName.js — 낭독되는 이름의 출처)과는 다른
 * 것이라 이름을 갈라 둔다: 하나는 «어느 열의 값을 읽어 주나», 하나는 «어느 열을 없애면
 * 안 되나» 다.
 *
 * `numeric` 은 «자릿수를 세로로 맞춘다»(tabular-nums)는 뜻이다. 우정렬과 짝이지만 같은
 * 것은 아니다 — 식별자형 숫자(티켓번호·포트·버전)는 **좌정렬인데 자릿수는 고정**이다.
 * 크기를 비교하지 않으므로 우정렬이 오히려 틀렸고, 그래서 `identifier` 는 `align:"left"`
 * 에 `numeric:true` 다. QA 의 `numeric_alignment` 가 그 열을 우정렬 위반으로 세지 않게
 * `DataTable` 이 `data-col-role="identifier"` 를 함께 내보낸다.
 */
export const COLUMN_TYPES = {
  /* 표당 **하나**다. 그 행이 무엇인지 말하는 열이고, 폭 경쟁에서 가장 세다. */
  title: { align: "left", numeric: false, minWidth: "16rem", overflow: OVERFLOW.word, identifying: true },
  /* 사람·프로젝트·조직 이름. 제목보다 짧고 한 줄로 읽힌다. */
  name: { align: "left", numeric: false, minWidth: "9rem", overflow: OVERFLOW.ellipsis, identifying: true },
  /* 이메일·코드·UUID·티켓번호. 글자 단위로 끊어도 되는 유일한 부류다. */
  identifier: { align: "left", numeric: true, minWidth: IDENTIFIER_COL_MIN_WIDTH, overflow: OVERFLOW.anywhere, identifying: true },
  /* 설명·오류 원문. 폭 경쟁에서 가장 약하고, 전 행이 비면 수축 후보다(§collapse). */
  text: { align: "left", numeric: false, minWidth: "12rem", overflow: OVERFLOW.ellipsis, collapsible: true },
  /* 상태 배지. 배지 자체가 시각 앵커라 좌정렬이다. */
  status: { align: "left", numeric: false, width: SHRINK, minWidth: "5rem", overflow: OVERFLOW.nowrap },
  /* 짧은 닫힌 집합(종류·범위·대상). 배지가 아니라 낱말이다. */
  enum: { align: "left", numeric: false, width: SHRINK, minWidth: DEFAULT_COL_MIN_WIDTH, overflow: OVERFLOW.nowrap },
  /* 개수. **우정렬 + 자릿수 고정** — 그래야 세로로 훑으며 비교할 수 있다. */
  count: { align: "right", numeric: true, width: SHRINK, minWidth: "4rem", overflow: OVERFLOW.nowrap },
  /* 크기·금액처럼 단위가 붙는 수치. 개수와 같은 규칙이다. */
  number: { align: "right", numeric: true, width: SHRINK, minWidth: "4rem", overflow: OVERFLOW.nowrap },
  /* 비율·점수. 자릿수가 하나 더 붙어 최소폭이 개수보다 넓다. */
  percent: { align: "right", numeric: true, width: SHRINK, minWidth: "5rem", overflow: OVERFLOW.nowrap },
  score: { align: "right", numeric: true, width: SHRINK, minWidth: "5rem", overflow: OVERFLOW.nowrap },
  /* 날짜·시각. **라벨이라 좌정렬**이 기본이다 — 「언제 만들어졌나」는 크기 비교가 아니라
     그 행의 성질이다. 값끼리 세로로 비교하는 자리(백업 목록의 크기 옆 시각 등)는 열이
     `align:"right"` 를 직접 적어 뒤집는다. 자릿수 고정은 어느 쪽이든 붙는다. */
  date: { align: "left", numeric: true, width: SHRINK, minWidth: "8.5rem", overflow: OVERFLOW.nowrap },
  datetime: { align: "left", numeric: true, width: SHRINK, minWidth: "8.5rem", overflow: OVERFLOW.nowrap },
  /* 행 액션 묶음. 오른쪽 끝에 놓인다. */
  actions: { align: "right", numeric: false, width: SHRINK, minWidth: DEFAULT_COL_MIN_WIDTH, overflow: OVERFLOW.nowrap },
  /* 선택 체크박스처럼 라벨이 낱말이 아닌 열. */
  select: { align: "left", numeric: false, width: SHRINK, minWidth: "2.5rem", overflow: OVERFLOW.nowrap },
};

/** `type` 을 안 준 열이 받는 값 — **예전 동작 그대로**다(회귀 0). */
const UNTYPED = { align: "left", numeric: false, minWidth: DEFAULT_COL_MIN_WIDTH, overflow: null };

/** 자릿수를 세로로 맞춰야 하는 타입. 시험과 `DataTable` 이 같은 목록을 본다. */
export const NUMERIC_TYPES = Object.freeze(
  Object.keys(COLUMN_TYPES).filter((k) => COLUMN_TYPES[k].numeric));

/** 우정렬이 계약인 타입. `numeric_alignment` 가 재는 것과 같은 집합이다. */
export const END_ALIGNED_TYPES = Object.freeze(
  Object.keys(COLUMN_TYPES).filter((k) => COLUMN_TYPES[k].align === "right"));

/** 표당 하나만 허용하는 타입. 둘이면 무엇이 그 행의 이름인지 알 수 없다. */
export const SINGLETON_TYPES = Object.freeze(["title"]);

/* 열 하나를 해석한다 — **호출부의 명시 값이 언제나 이긴다.**
 *
 * 옛 `identifier: true` 는 그대로 산다. 그 플래그는 «이 열이 행을 식별한다» 는 선언이고
 * 새 어휘의 `type:"identifier"` 와 같은 뜻이라, 둘 중 하나만 있어도 같은 결과를 준다.
 */
export function resolveColumn(col) {
  const c = col || {};
  const key = c.type && COLUMN_TYPES[c.type] ? c.type : (c.identifier ? "identifier" : null);
  const spec = key ? COLUMN_TYPES[key] : UNTYPED;
  const identifierLike = key === "identifier" || !!c.identifier;
  /* **호출부가 폭을 적었으면 타입의 바닥값을 안 씌운다.**
   *
   * 바닥값은 아무 말도 안 한 열을 지키려고 있다. 그런데 「이 열은 7rem 이다」라고 잰 열에
   * 12.5rem 바닥을 몰래 얹으면, 열이 자기가 적은 것보다 넓어지고 그 여유를 접히는 열에서
   * 빼앗는다 — 홈의 티켓 표에서 「티켓」칸이 200px 를 11%만 채운 채 「제목」이 100% 접혔다
   * (`column_width_vs_content` 실측). 바닥값을 원하면 `minWidth` 로 직접 적으면 된다. */
  const floor = c.minWidth != null ? c.minWidth
    : (c.width != null ? DEFAULT_COL_MIN_WIDTH : spec.minWidth);
  return {
    type: key,
    align: c.align || spec.align,
    numeric: c.numeric != null ? !!c.numeric : !!spec.numeric,
    width: c.width != null ? c.width : spec.width,
    minWidth: floor,
    overflow: c.nowrap ? OVERFLOW.nowrap : (c.overflow || spec.overflow),
    identifier: identifierLike,
    collapsible: !!spec.collapsible,
  };
}

/* 이 표에 `title` 이 둘 이상인가 — 개발 중에만 부르는 진단용. (§어휘표 title 참고)
 * 화면을 죽이지 않고 목록만 돌려준다: 판정은 시험이 하고 렌더는 계속 돼야 한다. */
export function duplicateSingletonTypes(columns) {
  const seen = {};
  const dup = [];
  for (const c of columns || []) {
    const t = c && c.type;
    if (!t || SINGLETON_TYPES.indexOf(t) < 0) continue;
    seen[t] = (seen[t] || 0) + 1;
    if (seen[t] === 2) dup.push(t);
  }
  return dup;
}

/* ── 열을 언제 빼도 되는가 (R-91) ────────────────────────────────────────────
 *
 * 처음 초안은 「지금 렌더된 행이 전부 같은 값이면 그 열을 뺀다」였다. **그건 틀렸다.**
 * 서버가 페이지를 자르는 목록에서 이번 페이지의 값이 같다는 것은 전체 결과가 같다는 뜻이
 * 아니다. 그 규칙대로 하면 페이지를 넘길 때마다, 조건을 바꿀 때마다 **열이 생겼다
 * 사라진다** — 사용자는 자기가 무엇을 해서 표가 바뀌었는지 알 수 없다.
 *
 * 그래서 표는 **혼자 판단하지 않는다.** 호출부가 자기 질의 계약을 `resultScope` 로
 * 알려 주고, 표는 그것 없이는 아무 열도 빼지 않는다:
 *
 *   `serverPaged`    서버가 페이지를 자르는가. 참이면 「전 행이 비었다」로는 못 뺀다
 *   `activeFilters`  사용자가 **명시적으로** 건 조건의 열 키. 조건을 풀면 열이 돌아온다
 *   `fixedColumns`   그 화면·질의에서 값이 구조적으로 불변인 열 키(전용 View·질의 계약)
 *
 * 빼지 않기로 한 열도 그냥 두지 않는다 — 폭을 내용만큼으로 줄이고(`shrink`) 좁은 화면의
 * 숨김 후보로 표시한다. 「우연히 같다」와 「원래 같다」는 다른 사실이고, 다르게 다룬다.
 */

/* 「은/는」을 받침으로 고른다. 열 이름은 데이터라 문장을 손으로 적어 둘 수 없다 —
 * 「상태은」·「제목는」 같은 조사 오류는 화면에서 바로 읽힌다. 한글 음절 영역에서 종성이
 * 있는지만 보면 되고(0xAC00 부터 28음절 주기), 한글이 아니면 「는」이 무난하다. */
export function topicParticle(word) {
  const s = String(word || "");
  const last = s.charCodeAt(s.length - 1);
  if (!(last >= 0xac00 && last <= 0xd7a3)) return "는";
  return (last - 0xac00) % 28 === 0 ? "는" : "은";
}

/** 이 열의 렌더된 값이 전부 같은가. 값이 없으면(행 0) 판단하지 않는다. */
function sameEverywhere(col, rows) {
  if (!rows || rows.length === 0) return false;
  const first = rows[0][col.key];
  for (const r of rows) {
    if (r[col.key] !== first) return false;
  }
  return true;
}

function allEmpty(col, rows) {
  if (!rows || rows.length === 0) return false;
  return rows.every((r) => r[col.key] == null || r[col.key] === "");
}

/* 열 목록과 행을 받아 «빼는 열 · 줄이는 열» 로 가른다.
 *
 * `resultScope` 가 없으면 **둘 다 비어 있다** — 표가 스스로 열을 없애는 경로는 없다.
 * 반환의 `caption` 은 뺀 열이 무엇이었고 그 값이 무엇인지 한 번 적는 문장이다.
 */
export function planColumnCollapse(columns, rows, resultScope) {
  const cols = Array.isArray(columns) ? columns : [];
  const list = Array.isArray(rows) ? rows : [];
  const empty = { removed: [], shrink: [], caption: "" };
  if (!resultScope || !list.length) return empty;

  const scope = resultScope || {};
  const serverPaged = !!scope.serverPaged;
  const filters = Array.isArray(scope.activeFilters) ? scope.activeFilters : [];
  const fixed = Array.isArray(scope.fixedColumns) ? scope.fixedColumns : [];

  const removed = [];
  const shrink = [];
  for (const c of cols) {
    if (!c || !c.key) continue;
    // 행을 여는 이름을 뺄 수는 없다 — 그 열이 사라지면 무엇을 여는지 알 수 없다.
    const spec = resolveColumn(c);
    if (spec.type && COLUMN_TYPES[spec.type] && COLUMN_TYPES[spec.type].identifying) continue;
    if (c.render && !c.collapseValue) continue;   // 값이 아니라 그림인 열은 판단 대상이 아니다

    const structural = fixed.indexOf(c.key) >= 0 || filters.indexOf(c.key) >= 0;
    const same = sameEverywhere(c, list);
    const blank = allEmpty(c, list);

    if (structural && same) {
      removed.push({ key: c.key, label: c.label, value: list[0][c.key] });
      continue;
    }
    // 전 행이 비었는데 서버가 전체를 준다 — 다음 페이지가 없으니 「없다」가 사실이다.
    if (blank && !serverPaged) {
      removed.push({ key: c.key, label: c.label, value: null });
      continue;
    }
    // 여기부터는 **우연**일 수 있다. 빼지 않고 줄인다.
    if (same || blank) shrink.push(c.key);
  }

  const caption = removed.length
    ? removed.map((r) => (r.value == null || r.value === ""
        ? `${r.label} 열은 이 목록에서 전부 비어 있어 숨겼습니다.`
        : `${r.label}${topicParticle(r.label)} 이 목록에서 전부 '${String(r.value)}'이라 열을 숨겼습니다.`)).join(" ")
    : "";
  return { removed, shrink, caption };
}
