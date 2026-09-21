/* 밀도 치수 — 판·타일·격자 간격의 단일 출처.
 *
 * ## 이 파일이 있는 이유
 *
 * 카드 패딩·격자 열·간격이 화면 파일 스무 곳에 손으로 흩어져 있었다. 그래서 기준과
 * 어긋나도 **어디를 고쳐야 하는지 아무도 몰랐고**, 실제로 사용자가 배포 화면을 보고
 * "설계한 대로 된 게 하나도 없다"고 했다. 값을 여기 한 곳에만 둔다.
 *
 * ## 값의 출처가 바뀌었다 (W4)
 *
 * 예전 주석은 이 숫자들이 **폐기한 목업**(지시 64)에서 왔다고 적고 있었고, 그래서
 * "기준선에 있는 값만 적는다" 가 이 파일의 유일한 존재 이유라고 선언했다. 목업은 정본이
 * 아니다 — 그 문장을 그대로 두면 다음 사람이 없는 문서를 찾아 헤맨다.
 *
 * 지금 이 값들의 정본은 **PLAN «Typography · Density»** 다. W4 가 네 개를 올렸다:
 *
 *   cardPadding    20 -> 24   판 안쪽이 20 이면 19px 구획 제목이 테두리에 붙는다
 *                  24 -> 20   (핸드오프 D-16) 판 제목이 1.0625rem(17px)으로 내려오면서 위 근거가
 *                             사라졌다 — 17px 제목은 20px 안쪽에서 테두리에 붙지 않는다. 판 여백
 *                             하나가 20 이다(메시지 박스 12/14 · 칸반 카드 12/14 는 자기 계약).
 *   sectionGap     24 -> 32   구획 사이가 카드 안쪽 여백과 비슷하면 묶음이 안 읽힌다
 *   gridGap        16 -> 24   판이 커졌으니 판 사이도 같이 벌어져야 관계가 유지된다
 *   healthGridGap  12 -> 16   작은 타일 줄은 판보다 촘촘하되 같은 비율로 따라온다
 *
 * 계약은 값이 아니라 **성질**이고, `density-contract.test.jsx` 가 그 성질을 지킨다:
 * 구획 간격 > 판 여백의 절반 · 타일은 판보다 촘촘 · 모든 치수 양수 · 상세/폼 격자에 `fr`.
 * 값을 다시 움직일 때 그 시험이 관계를 잡아 준다.
 *
 * ## px 를 rem 으로 바꿔 내보내는 이유
 *
 * 이 앱은 `styles/root.css` 의 루트 폰트사이즈 하나로 4K 배율을 맞춘다(16 -> 18 -> 20px).
 * px 로 박으면 그 조각만 4K 에서 혼자 작게 남는다. 기본 루트(16px)에서는 아래 표와
 * **정확히 같은 픽셀**이 되고, 큰 화면에서는 다른 요소와 같은 비율로 커진다.
 *
 * ## 쓰이지 않는 값은 두지 않는다
 *
 * 예전에는 열세 개를 적어 두었는데 그중 여덟(`detailBlockPadding`·`kpi*` 넷·`cardHeadGap`·
 * `topbarHeight`·`sidebarWidth`)은 **이 파일 밖에 소비처가 0** 이었다. 소비처 없는 치수는
 * 다음 사람에게 "여기에 정본이 있다" 고 거짓말을 한다 — 실제 정본은 각각 `theme.js`
 * (`CONTROL`·`FONT_SIZE`)와 `AppShell.jsx`(`APPBAR_HEIGHT`·`SIDEBAR_WIDTH`)에 있다.
 */

/* 치수의 정본 px. 아래 rem 상수가 전부 여기서 나온다. */
export const DENSITY_PX = {
  cardPadding: 20,      // 판(plate) 안쪽 여백 — 핸드오프 D-16
  healthCardPadding: 16, // 작은 상태 타일 안쪽 여백
  gridGap: 24,          // 판끼리의 간격
  healthGridGap: 16,    // 작은 타일끼리의 간격
  sectionGap: 32,       // 구획과 구획 사이
};

