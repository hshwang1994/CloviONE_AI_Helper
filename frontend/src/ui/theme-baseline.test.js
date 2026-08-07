/* theme.js 가 기준선 미리보기의 토큰을 그대로 쓰는가.
 *
 * ## 왜 이 검사가 필요했나
 *
 * `design/baseline/preview-standalone.html` 이 설계 정본인데, 여러 세션 동안 그 파일을 열지
 * 않고 "토큰이 같아 보인다"는 눈대중으로 넘어갔다. 배포된 화면을 본 사용자의 지적은
 * "설계한 대로 된 게 하나도 없다" 였고 실제로 페이지 배경(#F3F6FF vs #f5f7fc), 본문색,
 * 테두리색, 표 머리 배경이 전부 달랐다.
 *
 * ## 왜 상수를 여기 적지 않는가
 *
 * 기준선 값을 이 파일에 손으로 옮겨 적으면, 옮긴 값과 theme.js 가 **같이** 틀렸을 때
 * 통과한다. 그래서 이 파일에는 색·크기 리터럴이 없다. 전부 baselineTokens.js 가 기준선
 * HTML 을 파싱해서 만든 값이고, 기준선 파일이 바뀌면 기대값도 같이 움직인다.
 */

import { describe, expect, it } from "vitest";

import { baseline, baselineScope, lastDeclaration } from "./baselineTokens.js";
import { createClovirTheme, DEFAULT_ACCENT, RADIUS } from "./theme.js";

const { rules } = baseline();
const tokensFor = (mode) => baselineScope(rules, { mode, accent: DEFAULT_ACCENT });

/* 색 문자열 비교용 정규화. 기준선은 `rgba(19, 28, 56, .08)`, 테마는 `rgba(19,28,56,.08)`
 * 처럼 공백만 다르게 쓸 수 있고 16진수 대소문자도 섞여 있다. 값이 같은지만 본다. */
const norm = (value) => String(value).trim().toLowerCase().replace(/\s+/g, "");

const px = (value) => Number.parseFloat(String(value));
/* MUI 타이포는 rem, 기준선은 px 다. 루트 폰트사이즈 16px 기준으로 맞춰 본다
 * (styles/root.css 의 미디어쿼리가 이 기본값을 화면 폭에 따라 키운다). */
const remToPx = (value) => px(value) * 16;

/* 기준선 CSS 변수 → theme.palette 경로. 왼쪽은 기준선 파일이 정하고, 오른쪽은 우리가
 * 어디에 담기로 했는지다. 이름은 바꾸지 않는다 - 화면 코드가 이 경로를 참조한다. */
const PALETTE_MAP = [
  ["--bg", (p) => p.background.default],
  ["--surface", (p) => p.background.paper],
  ["--surface-2", (p) => p.background.surface2],
  ["--surface-3", (p) => p.background.surface3],
  ["--text", (p) => p.text.primary],
  ["--muted", (p) => p.text.secondary],
  ["--border", (p) => p.divider],
  ["--border-strong", (p) => p.dividerStrong],
  ["--primary", (p) => p.primary.main],
  ["--primary-strong", (p) => p.primary.dark],
  ["--primary-soft", (p) => p.primary.soft],
  ["--accent", (p) => p.secondary.main],
  ["--cyan", (p) => p.cyan],
  ["--success", (p) => p.success.main],
  ["--success-bg", (p) => p.success.bg],
  ["--warning", (p) => p.warning.main],
  ["--warning-bg", (p) => p.warning.bg],
  ["--danger", (p) => p.error.main],
  ["--danger-bg", (p) => p.error.bg],
  ["--info", (p) => p.info.main],
  ["--info-bg", (p) => p.info.bg],
  ["--sidebar", (p) => p.sidebar.bg],
  ["--sidebar-text", (p) => p.sidebar.text],
  ["--sidebar-muted", (p) => p.sidebar.muted],
  ["--sidebar-hover", (p) => p.sidebar.hover],
  ["--brand-accent", (p) => p.brand.accent],
  ["--brand-deep", (p) => p.brand.deep],
  ["--brand-mid", (p) => p.brand.mid],
  ["--brand-purple", (p) => p.brand.purple],
  ["--brand-mint", (p) => p.brand.mint],
];

