import { createTheme } from "@mui/material/styles";

/* ClovirAssist 디자인 테마 — 방향 "인디고 계측면(Indigo Instrument)"
 * (docs/DECISIONS.md D-141 → D-179 로 방향 갱신)
 *
 * ## 이 파일이 정본이다
 *
 * 색·타이포·간격·모서리·그림자·모션의 **단일 출처**다. `styles/tokens.css` 와
 * `app/static/css/tokens.css` 는 `scripts/generate_design_tokens.mjs` 가 여기서 만든다.
 * 손으로 고치지 마라 — 다음 생성에서 조용히 되돌아간다.
 *
 * ## 방향 계약 (D-179 — D-141 의 계측 규율은 유지하고 Thesis 만 바꾼다)
 *
 *   THESIS     이 화면은 판독 장치이고, **그 계측기의 하우징이 ClovirAssist 인디고다.**
 *              상단바와 사이드바가 하나의 L자 Brand 오브젝트로 연결되고, 그 안에 차가운
 *              인디고 계열 Work Canvas 가 놓인다.
 *   OWN-WORLD  데이터는 흰 판 위에서 무채색·정밀하게 유지한다. Brand 채도는 바깥(Frame)
 *              으로 갈수록 강해지고, 안쪽으로는 **제품이 곧 Brand 인 세 자리** —
 *              Primary Action · 현재 선택 · Clovi/AI — 에서만 나타난다.
 *
 * D-141 에서 **유지하는 것**: tabular numerals · 선 위주 위계 · 판에 그림자 없음 ·
 * 선택 신호 하나 · 모든 색쌍 실측. **바꾸는 것**: chrome 이 캔버스 계열 무채색이라는 규칙.
 * 그 규칙이 있는 동안 로고를 가리면 화면이 아무 제품도 아니었다 — Before 측정에서
 * `brand_presence` 는 1,494장 중 1,452장이 실패했고 통과한 42장은 전부 로그인 화면이었다.
 *
 * **반증 가능한 판정 기준**: `blue(chrome.shell) − red(chrome.shell) ≥ 24`.
 * 옛 `#E7EAEE` 는 7 이라 실패하고 새 `#1E2758` 은 58 이라 통과한다. 이 단언이 없었기
 * 때문에 "chrome 은 발광하지 않는다"는 결정이 "제품에 Brand 가 없다"로 미끄러진 것을
 * 아무 시험도 잡지 못했다. `theme-contract.test.js` 가 이 값을 단언한다.
 *
 * ## Brand Identity 와 사용자 Accent 는 다른 계층이다
 *
 *   palette.chrome / palette.brand   **고정.** 사용자 입력으로 바꿀 수 없다. Shell·워드마크·
 *                                    Clovi Halo·AI 면·Chart 주요 시리즈·Brand Tint 를 소유한다.
 *   palette.primary                  사용자 Accent(`/my-display`). Button·Link·Focus Ring·
 *                                    Tab Indicator·선택 Row Wash·Checkbox/Switch 를 소유한다.
 *
 * 이 분리가 막는 실패는 둘이다 — 사용자가 청록을 고르면 제품이 ClovirAssist 가 아니게 되는
 * 것, 그리고 모두에게 같은 Accent 를 강제하는 것. Accent 기능은 없어지지 않고 **역할을
 * 얻는다.** `theme-contract.test.js` 가 "Accent 를 바꿔도 Brand 는 그대로"를 단언한다.
 *
 * ## 4K(3840×2160)
 *   · 브레이크포인트 xxl(2200)·uhd(3000) 추가. MUI 기본 5개는 이름·값 그대로 둔다.
 *   · spacing 이 rem 이라 `styles/root.css` 의 루트 폰트사이즈 미디어쿼리 하나로 글자와
 *     여백이 함께 커진다. borderRadius 는 의도적으로 px 다 — 모서리는 같이 커지면 안 된다.
 */

/* 새 기본 Accent. 색상각 ≈245°, 진짜 인디고-바이올렛이고 흰 글자 대비 6.08:1 이다
 * (옛 기본값 `#536CD6` 은 4.68:1 이었다). */
export const DEFAULT_ACCENT = "#5A4FCF";
/* 계정별 강조색 프리셋 — **기존 값을 하나도 제거하지 않는다.** 사용자가 고른 색은
 * localStorage 에 hex 로 남고(`/my-display`), `settingsRegistry.js::ACCENT_NAMES` 가 이
 * hex 들에 한국어 이름을 붙인다. 목록에서 hex 하나를 빼면 그 색을 이미 고른 사람의 화면에서
 * "선택됨" 표시가 사라지고 이름도 hex 로 떨어진다. 다섯 값 전부 새 팔레트에서 AA 를 넘는
 * 것을 실측 확인했다(theme-contract.test.js 가 프리셋 전체 × 두 모드로 계속 검증한다). */