/* 격자 트랙. 문자열 그대로 CSS 에 넣는다 — 옮겨 적으면서 숫자가 바뀌는 것이 지금까지
 * 어긋남의 절반이었다.
 *
 * ⚠️ **세 트랙 모두 `fr` 이 하나 이상 들어 있다.** 이게 이 목록에서 가장 중요한 성질이다.
 * `minmax(0, 78ch) minmax(18rem, 26rem)` 처럼 트랙의 상한이 전부 고정값이면, 격자는
 * 컨테이너가 아무리 넓어도 그 합만큼만 차지하고 **남는 폭을 오른쪽에 빈 채로 남긴다**.
 * 사용자가 "왼쪽으로 쏠려있다, 페이지 전체에 정보가 담기는 게 아니라" 고 한 것이 그것이다.
 * `mx:"auto"` 는 이 증상을 못 고친다 — 가운데로 옮길 뿐 폭을 채우지는 않는다.
 * `density-contract.test.jsx` 가 소비처 세 곳에서 이 성질을 단언한다.
 *
 * 이름은 유지한다 — 소비처가 `BASELINE_TRACKS` 로 부르고 있고, 이름을 바꾸면 W4 소유가
 * 아닌 화면 파일 넷을 같은 커밋에서 건드려야 한다. 값의 정본은 이 파일이다. */
export const BASELINE_TRACKS = {
  // 티켓·문서 상세(본문 + 속성 레일)
  detail: "minmax(0, 1.5fr) minmax(300px, 0.65fr)",
  // 주 판 + 보조 레일(새 티켓 · LLM 콘솔 · 퇴직 처리 · 초기 설정) — 핸드오프 RULES §0 의 2열.
  // 소비처 넷이 모두 「주 판 + 보조 레일」이라 한 값을 같이 쓴다(D-458 이 앞 둘을 「/new-ticket
  // 모양」으로 적었다). 두 트랙 모두 바닥이 0 이다 — 좁아지면 `lg` 미만에서 1열로 접히는 것이
  // 폭을 지키는 방법이지 레일의 px 바닥이 아니다.
  two: "minmax(0, 1.62fr) minmax(0, 1fr)",
  // 좌측 구조 레일 + 목록(문서 작업공간·조직 콘솔). 이 트랙이 없던 동안 두 화면이
  // 서로 다른 값(18rem·gap16 vs 20~26rem·gap20)을 각자 하드코딩했다 — density.js 가
  // 세 번 겪은 「값이 화면마다 흩어진다」의 네 번째였다. fr 트랙의 최소가 0이라
  // 공간이 있으면 레일은 항상 최대값으로 선다 — 22rem 은 문서 레일의 실측 하한
  // (18rem — 그 아래에서 제목·「폴더 추가」 줄이 잘렸다)을 여유 있게 넘고, 조직
  // 트리의 축소를 64px 로 한정하는 값이다.
  listRail: "minmax(18rem, 22rem) minmax(0, 1fr)",
};

/* 🔴 `kpi`(4열) · `three`(3열) · `health`(5열)를 걷었다 — 셋 다 **소비처가 0** 이었다.
 * 어휘는 쓰이는 만큼만 있어야 한다. 이름만 남은 트랙은 다음 사람에게 「여기 정본이 있으니
 * 이걸 쓰면 되겠다」로 읽히는데, 정작 그 값이 어느 화면에서도 검증된 적이 없다. 균등 N열이
 * 필요하면 그 화면이 `repeat(N, minmax(0, 1fr))` 를 직접 적고, 두 번째 소비처가 생기는
 * 순간 여기로 올린다(이 파일이 세 번 겪은 「값이 화면마다 흩어진다」의 반대편 실수다). */

