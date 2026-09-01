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

/** `table-layout:fixed` 에서 열 하나의 폭. `title` 은 남는 폭을 먹는다(undefined).
 *  `SHRINK`(`1%`)는 fixed 배치에서 망가지므로 **바닥 minWidth** 를 쓴다. */
export function columnLayoutWidth(col) {
  const s = resolveColumn(col);
  if (s.type === "title") return undefined;
  const c = col || {};
  const explicit = c.width != null ? c.width : s.width;
  if (explicit && explicit !== SHRINK) return explicit;
  return s.minWidth;
}

/* 이 표가 **줄어들 수 있는 바닥 폭** — 모든 열이 자기 폭을 지킬 때의 합.
 *
 * `table-layout: fixed` 는 열의 `min-width` 를 **안 본다.** 열 폭은 `<col>`(=위
 * `columnLayoutWidth`) 하나로 정해지고, 그 합이 표 폭보다 크면 남는 폭을 먹기로 한
 * `title` 이 0 을 받는다. 그러면 제목 칸은 `maxWidth: 0` + `overflow: hidden` 이라
 * **글자가 통째로 사라지고**, 머리글은 `overflow: visible` 이라 옆 이름 위에 겹쳐 그려진다.
 *
 * 실측(2026-09-01 · 팀 티켓 · light):
 *
 *     폭      표     칸    제목 열
 *     1280   1272   934      0px
 *     1366   1272  1020      0px
 *     1536   1272  1174      0px     ← 1920 화면 브라우저 125%
 *     1600   1272  1238      0px
 *     1920   1558  1558    286px
 *
 * 1920 아래로는 **어느 해상도에서도 제목이 없었다.** 창을 줄여서가 아니라 그 표의 나머지
 * 열이 1272px 을 이미 차지하기 때문이고, 그래서 배율을 한 칸만 올려도 같은 일이 난다.
 *
 * 바닥을 **표 자신**(`min-width`)에 걸면 그 일이 안 일어난다. 표는 바닥 아래로 안 줄고
 * `TableContainer` 가 가로로 굴러간다 — 이 저장소가 이미 여러 번 적어 둔 거래다
 * (「폭이 정말 모자라면 표를 줄이는 대신 가로로 민다, 읽을 수 없는 표보다 낫다」).
 * 그 문장은 있었는데 그것을 실제로 만드는 값이 없었다.
 *
 * 합은 `calc()` 로 낸다. 단위가 섞여도(rem·px) CSS 가 더하고, 루트 폰트사이즈가
 * 2200/3000 에서 커지면(`styles/root.css`) 바닥도 같은 비율로 함께 커진다.
 */
export function tableMinWidth(columns) {
  const parts = [];
  for (const c of columns || []) {
    if (!c) continue;
    const s = resolveColumn(c);
    const w = columnLayoutWidth(c) || s.minWidth || DEFAULT_COL_MIN_WIDTH;
    const token = typeof w === "number" ? `${w}px` : String(w);
    /* 퍼센트는 표 폭에서 파생하는 값이라 표 폭의 바닥이 될 수 없다(순환). `SHRINK` 는
       `columnLayoutWidth` 가 이미 rem 바닥으로 바꿔 주므로 여기 오는 일은 드물다. */
    if (!token || token.indexOf("%") >= 0) continue;
    parts.push(token);
  }
  if (!parts.length) return undefined;
  return parts.length === 1 ? parts[0] : `calc(${parts.join(" + ")})`;
}

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
 * `numeric` 은 «자릿수를 세로로 맞춘다»(tabular-nums)는 뜻이고 정렬과는 다른 축이다.
 * 지금은 모든 수치 열이 가운데지만 자릿수 고정은 그대로 필요하다 — 고정 폭이라야 값이
 * 칸 안에서 흔들리지 않는다. 식별자형 숫자(티켓번호·포트·버전)는 크기를 비교하지
 * 않는다는 사실을 `DataTable` 이 `data-col-role="identifier"` 로 내보낸다.
 */
