import { createTheme } from "@mui/material/styles";

/* Clovir Assist 디자인 테마 — 방향 "계측 전면(Instrument Face)" (docs/DECISIONS.md D-141)
 *
 * ## 이 파일이 정본이다
 *
 * 색·타이포·간격·모서리·그림자·모션의 **단일 출처**다. 예전에는 정본이 네 겹이었다:
 * 목업 파일 → 이 파일 → `styles/tokens.css` →
 * `app/static/css/tokens.css`. 목업은 사용자 지시 64로 폐기했다. 지금 정본은 **실제 제품이
 * 쓰는 이 토큰들과 실제 브라우저 렌더링 결과**다. CSS 커스텀 프로퍼티는 여기서 파생한다.
 *
 * ## 방향 계약 (D-141)
 *
 *   THESIS     이 화면은 판독 장치다. 상자를 나열해 정보를 담는 대신 판독값의 크기·정렬·
 *              간격이 위계를 만든다.
 *   OWN-WORLD  무채색 판(plate) 위에 판독값이 얹힌다. 채도는 오직 세 곳에만 쓴다 —
 *              ① 조치가 필요한 상태 ② 현재 선택 ③ 주요 행동. chrome 은 발광하지 않는다.
 *
 * 그래서 이 파일이 예전과 다른 점 다섯 가지:
 *
 *   1. **바탕이 중립이다.** 예전 캔버스 #F5F7FC 는 라벤더 기가 있었고 그 위에 순백 카드를
 *      올려서, 화면 전체가 "AI가 만든 SaaS" 로 보이는 가장 큰 원인이었다. 이제 캔버스는
 *      채도 없는 회색이고, 브랜드 인디고는 강조 세 자리에서만 나온다.
 *   2. **chrome 이 물러난다.** 사이드바가 더 이상 짙은 남색 덩어리가 아니다. 캔버스와 같은
 *      중립 계열에 실선 하나로 구분한다. 덕분에 사이드바 색이 세 곳(theme / tokens.css /
 *      AppShell 인라인 rgba)에 중복 정의되던 문제도 같이 사라진다.
 *   3. **enclosure 가 기본값이 아니다**(D-141 RAISE, cracktro). 예전 `MuiCard` 는 테두리 +
 *      그림자 + 18px 모서리를 자동으로 얹어서 모든 정보가 흰 상자에 갇혔다. 이제 판은
 *      실선 하나뿐이고 그림자가 없다. 그림자는 **정말로 떠 있는 것**(메뉴·팝오버·모달)만
 *      갖는다.
 *   4. **모서리가 좁다.** 18px → 6px. 계측기 전면은 둥글지 않다.
 *   5. **숫자는 등폭이다.** 표·지표·시각이 세로로 정렬된다(`NUMERIC`).
 *
 * ## 바꾸기 전에 알아야 할 것
 *
 * 상태색은 강조색과 **별개 계열**이다. 사용자가 계정별 강조색(`/my-display`)을 바꿔도
 * 상태색과 판 색은 흔들리지 않아야 한다. 그래서 강조색에서 파생하는 것은 primary 계열뿐이다.
 *
 * 4K(3840×2160)까지 지원한다:
 *   · 브레이크포인트 xxl(2200)·uhd(3000) 추가. MUI 기본 5개는 이름·값 그대로 둔다.
 *   · spacing 이 rem 이라 `styles/root.css` 의 루트 폰트사이즈 미디어쿼리 하나로 글자와
 *     여백이 함께 커진다. borderRadius 는 의도적으로 px 다 — 모서리는 같이 커지면 안 된다.
 */

export const DEFAULT_ACCENT = "#536CD6";
/* 계정별 강조색 프리셋 — **값을 바꾸지 않는다.** 사용자가 고른 색은 localStorage 에 hex 로
 * 남고(`/my-display`), `settingsRegistry.js::ACCENT_NAMES` 가 이 hex 들에 한국어 이름을
 * 붙인다. 목록에서 hex 하나를 빼면 그 색을 이미 고른 사람의 화면에서 "선택됨" 표시가
 * 사라지고 이름도 hex 로 떨어진다. 네 값 전부 새 팔레트에서 AA 를 넘는 것을 실측 확인했다
 * (theme-contract.test.js 가 프리셋 전체 × 두 모드로 계속 검증한다). */
export const ACCENT_PRESETS = ["#536CD6", "#4058BD", "#6B5BC7", "#327C98"];