const SHADOW_MAP = [
  ["--shadow-sm", (s) => s.sm],
  ["--shadow-md", (s) => s.md],
  ["--shadow-lg", (s) => s.lg],
];

describe.each(["light", "dark"])("%s 모드", (mode) => {
  const tokens = tokensFor(mode);
  const theme = createClovirTheme(mode);

  it.each(PALETTE_MAP)("팔레트 %s", (name, pick) => {
    expect(tokens[name], `기준선에 ${name} 이 없다`).toBeTruthy();
    expect(norm(pick(theme.palette))).toBe(norm(tokens[name]));
  });

  it.each(SHADOW_MAP)("그림자 %s", (name, pick) => {
    expect(norm(pick(theme.shadowTokens))).toBe(norm(tokens[name]));
  });

  it("표면이 하나가 아니다 - surface/surface-2/surface-3 이 서로 다른 색이다", () => {
    const { paper, surface2, surface3 } = theme.palette.background;
    expect(new Set([norm(paper), norm(surface2), norm(surface3)]).size).toBe(3);
  });
});

describe("반지름", () => {
  const tokens = tokensFor("light");
  const theme = createClovirTheme("light");

  it.each([
    ["--radius-sm", () => RADIUS.sm],
    ["--radius-md", () => RADIUS.md],
    ["--radius-lg", () => RADIUS.lg],
  ])("%s", (name, pick) => {
    expect(pick()).toBe(px(tokens[name]));
  });

  it("MUI 기본 반지름은 기준선의 --radius-md 다", () => {
    expect(theme.shape.borderRadius).toBe(px(tokens["--radius-md"]));
  });
});

describe("컴포넌트가 기준선과 같은 표면·모서리·그림자를 쓴다", () => {
  const tokens = tokensFor("light");
  const theme = createClovirTheme("light");
  /* 기준선 규칙에서 값을 읽어 온다. `.card { background: var(--surface) }` 처럼
   * 변수 이름 자체가 적혀 있으므로, 어느 표면을 쓰는지를 파일이 알려 준다. */
  const cardBg = lastDeclaration(rules, ".card", "background");
  const cardRadius = lastDeclaration(rules, ".card", "border-radius");
  const cardShadow = lastDeclaration(rules, ".card", "box-shadow");
  const headBg = lastDeclaration(rules, "th", "background");
  const btnRadius = lastDeclaration(rules, ".btn", "border-radius");
  const btnHeight = lastDeclaration(rules, ".btn", "min-height");
  const fieldRadius = lastDeclaration(rules, ".field", "border-radius");

  const resolve = (declaration) => tokens[/var\((--[\w-]+)\)/.exec(declaration)?.[1]] ?? declaration;

  const card = theme.components.MuiCard.styleOverrides.root({ theme });
  const tableHead = theme.components.MuiTableCell.styleOverrides.head({ theme });

  it("카드 배경은 기준선의 .card 배경과 같다", () => {
    expect(norm(theme.palette.background.paper)).toBe(norm(resolve(cardBg)));
  });

  it("카드 모서리·그림자는 기준선의 .card 와 같다", () => {
    expect(card.borderRadius).toBe(px(resolve(cardRadius)));
    expect(norm(card.boxShadow)).toBe(norm(resolve(cardShadow)));
  });

  /* 사용자 지적: "카드 색상이 안 바뀌었다, 여전히 하얀색". 기준선에서 카드(.card)는 정말
   * 흰색이고, 위계는 표 머리·칸반 열·보조 패널이 쓰는 --surface-2 가 만든다. 우리 표 머리는
   * primary 를 4% 섞은 파란 기가 도는 색이라 기준선과 달랐다. */
  it("표 머리 배경은 기준선의 th 배경(--surface-2)과 같다", () => {
    expect(norm(tableHead.background)).toBe(norm(resolve(headBg)));
  });

  it("버튼 높이·모서리는 기준선의 .btn 과 같다", () => {
    const button = theme.components.MuiButton.styleOverrides.root;
    expect(button.minHeight).toBe(px(btnHeight));
    expect(button.borderRadius).toBe(px(btnRadius));
  });

  it("입력 모서리는 기준선의 .field 와 같다", () => {
    expect(theme.components.MuiOutlinedInput.styleOverrides.root.borderRadius).toBe(px(fieldRadius));
  });

  /* 🔴 여기는 **의도적으로 기준선을 안 따른다**(사용자 확인, 08-07).
   * 기준선은 `.field { background: var(--surface) }` 라 카드와 입력칸이 똑같은 흰색인데,
   * 실사용에서 흰 카드 위 흰 입력칸이 안 보인다는 지적이 나왔다. --surface-2(#F8FAFF)로
   * 카드와 구별한다. 이 테스트는 "왜 다른지"를 기록해 다음 사람이 기준선과 다르다고
   * 되돌리지 않게 한다. */
  it("입력칸 배경은 카드와 구별되는 --surface-2 다 (기준선과 다름, 의도됨)", () => {
    const bg = theme.components.MuiOutlinedInput.styleOverrides.root.background;
    expect(bg).toBe(theme.palette.background.surface2);
    expect(bg).not.toBe(theme.palette.background.paper);
  });

  /* 기준선의 제품 화면 기본 버튼은 단색 var(--primary) 다. 그라데이션은 로그인
   * (.auth-submit)에만 있다 - 제품 버튼에 그라데이션을 칠하면 기준선에 없는 모양이 된다. */
  it("기본 버튼은 기준선의 .btn.primary 처럼 단색이다", () => {
    const btnPrimary = lastDeclaration(rules, ".btn.primary", "background");
    const contained = theme.components.MuiButton.styleOverrides.containedPrimary;
    expect(norm(contained.background)).toBe(norm(resolve(btnPrimary)));
  });
});