/* 보드·회의 KPI / 논의 카드.
 *
 * `auto-fill` 은 컨테이너에 들어갈 **최대 칸 수**만큼 빈 트랙을 만들고, 항목은 앞칸에만
 * 채운다 — 1920 에서 칸이 일곱인데 트랙이 열한 개면 오른쪽이 통째로 비어 「왼쪽에만
 * 몰렸다」고 보인다. 개수가 정해진 줄은 `fixedTileTrack` 으로 칸 수만큼만 트랙을 만든다.
 * 좁은 화면에서 줄바꿈이 필요할 때만 `KPI_TILE_TRACK` 을 쓴다. */
export function fixedTileTrack(count) {
  const n = Math.max(1, Number(count) || 1);
  return `repeat(${n}, minmax(0, 1fr))`;
}

export const KPI_TILE_TRACK = "repeat(auto-fill, minmax(7.5rem, 1fr))";

/* ── 반만 찬 마지막 줄을 안 만든다 ──────────────────────────────────────────
 *
 * 🔴 회의의 「오늘 논의할 항목」은 카드가 **여덟** 인데 트랙은 `repeat(5, …)` 로 박혀
 * 있었다. 다섯이 첫 줄에 서고 셋이 둘째 줄에 남아, 그 줄의 오른쪽 40% 가 통째로 빈
 * 띠가 됐다 — 사용자가 「카드가 잘렸나」로 읽은 자리다.
 *
 * 칸 수를 **개수에서 유도**한다: 상한 이하이면서 개수를 나누어떨어지게 하는 가장 큰 값.
 * 여덟이면 2·4·8 이 되어 어느 폭에서도 마지막 줄이 꽉 찬다. 나누어떨어지는 값이 없으면
 * (일곱처럼) 상한을 그대로 쓴다 — 그때는 빈칸이 구조적으로 피할 수 없다. */
function evenColumns(count, cap) {
  const n = Math.max(1, Number(count) || 1);
  const top = Math.min(cap, n);
  for (let c = top; c >= 2; c -= 1) if (n % c === 0) return c;
  return top;
}

/** 개수에 맞춰 균형 잡힌 타일 트랙(반만 찬 줄이 없게). */
export function balancedTileTracks(count) {
  return {
    xs: `repeat(${evenColumns(count, 2)}, minmax(0, 1fr))`,
    sm: `repeat(${evenColumns(count, 4)}, minmax(0, 1fr))`,
    xl: `repeat(${evenColumns(count, 8)}, minmax(0, 1fr))`,
  };
}

/* 회의의 짝 판(번다운 | 건강, 업무량 | 범위 변경, 결정 | 할 일).
 *
 * 🔴 오른쪽 트랙에 **바닥**(20rem)이 있다. 예전 `2fr 1fr` 은 1366 폭에서 오른쪽 판을
 * 300px 남짓으로 눌러 건강 게이지가 손톱만 했고, 그 옆의 번다운은 반쯤 비어 있었다.
 * 게이지는 원이라 폭이 곧 크기다 — 바닥을 주면 왼쪽이 그만큼 양보한다. 높이도 함께 올린다
 * (`18rem`): 큰 게이지와 그 아래 진도 막대가 서는 데 12rem 은 모자랐다. */
export const MEETING_PAIR_TRACKS = {
  xs: "1fr",
  lg: "minmax(0, 1.6fr) minmax(20rem, 1fr)",
};
export const PAIR_CHART_MIN_HEIGHT = { lg: "18rem" };

/* px 를 기본 루트(16px)에서 같은 픽셀이 되는 rem 문자열로. */
export function rem(px) {
  return `${px / 16}rem`;
}

