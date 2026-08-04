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
      // 웹폰트를 쓰지 않는다. Pretendard 단일 TTF가 6.7MB인데 사내망은 CDN이 막혀 있고,
      // 시스템 폰트 스택이 한글 환경에서 충분히 잘 나온다(디자인 원본도 같은 스택을 쓴다).
      fontFamily:
        '-apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo", Roboto, Arial, sans-serif',
      h1: display(1.75, 1.4, 3.25, 820, "-0.045em"),
      h2: display(1.5, 1.0, 2.5, 800, "-0.035em"),
      h3: display(1.25, 0.7, 2.0, 760, "-0.025em"),
      h4: display(1.125, 0.5, 1.625, 740, "-0.02em"),
      h5: { fontWeight: 720, letterSpacing: "-0.015em" },
      h6: { fontWeight: 700 },
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
      MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
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
export const PROSE_MAX_WIDTH = "78ch";

/* 마스코트 FAB이 차지하는 오른쪽 아래 영역의 높이.
 *
 * FAB은 position:fixed 라 문서 흐름 밖에 있다. 셸이 본문에 하단 여백을 줘도, 화면이
 * 100vh 로 자기 높이를 직접 계산하면 그 여백을 벗어나 FAB 밑으로 들어간다. 실제로
 * 놀이방 채팅의 '보내기' 버튼이 그렇게 깔렸고, 클릭이 FAB에 가로채졌다.
 *
 * 그래서 **높이를 직접 계산하는 화면은 이 값을 함께 빼야 한다.** QA 하네스의
 * fab_overlap 검사가 어긴 화면을 잡는다(겹치기만 하는 건 통과, 못 누르게 되면 실패). */
export const FAB_CLEARANCE = "5rem";
