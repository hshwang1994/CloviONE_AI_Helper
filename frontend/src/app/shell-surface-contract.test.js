import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/* 셸 위 컨트롤은 **셸의 재료**로 그린다 — 캔버스 토큰으로 되돌아가면 여기서 걸린다.
 *
 * ## 이 시험이 막는 것
 *
 * 이 저장소는 같은 결함을 **세 번** 겪었고 매번 다른 얼굴이었다.
 *
 *   1차 (WF7) 상단바가 딥 인디고 그라디언트라는 전제로 `rgba(0,0,0,.15)` 알약 리터럴.
 *             chrome 이 밝아지자 밝은 바탕 위 검은 알약이 됐다.
 *   2차 (D-141) 그래서 값을 캔버스 토큰(`background.plate`)으로 옮겼다. 그때는 맞았다.
 *   3차 (D-179) chrome 이 다시 인디고가 되자 같은 값이 **하우징에 뚫린 순백 구멍**이 됐다.
 *             독립 리뷰가 배포본 픽셀에서 잡았다 — 상단바 검색 675px(뷰포트의 35%),
 *             사이드바 '메뉴 찾기', 클로비 알약, 아바타 원. 라이트에서 셸 대비 14.13:1 로
 *             화면에서 가장 밝은 면이었고, 다크에서는 반대로 1.12:1 로 묻혔다
 *             (F-W1R-01 · F-W1R-13 · F-W1R-32).
 *
 * 세 번 다 **대비 위반이 아니었다** — 그래서 대비 단언이 전부 초록인 채로 지나갔다.
 * 문제는 위계다: 컨트롤이 자기가 앉은 면과 다른 계열의 색을 골랐다. 그래서 이 시험은
 * 비율이 아니라 **어느 토큰 계열을 쓰는가**를 본다.
 *
 * ## 왜 소스를 읽는가
 *
 * jsdom 은 레이아웃도 합성도 하지 않으므로 "이 면이 저 면보다 밝다"를 렌더로 물을 수 없다.
 * 실제 밝기 판정은 브라우저 하네스(`scripts/ui_qa` 의 `brand_role_coverage`·`contrast`)가
 * 맡고, 여기서는 **되돌림 자체**를 막는다. 두 층이 같은 결함의 서로 다른 절반을 지킨다.
 * (같은 발상: `usermenu-topbar-contrast.test.js`, `scripts/check_brand_tokens.py`.)
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const read = (rel) => readFileSync(path.join(HERE, rel), "utf-8");

/** 주석을 걷어낸 소스. 주석 안의 "왜 바꿨는지" 설명까지 잡으면 그 설명을 지우는 것이
 *  시험을 통과시키는 길이 되고, 그러면 다음 사람이 같은 리터럴을 되돌린다. */