export const ACCENT_PRESETS = ["#5A4FCF", "#536CD6", "#4058BD", "#6B5BC7", "#327C98"];

export function normalizeAccent(value) {
  const candidate = String(value || "").trim();
  return /^#[0-9A-Fa-f]{6}$/.test(candidate) ? candidate.toUpperCase() : DEFAULT_ACCENT;
}

/* 모서리 — 4개 의미 슬롯.
 *   sm   입력·버튼·칩          6
 *   md   판(plate)·패널        8   ← MUI 기본 shape
 *   lg   떠 있는 것(모달·팝오버) 14
 *   full 아바타처럼 완전한 원   999
 * 계측 전면은 여전히 둥글지 않다. 다만 4/6/10 은 34~36px 컨트롤 옆에서 **모서리가 없는
 * 것처럼** 보였다 — 형태가 형태로 읽히는 최소치로 한 단계씩 올린다. */
export const RADIUS = { sm: 6, md: 8, lg: 14, full: 999 };

/* 굵기 — 5단계. extrabold 는 워드마크 전용 예외다(본문 위계에 쓰지 않는다). */
export const FONT_WEIGHT = { regular: 400, medium: 500, semibold: 600, bold: 700, extrabold: 800 };

/* 글자 크기 — 7개 **역할 이름** 슬롯. 크기가 아니라 쓰임으로 부른다.
 *
 * 옛 스케일의 실제 결함은 "14px 가 작다"가 아니라 **7단계 중 4단계가 3px 밴드
 * (11/12/13/14) 안에 몰려 있어 위계 일을 전혀 안 한다**는 것이었다. `body 14 → title 17`
 * 이 1.21배라 구획 제목이 제목으로 읽히지 않고 화면 전체가 한 겹 질감이 됐다. 그리고
 * 11px micro 는 한글에 실제로 너무 작다 — `tiny_text` 검사가 폭 ≥2200 에서만 돌아
 * 1920 에서 안 잡혔을 뿐이다.
 *
 *   micro      0.75rem   (@16 = 12)  셀 내부 배지/메타. **절대 하한.**
 *   caption    0.8125rem (13)        라벨·각주·breadcrumb·nav group
 *   bodySm     0.875rem  (14)        밀집 표 칸
 *   body       0.9375rem (15)        기본 본문·nav 라벨·입력값
 *   title      1.1875rem (19)        구획 제목
 *   pageTitle  1.75rem   (28)        화면 제목
 *   readout    2.5rem    (40)        그 화면을 지배하는 판독값 하나
 *
 * 머리쪽 배율이 1.27× / 1.47× / 1.43× 로 열려 제목이 실제로 앞선다. 슬롯 수 7은 그대로다.
 * clamp 를 쓰지 않는다 — Operate 모드에서 유동 제목은 손해고, 4K 확대는 루트 폰트사이즈
 * 레버가 담당한다. */
export const FONT_SIZE = {
  micro: "0.75rem",
  caption: "0.8125rem",
  bodySm: "0.875rem",
  body: "0.9375rem",
  title: "1.1875rem",
  pageTitle: "1.75rem",
  readout: "2.5rem",
};

/* 예전 이름 두 개는 소비처가 많아 별칭으로 남긴다. 새 코드는 title/readout 을 쓴다. */
FONT_SIZE.sectionTitle = FONT_SIZE.title;
FONT_SIZE.statValue = FONT_SIZE.readout;

/* 역할별 줄간격. 크기가 커질수록 좁아진다 — 40px 판독값에 1.5 를 주면 숫자 사이가 벌어져
 * 한 덩어리로 안 읽힌다. */
export const LINE_HEIGHT = {
  micro: 1.4,
  caption: 1.45,
  bodySm: 1.55,
  body: 1.6,
  title: 1.3,
  pageTitle: 1.22,
  readout: 1.05,
};

/* 컨트롤 높이 — 한 곳에 모은다. 예전에는 32/28/38 이 컴포넌트 오버라이드 안에 흩어져 있어
 * "이 제품의 컨트롤은 몇 px 인가"에 답할 자리가 없었다.
 * `iconButtonHit` 은 시각 크기가 아니라 **포인터 목표 크기**다(WCAG 2.2 Target Size).
 * IconButton 은 34px 로 그리고 `::after` 로 40px 를 잡는다 — 아이콘 열의 리듬을 깨지 않고
 * 목표만 넓힌다. */
