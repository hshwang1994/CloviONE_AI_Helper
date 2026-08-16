/* alpha 는 더 이상 쓰지 않는다. 예전에는 카드 그림자와 표 머리 배경을 alpha 로 지어냈는데
 * (`alpha(black,.06)`, `alpha(primary,.04)`), 둘 다 기준선에 없는 색이었다. 이제 그림자는
 * --shadow-sm, 표 머리는 --surface-2 를 그대로 쓴다. 다시 넣기 전에 기준선부터 확인해라. */
import { createTheme } from "@mui/material/styles";

/* ClovirONE 디자인 테마 (MUI)
 *
 * 색·타이포·컴포넌트 규칙의 단일 출처다. 예전에는 CSS 커스텀 프로퍼티(tokens.css)와
 * 서버 렌더 페이지용 사본(app/static/css/tokens.css) 두 벌이 따로 굴러가며 서로 어긋났다.
 * 이제 SPA 쪽은 이 파일 하나만 본다.
 *
 * ⚠️ 이 파일의 색·그림자·반지름은 **전부 `design/baseline/preview-standalone.html` 에서
 * 온 값**이다. 눈대중으로 고르지 않는다. 예전에 여기서 배경을 #F3F6FF 로, 본문색을
 * #1B2235 로 "비슷하게" 적어 두고 기준선과 같다고 결론 냈는데, 기준선은 각각 #F5F7FC,
 * #20263A 였다. 값을 바꾸려면 기준선 파일을 먼저 고쳐라 - `theme-baseline.test.js` 가
 * 그 파일을 파싱해서 여기 값과 대조한다.
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

/* 기준선 --radius-sm/-md/-lg. 카드는 lg(18), 입력·버튼은 10px(기준선 .field/.btn 이
 * 토큰이 아니라 리터럴로 적어 둔 값이다), 나머지 기본값은 md(12) 다.
 * full(PA-RC-0001, RD-3) — 아바타·pill 배지처럼 "완전히 둥글게"는 md/lg 배율이 아니라
 * 별도 의미 슬롯이다. 999는 어떤 높이에서도 알약 모양이 되게 하는 관용값(대비되는 px
 * 반지름을 굳이 계산하지 않아도 된다) — 기준선에 이 값 자체는 없지만 실제로 쓰이는
 * 값(예: --radius-pill: 999px, app/static/css/tokens.css:134)과 같은 관용이다. */
export const RADIUS = { sm: 8, md: 12, lg: 18, full: 999 };

/* fontWeight 값이 파일 70개에 걸쳐 원시 숫자로 흩어져 있다(700이 최다, 그 외 750/800/600/
 * 400/650/500/780 등 — DS-05). 여기서 한꺼번에 옮기지는 않는다(호출부 70여 곳을 한 번에
 * 바꾸는 건 이 정리의 범위 밖) — 새로 쓰는 자리와 kit.jsx 자신이 우선 이 토큰을 쓰게 한다.
 * h1~h6/button 자체의 굵기 배율(아래 typography 설정)은 건드리지 않는다 — 그건 베이스라인이
 * 정한 값이라 별개다. */
export const FONT_WEIGHT = { regular: 400, medium: 500, semibold: 600, bold: 700, extrabold: 800 };

