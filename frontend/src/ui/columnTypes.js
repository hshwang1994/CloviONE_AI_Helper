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
 * ## `SHRINK` 는 이제 「폭을 따로 정하지 않음」이라는 표시다
 *
 * `DataTable` 은 고정 배치(`tableLayout: fixed`) + `<colgroup>` 이고, 열 폭은 `columnPlan.planColumns` 가 이 표의 바닥 ·
 * 비중 · 상한과 머리글 · 값 길이로 나눈 px 다(D-529). 예전 auto 배치에서 「내용만큼만」을 뜻하던 `1%` 는 고정 배치에서는
 * 폭이 될 수 없으므로, 지금은 「호출부가 폭을 정하지 않았다 - 타입의 바닥을 쓴다」는 표시로만 읽는다(`columnLayoutWidth`).
 */

/** auto 배치 표에서 「내용 폭만큼」을 뜻하는 값. 위 주석 참고. */
export const SHRINK = "1%";

/** `table-layout:fixed` 에서 열 하나의 폭. undefined 는 「남는 폭을 먹는다」는 뜻이다.
 *  `SHRINK`(`1%`)는 fixed 배치에서 망가지므로 **바닥 minWidth** 를 쓴다.
 *
 *  남는 폭을 먹는 열은 둘이다(D-501). `grow: true` 를 단 산문 열과, 폭을 적지 않은 `title` 이다.
 *  `title` 이라도 호출부가 `width` 를 적었으면 그 폭을 지킨다 — 「26-08」처럼 값이 짧은 제목 열이나
 *  설정 「항목명」은 남는 폭을 가져도 빈칸만 는다. 그 폭은 옆의 산문 열(설명 · 오류)이 가져야 읽힌다. */
export function columnLayoutWidth(col) {
  const c = col || {};
  const s = resolveColumn(c);
  if (c.grow) return undefined;
  /* 상한(`max`)을 적은 제목 열은 첫 그림에서도 그 폭에 선다 — 짧은 이름 열(설정 「항목명」)이 남는 폭을 다 먹지 않는다. 칸을
     잰 뒤의 폭은 열 배분(`columnPlan.planColumns`)이 정한다. */
  if (s.type === "title" && c.width == null) return c.max != null ? c.max : undefined;
  const explicit = c.width != null ? c.width : s.width;
  if (explicit && explicit !== SHRINK) return explicit;
  return s.minWidth;
}

/* ── 남는 폭의 주인 (D-501) ─────────────────────────────────────────────────
 *
 * `table-layout: fixed` 에서 남는 폭은 폭을 안 받은 열이 나눠 갖는다. 그런 열이 하나도 없으면
 * 브라우저가 **모든 열에 비례로** 나눈다 — 관리자 목록 열아홉이 전부 그 모양이었다. 제목 열이 없는
 * 표에서 「설명」 · 「오류」 같은 산문 열은 바닥 12rem 의 두 배쯤을 받고 스무 글자 남짓에서 잘렸고,
 * 「상태」 · 「시도」 같은 짧은 값 열도 똑같이 두 배로 늘어 빈칸만 넓어졌다(기능 플래그 「설명」, 작업 큐
 * 「오류」 실측).
 *
 * 그래서 남는 폭을 먹는 열이 없는 표에서는 **마지막 산문 열(`type: "text"`)** 이 그 폭을 갖는다. 뒤에
 * 선 산문 열을 고르는 이유는 표가 왼쪽에서 오른쪽으로 중요도가 낮아지게 적히고,
 * 긴 설명은 대개 끝에 서기 때문이다. 호출부가 `width` 를 적은 산문 열은 고르지 않는다 — 그 폭은
 * 호출부의 결정이다(열 접기가 「우연히 같다」로 줄인 열도 `width` 를 받는다). 산문 열이 없으면 예전처럼
 * 브라우저가 비례로 나눈다. 정렬(D-471)은 바꾸지 않는다 — 폭의 주인만 정한다.
 *
 * 열 목록이 그대로면 **같은 배열**을 돌려준다. 호출부의 메모(`useMemo`)가 깨지지 않게 한다. */