/* ── 판의 «높이 예산» ────────────────────────────────────────────────────────
 *
 * 가로 밀도와 같은 이유로 세로도 여기 있다: 예산을 화면 파일에 손으로 적으면 어디를
 * 고쳐야 하는지 아무도 모른다.
 *
 * ## 무엇을 푸는 문제인가
 *
 * 판이 자료 수를 그대로 따라 자란다. 실측(2026-08-26, 1920):
 *
 *   오늘 마감    2건 272px · 30건 440px · **0건 451px**   (0건이 가장 크다)
 *   AI 도우미    오늘 요약 444px · **이번 주 요약 1,318px** (문장 요약 1,200자)
 *   최근 문서    3건 213px · 12건 327px
 *
 * 한 화면 안에서 같은 판이 세 배로 자라면 사용자는 매번 다른 화면을 본다. 아래 오는
 * 것들의 자리도 자료 수에 따라 움직인다.
 *
 * ## 판마다 «예산» 이거나 «계약» 이다
 *
 * 대부분의 판은 **예산**을 갖는다. 바닥과 천장 사이에서 자기 내용만큼 서고, 넘치면 판이
 * 아니라 판 안의 자라는 칸이 굴린다:
 *
 *   min   바닥. 자료가 적거나 없을 때 판이 한 줄로 쪼그라들어 다음 구역이 위로 튀는 것을
 *         막는다. **주요 판에만 준다** — 곁열의 보조 판에 바닥을 주면 짧은 목록 아래에
 *         뜻 없는 빈 자리가 생긴다.
 *   max   천장. 자료가 늘어도 판이 여기서 멈춘다. 넘치는 것은 판이 아니라 **판 안의
 *         자라는 칸**이 맡는다(`ScrollArea`).
 *
 * 값은 실측에서 고른다 — 천장은 「그 판이 담아야 하는 가장 큰 정상 상태」이고, 바닥은
 * 「빈 상태가 차지하는 높이」다.
 *
 * 판 하나는 예산이 아니라 **계약**을 갖는다(`height`). 예산은 「이 범위 안에 있어라」이고
 * 계약은 「언제나 이 높이여라」다. 둘의 차이가 필요한 자리가 실제로 있다 — 사용자가 **칸을
 * 눌러 같은 판의 내용을 갈아 끼우는** 자리(홈의 「오늘 마감」 판독 줄)다. 거기서는 예산이
 * 아무리 좁아도 칸마다 판이 다른 높이로 서고, 그러면 **판 아래에 있는 것이 누를 때마다
 * 위아래로 뛴다.** 근거와 실측은 아래 `today` 항목에 있다.
 *
 * ## 좁은 화면에는 예산을 안 준다
 *
 * 세로로 쌓인 화면에서 판마다 상한을 주면 브라우저 스크롤 안에 스크롤 칸이 서넛 생긴다.
 * 손가락으로 훑다가 그 칸에 들어가면 페이지가 안 움직인다. 좁은 화면에서는 판이 자기
 * 자료만큼 길어지는 것이 자연스러운 세로 흐름이다. 그래서 `lg` 이상에만 건다.
 *
 * ## rem 인 이유
 *
 * `styles/root.css` 의 루트 폰트사이즈 하나가 4K 배율을 맞춘다(16 → 18 → 20px). 예산만
 * px 로 박으면 넓은 화면에서 내용은 커지는데 상자는 그대로라 **없던 스크롤이 생긴다.**
 */
/* ## 천장(계약이면 그 높이)은 **빈 상태를 여유 있게 넘어야 한다**
 *
 * 자라는 칸은 넘치면 굴리면 되지만 **빈 상태는 굴릴 수 없다** — 그림 하나와 두 줄이 통째로
 * 한 덩이라, 위쪽 한계가 그보다 낮으면 그건 예산이 아니라 잘림이다. 그래서 값을 고를 때
 * 마지막 확인은 언제나 「0건이 이 안에 드는가」다. 실측 여유(1200~2560 가운데 가장 좁은 자리):
 *
 *   오늘 마감  0건 483px / 천장 512px — 29px
 *   이번 주    0건 858px / 천장 928px — 70px
 *   최근 문서  0건 336px / 천장 368px — 32px  (1200 에서 레일이 320px 라 문장이 넉 줄이다)
 */
