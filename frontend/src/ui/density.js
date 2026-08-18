/* 밀도 치수 — 판·타일·격자 간격의 단일 출처.
 *
 * 원래는 폐기한 목업에서 뽑은 값이었다(지시 64). 지금은 이 파일이 스스로 정본이고,
 * 계약은 `density-contract.test.jsx` 가 성질(왼쪽 쏠림 방지·빈 칸 없음·상대 밀도)로 지킨다.
 *
 * ## 왜 이 파일이 있나
 *
 * 카드 패딩·격자 열·간격이 화면 파일 스무 곳에 손으로 흩어져 있었다. 그래서 기준선과
 * 어긋나도 **어디를 고쳐야 하는지 아무도 몰랐고**, 실제로 사용자가 배포 화면을 보고
 * "설계한 대로 된 게 하나도 없다"고 했다. 값을 여기 한 곳에만 두고, 검사
 * (`density.test.jsx`)가 **기준선 HTML 을 직접 열어** 이 숫자와 대조한다.
 * 손으로 적은 값이 슬며시 바뀌면 그 검사가 잡는다.
 *
 * ## px 를 rem 으로 바꿔 내보내는 이유
 *
 * 이 앱은 `styles/root.css` 의 루트 폰트사이즈 하나로 4K 배율을 맞춘다(16 → 18 → 20px).
 * px 로 박으면 그 조각만 4K 에서 혼자 작게 남는다. 기본 루트(16px)에서는 기준선과
 * **정확히 같은 픽셀**이 되고, 큰 화면에서는 다른 요소와 같은 비율로 커진다.
 *
 * ## 기준선에 있는 값만 적는다
 *
 * 기준선에 없는 치수는 여기 넣지 않는다. 지어낸 숫자가 이 파일에 들어오는 순간
 * "기준선에서 왔다"는 이 파일의 유일한 존재 이유가 사라진다.
 */

/* 기준선 원본 px. 검사가 기준선 HTML 에서 읽은 값과 그대로 비교하는 대상이다.
 * 각 항목의 주석은 기준선 파일의 **선택자**다 — 검사가 그 선택자로 파일을 찾아간다. */
export const BASELINE_PX = {
  cardPadding: 20,         // .card.pad  padding: 20px
  detailBlockPadding: 20,  // .detail-block padding: 20px
  kpiPaddingY: 17,         // .kpi-card  padding: 17px 18px
  kpiPaddingX: 18,         // .kpi-card  padding: 17px 18px
  kpiValueFontSize: 30,    // .kpi-value font-size: 30px
  kpiLabelFontSize: 12,    // .kpi-label font-size: 12px
  healthCardPadding: 16,   // .health-card padding: 16px
  gridGap: 16,             // .grid      gap: 16px
  healthGridGap: 12,       // .admin-health gap: 12px
  sectionGap: 24,          // .section   margin-top: 24px
  cardHeadGap: 14,         // .card-head margin-bottom: 14px
  topbarHeight: 64,        // :root      --topbar-h: 64px
  sidebarWidth: 264,       // :root      --sidebar-w: 264px
};

/* 기준선의 본문 열은 **폭을 남기지 않는다.**
 *
 * 파일 앞쪽(§.content)에는 `width: min(1720px, 100%)` 가 있지만, 뒤쪽 최종 절
 * ("2026-07-31 final responsive containment")이 `.topbar, .layout, .main, .content
 * { width:100%; max-width:100% }` 로 **덮어쓴다**. CSS 는 뒤가 이기므로 기준선이 실제로
 * 그리는 본문 열은 화면 폭 전체다. 앞쪽 1720 만 보고 "기준선은 1720 에서 멈춘다"고 적으면
 * 틀린다 — 검사가 마지막 선언을 읽는 이유가 이것이다.
 *
 * 우리 앱의 `CONTENT_MAX_WIDTH`(theme.js)는 4K 를 위해 브레이크포인트별 상한을 둔다.
 * 1920·2560 에서는 그 상한이 사이드바를 뺀 폭보다 커서 **실제로는 꽉 찬다** — 그래서
 * 사용자가 본 왼쪽 쏠림의 원인이 아니다(원인은 화면 안쪽 격자다). 3840 에서만 상한이
 * 실제로 걸린다. 그 값을 기준선처럼 풀 것인지는 사용자에게 물을 일이라 여기서 바꾸지 않는다. */