/* PA-RC-0001 — 글자 크기 15종이 화면 전반에 리터럴로 흩어져(31종·278회, 11~17px 사이
 * 1px 연속체) 위계가 지각 임계 이하로 눌렸다. Product Audit의 재양자화 확정값(RD-1)을
 * 그대로 쓴다: 12 caption / 13 bodySm / 14 body / 17 sectionTitle / 20 pageTitle / 30
 * statValue(브랜드 워드마크의 62px는 이 스케일 밖 — 로고 전용).
 *
 * caption(MUI 기본과 동일)·bodySm/body(아래 typography의 body2/body1과 동일)·
 * pageTitle(h6와 동일)은 **이미 존재하는 값과 겹친다** — 새 상수를 만드는 이유는
 * body1/body2/h6 같은 MUI 이름이 "몇 번째 본문인가"만 말하고 "지금 어떤 의미로 쓰는가"를
 * 말하지 않기 때문이다(그래서 리터럴이 더 쉬운 선택이 됐다 — PA-F-013). sectionTitle·
 * statValue는 기존에 대응하는 MUI variant가 없어 정말 새로 필요했다.
 *
 * ⚠️ 이름 혼동 주의: 여기 pageTitle(20px, h6)은 `PageHeader`(kit.jsx)가 그리는 **화면
 * 맨 위 제목**(h4, 기준선 .page-title, clamp(24~34px) — theme-baseline.test.js "화면
 * 제목의 상·하한"이 그 계약이다)과 **다른 것이다.** RD-1이 정한 이름을 그대로 썼을 뿐,
 * PageHeader의 그 제목과 바꿔 쓰면 안 된다 — 필요하면 "카드/패널 안의 20px 소제목" 같은
 * 국소적 의미로만 쓴다.
 *
 * 새 코드는 `sx={{ fontSize: FONT_SIZE.bodySm }}`로 직접 쓰거나, Typography라면
 * `variant="sectionTitle"`처럼 쓴다(MUI는 `theme.typography[variant]`가 있으면 그 값을
 * 그대로 렌더한다 — TS 프로젝트의 모듈 보강 없이도 런타임에서는 동작한다).
 * `variant="body1"`을 쓰는 기존 화면 수십 곳이 있어 body1/body2 이름 자체는 바꾸지
 * 않는다(바꾸면 그 화면들이 전부 깨진다) — 이 상수는 나란히 놓는 새 이름일 뿐이다.
 *
 * 이번 커밋에서 kit.jsx만 이 상수로 옮긴다. 나머지 호출부(약 270여 곳)는 아직 리터럴로
 * 남아 있다 — RADIUS·FONT_WEIGHT와 같은 이유로 한꺼번에 옮기지 않는다(위 주석 참고).
 * docs/BACKLOG.md PA-01이 남은 범위를 추적한다. */
export const FONT_SIZE = {
  caption: "0.75rem",
  bodySm: "0.8125rem",
  body: "0.875rem",
  sectionTitle: "1.0625rem",
  pageTitle: "1.25rem",
  statValue: "1.875rem",
};

/* 기준선 --brand-*. --brand-accent 만 런타임 강조색으로 덮인다
 * (기준선 render(): documentElement.style.setProperty('--brand-accent', state.accent)). */
const BRAND = { deep: "#17204D", mid: "#293B8D", purple: "#8E75E1", mint: "#62C7BD" };

/* 기준선 --shadow-sm/-md/-lg. 라이트는 잉크색(19,28,56)이 섞인 그림자고 다크는 순수 검정이다. */
const SHADOW = {
  light: {
    sm: "0 1px 3px rgba(19,28,56,.08)",
    md: "0 10px 28px rgba(19,28,56,.12)",
    lg: "0 24px 60px rgba(19,28,56,.18)",
  },
  dark: {
    sm: "0 1px 3px rgba(0,0,0,.4)",
    md: "0 12px 32px rgba(0,0,0,.4)",
    lg: "0 28px 70px rgba(0,0,0,.55)",
  },
};

/* MUI 는 elevation 0~24 를 요구하는데 기준선에는 sm·md·lg 셋뿐이다. 어느 단계에 무엇을
 * 놓을지는 기준선에 없어서 우리가 정한다 - 기준선의 실제 쓰임(카드=sm, FAB·팝오버=md,
 * 드로어·커맨드팔레트=lg)에 맞춰 MUI 관례(메뉴 8, 드로어 16, 모달 24)와 겹치게 나눴다. */
function shadowScale({ sm, md, lg }) {
  return ["none", ...Array(4).fill(sm), ...Array(11).fill(md), ...Array(9).fill(lg)];
}