export const PLATE_BUDGET = {
  /* 홈 「오늘 마감」 — 판독 줄의 다섯 칸이 **공유하는 하나의 업무 판**이다.
   *
   * 이 판만 `height` 를 갖는다. 이유는 이 판이 다른 판과 다른 일을 하기 때문이다:
   * 「오늘 마감 · 지연 · 진행 중 · 7일 내 마감 · 막힌 일」은 다섯 개의 판이 아니라 **한
   * 판의 다섯 칸**이고, 사용자는 그 칸을 눌러 가며 같은 자리에서 내용을 갈아 끼운다.
   *
   * 🔴 예산(min 13rem / max 32rem)으로는 그 자리가 안 선다. 실측(2026-08-26 · 1920):
   *
   *     오늘 마감 0건 483 · 지연 3건 250 · 진행 중 30건 512 · 7일 내 마감 1건 164
   *
   * 같은 판이 칸에 따라 164~512px 사이를 오갔다. 「예산을 줬다」와 「높이가 하나다」는
   * 다른 말이고, 사용자가 보는 것은 **칸을 누를 때마다 아래의 AI 도우미가 위아래로 뛰는
   * 화면**이다. 예산을 아무리 좁혀도 이 증상은 안 없어진다 — 범위가 좁아질 뿐이다.
   *
   * 값 하나가 셋을 동시에 만족해야 한다:
   *   ① 0건 빈 상태가 안 잘린다 — 빈 상태는 굴릴 수 없다(1200 에서 483px 로 가장 크다)
   *   ② 다량일 때 목록이 읽을 만큼 보인다 — 한 줄 43px 로 여덟 줄이 든다
   *   ③ 소량일 때 아래가 남는 것은 **받아들인다** — 이 판만은 그렇게 정했다(D-348)
   *
   * 32rem(기본 루트 512px)이 그 셋을 만족하는 가장 낮은 자리다. 4K 에서는 rem 이 루트
   * 폰트사이즈 레버를 함께 타서 2200 에서 576px, 3000 에서 640px 이 된다 — 안의 글자도
   * 같은 비율로 커지므로 화면의 비례가 유지된다. 뷰포트마다 픽셀은 달라도 **한 뷰포트
   * 안에서는 다섯 칸이 언제나 같은 높이**다. */
  today: { height: "32rem" },
  // 홈 곁열 「이번 주」 — 제목과 도넛은 고정이고 아래 두 묶음이 자란다. 바닥은 없다.
  //
  // 50rem 을 먼저 재 봤는데 **평소 상태가 35px 넘쳤다**(세부 457 / 칸 422). 자라지도 않는
  // 내용에 스크롤바가 상시로 서고 「집계 기준」이 접힌 채로 잘렸다. 53rem 도 1200 에서
  // 같은 일이 났다 — 그 폭에서는 레일이 320px 라 도넛과 범례가 세로로 접혀 머리가 58px
  // 더 높다(실측 906px). 천장은 「평소에는 안 닿고, 늘어나면 닿는」 자리여야 한다:
  // 접힌 기술 정보 둘을 펴면 120px 남짓 늘고, 그때 굴린다.
  week: { max: "58rem" },
  // 홈 곁열 「최근 문서」 — 서버가 12줄까지 싣는다. 바닥은 없다(3건짜리 목록이 맞다).
  // 21rem 은 1200 에서 빈 상태와 **0px 차이**로 스쳤다 — 한 줄만 더 꺾여도 잘린다.
  docs: { max: "23rem" },
};

/* AI 도우미의 **세부 콘텐츠 칸** 상한.
 *
 * 이 판만 예산을 판이 아니라 칸에 건다. 탭을 옮길 때 높이가 이어지도록 `useAutoHeight`
 * 가 **안쪽 상자의 높이를 재서** 바깥에 그대로 주는데, 판에 천장을 주면 그 측정과
 * 서로를 밀어낸다(잰 값은 1,020px 인데 판은 704px 이라고 말하는 상태). 자라는 칸이
 * 스스로 멈추면 잰 값이 이미 예산 안이라 둘이 안 싸운다. */
