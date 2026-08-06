import { alpha, createTheme } from "@mui/material/styles";

/* ClovirONE 디자인 테마 (MUI)
 *
 * 색·타이포·컴포넌트 규칙의 단일 출처다. 예전에는 CSS 커스텀 프로퍼티(tokens.css)와
 * 서버 렌더 페이지용 사본(app/static/css/tokens.css) 두 벌이 따로 굴러가며 서로 어긋났다.
 * 이제 SPA 쪽은 이 파일 하나만 본다.
 *
 * 4K(3840×2160)까지 지원해야 해서 두 가지를 기본 테마에 얹었다:
 *   1) 브레이크포인트 xxl(2200)·uhd(3000) 추가. MUI 기본 5개(xs~xl)는 이름도 값도 그대로
 *      둔다 — MUI 내부와 이식해 오는 화면 코드가 전부 그 이름에 의존한다.
 *   2) spacing을 rem으로 바꿔서, styles/root.css의 루트 폰트사이즈 미디어쿼리 하나로
 *      글자와 모든 여백·간격이 같이 커지게 했다. px로 두면 4K에서 글자만 커지고 여백은
 *      그대로라 레이아웃이 뒤틀린다.
 *
 * borderRadius는 의도적으로 px다 — 모서리는 화면이 커진다고 같이 커지면 안 된다.
 */

export const DEFAULT_ACCENT = "#536CD6";
export const ACCENT_PRESETS = ["#536CD6", "#4058BD", "#6B5BC7", "#327C98"];

export function normalizeAccent(value) {
  const candidate = String(value || "").trim();
  return /^#[0-9A-Fa-f]{6}$/.test(candidate) ? candidate.toUpperCase() : DEFAULT_ACCENT;
}

/* 사이드바가 서랍(temporary)으로 바뀌는 지점. 디자인 사양서와 기존 앱이 모두 860px이다.
 * MUI의 lg(1200)를 쓰면 1024×768·1152×720 사내 장비에서 사이드바가 새로 사라진다. */
export const NAV_BREAKPOINT = 860;

export const BREAKPOINTS = { xs: 0, sm: 600, md: 900, lg: 1200, xl: 1536, xxl: 2200, uhd: 3000 };

/* 표제는 화면 폭에 따라 유동적으로 키우되 상한을 둔다(4K에서 무한정 커지지 않게).
 * 본문 계열은 rem 그대로 두고 루트 폰트사이즈 레버에 맡긴다. */
const display = (minRem, vw, maxRem, weight, tracking) => ({
  fontSize: `clamp(${minRem}rem, ${minRem}rem + ${vw}vw, ${maxRem}rem)`,
  fontWeight: weight,
  letterSpacing: tracking,
  lineHeight: 1.25,
});