function code(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

function between(src, startNeedle, endNeedle) {
  const start = src.indexOf(startNeedle);
  expect(start, `블록 시작을 못 찾았다: ${startNeedle}`).toBeGreaterThan(-1);
  const end = src.indexOf(endNeedle, start + startNeedle.length);
  expect(end, `블록 끝을 못 찾았다: ${endNeedle}`).toBeGreaterThan(-1);
  return src.slice(start, end);
}

const APP_SHELL = code(read("./AppShell.jsx"));
const TOP_SEARCH = code(read("./TopSearch.jsx"));
const MASCOT = code(read("../ui/Mascot.jsx"));
const USER_MENU = code(read("./UserMenu.jsx"));

/* 캔버스 계열 = 본문이 사는 면과 잉크. 셸 위에서는 이것들이 곧 결함이다.
 *
 * **철자 두 갈래를 다 잡아야 한다.** 처음 쓴 정규식은 문자열 토큰(`bgcolor: "background.plate"`)
 * 만 봤는데, 정작 W2 는 이 컨트롤들을 콜백 철자(`bgcolor: t.palette.chrome.track`)로 옮겨
 * 놓았다 — 즉 **되돌림을 콜백으로 하면 이 파일의 단언이 전부 초록**이었다. 독립 검수자가 실제로
 * 두 파일을 되돌려 보고 그 사실을 실증했다(69 tests PASS). "지킨다고 선언했는데 실제로는 안
 * 지키는 시험" 은 이 저장소가 반복해 겪은 실패 그 자체라, 여기서 두 철자를 모두 막고 아래
 * «되돌림 철자» 절이 그 정규식이 다시 좁아지는 것까지 막는다. 렌더 후 **실제 색**은
 * `topbar-contract.test.jsx` 가 네 컨트롤 전부에 대해 확인한다 — 소스와 화면 두 층이다. */
const CANVAS_PATH = '("|t\\.palette\\.|theme\\.palette\\.)?';
const CANVAS_SURFACE = new RegExp(
  `(bgcolor|backgroundColor|background)\\s*:\\s*${CANVAS_PATH}background\\.(plate|inset|canvas|paper|sunken|brandTint)\\b`,
);
const CANVAS_INK = new RegExp(
  `\\bcolor\\s*:\\s*${CANVAS_PATH}text\\.(primary|secondary|faint)\\b`,
);
/* chrome 계열 = 셸이 자기 위 컨트롤을 위해 들고 있는 반전 토큰. `sidebar.*` 는 같은 값의
   별칭이다(theme.js: `sidebar.track === chrome.track`) — 이름 두 개를 다 인정한다. */
const CHROME_TOKEN = /\b(chrome|sidebar)\.(track|trackSelected|edge|onShell|onShellMuted|onShellFaint|text|muted|faint|line|focusRing)\b/;

/* 이 시험이 **자기가 막겠다고 한 것을 실제로 막는가**. 정규식을 눈으로 확인하는 대신 되돌림
   철자를 직접 먹여 본다 — 정규식이 다시 좁아지면 대상 파일이 아니라 여기가 먼저 빨개진다. */
const REGRESSION_SPELLINGS = [
  'bgcolor: "background.plate"',
  "bgcolor: t.palette.background.plate",
  "backgroundColor: theme.palette.background.inset",
  'color: "text.primary"',
  "color: t.palette.text.secondary",
  "color: theme.palette.text.faint",
];
/* 반대 방향의 오탐도 막는다 — chrome 토큰을 캔버스로 오인하면 이 시험은 곧 꺼진다. */
const CHROME_SPELLINGS = [
  "bgcolor: t.palette.chrome.track",
  'color: "sidebar.text"',
  "borderColor: t.palette.chrome.edge",
  'bgcolor: "sidebar.track"',
];

const CHROME_MOUNTED = [
  ["상단바 검색 (TopSearch)", TOP_SEARCH],
  [
    "사이드바 '메뉴 찾기' 입력 (AppShell)",
    between(APP_SHELL, 'placeholder="메뉴 찾기"', "</Box>"),
  ],
  [
    "상단바 클로비 버튼 (Mascot::MascotTopButton)",
    between(MASCOT, "export function MascotTopButton", "</Tooltip>"),
  ],
  ["계정 버튼·아바타 (UserMenu)", between(USER_MENU, "<Button", "</Button>")],
];

describe("되돌림 철자 — 이 시험이 자기가 막겠다고 한 것을 실제로 잡는가", () => {
  it.each(REGRESSION_SPELLINGS)("«%s» 를 캔버스 복귀로 인식한다", (spelling) => {
    expect(
      CANVAS_SURFACE.test(spelling) || CANVAS_INK.test(spelling),
      `이 철자를 못 잡으면 그 철자로 되돌리는 것을 아무도 못 막는다: ${spelling}`,
    ).toBe(true);
  });

  it.each(CHROME_SPELLINGS)("«%s» 는 캔버스로 오인하지 않는다 (위양성 금지)", (spelling) => {
    expect(CANVAS_SURFACE.test(spelling), spelling).toBe(false);
    expect(CANVAS_INK.test(spelling), spelling).toBe(false);
  });
});

describe("셸 위 컨트롤은 캔버스 토큰을 쓰지 않는다", () => {
  it.each(CHROME_MOUNTED)("%s — 캔버스 면 토큰이 없다", (_label, block) => {
    expect(block).not.toMatch(CANVAS_SURFACE);
  });

  it.each(CHROME_MOUNTED)("%s — 캔버스 잉크 토큰이 없다", (_label, block) => {
    expect(block).not.toMatch(CANVAS_INK);
  });

  it.each(CHROME_MOUNTED)("%s — chrome 반전 토큰을 실제로 쓴다", (_label, block) => {
    expect(block).toMatch(CHROME_TOKEN);
  });

  it.each(CHROME_MOUNTED)("%s — 색 리터럴을 다시 박지 않는다", (_label, block) => {
    // 1차 결함의 형태. 리터럴은 배경이 바뀌어도 안 따라온다.
    expect(block).not.toMatch(/(bgcolor|backgroundColor|color|borderColor)\s*:\s*["'`]?(#[0-9a-fA-F]{3,8}|rgba?\()/);
  });
});

/* ── 선언했는데 안 그려지는 테두리 ────────────────────────────────────────────
 *
 * MUI 의 border 스타일 함수(`@mui/system` borders.js)가 펴 주는 이름은
 * `border`/`borderTop|Right|Bottom|Left` **뿐**이다. `borderInlineStart: 2` 같은 논리 속성
 * shorthand 는 그대로 통과해 `border-inline-start: 2px` 가 되고, `border-*-style` 이 없으니
 * CSS 기본값 `none` 이라 **한 픽셀도 안 그려진다.** 이 저장소는 이 함정을 셸에서 두 번
 * 밟았다 — 사이드바 바깥 모서리(배포본 실측: 선 없음)와 팔레트 선택 레일(선택 신호가
 * 워시 하나로 남음). 둘 다 "선언은 있는데 화면에는 없다" 라 눈으로 코드를 읽으면 통과한다. */
const LOGICAL_BORDER_SHORTHAND = /border(Inline|Block)(Start|End)?\s*:\s*[0-9]/;

describe("논리 속성 테두리는 shorthand 로 적지 않는다 (MUI 가 안 펴서 안 그려진다)", () => {
  it.each([
    ["AppShell", APP_SHELL],
    ["TopSearch", TOP_SEARCH],
    ["CommandPalette", code(read("./CommandPalette.jsx"))],
  ])("%s — borderInline*: <숫자> 가 없다", (_label, src) => {
    expect(src).not.toMatch(LOGICAL_BORDER_SHORTHAND);
  });

  it("사이드바 바깥 모서리가 **그려지는 형태**로 선언돼 있다", () => {
    expect(APP_SHELL).toMatch(/borderInlineEndStyle:\s*"solid"/);
    expect(APP_SHELL).toMatch(/borderInlineEndColor/);
  });
});

/* ── Gradient 3종의 소비처 (F-W1R-39) ──────────────────────────────────────
 *
 * W1 은 `chrome.shellImage`·`chrome.aiWash`·`chrome.shellTop` 을 만들고 대비 시험까지
 * 붙였지만 **제품이 그 토큰을 아무도 읽지 않았다** — 시험은 토큰끼리만 비교하므로 초록인
 * 채로 화면은 계약 밖에 있었다. `check_brand_tokens.py` 가 `palette.brand` 에 대해 막는
 * 실패 모드("정의했는데 소비처 0")를 chrome Gradient 에 대해서도 막는다. */
describe("chrome Gradient 3종은 소비처를 갖는다", () => {
  it("사이드바가 `chrome.shellImage` 를 background-image 로 읽는다", () => {
    expect(APP_SHELL).toMatch(/backgroundImage:\s*\(t\)\s*=>\s*t\.palette\.chrome\.shellImage/);
  });

  it("상단바 채움이 `chrome.shellTop`(Gradient 첫 stop)이다", () => {
    expect(APP_SHELL).toMatch(/background:\s*t\.palette\.chrome\.shellTop/);
    // 옛 값으로 되돌리면(= 한 stop 어긋난 상태) 여기서 걸린다.
    expect(APP_SHELL).not.toMatch(/background:\s*t\.palette\.sidebar\.bg/);
  });

  it("`chrome.aiWash` 가 상단바 전체가 아니라 우상단 앵커에만 있다", () => {
    const anchor = between(APP_SHELL, 'data-shell-region="ai"', "</Box>");
    expect(anchor).toMatch(/backgroundImage:\s*t\.palette\.chrome\.aiWash/);
    /* 전폭에 깔면 검색 inset 의 `onShellMuted` 가 워시 안으로 들어가고, 그 합성 대비는
       dark 에서 4.36:1 로 AA 아래다(theme.js §CHROME 실측). AppBar 자신은 워시를 갖지
       않아야 한다 — 앵커 블록 앞쪽(AppBar sx)에 aiWash 가 나오면 실패. */
    const beforeAnchor = APP_SHELL.slice(0, APP_SHELL.indexOf('data-shell-region="ai"'));
    expect(beforeAnchor).not.toMatch(/aiWash/);
  });

  it("AI 앵커 안의 잉크는 `onShell` 하나다 (Wash 위 잉크 하드 룰, D-179)", () => {
    const anchor = between(APP_SHELL, 'data-shell-region="ai"', "</Box>");
    expect(anchor).toMatch(/color:\s*t\.palette\.chrome\.onShell\b/);
    expect(anchor).not.toMatch(/onShellMuted|onShellFaint/);
  });
});