/* 기준선의 `color-mix(in srgb, A p%, B)` 와 같은 계산.
 *
 * srgb 보간은 감마 인코딩된 채널의 가중 평균이다(선형화하지 않는다). 이 함수가 필요한
 * 이유는 기준선이 --primary-strong / --primary-soft 를 **강조색에서 유도**하기 때문이다:
 *   --primary-strong: color-mix(in srgb, var(--primary) 78%, #17204d)
 *   --primary-soft:   color-mix(in srgb, var(--primary) 12%, var(--surface))
 * 결과값을 상수로 박아 두면 사용자가 강조색 프리셋을 바꿨을 때 파생색만 기본색에 남는다
 * (지금 코드가 그랬다 - dark 를 #4058BD 로 고정해 뒀다). */
function mixSrgb(from, to, ratio) {
  const channels = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const target = channels(to);
  return `#${channels(from)
    .map((value, i) => Math.round(value * ratio + target[i] * (1 - ratio)))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("")}`;
}

/* 기준선 :root / [data-theme="dark"] 의 색 토큰을 그대로 옮긴 것.
 *
 * --primary 는 여기 없다. 기준선 미리보기도 실행할 때마다 :root 인라인 스타일로
 * --primary 를 강조색으로 덮어쓰므로(인라인 스타일이 [data-theme="dark"] 규칙을 이긴다),
 * 두 모드 모두 런타임 강조색이 곧 primary 다. */
const TOKENS = {
  light: {
    surface: "#FFFFFF",
    surface2: "#F8FAFF",
    surface3: "#EEF2F8",
    bg: "#F5F7FC",
    text: "#20263A",
    muted: "#667085",
    border: "#DFE4EF",
    borderStrong: "#CBD3E3",
    accent: "#8E75E1",
    cyan: "#58A9C4",
    success: "#16865C",
    successBg: "#EAF8F1",
    warning: "#B15B09",
    warningBg: "#FFF5E6",
    danger: "#C63D4E",
    dangerBg: "#FFF0F2",
    info: "#3167C9",
    infoBg: "#EDF3FF",
    sidebar: "#111831",
    sidebarText: "#DBE2FF",
    sidebarMuted: "#96A0C6",
    sidebarHover: "rgba(255,255,255,.08)",
    /* --primary-strong 은 라이트에서 --brand-deep 을 22% 섞고, 다크에서는 흰색을 28%
     * 섞는다. 그래서 다크에서는 primary 보다 **밝다** - MUI 이름이 다크 라서 헷갈리지만
     * 기준선이 그 슬롯을 "읽히는 강조색"으로 쓴다(.btn.ghost, .tab.is-on, .link-button). */
    strongMix: [BRAND.deep, 0.78],
    softMix: 0.12,
    /* 포커스 링 전용(KBD-01/02/03). tokens.css --color-primary-soft 와 동일한 리터럴이다 —
     * 기준선의 `:focus-visible { outline: 3px solid color-mix(in srgb, primary 70%, white) }`
     * 공식 그대로는 흰 배경 대비 2.76(3:1 미달)이라, tokens.css가 실측으로 검증해 둔 값
     * (흰 배경 대비 3.2)을 그대로 가져온다 — 새로 계산하지 않는다(두 파일이 각자 계산하면
     * 서로 다른 값이 나올 위험이 있다). palette.primary.soft(12% 배경 틴트, 대비 1.05)는
     * 별개 용도이고 포커스 링에는 못 쓴다 — KBD-01 감사가 바로 그 틴트의 대비 미달을 지적했다. */
    focusRing: "#758AE1",
  },
  dark: {
    surface: "#11182D",
    surface2: "#151E37",
    surface3: "#1D2948",
    bg: "#090E1D",
    text: "#EEF1FB",
    muted: "#A4AEC7",
    border: "#2B3655",
    borderStrong: "#3A476B",
    accent: "#B6A3FF",
    cyan: "#72C0D7",
    success: "#65D8A6",
    successBg: "#15382F",
    warning: "#F6BD67",
    warningBg: "#3B2C17",
    danger: "#FF8B9B",
    dangerBg: "#3D2029",
    info: "#92B5FF",
    infoBg: "#1D315B",
    sidebar: "#070B18",
    sidebarText: "#EDF0FF",
    sidebarMuted: "#9CA7C8",
    sidebarHover: "rgba(255,255,255,.1)",
    strongMix: ["#FFFFFF", 0.72],
    softMix: 0.18,
    /* tokens.css [data-theme="dark"] --color-primary-soft 와 동일 리터럴(포커스 링 전용). */
    focusRing: "#536CD6",
  },
};