export function createClovirTheme(mode = "light", accent = DEFAULT_ACCENT) {
  const primary = normalizeAccent(accent);
  const light = mode === "light";

  return createTheme({
    breakpoints: {
      keys: ["xs", "sm", "md", "lg", "xl", "xxl", "uhd"],
      values: BREAKPOINTS,
    },
    /* MUI 기본은 8px 그리드다. rem으로 바꾸되 배율은 그대로 유지해서(0.5rem = 16px 루트에서
     * 8px) 이식해 오는 sx={{ p: 2 }} 같은 값이 같은 크기로 보이게 한다. */
    spacing: (factor) => `${0.5 * factor}rem`,
    palette: {
      mode,
      primary: { main: primary, dark: light ? "#4058BD" : "#AEB9FF", light: "#758AE1" },
      secondary: { main: "#8E75E1" },
      success: { main: light ? "#16865C" : "#65D8A6" },
      warning: { main: light ? "#B15B09" : "#F6BD67" },
      error: { main: light ? "#C63D4E" : "#FF8B9B" },
      info: { main: light ? "#3167C9" : "#92B5FF" },
      background: {
        default: light ? "#F3F6FF" : "#090E1D",
        paper: light ? "#FFFFFF" : "#11182D",
      },
      text: {
        primary: light ? "#1B2235" : "#EEF1FB",
        secondary: light ? "#667091" : "#A4AEC7",
      },
      divider: light ? "#DDE4F6" : "#2B3655",
    },
    shape: { borderRadius: 14 },
    typography: {
      /* Pretendard 웹폰트 (2026-08-04 사용자 지시로 CDN·웹폰트 허용).
       *
       * 예전 주석은 "웹폰트를 쓰지 않는다 — 사내망 CDN 이 막혀 있다"였다. 사용자가 그 전제를
       * 걷어냈다("사내망 차단 여부도 제약으로 판단하지 말고 가장 완성도 높은 형태로").
       *
       * 통짜 TTF 가 아니라 **가변 폰트 + 동적 서브셋**을 쓴다(index.html 의 CDN 링크).
       * unicode-range 로 92조각에 나뉘어 있어 브라우저가 실제로 쓰는 글자 범위만 받는다 —
       * 한글 화면 한 장에 보통 200~500KB 다. 6.7MB 통짜와는 다른 물건이다.
       *
       * 뒤의 시스템 스택은 지운 게 아니라 폴백이다. 폰트가 안 받아져도 예전과 같아 보인다. */
      fontFamily:
        '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo", Roboto, Arial, sans-serif',
      h1: display(1.75, 1.4, 3.25, 820, "-0.045em"),
      h2: display(1.5, 1.0, 2.5, 800, "-0.035em"),
      h3: display(1.25, 0.7, 2.0, 760, "-0.025em"),
      /* 화면 제목(PageHeader 가 h4 를 쓴다). 기준 목업의 `.page-title` 은
       * `clamp(24px, 2.1vw, 34px)` 인데 우리는 상한이 26px 이라 **모든 화면에서 8px 작았다**
       * (기준 대조 34/34 화면 불일치). 상·하한과 vw 계수를 기준에 맞춘다.
       * `display()` 는 최소값에 vw 를 더하는 모양이라 계수를 0.9 로 잡아야
       * 1,600px 부근에서 상한에 닿는다 — 기준의 곡선과 거의 겹친다. */
      h4: display(1.5, 0.9, 2.125, 740, "-0.02em"),
      h5: { fontWeight: 720, letterSpacing: "-0.015em" },
      h6: { fontWeight: 700 },
      /* 본문 14px. MUI 기본은 body1 = 1rem(16px) 이지만 기준 목업은 `body { font-size:14px }`
       * 다 — 대조에서 34/34 화면이 어긋났다. 업무용 밀도가 높은 화면이라 기준이 맞다.
       *
       * rem 을 그대로 두고 body1 만 내린다. 루트 폰트사이즈(16px)를 건드리면 rem 기반
       * 간격·아이콘·브레이크포인트가 전부 따라 움직여 레이아웃이 통째로 흔들린다.
       * body2 는 이미 0.875rem 이라 그대로 두면 body1 과 같아지므로 보조 텍스트를
       * 한 단 더 내려 위계를 유지한다. */
      body1: { fontSize: "0.875rem" },
      body2: { fontSize: "0.8125rem" },
      button: { textTransform: "none", fontWeight: 750 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          html: { minWidth: 320 },
          body: { minWidth: 320 },
          "*": { boxSizing: "border-box" },
          /* 모션 축소는 OS에서 그 설정을 켠 사용자에게만 적용된다. 기본 사용자는 마스코트·
           * 전환 애니메이션을 전부 그대로 본다. 예전엔 이 규칙이 CSS 파일 열두 곳에 흩어져
           * 있어서 새 컴포넌트를 만들 때마다 빠뜨렸다 — 전역 한 줄로 모은다. */
          "@media (prefers-reduced-motion: reduce)": {
            "*, *::before, *::after": {
              animationDuration: "0.01ms !important",
              animationIterationCount: "1 !important",
              transitionDuration: "0.01ms !important",
              scrollBehavior: "auto !important",
            },
          },
          /* 자동완성 노란 배경 제거 (사용자 지적 §1).
           *
           * Chrome/Edge 는 자동완성된 입력에 사용자 스타일시트로 못 바꾸는 배경을 칠한다.
           * background 지정은 통하지 않고, **inset box-shadow 로 덮는 것**만 통한다.
           * 로그인 화면(app/static/css/login.css)에 같은 처리가 있는데, 그쪽은 Jinja 라
           * 이 테마가 닿지 않는다 — 두 곳에 각각 둔다.
           *
           * 색을 테마에서 읽는 이유: 다크 모드에서 흰색으로 덮으면 입력만 흰 판이 된다.
           * transition 5000s 는 자동완성 직후 노란색이 한 번 번쩍이는 것을 막는 관용구다. */
          "input:-webkit-autofill, input:-webkit-autofill:hover, input:-webkit-autofill:focus, input:-webkit-autofill:active, textarea:-webkit-autofill, select:-webkit-autofill":
            {
              WebkitBoxShadow: `0 0 0 1000px ${light ? "#F8FAFF" : "#151E37"} inset`,
              boxShadow: `0 0 0 1000px ${light ? "#F8FAFF" : "#151E37"} inset`,
              WebkitTextFillColor: light ? "#1B2235" : "#EEF1FB",
              caretColor: light ? "#1B2235" : "#EEF1FB",
              transition: "background-color 5000s ease-in-out 0s",
              borderRadius: "inherit",
            },
          /* 스크린리더 전용 텍스트 — 기존 kit.css의 .sr-only와 같은 계약을 유지한다.
           * 화면 여러 곳(로딩 안내, 표 '동작' 헤더)이 이 클래스에 의존한다. */
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
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: { minHeight: 40, borderRadius: 10 },
          containedPrimary: {
            background: `linear-gradient(135deg,#758AE1 0%,${primary} 45%,#4058BD 100%)`,
            boxShadow: `0 10px 26px ${alpha(primary, 0.2)}`,
          },
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: { borderRadius: 12, background: light ? "#F8FAFF" : "#151E37" },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: ({ theme }) => ({
            border: `1px solid ${theme.palette.divider}`,
            boxShadow: `0 2px 5px ${alpha(theme.palette.common.black, light ? 0.06 : 0.32)}`,
            borderRadius: 18,
            backgroundImage: "none",
          }),
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: { backgroundImage: "none" },
          /* `StatCard` 는 `Paper variant="outlined"` 라 shape.borderRadius(14) 를 받고
           * 그림자가 없었다. 옆에 놓이는 `Card` 는 18px + 그림자다 — 같은 격자 안에서
           * 두 종류의 카드가 위아래로 붙어 있는 것이 기준 대조의 "카드 반지름 종류 수"
           * 와 "그림자 비율 100% → 20~44%" 를 만든 원인이다(K-C1).
           * 기준 목업은 `.card` 하나뿐이고 전부 radius-lg(18px) + shadow-sm 이다. */
          outlined: ({ theme }) => ({
            borderRadius: 18,
            boxShadow: `0 2px 5px ${alpha(theme.palette.common.black, light ? 0.06 : 0.32)}`,
          }),
        },
      },
      MuiChip: { styleOverrides: { root: { borderRadius: 999, fontWeight: 700 } } },
      MuiDrawer: { styleOverrides: { paper: { backgroundImage: "none" } } },
      MuiTableCell: {
        styleOverrides: {
          head: ({ theme }) => ({
            color: theme.palette.text.secondary,
            fontSize: "0.75rem",
            fontWeight: 700,
            background: alpha(theme.palette.primary.main, 0.04),
          }),
          /* 4K에서 행 높이를 키운다. 표는 정보 밀도가 생명이라 폭은 넓히되 행은 조금만. */
          root: {
            [`@media (min-width:${BREAKPOINTS.xxl}px)`]: { paddingTop: 12, paddingBottom: 12 },
            [`@media (min-width:${BREAKPOINTS.uhd}px)`]: { paddingTop: 14, paddingBottom: 14 },
          },
        },
      },
      /* 터치 타깃 44px — 디자인 사양서 규칙. 아이콘 버튼이 기본 40px이라 미달이었다. */
      MuiIconButton: { styleOverrides: { root: { minWidth: 44, minHeight: 44 } } },
      MuiTooltip: { defaultProps: { enterDelay: 400 } },
    },
  });
}