/* ── 머리글은 언제나 가운데다 ──────────────────────────────────────────────
 *
 * 몸통 칸의 정렬은 값의 의미가 정하고(아래 표), 머리글은 그것과 **따로** 가운데에 선다.
 * 둘을 같은 값으로 묶으면 표마다 머리글 줄이 들쭉날쭉해진다 — 왼쪽에 붙은 이름 옆에
 * 가운데 이름이 서고 그 옆에 오른쪽 이름이 서면, 눈이 머리글 줄을 한 줄로 못 읽는다.
 *
 * 정렬·필터 조작기는 이름과 **한 덩어리**로 칸 가운데에 선다. 이름만 따로 가운데에
 * 두고 조작기를 양옆 저울추로 밀면(`1fr auto 1fr`), 좁은 숫자 열에서 글자가 옆 칸과
 * 겹친다. `TableHeaderCell` 이 그 한 덩어리를 그린다.
 */
export const HEADER_ALIGN = "center";

/* ── 몸통 칸의 정렬 ────────────────────────────────────────────────────────
 *
 * **왼쪽은 「읽는 것」이다** — 티켓 제목 · 프로젝트 이름 · 문서 이름 · 사람 이름 ·
 * 설명. 이 값들은 길이가 제각각이라 왼쪽 모서리가 맞아야 눈이 다음 줄로 내려간다.
 *
 * **가운데는 「보는 것」이다** — 티켓 ID · 상태 · 우선순위 · 난이도 · WD · 날짜 ·
 * 건수 · 퍼센트 · 점수 · 짧은 코드 · 행 동작. 폭이 고정된 짧은 값이고, 칸 안에서
 * 가운데에 서면 열이 하나의 띠로 읽힌다.
 *
 * ⚠️ **수치 열의 우정렬을 가운데로 바꿨다** (2026-08-27 지시 6·13). 우정렬은 자릿수가
 * 다른 값을 세로로 비교하기에 낫고, 그것이 예전 계약이었다. 대신 `tabular-nums` 는
 * 그대로 둔다 — 자릿수가 같은 값끼리는 가운데에서도 세로로 맞는다. 자릿수가 크게
 * 다른 열(1 과 1,240)에서는 비교가 예전만 못하다는 것을 알고 고른 값이다.
 */