export const AI_DETAIL_MAX = "26rem";

/** 판에 예산(min/max) 또는 계약(height)을 건다. 판 자신이 세로 flex 라야 안쪽 칸이
 * 남는 높이를 받는다.
 *
 * 계약을 가진 판은 **바닥·천장을 같은 값으로 함께** 받는다. 셋이 다 필요하다:
 * `height` 만 주면 세로 flex 안에서 기본 `flex-shrink:1` 이 판을 내용만큼 줄일 수 있고
 * (바닥이 그 줄어듦을 막는다), 바닥만 주면 내용이 넘칠 때 판이 자란다(천장이 막는다).
 * 계약은 «최소» 도 «최대» 도 아니라 «그 높이» 라, 세 값이 한 자리에서 만나야 한다. */
export function plateBudget(name) {
  const budget = PLATE_BUDGET[name];
  if (!budget) throw new Error(`높이 예산에 없는 판: ${name}`);
  const min = budget.height || budget.min;
  const max = budget.height || budget.max;
  return {
    display: "flex", flexDirection: "column",
    ...(budget.height ? { height: { lg: budget.height } } : null),
    ...(min ? { minHeight: { lg: min } } : null),
    ...(max ? { maxHeight: { lg: max } } : null),
  };
}

/** 예산 안에서 **남는 높이를 받는** 칸. 머리와 꼬리 사이에 놓인다. */
export const BUDGET_BODY = { flex: 1, minHeight: 0, display: "flex", flexDirection: "column" };

/** 예산이 모자랄 때 **줄어드는 쪽**. 자라지는 않는다 — 자라면 짧은 목록 아래가 빈다. */
export const BUDGET_SCROLL = { flex: "0 1 auto", minHeight: 0 };

/* 화면에서 그대로 쓰는 값들. sx 에 넣기 좋은 모양으로 미리 만들어 둔다 —
 * 호출부마다 rem() 을 다시 부르면 결국 또 숫자가 흩어진다. */
export const CARD_PADDING = rem(DENSITY_PX.cardPadding);        // 20px
export const TILE_PADDING = rem(DENSITY_PX.healthCardPadding);  // 16px
export const GRID_GAP = rem(DENSITY_PX.gridGap);                // 24px
export const TILE_GRID_GAP = rem(DENSITY_PX.healthGridGap);     // 16px
export const SECTION_GAP = rem(DENSITY_PX.sectionGap);          // 32px

/** 판을 **위아래로만 쌓는 화면**의 판 폭 (2026-09-21).
 *
 * 두 판을 나란히 두지 않고 차례로 읽게 한 화면(조직 정합성 · 초기 설정)에서 판이 본문 폭을 다 쓰면
 * 설명 한 줄이 1,500px 를 달리고, 줄 오른쪽 끝의 값(건수 칩)이 글과 멀어져 어느 줄의 값인지 안 보인다.
 * 세 열짜리 작은 표도 값 셋이 흩어진다. **글에 상한을 걸지 않고 판에 건다** — 판 안에서는 글이 칸을
 * 끝까지 쓰므로 「카드는 넓은데 글만 왼쪽에 붙는」 모양(`theme.js::PROSE_MAX_WIDTH` 주석)이 되지 않는다.
 * 1366 이하는 본문이 이보다 좁아 상한이 안 걸린다. */
export const READ_COLUMN = "min(100%, 70rem)";

/* 좌측 레일 목록 화면의 그리드 한 벌 — `BASELINE_TRACKS.listRail` 의 소비 형태.
 * 값 조정은 여기(트랙)와 위(트랙 주석) 한 곳에서만 한다. */
export const LIST_RAIL_GRID = {
  display: "grid",
  alignItems: "start",
  gap: GRID_GAP,
  gridTemplateColumns: { xs: "1fr", lg: BASELINE_TRACKS.listRail },
};

/** 칸반 레인·논의 목록 등 **캔버스 위의 함몰 구역**. 카드(plate)가 그 위에 선다. */
export const LANE_SURFACE = {
  bgcolor: "background.inset",
  border: 1,
  borderColor: "divider",
  borderRadius: rem(8),
};