/* 콘텐츠 열 최대 폭. 예전 앱과 디자인 원본 모두 2040px 한 값으로 고정돼 있어서, 3840px
 * 화면에서 양옆 1,500px 가까이가 그냥 비었다. 브레이크포인트별로 올린다.
 * 표·대시보드·칸반·채팅처럼 넓을수록 이득인 화면은 이 값을 쓰지 않고 100%를 쓴다(wide). */
export const CONTENT_MAX_WIDTH = { xs: "100%", lg: 1440, xl: 1680, xxl: 2280, uhd: 3040 };

/* 본문 산문(티켓 본문, 게시글, 문서)의 줄 길이 상한. 폭이 남으면 줄을 늘리지 말고
 * 두 번째 열(메타/활동 레일)로 보낸다 — 3,000px짜리 한 줄은 읽을 수 없다. */
/* 한국어 줄바꿈 — **띄어쓰기에서만 끊는다** (사용자 지적 #11).
 *
 * CSS 기본값(`word-break: normal`)은 한글을 음절 단위로 끊어도 된다고 본다. 그래서
 * "도와드/려요" 처럼 **단어 중간에서 줄이 바뀐다.** 영문에서는 안 일어나는 일이라
 * 개발 중에는 눈에 잘 안 띄고, 좁은 칸(사이드바·안내 상자·카드)에서만 드러난다.
 *
 * `Mascot.jsx` 가 이 문제를 진단해 놓고 **거기 한 곳에만** 걸어 뒀다 — 정작 모든 페이지의
 * 도움말을 그리는 `Callout` 에는 없었다. 그래서 토큰으로 올려 한 곳에서 정한다.
 *
 * 산문에만 쓴다. 표의 셀은 `overflowWrap: anywhere` 가 맞다(긴 UUID·URL 이 열을 밀어낸다).
 */