export const CONTROL = {
  buttonSm: 30,
  button: 34,
  buttonLg: 40,
  input: 36,
  iconButton: 34,
  iconButtonHit: 40,
  tab: 40,
  navItem: 38,
  tableRow: 44,
  tableRowCompact: 36,
  /* 표 **안**의 컨트롤(인라인 편집 select·아이콘 버튼)은 44px 행 안에 들어가야 하므로
     일반 컨트롤(34/36)보다 작다. 배선은 W6 이 한다 — 값을 여기 두는 이유는 그때 새 리터럴이
     생기지 않게 하기 위해서다. */
  tableCellDense: 32,
};

/* 아이콘 크기 — 4개 **역할 이름** 슬롯 (지시 79). 크기가 아니라 쓰임으로 부른다.
 *
 *   nav     20  사이드바 글리프 · 팔레트 결과 유형
 *   inline  18  글자 줄 안에 끼는 표지(펼침 화살표 같은 것)
 *   action  20  버튼 안의 글리프
 *   hero    24  한 화면에 한 번 나오는 큰 표지
 *
 * **px 가 아니라 rem 으로 렌더한다.** `styles/root.css` 의 4K 레버가 루트 폰트사이즈를
 * 16→18→20 으로 올릴 때 아이콘만 px 로 남으면 틀만 1.25배가 되어 글리프가 상대적으로
 * 쪼그라들고(D-182 가 셸 컨트롤에서 겪은 것과 같은 결함), 반대로 **px 로 고정한 칸 안의
 * rem 글리프**는 칸을 넘쳐 라벨과 맞붙는다 — 3840 에서 실측된 F-W2R-02 가 정확히 그것이다.
 * 칸과 글리프가 같은 단위를 쓰게 `remPx()` 한 자리에서 변환한다.
 *
 * MUI `SvgIcon` 에는 `size` prop 이 **없다**(`fontSize` 다). `size={18} strokeWidth={1.8}` 는
 * 조용히 무시되는 죽은 prop 이었고 자식 아이콘 24px 가 부모 그룹 20px 보다 크게 나오도록
 * 구현을 오도했다(F-W1R-05). `scripts/check_icon_props.py` 가 그 형태 자체를 금지한다. */
export const ICON = { nav: 20, inline: 18, action: 20, hero: 24 };

/** px 계약값을 4K 레버가 따라오는 rem 문자열로. 값의 정본은 위 표 하나다. */
export function remPx(px) { return `${px / 16}rem`; }

/* 사이드바 항목의 **가로 해부구조** — PLAN «Icon System» 의 라벨 시작선 계약.
 *
 *   padInline 12 + glyph 20 + gap 10 = labelStart 42
 *
 * 그룹 헤더와 자식 항목의 라벨이 **같은 42px 열**에서 시작한다. 깊이는 그룹의 접힘 상태로
 * 표현하고 들여쓰기로 중복 표현하지 않는다 — 예전에는 그룹 60px / 자식 64px 로 4px 어긋나
 * 사이드바가 두 격자를 쓰는 것처럼 보였다(F-W1R-18 픽셀 실측). 자식은 글리프를 갖지
 * 않으므로(그룹이 가졌다) 그 자리를 padding 으로 채운다. 두 경로가 **같은 숫자 하나**에서
 * 나와야 다시 갈라지지 않는다.
 *
 * `rail` 은 활성 위치 신호다. 하우징 **가장자리**(inline-start 0)에 붙는다 — 목록 안쪽으로
 * 20px 들어와 떠 있으면 위치 신호가 아니라 조각으로 읽힌다. 이것도 rem 으로 그린다. */
export const NAV_ANATOMY = {
  padInline: 12,
  glyph: ICON.nav,
  gap: 10,
  labelStart: 42,
  rail: 3,
};

/* 숫자는 세로로 정렬되어야 읽힌다 — 표·지표·시각·ID. 계측 전면의 핵심 규율이다. */
export const NUMERIC = { fontVariantNumeric: "tabular-nums", fontFeatureSettings: '"tnum" 1' };

/* 모션 — 상태 전달용만. 장식하지 않는다. Operate 는 흐름 중이라 안무를 기다리지 않는다. */
export const MOTION = {
  instant: "90ms",
  fast: "140ms",
  base: "200ms",
  ease: "cubic-bezier(0.2, 0, 0.2, 1)",
};