export function normalizeAccent(value) {
  const candidate = String(value || "").trim();
  return /^#[0-9A-Fa-f]{6}$/.test(candidate) ? candidate.toUpperCase() : DEFAULT_ACCENT;
}

/* 모서리 — 4개 의미 슬롯. 계측 전면은 둥글지 않다(D-141).
 *   sm   입력·버튼·칩          4
 *   md   판(plate)·패널        6   ← MUI 기본 shape
 *   lg   떠 있는 것(모달·팝오버) 10
 *   full 아바타처럼 완전한 원   999
 * 이전 값은 8/12/18/999 였고 입력·버튼은 토큰을 안 쓰고 10px 리터럴이었다. */
export const RADIUS = { sm: 4, md: 6, lg: 10, full: 999 };

/* 굵기 — 5단계. extrabold 는 워드마크 전용 예외다(본문 위계에 쓰지 않는다). */
export const FONT_WEIGHT = { regular: 400, medium: 500, semibold: 600, bold: 700, extrabold: 800 };

/* 글자 크기 — 7개 **역할 이름** 슬롯. 크기가 아니라 쓰임으로 부른다.
 *
 * 이름을 역할로 두는 이유: 예전 이름(body1/body2/h6)은 "몇 번째 본문인가"만 말하고 "지금
 * 어떤 의미로 쓰는가"를 말하지 않아서, 결국 리터럴을 쓰는 편이 쉬웠다(PA-RC-0001 —
 * 11~17px 사이 1px 연속체 31종·278회).
 *
 *   micro      11  배지·표 안 보조 메타
 *   caption    12  라벨·각주
 *   bodySm     13  밀도 높은 표 칸
 *   body       14  기본 본문
 *   title      17  구획 제목
 *   pageTitle  22  화면 제목
 *   readout    28  그 화면을 지배하는 판독값 하나
 *
 * `pageTitle` 은 이제 **고정값**이다. 예전에는 clamp(24~34px) 였는데, Operate 모드에서
 * 유동 제목은 도움이 안 된다 — 사용자는 일정한 DPI 로 보고, 사이드바 옆에서 줄어드는 h1 은
 * 더 나빠 보인다. 4K 확대는 루트 폰트사이즈 레버가 담당한다. */
export const FONT_SIZE = {
  micro: "0.6875rem",
  caption: "0.75rem",
  bodySm: "0.8125rem",
  body: "0.875rem",
  title: "1.0625rem",
  pageTitle: "1.375rem",
  readout: "1.75rem",
};

/* 예전 이름 두 개는 소비처가 많아 별칭으로 남긴다. 새 코드는 title/readout 을 쓴다. */
FONT_SIZE.sectionTitle = FONT_SIZE.title;
FONT_SIZE.statValue = FONT_SIZE.readout;

/* 숫자는 세로로 정렬되어야 읽힌다 — 표·지표·시각·ID. 계측 전면의 핵심 규율이다. */
export const NUMERIC = { fontVariantNumeric: "tabular-nums", fontFeatureSettings: '"tnum" 1' };

/* 모션 — 상태 전달용만. 장식하지 않는다. Operate 는 흐름 중이라 안무를 기다리지 않는다. */
export const MOTION = {
  instant: "90ms",
  fast: "140ms",
  base: "200ms",
  ease: "cubic-bezier(0.2, 0, 0.2, 1)",
};

/* 브랜드 고정색. 로고와 마스코트가 쓰는 값이라 UI 강조색과 별개로 보존한다(§1.5 브랜드 커밋). */
const BRAND = { deep: "#17204D", mid: "#293B8D", purple: "#8E75E1", mint: "#62C7BD" };

/* 그림자 — 떠 있는 것만 갖는다. 판에는 그림자가 없다(D-141).
 * 예전에는 sm/md/lg 셋에 별칭 다섯(--shadow-card/-subtle/-dropdown/-modal/-hero)이 붙어
 * 있었고 카드가 전부 sm 을 달고 있었다. */
const SHADOW = {
  light: {
    none: "none",
    overlay: "0 6px 18px rgba(16,20,28,.10), 0 1px 3px rgba(16,20,28,.06)",
    modal: "0 24px 56px rgba(16,20,28,.20)",
  },
  dark: {
    none: "none",
    overlay: "0 6px 18px rgba(0,0,0,.50), 0 1px 3px rgba(0,0,0,.40)",
    modal: "0 24px 56px rgba(0,0,0,.62)",
  },
};