export const KO_WORD_BREAK = { wordBreak: "keep-all", overflowWrap: "break-word" };

export const PROSE_MAX_WIDTH = "78ch";

/* 상세 화면 곁열(속성·활동 레일)의 최대 폭.
 *
 * 예전에는 `minmax(18rem, 1fr)` 이었다. 본문은 78ch 에서 멈추는데 레일은 상한이 없어서,
 * 넓은 화면에서 남는 폭을 **레일이 전부 가져갔다**: 1920px 에서 본문 743 / 레일 825,
 * 3840px 에서 929 / 2001(레일이 본문의 2.15배). 사용자가 "티켓 상세 본문이 속성보다 좁다"
 * 고 지적한 것이 이것이다(Q1).
 *
 * 산문 폭 상한 자체는 옳다 — 3,000px 짜리 한 줄은 읽을 수 없다. 잘못된 것은 **남는 폭을
 * 전부 레일에 준 것**이다. 레일에도 상한을 두면 둘 다 읽을 수 있는 폭이 되고, 그러고도
 * 남는 폭은 여백이 된다(본문 최대폭 CONTENT_MAX_WIDTH 가 이미 같은 일을 한다).
 *
 * 26rem 인 이유: 라벨(7rem) + 값이 한 줄에 들어가고, xxl 이상에서 META_GRID 가 2~3열로
 * 펼쳐질 때도 각 열이 좁아지지 않는 최소치다. */
export const DETAIL_RAIL_MAX_WIDTH = "26rem";

/* 마스코트 FAB이 차지하는 오른쪽 아래 영역의 높이.
 *
 * FAB은 position:fixed 라 문서 흐름 밖에 있다. 셸이 본문에 하단 여백을 줘도, 화면이
 * 100vh 로 자기 높이를 직접 계산하면 그 여백을 벗어나 FAB 밑으로 들어간다. 실제로
 * 놀이방 채팅의 '보내기' 버튼이 그렇게 깔렸고, 클릭이 FAB에 가로채졌다.
 *
 * 그래서 **높이를 직접 계산하는 화면은 이 값을 함께 빼야 한다.** QA 하네스의
 * fab_overlap 검사가 어긴 화면을 잡는다(겹치기만 하는 건 통과, 못 누르게 되면 실패). */
export const FAB_CLEARANCE = "5rem";