/** 차트·건강 등 **판 위의 위젯 상자**. KPI 타일과 같은 계층이다. */
export const PANEL_SURFACE = {
  bgcolor: "background.plate",
  border: 1,
  borderColor: "divider",
  borderRadius: rem(8),
  p: TILE_PADDING,
};

/* ── 설정성 화면의 판 2열 (D-457) ─────────────────────────────────────────
 *
 * `/profile` 이 먼저 만든 `twoCol(weight)` 를 여기로 올린다 — 관리자 설정 4탭이 같은 격자를
 * 쓴다. 가중치는 줄마다 선언한다(`1fr 1fr` 금지 — D-333: 폭을 요구하는 쪽이 더 받는다).
 * `lg` 미만에서는 한 열이다. 바닥 정렬(`stretch`)이 같은 줄의 판 높이를 맞춘다. */
export function pairTracks(weight) {
  return {
    display: "grid", gap: GRID_GAP, alignItems: "stretch",
    gridTemplateColumns: { xs: "minmax(0, 1fr)", lg: weight },
  };
}

/* ── 내용 폭 짝 트랙 — 주 판 + 보조 레일 (UI 3차 · 조합 계약 C-5) ──────────────────────────────────
 *
 * `pairTracks` 는 **뷰포트** `lg`(1200)에서 2열로 선다. 주 판 + 보조 레일 화면(새 티켓 · LLM 콘솔 · 오프보딩 · 초기 설정)
 * 에서는 그 문턱이 틀렸다: 1200 뷰포트의 본문 칸은 사이드바를 빼면 59.5rem 인데 2열로 서서 폼이 1칸 8줄로 좁고 레일
 * 아래가 비었다. 2열은 **본문이 받은 폭**이 정한다 — 본문 칸 64rem 이상이면 2열(1366 → 69.9rem), 아니면 1열이고 레일은
 * 폼 아래로 간다. 사이드바를 접으면 같은 뷰포트에서도 본문 폭을 따라 2열이 된다.
 *
 * 🔴 `pairTracks` 자체는 바꾸지 않는다 — 소비처 일곱 중 내 프로필(보호 화면)이 뷰포트 문턱에 레이아웃을 걸고 있다.
 *
 * 쓰는 법: 컨테이너 상자(`CONTENT_PAIR_CONTAINER`) 안에 격자(`contentPairTracks(weight)`)를 둔다 — 컨테이너 질의는
 * 자기 자신이 아니라 조상의 폭을 본다. 1열에서도 두 판은 같은 격자의 두 줄이다(바닥 정렬 규칙 그대로). */
export const CONTENT_PAIR_MIN_REM = 64;
export const CONTENT_PAIR_CONTAINER = { containerType: "inline-size", containerName: "content-pair" };
export function contentPairTracks(weight) {
  return {
    display: "grid", gap: GRID_GAP, alignItems: "stretch",
    gridTemplateColumns: "minmax(0, 1fr)",
    [`@container content-pair (min-width: ${CONTENT_PAIR_MIN_REM}rem)`]: { gridTemplateColumns: weight },
  };
}

/* ── 화면 아래까지 서는 판의 높이 (UI 3차 · 조합 계약 C-5 · C-6) ─────────────────────────────────────
 *
 * 새 티켓의 두 판과 채팅방 판은 화면 아래까지 선다 — 짧은 폼 · 짧은 대화에서 판이 내용만큼만 서면 판 아래 캔버스가 비고
 * 판 발이 화면 가운데 떠 보였다. 값은 뷰포트 높이에서 판 윗변(상단바 + 본문 열 위 여백 + 설명 없는 페이지 머리 = 161px)과
 * 본문 열 아래 여백(32px)을 뺀 것이다 — 193px ≈ 12rem. 채팅방이 먼저 쓰던 13rem 은 판 아래 캔버스가 47px 비었다(1920 실측
 * `page_fill`, 허용 40). 부르는 쪽은 넓은 화면(`md` 이상)에서만 건다 — 좁은 화면은 판이 쌓여 흐른다.
 * 새 티켓은 이 값을 **바닥**(`minHeight`, `data-page-fill="grow"`)으로 쓴다 — 폼이 더 길면 판이 자라고 페이지가 굴러가며, 판 발이 따라온다. */
