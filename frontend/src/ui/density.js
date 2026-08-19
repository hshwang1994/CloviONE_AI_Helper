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
  cardPadding: 24,      // 판(plate) 안쪽 여백
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
  // 폼 + 보조 레일(새 티켓 등)
  two: "minmax(0, 1.45fr) minmax(280px, 0.8fr)",
  // 지표 한 줄
  kpi: "repeat(4, minmax(0, 1fr))",
  three: "repeat(3, minmax(0, 1fr))",
  // 작은 상태 타일 한 줄
  health: "repeat(5, minmax(0, 1fr))",
};

/* px 를 기본 루트(16px)에서 같은 픽셀이 되는 rem 문자열로. */
export function rem(px) {
  return `${px / 16}rem`;
}

/* 화면에서 그대로 쓰는 값들. sx 에 넣기 좋은 모양으로 미리 만들어 둔다 —
 * 호출부마다 rem() 을 다시 부르면 결국 또 숫자가 흩어진다. */
export const CARD_PADDING = rem(DENSITY_PX.cardPadding);        // 24px
export const TILE_PADDING = rem(DENSITY_PX.healthCardPadding);  // 16px
export const GRID_GAP = rem(DENSITY_PX.gridGap);                // 24px
export const TILE_GRID_GAP = rem(DENSITY_PX.healthGridGap);     // 16px
export const SECTION_GAP = rem(DENSITY_PX.sectionGap);          // 32px