export const COLUMN_TYPES = {
  /* 표당 **하나**다. 그 행이 무엇인지 말하는 열이고, 폭 경쟁에서 가장 세다. */
  title: { align: "left", numeric: false, minWidth: "16rem", overflow: OVERFLOW.word, identifying: true },
  /* 사람·프로젝트·조직 이름. 제목보다 짧고 한 줄로 읽힌다.
     **폭 경쟁에 나서지 않는다**(`width: SHRINK`). 이름은 길어야 스무 글자인데 이 열이
     `title` 과 함께 남는 폭을 나눠 가지면 둘이 반씩 갖는다 — 게시판에서 「작성자」가
     740px 로 서고 제목이 같은 폭에서 잘렸다(S19 실측). 폭이 더 필요하면 그 화면이
     `minWidth` 로 바닥을 올린다. 남는 폭을 갖는 열은 표당 하나(`title`)다. */
  name: { align: "left", numeric: false, width: SHRINK, minWidth: "9rem", overflow: OVERFLOW.ellipsis, identifying: true },
  /* 이메일·코드·UUID·티켓번호. 글자 단위로 끊어도 되는 유일한 부류다. */
  identifier: { align: "center", numeric: true, minWidth: IDENTIFIER_COL_MIN_WIDTH, overflow: OVERFLOW.anywhere, identifying: true },
  /* 설명·오류 원문. 폭 경쟁에서 가장 약하고, 전 행이 비면 수축 후보다(§collapse). */
  text: { align: "left", numeric: false, minWidth: "12rem", overflow: OVERFLOW.ellipsis, collapsible: true },
  /* 상태 배지. 머리글이 「우선순위」처럼 네 글자면 5rem 으로는 정렬 화살표와 겹친다. */
  status: { align: "center", numeric: false, width: SHRINK, minWidth: "7.5rem", overflow: OVERFLOW.nowrap },
  /* 짧은 닫힌 집합(종류·범위·대상). 머리글 「난이도」+정렬이 한 줄로 서는 폭. */
  enum: { align: "center", numeric: false, width: SHRINK, minWidth: "6.5rem", overflow: OVERFLOW.nowrap },
  /* 개수. **가운데 + 자릿수 고정.** 머리글 「조회」+정렬이 한 줄로 서는 폭. */
  count: { align: "center", numeric: true, width: SHRINK, minWidth: "6rem", overflow: OVERFLOW.nowrap },
  /* 크기·금액·공수처럼 단위가 붙는 수치. 머리글이 「예상 WD」처럼 두 토막이면 4rem 으로는
     이름+정렬 화살표가 칸을 넘쳐 옆 열과 겹친다(`table-layout:fixed`). 바닥을 머리글이
     한 줄로 서는 폭에 맞춘다. */
  number: { align: "center", numeric: true, width: SHRINK, minWidth: "8rem", overflow: OVERFLOW.nowrap },
  /* 비율·점수. 머리글 「진행률」+정렬이 한 줄로 서는 폭. */
  percent: { align: "center", numeric: true, width: SHRINK, minWidth: "6.5rem", overflow: OVERFLOW.nowrap },
  score: { align: "center", numeric: true, width: SHRINK, minWidth: "6.5rem", overflow: OVERFLOW.nowrap },
  /* 날짜·시각. 폭이 고정된 짧은 값이라 가운데다. 자릿수 고정은 그대로 붙는다 —
     'YYYY-MM-DD' 는 자릿수가 언제나 같아서 가운데에서도 세로로 맞는다. */
  date: { align: "center", numeric: true, width: SHRINK, minWidth: "8.5rem", overflow: OVERFLOW.nowrap },
  datetime: { align: "center", numeric: true, width: SHRINK, minWidth: "11rem", overflow: OVERFLOW.nowrap },
  /* 행 액션 묶음. 표의 마지막 열이고 칸 가운데에 선다. 머리글 「작업」·「결재」가 서는 폭. */
  actions: { align: "center", numeric: false, width: SHRINK, minWidth: "6.5rem", overflow: OVERFLOW.nowrap },
  /* 선택 체크박스처럼 라벨이 낱말이 아닌 열.
     🔴 `left` 였다. 그런데 이 타입을 만드는 **유일한 자리**(`ui/bulkSelect.jsx`)는
     `align: "center"` 를 직접 박고 있었다 — 어휘와 그 어휘의 유일한 생산자가 서로 다른
     말을 하면 어휘가 아니다. 체크박스는 글이 아니라 표식이라 가운데가 맞다. */
  select: { align: "center", numeric: false, width: SHRINK, minWidth: "2.5rem", overflow: OVERFLOW.nowrap },
};

/** `type` 을 안 준 열이 받는 값 — **예전 동작 그대로**다(회귀 0). */
const UNTYPED = { align: "left", numeric: false, minWidth: DEFAULT_COL_MIN_WIDTH, overflow: null };

/** 자릿수를 세로로 맞춰야 하는 타입. 시험과 `DataTable` 이 같은 목록을 본다. */
export const NUMERIC_TYPES = Object.freeze(
  Object.keys(COLUMN_TYPES).filter((k) => COLUMN_TYPES[k].numeric));

/** 가운데 정렬이 계약인 타입. `numeric_alignment` 가 재는 것과 같은 집합이다.
 *
 * 이름을 `END_ALIGNED_TYPES` 에서 바꿨다 — 「끝에 붙인다」가 더 이상 사실이 아니다.
 * 이름과 뜻이 갈린 상수는 다음 사람이 읽고 반대로 고친다. */
export const CENTER_ALIGNED_TYPES = Object.freeze(
  Object.keys(COLUMN_TYPES).filter((k) => COLUMN_TYPES[k].align === "center"));

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