export const PAGE_FILL_HEIGHT = "calc(100vh - 12rem)";

/* ── 폼 필드 격자 (D-458) — `/new-ticket` 의 것과 같은 값 ──────────────────
 *
 * 칸이 16rem 보다 좁아지면 값이 잘리기 시작한다. 컨테이너 질의라 폼 판이 레일 옆에서 좁아지면
 * 열 수도 따라 준다(뷰포트가 아니라 칸이 정한다). 소비처는 `FORM_FIELD_CONTAINER` 상자 안에
 * 이 격자를 둔다. 3열에서 멈춘다 — 짧은 입력 여섯이 한 줄에 몰리면 라벨을 훑기 어렵다. */
const FORM_FIELD_MIN_REM = 16;
const FORM_FIELD_GAP_REM = 1.25;
const formFieldsFit = (n) =>
  `@container form-fields (min-width: ${n * FORM_FIELD_MIN_REM + (n - 1) * FORM_FIELD_GAP_REM}rem)`;
export const FORM_FIELD_CONTAINER = { containerType: "inline-size", containerName: "form-fields" };
export const FORM_FIELD_GRID = {
  display: "grid",
  gap: `${FORM_FIELD_GAP_REM}rem`,
  gridTemplateColumns: "minmax(0, 1fr)",
  [formFieldsFit(2)]: { gridTemplateColumns: "repeat(2, minmax(0, 1fr))" },
  [formFieldsFit(3)]: { gridTemplateColumns: "repeat(3, minmax(0, 1fr))" },
};

/* ── 12칸 폼 격자 (핸드오프 RULES §7 · README §A) ──────────────────────────────
 *
 * 관련 필드를 한 줄에 세운다(제목 12 / 프로젝트 6 · 상태 3 · 우선순위 3 / …). 열 수는 뷰포트가
 * 아니라 **폼이 받은 칸의 폭**이 정한다 — 위 `FORM_FIELD_GRID` 와 같은 컨테이너 질의 문턱이다:
 * 칸 셋이 들어가면 12칸, 둘이면 2칸, 그보다 좁으면 1칸.
 *
 * 🔴 **데스크톱 span 을 2칸 격자에 그대로 쓰지 않는다.** `span 6` 을 2칸 격자에 주면 암묵 열이
 * 생겨 칸이 화면 밖으로 밀린다. 그래서 칸마다 `fieldSpan({ wide, mid })` 로 문턱별 span 을 따로
 * 말한다 — 좁은 1칸에서는 언제나 `span 1` 이다. */
export const FORM_FIELD_GRID_12 = {
  display: "grid",
  gap: `${FORM_FIELD_GAP_REM}rem`,
  alignItems: "start",
  gridTemplateColumns: "minmax(0, 1fr)",
  [formFieldsFit(2)]: { gridTemplateColumns: "repeat(2, minmax(0, 1fr))" },
  [formFieldsFit(3)]: { gridTemplateColumns: "repeat(12, minmax(0, 1fr))" },
};

/** 12칸 격자의 칸 하나가 문턱마다 몇 칸을 쓰는가. `wide` 는 12칸일 때, `mid` 는 2칸일 때(1 또는 2). */
export function fieldSpan({ wide = 12, mid = 2 } = {}) {
  return {
    gridColumn: "span 1",
    [formFieldsFit(2)]: { gridColumn: `span ${Math.max(1, Math.min(2, mid))}` },
    [formFieldsFit(3)]: { gridColumn: `span ${Math.max(1, Math.min(12, wide))}` },
  };
}