export function assignLeftoverWidth(columns) {
  const cols = columns || [];
  if (!cols.length || cols.some((c) => c && columnLayoutWidth(c) === undefined)) return cols;
  let at = -1;
  for (let i = cols.length - 1; i >= 0; i -= 1) {
    const c = cols[i];
    if (c && c.width == null && resolveColumn(c).type === "text") { at = i; break; }
  }
  if (at < 0) return cols;
  const out = cols.slice();
  out[at] = { ...cols[at], grow: true };
  return out;
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

/* ── 길이를 **숫자로** (열 배분이 렌더 전에 판단하려면) ────────────────────────
 *
 * 위 `tableMinWidth` 는 CSS 에 거는 문자열이라 브라우저가 더한다. 그런데 「이 칸에 들어가는가」 · 「남는 폭이 얼마인가」는
 * 우리가 **렌더 전에** 판단해야 한다(`columnPlan.planColumns`). 그래서 rem · px 길이를 px 숫자로 바꾼다.
 *
 * rem 은 루트 폰트사이즈로 곱한다 — 2200/3000 에서 그 값이 커지므로(`styles/root.css`)
 * 16 을 상수로 박으면 4K 에서 「들어간다」고 잘못 센다. */
export function lengthToPx(token, rootPx) {
  const root = rootPx > 0 ? rootPx : 16;
  if (typeof token === "number") return Number.isFinite(token) ? token : null;
  const t = String(token || "").trim();
  const m = /^(-?\d*\.?\d+)(rem|em|px)?$/.exec(t);
  if (!m) return null;                       // `%`·`calc()`·`auto` — 셀 수 없다
  const n = parseFloat(m[1]);
  if (!Number.isFinite(n)) return null;
  return m[2] === "px" || !m[2] ? n : n * root;
}

/* 칸에 안 들어가면 열을 **필요한 만큼만** 숨기는 판단과 폭 배분은 `columnPlan.js::planColumns` 하나다(D-529). 예전 이 자리의
 * `planNarrowColumns` 는 「뷰포트가 아니라 그 표가 받은 칸」 · 「전부가 아니라 하나씩」을 처음 세운 함수였고, 그 두 규칙은
 * 배분이 그대로 잇는다 — 숨기는 순서가 열 순서에서 등급(문맥 → 보조) · priority · 오른쪽 순서로 바뀌었다. */

/** 지금 루트 폰트사이즈(px). 4K 에서 커진다(`styles/root.css`). */
export function rootFontPx(doc) {
  const d = doc || (typeof document !== "undefined" ? document : null);
  if (!d || !d.documentElement || typeof getComputedStyle !== "function") return 16;
  const v = parseFloat(getComputedStyle(d.documentElement).fontSize);
  return v > 0 ? v : 16;
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
/* ── 머리글은 **자기 열의 몸통과 같은 축**에 선다 (핸드오프 D-3 · ACCEPTANCE E2) ─────────
 *
 * 머리와 몸이 열마다 같은 축이다 — 왼쪽 열은 머리도 왼쪽, 오른쪽 열은 머리도 오른쪽이다. 2026-09-06
 * 에 「제목만 왼쪽, 나머지 가운데」로 모았던 까닭은 「머리글은 언제나 가운데, 몸은 왼쪽」이 축을 갈랐기
 * 때문이다. 머리와 몸을 **함께** 옮기면 그 문제는 생기지 않는다.
 *
 * 정렬·필터 조작기는 이름과 **한 덩어리**로 그 열의 축에 선다. 이름만 따로 두고 조작기를 양옆
 * 저울추로 밀면(`1fr auto 1fr`), 좁은 숫자 열에서 글자가 옆 칸과 겹친다. `TableHeaderCell` 이 그 한
 * 덩어리를 그린다.
 */
export const HEADER_ALIGN = "center";

/** 이 열의 머리글 정렬 — 몸통과 같다(left · center · right). */
export function headerAlignOf(column) {
  return resolveColumn(column || {}).align || HEADER_ALIGN;
}

/* ── 몸통 칸의 정렬 — **열의 의미가 정한다** (계획 2.9, D-506) ─────────────────────
 *
 * - **왼쪽(읽는 글)**: 제목 · 이름 · 이메일과 긴 토큰(identifier) · 설명과 원인(text) · 경로(path).
 *   글은 왼쪽 모서리에서 읽기 시작한다. 가운데에 두면 행마다 시작점이 흔들리고, 앞이 같고 뒤가 갈리는
 *   값(부서 경로, 파일 경로)은 왼쪽 모서리가 비교 수단이다.
 * - **가운데(보는 값)**: 상태 · 짧은 닫힌 집합(enum) · 날짜와 시각 · 짧은 코드(티켓 번호, 버전) ·
 *   행 동작 · 선택 칸. 폭이 거의 같은 짧은 값이라 칸 가운데가 가장 잘 보인다.
 * - **오른쪽(비교하는 수)**: 개수 · 수치 · 비율 · 점수. 자릿수가 다른 값(1 과 1,240)을 세로로 비교하려면
 *   끝자리가 맞아야 한다. `tabular-nums` 를 함께 건다.
 *
 * 화면은 `align` 을 직접 적지 않는다(`resolveColumn` 이 호출부 값을 보지 않는다). 예외가 필요하면
 * 그 뜻을 가진 타입을 이 표에 더한다 - 화면마다 정렬을 고르면 같은 뜻의 열이 화면마다 다른 축에 선다.
 */
/* 폭 배분의 세 갈래(D-529, `columnPlan.js`) — 「늘어나는 글」은 바닥(`minWidth`) · 비중(`weight`) · 상한(`maxWidth`)을 갖고
   남는 폭을 비중대로 상한까지 나눠 받는다. 「내용 길이」(`content`)는 바닥 · 머리글 · 값 가운데 가장 긴 것이 폭이다. 나머지는
   고정 폭이다. 머리글이 한 줄로 서는 폭(이름 + 정렬 · 필터 표지)은 열마다 따로 재서 바닥에 더하므로, 여기 바닥은 머리글을
   어림한 값이 아니다. */
export const COLUMN_TYPES = {
  /* 표당 **하나**다. 그 행이 무엇인지 말하는 열이고, 남는 폭을 가장 많이 받는다(비중 3). 혼자 다 먹지는 않는다(상한 36rem). */
  title: { align: "left", numeric: false, minWidth: "14rem", weight: 3, maxWidth: "36rem", overflow: OVERFLOW.word, identifying: true },
  /* 사람·프로젝트·조직 이름. 제목보다 짧고 한 줄로 읽힌다(비중 2, 상한 18rem). */
  name: { align: "left", numeric: false, width: SHRINK, minWidth: "9rem", weight: 2, maxWidth: "18rem", overflow: OVERFLOW.ellipsis, identifying: true },
  /* 이메일 · UUID · 파일 이름 · 모델 id 처럼 글자 단위로 끊어도 되는 긴 토큰. 짧은 코드(티켓 번호 · 버전)는 `code` 다. */
  identifier: { align: "left", numeric: false, minWidth: "11rem", weight: 2, maxWidth: "22rem", overflow: OVERFLOW.anywhere, identifying: true },
  /* 티켓 번호 · 버전 · Cron 식처럼 짧고 모양이 정해진 코드. 크기를 비교하지 않는다. 폭은 값 길이가 정한다. */
  code: { align: "center", numeric: true, width: SHRINK, minWidth: "6.5rem", content: true, overflow: OVERFLOW.nowrap, identifying: true },
  /* 설명·오류 원문. 전 행이 비면 수축 후보다(§collapse). 남는 폭을 제목과 같은 비중으로 받는다(상한 48rem). */
  text: { align: "left", numeric: false, minWidth: "12rem", weight: 3, maxWidth: "48rem", overflow: OVERFLOW.ellipsis, collapsible: true },
  /* 부서 경로 · 폴더 경로. 앞이 같고 뒤가 갈리는 값이라 왼쪽 모서리가 비교 수단이다. */
  path: { align: "left", numeric: false, minWidth: "10rem", weight: 2, maxWidth: "24rem", overflow: OVERFLOW.ellipsis },
  /* 상태 배지. 폭은 바닥 · 머리글(「우선순위」 + 정렬 · 필터) · 가장 긴 상태 낱말 가운데 가장 긴 것이다. `lead` 는 낱말 앞의 표지
     점(6px)과 사이(0.625rem)다(`kit.jsx::Badge`) — 이것을 빼고 재면 긴 낱말(「설정이 끝나지 않아 보내지 못함」)이 몇 px 모자라 잘렸다(랩 캡처). */
  status: { align: "center", numeric: false, width: SHRINK, minWidth: "6rem", content: true, lead: 1, overflow: OVERFLOW.nowrap },
  /* 짧은 닫힌 집합(종류·범위·대상·역할). 폭은 선택지 라벨(`values`)이나 받은 값의 가장 긴 낱말이 정한다. */
  enum: { align: "center", numeric: false, width: SHRINK, minWidth: "6.5rem", content: true, overflow: OVERFLOW.nowrap },
  /* 개수. **오른쪽 + 자릿수 고정.** */
  count: { align: "right", numeric: true, width: SHRINK, minWidth: "6rem", overflow: OVERFLOW.nowrap },
  /* 크기·금액·공수처럼 단위가 붙는 수치. 머리글 「예상 WD」 + 정렬은 머리글 폭 계산이 따로 지킨다. */
  number: { align: "right", numeric: true, width: SHRINK, minWidth: "7rem", overflow: OVERFLOW.nowrap },
  /* 비율·점수. */
  percent: { align: "right", numeric: true, width: SHRINK, minWidth: "6rem", overflow: OVERFLOW.nowrap },
  score: { align: "right", numeric: true, width: SHRINK, minWidth: "6rem", overflow: OVERFLOW.nowrap },
  /* 날짜·시각. 폭이 고정된 짧은 값이라 가운데다. 자릿수 고정은 그대로 붙는다. */
  date: { align: "center", numeric: true, width: SHRINK, minWidth: "8.5rem", overflow: OVERFLOW.nowrap },
  datetime: { align: "center", numeric: true, width: SHRINK, minWidth: "11rem", overflow: OVERFLOW.nowrap },
  /* 행 액션 묶음. 표의 마지막 열이고 칸 가운데에 선다. */
  actions: { align: "center", numeric: false, width: SHRINK, minWidth: "6.5rem", overflow: OVERFLOW.nowrap },
  /* 선택 체크박스처럼 라벨이 낱말이 아닌 열. 체크박스는 글이 아니라 표식이라 가운데다. */
  select: { align: "center", numeric: false, width: SHRINK, minWidth: "2.5rem", overflow: OVERFLOW.nowrap },
};

/** `type` 을 안 준 열이 받는 값.
 *
 * 가운데다. 값이 글이면 `type: "text"` 를, 수면 `type: "count"` 를 준다 — 정렬로 때울 일이 아니다. */
const UNTYPED = { align: "center", numeric: false, minWidth: DEFAULT_COL_MIN_WIDTH, overflow: null };

/** 자릿수를 세로로 맞춰야 하는 타입(파생 상수). */
export const NUMERIC_TYPES = Object.freeze(
  Object.keys(COLUMN_TYPES).filter((k) => COLUMN_TYPES[k].numeric));

/** 타입별 정렬 표(파생 상수). 시험과 프로브가 같은 표를 읽는다. */
export const ALIGN_BY_TYPE = Object.freeze(
  Object.fromEntries(Object.keys(COLUMN_TYPES).map((k) => [k, COLUMN_TYPES[k].align])));

/** 표당 하나만 허용하는 타입. 둘이면 무엇이 그 행의 이름인지 알 수 없다. */
export const SINGLETON_TYPES = Object.freeze(["title"]);

/* 열 하나를 해석한다 — 폭은 호출부의 명시 값이 이기지만, **정렬은 언제나 타입이 정한다.**
 *
 * 옛 `identifier: true` 는 그대로 산다. 그 플래그는 «이 열이 행을 식별한다» 는 선언이고
 * 새 어휘의 `type:"identifier"` 와 같은 뜻이라, 둘 중 하나만 있어도 같은 결과를 준다.
 */
export function resolveColumn(col) {
  const c = col || {};
  const key = c.type && COLUMN_TYPES[c.type] ? c.type : (c.identifier ? "identifier" : null);
  const spec = key ? COLUMN_TYPES[key] : UNTYPED;
  const identifierLike = key === "identifier" || key === "code" || !!c.identifier;
  /* **호출부가 폭을 적었으면 타입의 바닥값을 안 씌운다.** 바닥값을 원하면 `min`(또는 옛 `minWidth`)으로 직접 적는다. */
  const own = c.min != null ? c.min : c.minWidth;
  const floor = own != null ? (typeof own === "number" ? `${own}rem` : own)
    : (c.width != null ? DEFAULT_COL_MIN_WIDTH : spec.minWidth);
  return {
    type: key,
    align: spec.align,
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
 * 있는지만 보면 되고(0xAC00 부터 28음절 주기), 한글이 아니면 「는」이 무난하다.
 *
 * 구현은 `lib/format.js` 에 하나만 둔다 — 폼의 필수 칸 문구도 같은 규칙이 필요하고,
 * 두 번째로 베낀 순간 둘이 갈라진다. 이 이름으로 가져다 쓰던 호출자를 위해 다시 내보낸다. */
import { topicParticle } from "../lib/format.js";
export { topicParticle };

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