/* ── Brand 고정색 ──────────────────────────────────────────────────────────
 *
 * 사용자 Accent 와 **절대 섞이지 않는다.** 로고·마스코트·Chart 주요 시리즈·AI 면이 이
 * 값들을 쓴다. 네 개는 기존 값 그대로다(로고 SVG 와 마스코트 자산이 이미 이 색으로
 * 출력돼 있어 바꾸면 자산과 화면이 어긋난다). */
const BRAND_FIXED = { deep: "#17204D", mid: "#293B8D", purple: "#8E75E1", mint: "#62C7BD" };

/* Brand 잉크 — 흰 판/오목면/캔버스/brandTint 위에 **글자로** 놓이는 Brand 색이다.
 * 위 네 개는 면(fill)용이라 글자로 쓰면 대비가 모자란다. 여섯 개 전부 두 모드 × 네 면에서
 * AA(4.5)를 넘는 것을 실측했다(최악 5.04:1 — light `core` on `brandTint`). */
const BRAND_INK = {
  light: {
    core: "#4C58C8",
    indigoInk: "#3B47A8",
    violetInk: "#6A4FC4",
    mintInk: "#1F6F68",
    pinkInk: "#9E3A62",
    wordmark: "#5A4FCF",
  },
  dark: {
    core: "#8E9BF2",
    indigoInk: "#A9B6F5",
    violetInk: "#C0AEF7",
    mintInk: "#7FD6C9",
    pinkInk: "#F4A8C6",
    wordmark: "#B7C4FA",
  },
};

/* ── Chrome — Top bar 와 Sidebar 는 같은 재료다 ────────────────────────────
 *
 * 만나는 모서리가 같은 색인 이유는 Top bar 의 채움이 Sidebar Gradient 의 **첫 stop** 이기
 * 때문이다. 이 값들은 Brand 고정이라 사용자 Accent 를 따르지 않는다.
 *
 * 실측 대비(Gradient **모든 stop** 기준):
 *   onShell       10.04~14.07   onShellMuted 6.17~8.22   onShellFaint 4.88~6.69
 *   #FFFFFF       11.71~17.18   rail(비텍스트 ≥3) 6.22~9.13
 * Hover Wash 합성 후 onShellMuted 5.20(L)/4.85(D) — 통과.
 * Selected Wash 와 AI Wash 합성 후 onShellMuted 는 4.62/4.26, 4.53/4.36 으로 **AA 미만**이다.
 * 그래서 하드 룰: **Selected 행과 AI Wash 영역 안의 텍스트는 전부 `onShell`.**
 * `onShellMuted`/`onShellFaint` 는 정적 Shell 면에서만 쓴다. 시험이 이 숫자를 단언한다. */
const CHROME = {
  light: {
    shellTop: "#28336F",
    shellMid: "#1E2758",
    shellDeep: "#17204D",
    shell: "#1E2758",
    onShell: "#EAEDFB",
    onShellMuted: "#AFBBE8",
    onShellFaint: "#98A5DC",
    line: "#2E3A7B",
    hover: "rgba(255,255,255,.06)",
    selected: "rgba(255,255,255,.10)",
    rail: "#A9BAFF",
    focusRing: "#C3CEFF",
    /* 워드마크의 "Assist" 잉크 — **Shell 위 전용**이다. Canvas 용 워드마크(`brand.wordmark`
       `#5A4FCF`)를 인디고 Shell 위에 그리면 light 에서 **2.32:1** 로 제품명 절반이 배경에
       묻힌다(실측). 옛 chrome(밝은 회색) 위에서는 같은 자리가 3.88:1 이었으므로, 이 값이
       없으면 W1 이 로고 가독성을 **악화**시킨 것이 된다. `#B7C4FA` 는 Shell stop 전부에서
       6.85~10.06 이고, 이미 `BrandLogo.INVERSE_INK.accent` 로 존재하던 정본 값이다. */
    wordmark: "#B7C4FA",
    /* Shell 위 반전 컨트롤(ConsoleSwitch·검색 inset). 흰 판을 올리면 인디고 하우징 안에서
       그 판이 가장 밝은 면이 되어 데이터보다 먼저 눈에 띈다 — 대신 흰빛을 알파로 얹는다.
       실측: `onShellMuted` on `track` 4.90~6.51, `onShell` on `trackSelected` 6.20~8.10. */
    track: "rgba(255,255,255,.08)",
    trackSelected: "rgba(255,255,255,.16)",
    edge: "rgba(255,255,255,.22)",
  },
  dark: {
    shellTop: "#232A5E",
    shellMid: "#1A2046",
    shellDeep: "#141936",
    shell: "#1A2046",
    onShell: "#E4E8F8",
    onShellMuted: "#A3AEDC",
    onShellFaint: "#94A0CE",
    line: "#2A3162",
    hover: "rgba(255,255,255,.08)",
    selected: "rgba(255,255,255,.12)",
    rail: "#A9BAFF",
    focusRing: "#C3CEFF",
    wordmark: "#B7C4FA",
    track: "rgba(255,255,255,.10)",
    trackSelected: "rgba(255,255,255,.18)",
    edge: "rgba(255,255,255,.24)",
  },
};