describe("타이포", () => {
  const theme = createClovirTheme("light");
  const bodyFont = lastDeclaration(rules, "body", "font-size");
  const bodyTracking = lastDeclaration(rules, "body", "letter-spacing");
  const bodyLine = lastDeclaration(rules, "body", "line-height");
  const fontStack = tokensFor("light")["--font"];
  const pageTitle = lastDeclaration(rules, ".page-title", "font-size");

  it("본문 크기는 기준선의 body 와 같다", () => {
    expect(remToPx(theme.typography.body1.fontSize)).toBe(px(bodyFont));
  });

  it("본문 자간·행간은 기준선의 body 와 같다", () => {
    expect(px(theme.typography.body1.letterSpacing)).toBe(px(bodyTracking));
    expect(theme.typography.body1.lineHeight).toBe(px(bodyLine));
  });

  /* 웹폰트(Pretendard)는 2026-08-04 사용자 지시로 앞에 붙였다. 기준선 스택은 지운 것이
   * 아니라 폴백이어야 한다 - 폰트를 못 받아도 기준선과 같은 글꼴로 떨어진다. */
  it("글꼴 스택은 기준선의 --font 로 끝난다", () => {
    expect(norm(theme.typography.fontFamily).endsWith(norm(fontStack))).toBe(true);
  });

  /* 화면 제목(PageHeader 가 h4). 기준선은 clamp(24px, 2.1vw, 34px) 이다. 가운데 항의 계수는
   * 우리 display() 헬퍼가 `min + vw` 꼴이라 그대로 옮길 수 없다 - 상·하한만 맞춘다. */
  it("화면 제목의 상·하한은 기준선의 .page-title 과 같다", () => {
    const [min, , max] = pageTitle.replace(/^clamp\(|\)$/g, "").split(",");
    const ours = theme.typography.h4.fontSize.replace(/^clamp\(|\)$/g, "").split(",");
    expect(remToPx(ours[0])).toBe(px(min));
    expect(remToPx(ours[2])).toBe(px(max));
  });
});