export const BASELINE_CONTENT_FILLS = true;

/* .content padding: 28px clamp(18px, 3vw, 42px) 80px */
export const BASELINE_CONTENT_PADDING_PX = { top: 28, xMin: 18, xMax: 42, bottom: 80 };

/* 기준선의 격자 트랙. 문자열 그대로 CSS 에 넣는다 — 옮겨 적으면서 숫자가 바뀌는 것이
 * 지금까지 어긋남의 절반이었다.
 *
 * ⚠️ **세 트랙 모두 `fr` 이 하나 이상 들어 있다.** 이게 이 파일에서 가장 중요한 성질이다.
 * `minmax(0, 78ch) minmax(18rem, 26rem)` 처럼 트랙의 상한이 전부 고정값이면, 격자는
 * 컨테이너가 아무리 넓어도 그 합만큼만 차지하고 **남는 폭을 오른쪽에 빈 채로 남긴다**.
 * 사용자가 "왼쪽으로 쏠려있다, 페이지 전체에 정보가 담기는 게 아니라" 고 한 것이 그것이다.
 * `mx:"auto"` 는 이 증상을 못 고친다 — 가운데로 옮길 뿐 폭을 채우지는 않는다. */
export const BASELINE_TRACKS = {
  // .ticket-layout — 티켓·문서 상세(본문 + 속성 레일)
  detail: "minmax(0, 1.5fr) minmax(300px, 0.65fr)",
  // .grid.two — 폼 + 보조 레일(새 티켓 등)
  two: "minmax(0, 1.45fr) minmax(280px, 0.8fr)",
  // .grid.kpi — 지표 카드 한 줄
  kpi: "repeat(4, minmax(0, 1fr))",
  // .grid.three
  three: "repeat(3, minmax(0, 1fr))",
  // .admin-health — 작은 상태 타일 한 줄
  health: "repeat(5, minmax(0, 1fr))",
};

/* 기준선 px 를 기본 루트(16px)에서 같은 픽셀이 되는 rem 문자열로. */
export function rem(px) {
  return `${px / 16}rem`;
}

/* 화면에서 그대로 쓰는 값들. sx 에 넣기 좋은 모양으로 미리 만들어 둔다 —
 * 호출부마다 rem() 을 다시 부르면 결국 또 숫자가 흩어진다. */
export const CARD_PADDING = rem(BASELINE_PX.cardPadding);                 // 20px
export const TILE_PADDING = rem(BASELINE_PX.healthCardPadding);           // 16px
export const GRID_GAP = rem(BASELINE_PX.gridGap);                         // 16px
export const TILE_GRID_GAP = rem(BASELINE_PX.healthGridGap);              // 12px
export const SECTION_GAP = rem(BASELINE_PX.sectionGap);                   // 24px
export const CARD_HEAD_GAP = rem(BASELINE_PX.cardHeadGap);                // 14px

/* 개수가 정해진 카드 줄의 열 수를 고를 때 쓴다.
 *
 * 왜 필요한가 — 홈의 지표 줄은 카드가 6장인데 열 수가 4(xl)·5(xxl)였다. 그러면 마지막
 * 줄에 2장·1장만 남고 오른쪽이 빈 칸으로 뜬다. 줄이 하나 더 생기니 격자 높이는 두 배가
 * 되고("그리드 높이가 너무 크다"), 그 마지막 줄은 왼쪽으로 쏠려 보인다.
 * 기준선 `.grid.kpi` 는 카드 4장을 4열에 넣어 **한 줄**로 끝낸다 — 열 수가 카드 수를
 * 나누어떨어지게 고르는 것이 그 규칙이다. */
export function fitsWithoutOrphan(columns, cardCount) {
  return cardCount % columns === 0;
}