/* ── Gradient 는 제품에 정확히 넷만 존재한다 ───────────────────────────────
 *
 * 전부 여기서 나온다. `screens/**` 와 `app/**` 의 raw `linear-gradient(`/`radial-gradient(`
 * 리터럴은 static check 실패다 — 예전에 Gradient Chrome 이 미측정으로 배포된 경로가
 * 정확히 "화면 파일이 자기 그라디언트를 들고 있었다" 였다.
 *
 *   shell  Sidebar background-image. rail 은 하나의 객체다. 아래로 어두워지면서 하단
 *          (보조 항목·Clovi 카드)이 상단 주요 항목과 경쟁하지 않는다.
 *   ai     Top bar 우상단 앵커. Chrome 에서 **보라가 나타나는 유일한 자리**이고 AI 가
 *          사는 곳을 표시한다. Clovi 가 그 안에 앉는다.
 *   hero   로그인 패널·온보딩·AI Drawer 헤더 밴드. **`app/static/css/login.css` 의 현재
 *          값 그대로**를 토큰으로 승격한 것이다 — Jinja 로그인과 SPA 가 하나의 제품임을
 *          증명하는 방법이 이 한 값을 공유하는 것이다.
 *   mark   `BrandLogo.jsx` 내부. 로고 자체.
 *
 * 금지: 버튼·카드·판·배지·칩·표 행·차트 채움·페이지 배경·Empty State·모달·툴팁·아바타. */
const HERO_GRADIENT =
  "radial-gradient(circle at 82% 24%, rgba(142,117,225,.58), transparent 32%), " +
  "radial-gradient(circle at 18% 78%, rgba(98,199,189,.24), transparent 28%), " +
  "linear-gradient(145deg, #17204D 0%, #293B8D 48%, #536CD6 100%)";

const GRADIENT = {
  light: {
    shell: "linear-gradient(180deg,#28336F 0%,#1E2758 55%,#17204D 100%)",
    ai: "radial-gradient(120% 200% at 100% 0%, rgba(142,117,225,.26), transparent 60%)",
    /* hero 는 두 모드가 같은 값이다 — 이 밴드는 언제나 짙은 인디고 위에 흰 글자다.
       모드별로 갈라 두면 로그인(Jinja, 토글 없음)과 SPA 가 다시 분기한다. */
    hero: HERO_GRADIENT,
    mark: "linear-gradient(135deg,#4C58C8 0%,#8E75E1 100%)",
  },
  dark: {
    shell: "linear-gradient(180deg,#232A5E 0%,#1A2046 60%,#141936 100%)",
    ai: "radial-gradient(120% 200% at 100% 0%, rgba(142,117,225,.26), transparent 60%)",
    hero: HERO_GRADIENT,
    mark: "linear-gradient(135deg,#8E9BF2 0%,#C0AEF7 100%)",
  },
};

/* ── Chart 시리즈 — Brand 고정 ─────────────────────────────────────────────
 *
 * 1번 시리즈는 **항상 Brand 인디고**다. 사용자 Accent 를 따르지 않는다.
 * 전부 plate/inset/canvas 대비 ≥3:1 실측.
 *
 * **인접 슬롯 휘도 분리의 최대 달성치가 1.26:1 이다** — 즉 색만으로는 2개 시리즈 이상을
 * 절대 못 나른다. 그래서 `CHART_DASH` 는 장식이 아니라 필수이고, 직접 라벨과 숫자 범례도
 * 선택이 아니다. 상태색은 절대 범주 시리즈로 쓰지 않는다. */
export const CHART_SERIES = {
  light: ["#4C58C8", "#C0517E", "#2C3684", "#8158D8", "#2E9086", "#5D6B93"],
  dark: ["#8E9BF2", "#F49CBE", "#DDE3FF", "#C0A2FF", "#4FBFB2", "#7C88AE"],
};
/* 선 스타일. 인덱스가 CHART_SERIES 와 1:1 이다. 빈 문자열은 solid. */
export const CHART_DASH = ["", "4 3", "1 3", "6 3 1 3", "10 4", "2 2"];