/* MUI 는 elevation 0~24 를 요구한다. 우리에게는 none/overlay/modal 셋뿐이라
 * 메뉴·팝오버 구간(1~15)은 overlay, 드로어·모달 구간(16~24)은 modal 로 접는다. */
function shadowScale({ none, overlay, modal }) {
  return [none, ...Array(15).fill(overlay), ...Array(9).fill(modal)];
}

/* srgb 색 혼합 — 기준선이 쓰던 `color-mix(in srgb, A p%, B)` 와 같은 계산이다.
 * primary 파생색을 강조색에서 유도하는 데 쓴다. 결과를 상수로 박으면 사용자가 강조색을
 * 바꿨을 때 파생색만 기본값에 남는다. */
function mixSrgb(from, to, ratio) {
  const channels = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const [fr, fg, fb] = channels(from);
  const [tr, tg, tb] = channels(to);
  const mix = (a, b) => Math.round(a * ratio + b * (1 - ratio));
  return `#${[mix(fr, tr), mix(fg, tg), mix(fb, tb)]
    .map((v) => v.toString(16).padStart(2, "0"))
    .join("")}`.toUpperCase();
}

/* ── 중립 램프와 상태 계열 ──────────────────────────────────────────────────
 *
 * 캔버스·판·오목면·실선이 하나의 중립 램프에서 나온다. 채도가 없다 — 예전 라벤더 기
 * (#F5F7FC / #F8FAFF / #EEF2F8)를 걷어낸 자리다.
 *
 * 상태색은 강조색과 섞이지 않는 **독립 계열**이다. 각 상태는 fg(글자·아이콘) / bg(옅은 면) /
 * line(테두리) 셋을 갖고, **색만으로 상태를 전달하지 않는다**(D-141 RAISE, cyclorama) —
 * 화면 쪽에서 이름표나 아이콘을 반드시 함께 붙인다. */
const TOKENS = {
  light: {
    canvas: "#EDEFF2",
    plate: "#FFFFFF",
    inset: "#F4F6F8",
    sunken: "#E7EAEE",
    text: "#171A1F",
    muted: "#5C6370",
    faint: "#656D7A",
    line: "#DCE0E6",
    lineStrong: "#C0C6CF",
    accent: "#5B54B8",
    cyan: "#1F6F8B",
    success: "#0F7B4F",
    successBg: "#E8F4EE",
    successLine: "#A9D4BF",
    warning: "#8A5300",
    warningBg: "#FAF0E1",
    warningLine: "#E0C08A",
    danger: "#B3261E",
    dangerBg: "#FBECEB",
    dangerLine: "#E6B0AC",
    info: "#1F5FBF",
    infoBg: "#EAF0FA",
    infoLine: "#B3C8E8",
    /* chrome 은 캔버스 계열이다. 짙은 남색 덩어리가 아니다. */
    railBg: "#E7EAEE",
    railText: "#171A1F",
    railMuted: "#5C6370",
    railHover: "rgba(23,26,31,.06)",
    railLine: "#D3D8DE",
    /* 0.78 이었다. 캔버스가 중립 회색(#EDEFF2)으로 내려오면서 `alpha(primary,.14)` 워시 위
     * 글자가 4.48 로 AA 경계 아래에 걸렸다(theme-link-contrast 가 잡았다). 0.72 로 낮추면
     * 최악 조합이 4.80 이 되고, 링크·탭·선택 라벨 대비도 함께 올라간다. */
    strongMix: [BRAND.deep, 0.72],
    softMix: 0.1,
    /* 포커스 링 — 흰 판 대비 3:1 이상이어야 한다(KBD-01/02/03). 강조색 파생 공식
     * (primary 70% + white)은 2.76 으로 미달이라 실측 검증값을 쓴다. */
    focusRing: "#2F49B8",
  },
  dark: {
    canvas: "#0E1013",
    plate: "#16191E",
    inset: "#1C2026",
    sunken: "#101318",
    text: "#E6E9EE",
    muted: "#9BA3AF",
    faint: "#828B98",
    line: "#2A2F37",
    lineStrong: "#3D444F",
    accent: "#A99CF5",
    cyan: "#6FB6CE",
    success: "#4ADE9B",
    successBg: "#12291F",
    successLine: "#2A5943",
    warning: "#F0B357",
    warningBg: "#2B2113",
    warningLine: "#5C4522",
    danger: "#FF8A80",
    dangerBg: "#2E1A18",
    dangerLine: "#5F3330",
    info: "#8AB4F8",
    infoBg: "#151F31",
    infoLine: "#2C4265",
    railBg: "#101318",
    railText: "#E6E9EE",
    railMuted: "#9BA3AF",
    railHover: "rgba(230,233,238,.07)",
    railLine: "#242931",
    strongMix: ["#FFFFFF", 0.72],
    softMix: 0.16,
    focusRing: "#8AA4FF",
  },
};