/* 사이드바가 서랍(temporary)으로 바뀌는 지점. 디자인 사양서와 기존 앱이 모두 860px이다.
 * MUI의 lg(1200)를 쓰면 1024×768·1152×720 사내 장비에서 사이드바가 새로 사라진다. */
export const NAV_BREAKPOINT = 860;

export const BREAKPOINTS = { xs: 0, sm: 600, md: 900, lg: 1200, xl: 1536, xxl: 2200, uhd: 3000 };

/* 표가 카드 목록으로 접히는 지점 — kit.jsx의 DataTable과 MyTickets.jsx의 GroupedTickets가
 * 각자 "(max-width:899.95px)" 리터럴을 따로 갖고 있었다(DS-11) — BREAKPOINTS.md(900)에서
 * 값을 뽑아 한 곳만 고치면 둘 다 따라오게 한다. 899.95는 MUI가 `down("md")`에서 생성하는
 * 정확한 값(0.05px 겹침 방지)과 같다. */
export const TABLE_CARD_QUERY = `(max-width:${BREAKPOINTS.md - 0.05}px)`;

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
  const t = light ? TOKENS.light : TOKENS.dark;
  const shadows = light ? SHADOW.light : SHADOW.dark;
  const primaryStrong = mixSrgb(primary, t.strongMix[0], t.strongMix[1]);
  const primarySoft = mixSrgb(primary, t.surface, t.softMix);

  return createTheme({
    breakpoints: {
      keys: ["xs", "sm", "md", "lg", "xl", "xxl", "uhd"],
      values: BREAKPOINTS,
    },
    /* MUI 기본은 8px 그리드다. rem으로 바꾸되 배율은 그대로 유지해서(0.5rem = 16px 루트에서
     * 8px) 이식해 오는 sx={{ p: 2 }} 같은 값이 같은 크기로 보이게 한다. */
    spacing: (factor) => `${0.5 * factor}rem`,
    /* 그림자 토큰을 테마에 그대로 얹는다. MUI 의 elevation 배열만으로는 "기준선의
     * shadow-md 를 달라"고 쓸 수 없어서, 화면 코드가 제각각 그림자를 지어냈다. */
    shadowTokens: shadows,
    shadows: shadowScale(shadows),
    palette: {
      mode,
      /* dark = 기준선 --primary-strong, soft = --primary-soft. 둘 다 강조색에서 파생된다.
       * light 는 기준선에 토큰이 없다 - 로그인 제출 버튼 그라데이션(.auth-submit)의
       * 첫 정지점 리터럴 #758AE1 을 그대로 쓴다. */
      primary: { main: primary, dark: primaryStrong, light: "#758AE1", soft: primarySoft },
      secondary: { main: t.accent },
      /* `strong`: `.main`은 칩 배경(색 있는 면 위 흰 글자, 대비 문제 없음)엔 맞지만 작은
       * 글자색으로 그대로 쓰면(예: StatCard의 「주의」/「위험」 배지) primaryStrong과 똑같은
       * 이유로 근소 미달한다 — QAH-03(2026-08-11 하네스 실측): 라이트 warning `.main`이
       * 표면에 따라 4.48~4.6로 WCAG AA 4.5 경계에 걸쳐 있었다. primaryStrong과 같은 배합
       * (t.strongMix — 라이트는 brand-deep 22%, 다크는 흰색 28%)을 세 톤에도 그대로 적용해
       * 라이트 5.7~6.7, 다크 9.2~12로 확실한 여유를 둔다. */
      success: { main: t.success, bg: t.successBg, strong: mixSrgb(t.success, t.strongMix[0], t.strongMix[1]) },
      warning: { main: t.warning, bg: t.warningBg, strong: mixSrgb(t.warning, t.strongMix[0], t.strongMix[1]) },
      error: { main: t.danger, bg: t.dangerBg, strong: mixSrgb(t.danger, t.strongMix[0], t.strongMix[1]) },
      info: { main: t.info, bg: t.infoBg },
      cyan: t.cyan,
      /* 기준선은 표면이 셋이다. 카드(--surface)는 정말 흰색이고, 위계는 표 머리·칸반 열·
       * 채팅 곁열·팝오버 바닥이 쓰는 --surface-2 와 칩·진행바 트랙·말풍선·스켈레톤이 쓰는
       * --surface-3 이 만든다. 우리는 이 둘이 아예 없어서 화면이 통째로 흰 판이었다. */
      background: {
        default: t.bg,
        paper: t.surface,
        surface2: t.surface2,
        surface3: t.surface3,
      },
      text: { primary: t.text, secondary: t.muted },
      divider: t.border,
      dividerStrong: t.borderStrong,
      /* 사이드바는 두 모드 모두 짙은 남색이다(라이트에서도 어둡다). 밝은 배경 위 규칙을
       * 그대로 쓰면 글자가 안 보이므로 전용 토큰을 둔다. */
      sidebar: { bg: t.sidebar, text: t.sidebarText, muted: t.sidebarMuted, hover: t.sidebarHover },
      brand: { accent: primary, ...BRAND },
    },
    shape: { borderRadius: RADIUS.md },
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
      h5: { fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.015em" },
      h6: { fontWeight: FONT_WEIGHT.bold },
      /* 본문 14px. MUI 기본은 body1 = 1rem(16px) 이지만 기준 목업은 `body { font-size:14px }`
       * 다 — 대조에서 34/34 화면이 어긋났다. 업무용 밀도가 높은 화면이라 기준이 맞다.
       *
       * rem 을 그대로 두고 body1 만 내린다. 루트 폰트사이즈(16px)를 건드리면 rem 기반
       * 간격·아이콘·브레이크포인트가 전부 따라 움직여 레이아웃이 통째로 흔들린다.
       * body2 는 이미 0.875rem 이라 그대로 두면 body1 과 같아지므로 보조 텍스트를
       * 한 단 더 내려 위계를 유지한다. */
      /* 자간은 기준선의 `body { letter-spacing: -.012em }` 이다. MUI 기본은 +0.00938em 이라
       * 반대 방향으로 벌어져 있었다. 한글은 자간이 벌어지면 눈에 띄게 헐거워 보인다. */
      body1: { fontSize: FONT_SIZE.body, lineHeight: 1.5, letterSpacing: "-0.012em" },
      body2: { fontSize: FONT_SIZE.bodySm, lineHeight: 1.5, letterSpacing: "-0.012em" },
      button: { textTransform: "none", fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.012em" },
      /* PA-RC-0001(RD-1) — 기존 MUI variant에 대응이 없던 두 단계. `variant="sectionTitle"`/
       * `variant="statValue"`로 쓴다. FONT_SIZE 위 주석 참고. */
      sectionTitle: { fontSize: FONT_SIZE.sectionTitle, fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.012em" },
      statValue: { fontSize: FONT_SIZE.statValue, fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.02em" },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          html: { minWidth: 320 },
          /* 기준선은 자간을 `body` 에 걸어 문서 전체에 물려준다(`letter-spacing: -.012em`).
           * Typography 를 쓰지 않는 태그(표 셀, 목록, 원시 텍스트)까지 같이 좁아진다. */
          body: { minWidth: 320, letterSpacing: "-0.012em" },
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
           * 덮는 색은 **입력칸의 실제 배경(기준선 .field 는 --surface)** 이어야 한다.
           * transition 5000s 는 자동완성 직후 노란색이 한 번 번쩍이는 것을 막는 관용구다. */
          "input:-webkit-autofill, input:-webkit-autofill:hover, input:-webkit-autofill:focus, input:-webkit-autofill:active, textarea:-webkit-autofill, select:-webkit-autofill":
            {
              WebkitBoxShadow: `0 0 0 1000px ${t.surface} inset`,
              boxShadow: `0 0 0 1000px ${t.surface} inset`,
              WebkitTextFillColor: t.text,
              caretColor: t.text,
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
      /* 키보드 포커스 링(KBD-01/02/03).
       *
       * MUI ButtonBase 의 기본 root 스타일은 `outline: 0` 을 **항상**(포커스 상태와 무관하게)
       * 깐다 - 마우스 클릭 시 링이 뜨는 것을 막으려는 의도지만, 결과적으로 Button·IconButton·
       * ListItemButton·MenuItem·Tab·Chip(clickable)·Fab·Checkbox/Radio/Switch 등 ButtonBase를
       * 상속하는 모든 컴포넌트가 **키보드 포커스에서도** 링을 잃는다(감사: 정지점 45개 중
       * 38~45개가 `outline:0`+`boxShadow:none`). 유일한 표시는 MUI 기본 action.focusOpacity
       * (12% 배경 틴트, `palette.primary.soft`)인데 대비 1.05(라이트)/1.45(다크)로 WCAG
       * 1.4.11 최소 3:1 의 1/3 수준이다.
       *
       * 고치는 법은 MUI 공식 패턴대로 `.Mui-focusVisible`(마우스 클릭은 안 걸리고 키보드 탭에만
       * 걸리는 클래스)에만 별도 outline 을 준다 - hover 배경 틴트는 그대로 두므로 focus 와
       * hover 가 저절로 구별된다(KBD-02). 색은 위 focusRing 토큰(tokens.css --color-primary-soft
       * 와 동일 리터럴, 실측 대비 3.2:1) 을 쓴다 - 12% 틴트가 아니다.
       *
       * `MuiButtonBase` 하나에 거는 이유: 개별 컴포넌트(MuiButton/MuiIconButton/…)마다 따로
       * 걸면 ButtonBase 를 상속하는 컴포넌트를 하나씩 찾아 빠짐없이 걸어야 한다 - 이미 여러
       * 화면(BoardPost.jsx·ChatPane.jsx·ChatRooms.jsx·TicketAttachments.jsx 등)이 각자
       * `sx={{ "&:focus-visible": {...} }}` 로 개별 처방해 둔 것이 바로 그 증거다(KBD-03,
       * "MUI 컴포넌트는 그 목록에 없다"). 여기서 기본값을 주면 그 화면들의 개별 처방은 sx prop
       * 특이도가 더 높아 그대로 우선 적용되고, 나머지 전부가 새 기본값을 받는다. */
      MuiButtonBase: {
        styleOverrides: {
          root: {
            "&.Mui-focusVisible": {
              outline: `3px solid ${t.focusRing}`,
              outlineOffset: 2,
            },
          },
        },
      },
      /* MuiLink 는 ButtonBase 를 상속하지 않는다(Typography 기반 앵커) - 위 MuiButtonBase
       * 규칙이 안 닿는다. 네이티브 `:focus-visible` 을 그대로 쓴다(MUI 가 outline 을 0 으로
       * 깔지 않으므로 hasOutline 검사가 이미 통과할 수도 있지만, 색이 브라우저 기본 파란색이라
       * 제품 팔레트와 안 맞고 대비도 검증 안 된 값이었다). */
      MuiLink: {
        styleOverrides: {
          root: {
            /* CTR-01/CTR-04: color를 안 주면 MUI가 자기 기본값(color="primary" →
             * palette.primary.main, 즉 사용자가 고른 원본 accent hex)으로 렌더한다 — 다크
             * 카드/표면 위에서 3.52~3.76:1, 라이트 배경 위에서도 4.37:1로 WCAG AA 4.5:1
             * 미달(실측 확인). primaryStrong은 각 모드에서 명시적으로 대비를 올려 섞은
             * 변수(라이트: 어둡게, 다크: 밝게 — 위 strongMix 계산)라 4.81~6.77로 통과한다.
             * MuiButton의 containedPrimary hover가 이미 같은 토큰을 대비 개선 용도로 쓴다. */
            color: primaryStrong,
            "&:focus-visible": {
              outline: `3px solid ${t.focusRing}`,
              outlineOffset: 2,
            },
          },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          /* 기준선 `.btn { min-height:40px; border-radius:10px }`. 10 은 --radius-sm(8) 도
           * --radius-md(12) 도 아닌 리터럴이다 - 기준선이 그렇게 적어 뒀다. */
          root: { minHeight: 40, borderRadius: 10 },
          /* 기준선의 제품 버튼은 **단색**이다: `.btn.primary { background: var(--primary) }`,
           * 호버는 --primary-strong. 그라데이션은 로그인 제출 버튼(.auth-submit)에만 있고,
           * 그 화면은 Jinja 라 이 테마가 닿지 않는다. 예전 값은 그 그라데이션을 제품 화면
           * 전체에 옮겨 붙인 것이라 기준선에 없는 모양이었다. */
          containedPrimary: {
            background: primary,
            boxShadow: "none",
            "&:hover": { background: primaryStrong, boxShadow: "none" },
          },
          /* CTR-01/04와 같은 원인, 다른 컴포넌트: `variant`/`color`를 안 주면(기본값
           * text+primary) MUI가 이 텍스트 색도 palette.primary.main 원본 accent로 렌더한다 —
           * QAH-03(2026-08-11 하네스 실측)에서 68/68 라우트, 표본의 절반 이상(262/519)이
           * 이 패턴(`a.MuiButtonBase-root`, href가 있는 Button은 <a>로 렌더된다)이었다.
           * containedPrimary는 흰 글자라 무관 — 텍스트 자체가 accent 색인 text/outlined만
           * MuiLink와 같은 primaryStrong으로 맞춘다. */
          textPrimary: { color: primaryStrong },
          outlinedPrimary: { color: primaryStrong },
        },
      },
      MuiOutlinedInput: {
        /* 기준선은 `.field { background: var(--surface) }` 인데, 카드도 --surface 라 흰
         * 카드 위에서 입력칸이 안 보인다는 문제가 실사용에서 나왔다(사용자 확인, 08-07).
         * 그래서 카드와 구별되는 --surface-2(#F8FAFF)를 쓴다 - 원래 로그인 입력의 색이지만
         * "카드 위에서 입력칸을 알아볼 수 있어야 한다"는 요구가 기준선의 문자 그대로보다
         * 우선한다고 판단했다. */
        styleOverrides: {
          root: {
            borderRadius: 10,
            background: t.surface2,
            /* 입력칸도 KBD-01 감사 대상이다("MUI 컴포넌트(버튼·링크·입력)"). MUI 기본은 포커스
             * 시 <fieldset> 테두리 색만 primary 로 바뀐다(`Mui-focused`) - 색 대비는 나지만
             * outline/box-shadow 가 없어 실측 스크립트(scripts/ui_qa/keyboard.py 의 ACTIVE
             * 평가식)가 "표시 없음"으로 잡는다. 테두리 변화는 그대로 두고 outline 을 더한다 -
             * kit.css 의 `.k-input:focus-visible` 과 같은 처방(2px, offset 0, primary-soft). */
            "&.Mui-focused": {
              outline: `2px solid ${t.focusRing}`,
              outlineOffset: 0,
            },
          },
        },
      },
      MuiCard: {
        /* 기준선 `.card { background: var(--surface); border: 1px solid var(--border);
         * border-radius: var(--radius-lg); box-shadow: var(--shadow-sm) }`. */
        styleOverrides: {
          root: ({ theme }) => ({
            border: `1px solid ${theme.palette.divider}`,
            boxShadow: theme.shadowTokens.sm,
            borderRadius: RADIUS.lg,
            backgroundImage: "none",
          }),
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: { backgroundImage: "none" },
          /* `StatCard` 는 `Paper variant="outlined"` 라 shape.borderRadius 를 받고
           * 그림자가 없었다. 옆에 놓이는 `Card` 는 18px + 그림자다 — 같은 격자 안에서
           * 두 종류의 카드가 위아래로 붙어 있는 것이 기준 대조의 "카드 반지름 종류 수"
           * 와 "그림자 비율 100% → 20~44%" 를 만든 원인이다(K-C1).
           * 기준 목업은 `.card` 하나뿐이고 전부 radius-lg(18px) + shadow-sm 이다. */
          outlined: ({ theme }) => ({
            borderRadius: RADIUS.lg,
            boxShadow: theme.shadowTokens.sm,
          }),
        },
      },
      MuiChip: { styleOverrides: { root: { borderRadius: RADIUS.full, fontWeight: FONT_WEIGHT.bold } } },
      MuiDrawer: { styleOverrides: { paper: { backgroundImage: "none" } } },
      MuiTableCell: {
        styleOverrides: {
          /* 기준선 `th { background: var(--surface-2); color: var(--muted); font-size: 11px;
           * letter-spacing: .02em }`. 예전 값은 primary 를 4% 섞은 파란 기가 도는 색이라
           * 표 머리만 강조색 계열로 떠 보였다 - 기준선은 중립적인 보조 표면을 쓴다. */
          head: ({ theme }) => ({
            color: theme.palette.text.secondary,
            fontSize: "0.6875rem",
            fontWeight: FONT_WEIGHT.bold,
            letterSpacing: "0.02em",
            background: theme.palette.background.surface2,
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
      /* PA-RC-0012: `variant="h6"`은 시각 크기 선택이면서 동시에(component= 없으면) `<h6>`
       * 태그도 결정해 버려, 문서 구조를 의도치 않게 네 단계(h1→h6) 건너뛰게 만든 사례가
       * 다섯 화면에 있었다. `sectionTitle`(PA-RC-0001, 카드 소제목 전용 variant)은 의미상
       * 항상 h2~h3 수준의 구역 제목이므로 기본 태그를 h2로 못박는다 — 호출부가 실수로
       * component=를 빠뜨려도 옳은 태그가 나간다. MUI Typography는 `variantMapping[variant]
       * || defaultVariantMapping[variant]`로 폴백하므로(node_modules/@mui/material/
       * Typography/Typography.js) 여기 h6 등 표준 variant를 다시 안 적어도 그쪽 매핑은
       * 안 건드린다 — sectionTitle 하나만 추가한다. */
      MuiTypography: { defaultProps: { variantMapping: { sectionTitle: "h2" } } },
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

/* 상세 화면 곁열(속성·활동 레일)의 폭은 이제 `ui/density.js` 의 `BASELINE_TRACKS.detail`
 * (기준선 `.ticket-layout`)이 정한다. 여기 있던 `DETAIL_RAIL_MAX_WIDTH = "26rem"` 는 지웠다.
 *
 * 왜 지웠나 — 그 상수는 "레일이 남는 폭을 전부 가져가 본문보다 넓어진다"(Q1)를 막으려고
 * 레일에 **고정 상한**을 준 것이었다. 그런데 본문 트랙도 78ch 고정 상한이라, 두 트랙의
 * 상한 합이 컨테이너보다 작아지는 순간 격자가 오른쪽을 통째로 비웠다. 사용자가 본
 * "티켓·문서 상세가 왼쪽으로 쏠려있다"가 그것이다. 기준선처럼 두 트랙을 비율(1.5 : 0.65)로
 * 두면 본문이 레일의 2.3배라 Q1 도 그대로 지켜지면서 폭도 남지 않는다. */

/* 마스코트 FAB이 차지하는 오른쪽 아래 영역의 높이.
 *
 * FAB은 position:fixed 라 문서 흐름 밖에 있다. 셸이 본문에 하단 여백을 줘도, 화면이
 * 100vh 로 자기 높이를 직접 계산하면 그 여백을 벗어나 FAB 밑으로 들어간다. 실제로
 * 놀이방 채팅의 '보내기' 버튼이 그렇게 깔렸고, 클릭이 FAB에 가로채졌다.
 *
 * 그래서 **높이를 직접 계산하는 화면은 이 값을 함께 빼야 한다.** QA 하네스의
 * fab_overlap 검사가 어긴 화면을 잡는다(겹치기만 하는 건 통과, 못 누르게 되면 실패). */
export const FAB_CLEARANCE = "5rem";