/* 그림자 — 떠 있는 것만 갖는다. 판에는 그림자가 없다(D-141, 유지).
 * 그림자의 색도 중립 회색이 아니라 인디고 잉크다 — 회색 그림자는 인디고 캔버스 위에서
 * 누렇게 보인다. */
const SHADOW = {
  light: {
    none: "none",
    overlay: "0 6px 18px rgba(16,20,40,.12), 0 1px 3px rgba(16,20,40,.07)",
    modal: "0 24px 56px rgba(14,18,38,.22)",
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
 * 캔버스·판·오목면·실선이 하나의 중립 램프에서 나온다. **인디고 계열이고 절대 따뜻하지
 * 않다 — 모든 항목이 `B ≥ R` 이다.** 예전 램프는 채도 없는 회색(#EDEFF2, B−R=5)이라
 * 인디고 Shell 안에 놓으면 캔버스가 누렇게 보였다. 이제 하우징과 계측면이 같은 계열이다.
 *
 * 상태색은 강조색과 섞이지 않는 **독립 계열**이다. 각 상태는 fg(글자·아이콘) / bg(옅은 면) /
 * line(테두리) 셋을 갖고, **색만으로 상태를 전달하지 않는다**(D-141 RAISE, cyclorama) —
 * 화면 쪽에서 이름표나 아이콘을 반드시 함께 붙인다.
 *
 * Light 의 `*Bg` **네 값 전부**를 새 캔버스에 맞춰 미세 조정했다(success·warning·danger·info).
 * `B >= R` 규칙은 **중립 램프에만** 적용된다 — 상태색은 독립 계열이고 warning/danger 는
 * 원래 따뜻해야 한다(`warningBg #F7F0E6` 은 R>B 가 맞다). 계열 자체는 그대로다. */
const TOKENS = {
  light: {
    canvas: "#EEF0F7",
    plate: "#FFFFFF",
    inset: "#F5F6FB",
    sunken: "#E5E8F3",
    /* AI/Assistant/Brand 순간이 앉는 면. 앞머리 3px `brand.core` edge 와 함께 쓴다. */
    brandTint: "#E9ECFA",
    text: "#161A2C",
    muted: "#565E7A",
    /* `faint` 는 `muted` 와 대비가 1.10:1 이다 — 눈으로는 **같은 색**이고 3단 잉크 위계는
       사실상 2단이다. 이것은 값 선택 실수가 아니라 제약이다: 다섯 면(plate·inset·canvas·
       sunken·brandTint) 전부에서 AA(4.5)를 요구하면 가장 어두운 면 기준 여유가 5.24 -> 4.5,
       즉 1.16배뿐이라 세 단계를 시각적으로 벌릴 자리가 없다. 실제로 벌리려면 `faint` 를
       **AA-large(3:1) 가 허용되는 자리 — 18.66px 이상 또는 굵은 글자 — 로 한정**해야 하고,
       그 판단은 잉크 소비처를 소유하는 W4 의 몫이다(F-W1-02). 그때까지 두 값은 같은 단계로
       취급한다. `theme-contract.test.js` 가 이 분리도를 단언해 더 나빠지지 않게 잡는다. */
    faint: "#5C6480",
    line: "#DCDFEC",
    lineStrong: "#BCC2D9",
    accent: "#5B54B8",
    cyan: "#1F6F8B",
    success: "#0F7B4F",
    successBg: "#E8F3EF",
    successLine: "#A9D4BF",
    warning: "#8A5300",
    warningBg: "#F7F0E6",
    warningLine: "#E0C08A",
    danger: "#B3261E",
    dangerBg: "#FAEBEC",
    dangerLine: "#E6B0AC",
    info: "#1F5FBF",
    infoBg: "#E9EEFA",
    infoLine: "#B3C8E8",
    strongMix: [BRAND_FIXED.deep, 0.72],
    softMix: 0.1,
    /* 포커스 링 — Canvas 계열 위. 세 면 모두 3:1 이상이어야 한다(KBD-01/02/03).
     * 실측 6.93~8.48. Shell 위 포커스는 `chrome.focusRing` 이 따로 있다. */
    focusRing: "#4038B8",
  },
  dark: {
    canvas: "#0A0C16",
    plate: "#141829",
    inset: "#1C2136",
    sunken: "#0F1322",
    brandTint: "#1E2244",
    text: "#E5E8F5",
    muted: "#9BA4C4",
    faint: "#8C96B8",
    line: "#242A46",
    lineStrong: "#333B5E",
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
    /* 0.72 였다. `brandTint` 가 실제 텍스트 면이 되면서 0.72 에서 링크색이 4.48/4.51 로
     * AA 아래에 걸렸다. 0.62 면 5개 Preset × 4개 Dark 면 최악값이 5.46:1 이다. */
    strongMix: ["#FFFFFF", 0.62],
    softMix: 0.16,
    focusRing: "#9FB0FF",
  },
};

/* 사이드바가 서랍(temporary)으로 바뀌는 지점. 1024×768·1152×720 사내 장비를 고려한 값이라
 * MUI 의 lg(1200)를 쓰면 안 된다. `app/navConfig.js` 가 이 값을 가져다 쓴다(지시 23). */
export const NAV_BREAKPOINT = 860;

/* 입력이 멎었다고 보고 요청을 내보내기까지의 지연 (지시 26). 목록 필터는 타이핑 중에 표
 * 전체를 다시 그리므로 넉넉히 기다리고, 명령 팔레트는 키보드 도구라 더 빨리 반응한다. */
export const DEBOUNCE_MS = { filter: 300, palette: 220 };

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
  const chrome = light ? CHROME.light : CHROME.dark;
  const gradient = light ? GRADIENT.light : GRADIENT.dark;
  const brandInk = light ? BRAND_INK.light : BRAND_INK.dark;
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
    controlTokens: CONTROL,
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
        brandTint: t.brandTint,
        surface2: t.inset,
        surface3: t.sunken,
      },
      text: { primary: t.text, secondary: t.muted, disabled: t.faint, faint: t.faint },
      divider: t.line,
      dividerStrong: t.lineStrong,
      /* Chrome — Top bar + Sidebar. **Brand 고정이고 사용자 Accent 를 따르지 않는다.** */
      chrome: {
        ...chrome,
        shellImage: gradient.shell,
        aiWash: gradient.ai,
      },
      /* `sidebar` 는 Chrome 의 별칭이다. 소비처(AppShell·screens.css·생성 토큰)가 이 이름을
       * 쓰고 있어 유지하되, 값은 전부 `chrome` 에서 온다 — 같은 색이 두 곳에 살면 한쪽만
       * 바뀌는 날이 온다. */
      sidebar: {
        bg: chrome.shell,
        bgImage: gradient.shell,
        text: chrome.onShell,
        muted: chrome.onShellMuted,
        faint: chrome.onShellFaint,
        hover: chrome.hover,
        selected: chrome.selected,
        line: chrome.line,
        /* 현재 선택을 말하는 유일한 색. 앞머리 3px 레일로만 쓴다. **Brand 고정** —
         * 예전에는 `primary.main` 이라 사용자가 Accent 를 바꾸면 제품의 "현재 위치" 색이
         * 같이 바뀌었다. */
        activeRail: chrome.rail,
        focusRing: chrome.focusRing,
        wordmark: chrome.wordmark,
        track: chrome.track,
        trackSelected: chrome.trackSelected,
        edge: chrome.edge,
      },
      brand: { accent: primary, ...BRAND_FIXED, ...brandInk },
      gradient,
      chart: light ? CHART_SERIES.light : CHART_SERIES.dark,
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
      h1: { fontSize: FONT_SIZE.readout, fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.022em", lineHeight: LINE_HEIGHT.readout },
      h2: { fontSize: FONT_SIZE.pageTitle, fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.02em", lineHeight: LINE_HEIGHT.pageTitle },
      h3: { fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.018em", lineHeight: LINE_HEIGHT.title },
      /* 화면 제목. PageHeader 가 h4 를 쓴다. */
      h4: { fontSize: FONT_SIZE.pageTitle, fontWeight: FONT_WEIGHT.bold, letterSpacing: "-0.016em", lineHeight: LINE_HEIGHT.pageTitle },
      h5: { fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.semibold, letterSpacing: "-0.012em", lineHeight: LINE_HEIGHT.title },
      h6: { fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.semibold, letterSpacing: "-0.012em", lineHeight: LINE_HEIGHT.body },
      body1: { fontSize: FONT_SIZE.body, lineHeight: LINE_HEIGHT.body, letterSpacing: "-0.011em" },
      body2: { fontSize: FONT_SIZE.bodySm, lineHeight: LINE_HEIGHT.bodySm, letterSpacing: "-0.011em" },
      caption: { fontSize: FONT_SIZE.caption, lineHeight: LINE_HEIGHT.caption, letterSpacing: "-0.006em" },
      button: { textTransform: "none", fontWeight: FONT_WEIGHT.semibold, letterSpacing: "-0.011em" },
      /* 구획 제목과 판독값. MUI 에 대응 variant 가 없어 새로 만든 두 단계다. */
      sectionTitle: { fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.semibold, letterSpacing: "-0.012em", lineHeight: LINE_HEIGHT.title },
      statValue: {
        fontSize: FONT_SIZE.readout,
        fontWeight: FONT_WEIGHT.semibold,
        letterSpacing: "-0.02em",
        lineHeight: LINE_HEIGHT.readout,
        ...NUMERIC,
      },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          /* 포커스 링은 **CSS 커스텀 프로퍼티**로 캐스케이드시킨다.
           *
           * 이유: 이 제품에는 대비가 정반대인 두 면이 있다 — 밝은 Canvas 와 인디고 Shell.
           * Canvas 용 링(`#4038B8`)을 Shell 위에 그리면 light 에서 **1.38~1.83:1** 이라
           * 사실상 보이지 않는다(실측). 즉 링이 하나면 키보드 사용자가 사이드바와 상단바
           * 전체에서 포커스를 잃는다.
           *
           * 선택자 특이도로 덮으려 하면 컴포넌트 오버라이드와 (0,2,0) 대 (0,2,0) 으로 묶여
           * emotion 삽입 순서에 결과가 달라진다 — 결정적이지 않다. 커스텀 프로퍼티는
           * **상속**이라 그 싸움 자체가 없다: Shell 컨테이너가 값을 한 번 바꾸면 그 안의
           * 모든 후손이 따라온다. 그리고 `:focus-visible` 전역 규칙 덕에 MUI 컴포넌트가
           * 아닌 것(예: `component="a"` 로 그린 '본문 바로가기')도 같은 링을 갖는다 —
           * 그 링크는 실측에서 UA 기본 `#101010` 외곽선을 쓰고 있었다. */
          ":root": {
            "--clovir-focus-ring": t.focusRing,
            /* 워드마크도 같은 이유·같은 방식이다 — Shell 컨테이너가 이 변수를 덮으면
               그 안의 로고가 Shell 용 잉크로 그려진다. */
            "--clovir-wordmark": brandInk.wordmark,
          },
          ":focus-visible": {
            outline: `2px solid var(--clovir-focus-ring, ${t.focusRing})`,
            outlineOffset: 2,
          },
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
            "&.Mui-focusVisible": {
              outline: `2px solid var(--clovir-focus-ring, ${t.focusRing})`,
              outlineOffset: 2,
            },
          },
        },
      },
      MuiLink: {
        styleOverrides: {
          root: {
            color: primaryStrong,
            textUnderlineOffset: "0.15em",
            "&:focus-visible": {
              outline: `2px solid var(--clovir-focus-ring, ${t.focusRing})`,
              outlineOffset: 2,
            },
          },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: {
            minHeight: CONTROL.button,
            /* `paddingBlock: 0` 이 없으면 MUI 기본 세로 패딩(6px)이 남아 **선언 34px 인
               버튼이 화면에서 36px 로 그려진다** — 독립 리뷰어가 배포본 픽셀에서 잡았다.
               토큰이 실제 높이를 말하지 않으면 그 토큰은 문서일 뿐이다. 높이는 `minHeight`
               가 책임진다(줄바꿈된 라벨도 이 하한 아래로 내려가지 않는다). */
            paddingBlock: 0,
            borderRadius: RADIUS.sm,
            paddingInline: 14,
            transition: `background-color ${MOTION.fast} ${MOTION.ease}, border-color ${MOTION.fast} ${MOTION.ease}`,
          },
          sizeSmall: { minHeight: CONTROL.buttonSm, paddingBlock: 0, paddingInline: 11 },
          sizeLarge: { minHeight: CONTROL.buttonLg, paddingBlock: 0, paddingInline: 18 },
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
            minHeight: CONTROL.tab,
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
            minHeight: CONTROL.input,
            borderRadius: RADIUS.sm,
            background: t.plate,
            "&.Mui-focused": {
              outline: `2px solid var(--clovir-focus-ring, ${t.focusRing})`,
              outlineOffset: 0,
            },
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
      /* 아이콘 버튼은 34px 로 그리고 `::after` 로 40px 목표를 잡는다(WCAG 2.2 Target Size).
       * 시각 크기를 40 으로 키우면 표 안 아이콘 열의 행 높이가 함께 자란다 — 목표만 넓힌다. */
      MuiIconButton: {
        styleOverrides: {
          root: {
            minWidth: CONTROL.iconButton,
            minHeight: CONTROL.iconButton,
            borderRadius: RADIUS.sm,
            position: "relative",
            "&::after": {
              content: '""',
              position: "absolute",
              inset: `${(CONTROL.iconButton - CONTROL.iconButtonHit) / 2}px`,
            },
          },
        },
      },
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