/* 사이드바가 서랍(temporary)으로 바뀌는 지점. 1024×768·1152×720 사내 장비를 고려한 값이라
 * MUI 의 lg(1200)를 쓰면 안 된다. */
export const NAV_BREAKPOINT = 860;

export const BREAKPOINTS = { xs: 0, sm: 600, md: 900, lg: 1200, xl: 1536, xxl: 2200, uhd: 3000 };

/* 표가 카드 목록으로 접히는 지점. 899.95 는 MUI 가 `down("md")` 에서 만드는 값과 같다. */
export const TABLE_CARD_QUERY = `(max-width:${BREAKPOINTS.md - 0.05}px)`;

/* 카드로 접히기 전, 사이드바가 아직 안 접힌 900~1200 구간. 열이 많은 표는 여기서
 * `hideNarrow` 열을 뺀다(카드 뷰는 폭 제약이 없으니 전부 보여준다). */
export const TABLE_COMPACT_QUERY = `(max-width:${BREAKPOINTS.lg - 0.05}px)`;

export function createClovirTheme(mode = "light", accent = DEFAULT_ACCENT) {
  const primary = normalizeAccent(accent);
  const light = mode === "light";
  const t = light ? TOKENS.light : TOKENS.dark;
  const shadows = light ? SHADOW.light : SHADOW.dark;
  const primaryStrong = mixSrgb(primary, t.strongMix[0], t.strongMix[1]);
  const primarySoft = mixSrgb(primary, t.plate, t.softMix);

  return createTheme({
    breakpoints: { keys: ["xs", "sm", "md", "lg", "xl", "xxl", "uhd"], values: BREAKPOINTS },
    /* MUI 기본 8px 그리드를 rem 으로 옮긴다(0.5rem = 16px 루트에서 8px). 이식해 오는
     * sx={{ p: 2 }} 가 같은 크기로 보이도록 배율은 그대로 둔다. */
    spacing: (factor) => `${0.5 * factor}rem`,
    shadowTokens: shadows,
    shadows: shadowScale(shadows),
    motionTokens: MOTION,
    palette: {
      mode,
      primary: { main: primary, dark: primaryStrong, light: primarySoft, soft: primarySoft },
      secondary: { main: t.accent },
      /* `strong` 은 작은 글자색으로 쓸 때의 대비 확보용이다. `.main` 은 색 있는 면 위
       * 흰 글자(칩)엔 맞지만 흰 판 위 12~13px 글자로 쓰면 AA 경계에 걸린다(QAH-03 실측). */
      success: { main: t.success, bg: t.successBg, line: t.successLine, strong: mixSrgb(t.success, t.strongMix[0], t.strongMix[1]) },
      warning: { main: t.warning, bg: t.warningBg, line: t.warningLine, strong: mixSrgb(t.warning, t.strongMix[0], t.strongMix[1]) },
      error: { main: t.danger, bg: t.dangerBg, line: t.dangerLine, strong: mixSrgb(t.danger, t.strongMix[0], t.strongMix[1]) },
      info: { main: t.info, bg: t.infoBg, line: t.infoLine, strong: mixSrgb(t.info, t.strongMix[0], t.strongMix[1]) },
      cyan: t.cyan,
      /* 판 위계. `paper` 가 판(plate)이고, surface2 는 오목면(표 머리·읽기 전용·코드),
       * surface3 은 더 깊은 오목면(트랙·스켈레톤)이다. 이름은 소비처 55곳이 쓰고 있어
       * 유지하되, 의미를 plate/inset/sunken 으로 다시 정의했다. */
      background: {
        default: t.canvas,
        paper: t.plate,
        canvas: t.canvas,
        plate: t.plate,
        inset: t.inset,
        sunken: t.sunken,
        surface2: t.inset,
        surface3: t.sunken,
      },
      text: { primary: t.text, secondary: t.muted, disabled: t.faint, faint: t.faint },
      divider: t.line,
      dividerStrong: t.lineStrong,
      /* chrome(사이드바·상단바)은 캔버스 계열이다. 예전에는 두 모드 모두 짙은 남색이라
       * 전용 규칙이 필요했고, 그 색이 세 곳에 중복 정의돼 있었다. 이제 한 곳이다. */
      sidebar: {
        bg: t.railBg,
        text: t.railText,
        muted: t.railMuted,
        hover: t.railHover,
        line: t.railLine,
        /* 현재 선택을 말하는 유일한 색. 앞머리 2px 레일로만 쓴다(D-141 RAISE). */
        activeRail: primary,
      },
      brand: { accent: primary, ...BRAND },
      focusRing: t.focusRing,
    },
    shape: { borderRadius: RADIUS.md },
    typography: {
      /* Pretendard 가변 폰트 + 동적 서브셋(index.html). 뒤 스택은 폴백이다. */
      fontFamily:
        '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo", Roboto, Arial, sans-serif',
      /* 고정 rem 스케일. clamp 를 쓰지 않는다 — Operate 모드에서 유동 제목은 손해다. */
      /* h1~h3 은 이 제품에서 쓰이지 않는다(화면 제목은 h4=PageHeader, 구획 제목은
       * SectionTitle). MUI 기본값을 그대로 두면 스케일 밖 크기가 되므로 **스케일 안의 값**을
       * 내림차순으로 붙여 둔다 — 새 리터럴을 만들지 않는다. */
      h1: { fontSize: FONT_SIZE.readout, fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.022em", lineHeight: 1.25 },
      h2: { fontSize: FONT_SIZE.pageTitle, fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.02em", lineHeight: 1.28 },
      h3: { fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.018em", lineHeight: 1.3 },
      /* 화면 제목. PageHeader 가 h4 를 쓴다. */
      h4: { fontSize: FONT_SIZE.pageTitle, fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.016em", lineHeight: 1.3 },
      h5: { fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.semibold, letterSpacing: "-0.012em" },
      h6: { fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.semibold, letterSpacing: "-0.012em" },
      body1: { fontSize: FONT_SIZE.body, lineHeight: 1.55, letterSpacing: "-0.011em" },
      body2: { fontSize: FONT_SIZE.bodySm, lineHeight: 1.5, letterSpacing: "-0.011em" },
      caption: { fontSize: FONT_SIZE.caption, lineHeight: 1.45, letterSpacing: "-0.006em" },
      button: { textTransform: "none", fontWeight: FONT_WEIGHT.semibold, letterSpacing: "-0.011em" },
      /* 구획 제목과 판독값. MUI 에 대응 variant 가 없어 새로 만든 두 단계다. */
      sectionTitle: { fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.semibold, letterSpacing: "-0.012em", lineHeight: 1.35 },
      statValue: {
        fontSize: FONT_SIZE.readout,
        fontWeight: FONT_WEIGHT.semibold,
        letterSpacing: "-0.02em",
        lineHeight: 1.15,
        ...NUMERIC,
      },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          html: { minWidth: 320 },
          body: { minWidth: 320, letterSpacing: "-0.011em" },
          "*": { boxSizing: "border-box" },
          "@media (prefers-reduced-motion: reduce)": {
            "*, *::before, *::after": {
              animationDuration: "0.01ms !important",
              animationIterationCount: "1 !important",
              transitionDuration: "0.01ms !important",
              scrollBehavior: "auto !important",
            },
          },
          "input:-webkit-autofill, input:-webkit-autofill:hover, input:-webkit-autofill:focus, input:-webkit-autofill:active, textarea:-webkit-autofill, select:-webkit-autofill":
            {
              WebkitBoxShadow: `0 0 0 1000px ${t.inset} inset`,
              boxShadow: `0 0 0 1000px ${t.inset} inset`,
              WebkitTextFillColor: t.text,
              caretColor: t.text,
              transition: "background-color 5000s ease-in-out 0s",
              borderRadius: "inherit",
            },
          ".sr-only": {
            position: "absolute",
            width: 1,
            height: 1,
            padding: 0,
            margin: -1,
            overflow: "hidden",
            clip: "rect(0 0 0 0)",
            whiteSpace: "nowrap",
            border: 0,
          },
        },
      },
      MuiButtonBase: {
        styleOverrides: {
          root: {
            "&.Mui-focusVisible": { outline: `2px solid ${t.focusRing}`, outlineOffset: 2 },
          },
        },
      },
      MuiLink: {
        styleOverrides: {
          root: {
            color: primaryStrong,
            textUnderlineOffset: "0.15em",
            "&:focus-visible": { outline: `2px solid ${t.focusRing}`, outlineOffset: 2 },
          },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: {
            minHeight: 32,
            borderRadius: RADIUS.sm,
            paddingInline: 12,
            transition: `background-color ${MOTION.fast} ${MOTION.ease}, border-color ${MOTION.fast} ${MOTION.ease}`,
          },
          sizeSmall: { minHeight: 28, paddingInline: 10 },
          sizeLarge: { minHeight: 38, paddingInline: 16 },
          containedPrimary: {
            background: primary,
            boxShadow: "none",
            "&:hover": { background: primaryStrong, boxShadow: "none" },
          },
          textPrimary: { color: primaryStrong },
          outlinedPrimary: { color: primaryStrong },
        },
      },
      MuiTab: {
        styleOverrides: {
          root: {
            minHeight: 38,
            textTransform: "none",
            fontWeight: FONT_WEIGHT.medium,
            "&.Mui-selected": { color: primaryStrong, fontWeight: FONT_WEIGHT.semibold },
          },
        },
      },
      MuiTabs: { styleOverrides: { indicator: { backgroundColor: primaryStrong, height: 2 } } },
      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            borderRadius: RADIUS.sm,
            background: t.plate,
            "&.Mui-focused": { outline: `2px solid ${t.focusRing}`, outlineOffset: 0 },
          },
          input: { paddingTop: 7, paddingBottom: 7 },
        },
      },
      /* 판(plate). **테두리 하나뿐이고 그림자가 없다** — enclosure 는 기본값이 아니다(D-141). */
      MuiCard: {
        styleOverrides: {
          root: ({ theme }) => ({
            border: `1px solid ${theme.palette.divider}`,
            boxShadow: "none",
            borderRadius: RADIUS.md,
            backgroundImage: "none",
          }),
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: { backgroundImage: "none" },
          outlined: { borderRadius: RADIUS.md, boxShadow: "none" },
          /* 떠 있는 것만 그림자를 갖는다. */
          elevation1: ({ theme }) => ({ boxShadow: theme.shadowTokens.overlay }),
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { borderRadius: RADIUS.sm, fontWeight: FONT_WEIGHT.medium },
        },
      },
      MuiDrawer: { styleOverrides: { paper: { backgroundImage: "none" } } },
      MuiTableCell: {
        styleOverrides: {
          head: ({ theme }) => ({
            color: theme.palette.text.secondary,
            fontSize: FONT_SIZE.micro,
            fontWeight: FONT_WEIGHT.semibold,
            letterSpacing: "0.03em",
            textTransform: "none",
            background: theme.palette.background.inset,
            borderBottom: `1px solid ${theme.palette.dividerStrong}`,
          }),
          root: {
            fontSize: FONT_SIZE.bodySm,
            [`@media (min-width:${BREAKPOINTS.xxl}px)`]: { paddingTop: 10, paddingBottom: 10 },
            [`@media (min-width:${BREAKPOINTS.uhd}px)`]: { paddingTop: 12, paddingBottom: 12 },
          },
        },
      },
      MuiIconButton: { styleOverrides: { root: { minWidth: 32, minHeight: 32, borderRadius: RADIUS.sm } } },
      MuiTooltip: { defaultProps: { enterDelay: 400 } },
      MuiTypography: { defaultProps: { variantMapping: { sectionTitle: "h2", statValue: "p" } } },
    },
  });
}

/* 본문 최대 폭. 넓은 화면에서 가운데 좁은 기둥을 만들지 않는다(지시 63) — 판독 밀도를
 * 유지하면서 열 수와 여백으로 공간을 쓴다. */
export const CONTENT_MAX_WIDTH = { xs: "100%", lg: "100%", xl: 1720, xxl: 2320, uhd: 3080 };
export const KO_WORD_BREAK = { wordBreak: "keep-all", overflowWrap: "break-word" };
export const PROSE_MAX_WIDTH = "72ch";
export const FAB_CLEARANCE = "5rem";
