/* 디자인 토큰 CSS 생성기 — 정본은 `frontend/src/ui/theme.js` 하나다.
 *
 * ## 왜 생성하는가
 *
 * 예전에는 같은 값이 네 곳에 따로 적혀 있었다:
 *   design/baseline/preview-standalone.html (목업, 지시 64로 폐기)
 *   frontend/src/ui/theme.js                (MUI 테마)
 *   frontend/src/styles/tokens.css          (레거시 .k- / .c- 클래스용 CSS 변수)
 *   app/static/css/tokens.css               (Jinja 로그인·비밀번호 화면용 사본)
 *
 * 마지막 것은 **패리티 시험이 없어서 조용히 낡아 있었다** — 흰 사이드바, 56px 상단바,
 * surface 계층 없음. 로그인 화면만 다른 제품처럼 보이던 이유다.
 *
 * 이제 뒤의 둘은 이 스크립트가 만든다. 손으로 고치지 마라.
 *
 * ## 쓰는 법
 *
 *   node scripts/generate_design_tokens.mjs           # 생성
 *   node scripts/generate_design_tokens.mjs --check   # 드리프트 검사 (static_checks.sh 용)
 *
 * `scripts/generate_field_limits.py` + `check_field_limits_fresh.py` 와 같은 관용이다.
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..");
const THEME_SRC = join(REPO, "frontend", "src", "ui", "theme.js");
const SPA_OUT = join(REPO, "frontend", "src", "styles", "tokens.css");
const JINJA_OUT = join(REPO, "app", "static", "css", "tokens.css");

const theme = await import(pathToFileURL(THEME_SRC).href);
const { createClovirTheme, RADIUS, FONT_WEIGHT, FONT_SIZE, MOTION, NAV_BREAKPOINT } = theme;

/* 소스 해시 — 테마가 바뀌었는데 CSS 를 다시 안 만들면 검사가 잡는다. */
const SOURCE_HASH = createHash("sha256").update(readFileSync(THEME_SRC)).digest("hex").slice(0, 16);

/* 판 위계에 얹는 카테고리 배지 색. 상태(ok/warn/danger/info)와 **다른 계열**이다 —
 * 문서 종류·업무 분야처럼 "좋고 나쁨이 없는 분류"에 쓴다. 중립 램프 위에서 서로 구분되면
 * 되므로 채도를 낮게 잡는다. */
const CATEGORY = {
  light: {
    purple: ["#EFEBFA", "#4A3E8C"],
    teal: ["#E4F1F1", "#1E5F5F"],
    pink: ["#FAEBF0", "#8A3557"],
    indigo: ["#E9EDF9", "#33448C"],
  },
  dark: {
    purple: ["#241E3A", "#C3B6F5"],
    teal: ["#152B2B", "#8FD3D3"],
    pink: ["#2E1A22", "#F0A8C0"],
    indigo: ["#1A2038", "#A9B8EC"],
  },
};

function tokensFor(mode) {
  const t = createClovirTheme(mode);
  const p = t.palette;
  const bg = p.background;
  const sd = t.shadowTokens;
  const cat = CATEGORY[mode];
  const inverse = mode === "light" ? "#FFFFFF" : p.text.primary;

  return {
    /* 네이티브 컨트롤(날짜 선택기·스핀 버튼·스크롤바)이 테마를 따르게 한다. 이게 없으면
     * 다크에서 <input type="date"> 달력과 스크롤바가 밝은 크롬으로 떠 대비가 깨진다. */
    "color-scheme": mode,

    /* 면 */
    "--color-bg": bg.canvas,
    "--color-card": bg.plate,
    "--color-surface-2": bg.inset,
    "--color-surface-3": bg.sunken,

    /* 글자 */
    "--color-text": p.text.primary,
    "--color-heading": p.text.primary,
    "--color-ink": p.text.primary,
    "--color-muted": p.text.secondary,
    "--color-faint": p.text.faint,
    "--color-text-inverse": mode === "light" ? "#FFFFFF" : "#0E1013",

    /* 실선 — 계측 전면의 주된 위계 장치다. 상자가 아니라 선이 구획을 만든다. */
    "--color-border": p.divider,
    "--color-border-strong": p.dividerStrong,
    "--color-line": p.divider,

    /* 강조 — 세 자리에만 쓴다(주요 행동·현재 선택·포커스). */
    "--color-primary": p.primary.main,
    "--color-primary-strong": p.primary.dark,
    "--color-primary-tint": p.primary.soft,
    "--color-primary-soft": p.focusRing,
    "--color-on-primary": "#FFFFFF",
    "--color-on-status": "#FFFFFF",

    /* 상태 — 강조색과 섞이지 않는 독립 계열. 색만으로 전달하지 않는다. */
    "--color-success": p.success.main,
    "--color-success-bg": p.success.bg,
    "--color-success-line": p.success.line,
    "--color-warning": p.warning.main,
    "--color-warning-bg": p.warning.bg,
    "--color-warning-line": p.warning.line,
    "--color-error": p.error.main,
    "--color-error-bg": p.error.bg,
    "--color-error-line": p.error.line,
    "--color-info": p.info.main,
    "--color-info-bg": p.info.bg,
    "--color-info-line": p.info.line,

    /* 보조 색 — 로고·마스코트가 쓰는 브랜드 값이라 UI 강조와 별개로 남긴다. */
    "--color-accent-purple": p.brand.purple,
    "--color-accent-violet": p.secondary.main,
    "--color-accent-sky": p.cyan,

    /* 배지 — 상태 계열은 상태색에서, 카테고리 계열은 별도 램프에서 온다. */
    "--badge-neutral-bg": bg.inset,
    "--badge-neutral-fg": p.text.secondary,
    "--badge-neutral-border": p.divider,
    "--badge-success-bg": p.success.bg,
    "--badge-success-fg": p.success.strong,
    "--badge-warning-bg": p.warning.bg,
    "--badge-warning-fg": p.warning.strong,
    "--badge-error-bg": p.error.bg,
    "--badge-error-fg": p.error.strong,
    "--badge-info-bg": p.info.bg,
    "--badge-info-fg": p.info.strong,
    "--badge-purple-bg": cat.purple[0],
    "--badge-purple-fg": cat.purple[1],
    "--badge-teal-bg": cat.teal[0],
    "--badge-teal-fg": cat.teal[1],
    "--badge-pink-bg": cat.pink[0],
    "--badge-pink-fg": cat.pink[1],
    "--badge-indigo-bg": cat.indigo[0],
    "--badge-indigo-fg": cat.indigo[1],

    /* chrome — 사이드바와 상단바는 캔버스 계열이다. 그라디언트가 아니다.
     * 선택 표현은 제품 전체에서 하나다(D-141 RAISE): 앞머리 2px 레일 + 굵기. */
    "--sidebar-bg": p.sidebar.bg,
    "--sidebar-text": p.sidebar.text,
    "--sidebar-muted": p.sidebar.muted,
    "--sidebar-hover": p.sidebar.hover,
    "--sidebar-line": p.sidebar.line,
    /* 선택된 줄의 면. D-141 로 사이드바의 '현재 위치'는 앞머리 레일이 말하므로 이 토큰의
       실제 소비처는 채팅 대화 목록의 선택 행 하나뿐이다(styles/screens.css). 새 규칙대로
       **선택/호버 면은 `inset`** 이다 — 표와 판독 줄이 이미 같은 값을 쓴다. 반투명 대신
       불투명 값을 두는 이유는 그것이 실제로 그려지는 색이기 때문이다: 투명 틴트는 어떤 면
       위에 얹히느냐에 따라 대비가 달라져 "이 조합은 AA 인가"에 답할 수 없다. */
    "--sidebar-active-bg": bg.inset,
    "--sidebar-active-fg": p.text.primary,
    "--sidebar-active-rail": p.primary.main,
    "--sidebar-danger": p.error.main,
    "--sidebar-shadow": "none",
    "--sidebar-width": "248px",
    "--g-topbar": p.sidebar.bg,
    "--topbar-fg": p.text.primary,
    "--topbar-pill-bg": p.sidebar.hover,
    "--topbar-pill-fg": p.text.primary,
    "--topbar-height": "52px",

    /* 그림자 — 떠 있는 것만. 판에는 없다. 옛 별칭은 소비처가 남아 있어 유지하되 전부
     * none/overlay/modal 셋으로 접는다. */
    "--shadow-sm": sd.none,
    "--shadow-md": sd.overlay,
    "--shadow-lg": sd.modal,
    "--shadow-card": sd.none,
    "--shadow-subtle": sd.none,
    "--shadow-dropdown": sd.overlay,
    "--shadow-modal": sd.modal,
    "--shadow-hero": sd.none,
  };
}

/* 모드와 무관한 값. :root 에 한 번만 적는다. */
const STATIC_TOKENS = {
  "--radius-sm": `${RADIUS.sm}px`,
  "--radius-md": `${RADIUS.md}px`,
  "--radius-lg": `${RADIUS.lg}px`,
  "--radius-pill": `${RADIUS.full}px`,

  "--space-1": "4px",
  "--space-2": "8px",
  "--space-3": "12px",
  "--space-4": "16px",
  "--space-5": "24px",
  "--space-6": "32px",
  "--space-xs": "4px",
  "--space-sm": "8px",
  "--space-md": "12px",
  "--space-lg": "16px",
  "--space-xl": "24px",
  "--space-2xl": "32px",
  "--space-3xl": "48px",

  "--fw-normal": String(FONT_WEIGHT.regular),
  "--fw-medium": String(FONT_WEIGHT.medium),
  "--fw-semibold": String(FONT_WEIGHT.semibold),
  "--fw-bold": String(FONT_WEIGHT.bold),

  "--font-size-xs": FONT_SIZE.micro,
  "--font-size-sm": FONT_SIZE.caption,
  "--font-size-md": FONT_SIZE.body,
  "--font-size-lg": FONT_SIZE.title,
  "--font-size-xl": FONT_SIZE.pageTitle,

  "--font-stack":
    '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo", Roboto, Arial, sans-serif',
  "--font-serif": 'ui-serif, Georgia, "Times New Roman", serif',
  "--font-numeric": "tabular-nums",

  "--motion-fast": MOTION.fast,
  "--motion-base": MOTION.base,
  "--motion-ease": MOTION.ease,

  "--nav-breakpoint": `${NAV_BREAKPOINT}px`,
};

/* ── 대비 주석 ────────────────────────────────────────────────────────────
 *
 * 주석은 실행되지 않으므로 조용히 썩는다. 이 저장소에서 실제로 세 번 썩었고
 * (`tests/regression/test_css_says_what_it_does.py` 의 docstring 에 사례 셋이 있다),
 * 그래서 그 시험이 색에서 대비를 다시 계산해 주석과 대조한다.
 *
 * 여기서는 아예 **생성기가 계산해서 적는다.** 색을 바꾸면 주석이 저절로 따라오므로
 * 사람이 숫자를 옮겨 적을 일이 없다 — 썩을 자리 자체가 없어진다.
 *
 * 값은 그 시험과 같은 방식으로 낸다(WCAG 2.x 상대 휘도, 채널 0~255). */
function srgbChannel(c8) {
  const c = c8 / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function hexToRgb(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(String(hex).trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function luminance(rgb) {
  const [r, g, b] = rgb.map(srgbChannel);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(fgHex, bgHex) {
  const fg = hexToRgb(fgHex);
  const bg = hexToRgb(bgHex);
  if (!fg || !bg) return null;
  const a = luminance(fg);
  const b = luminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/* 글자 토큰 → 그 글자가 실제로 놓이는 면 토큰. "무엇을 무엇 위에 그리는가" 는 설계 의도라
 * 여기에 적어 두고, 숫자는 계산한다. 위 회귀 시험의 CASES 와 같은 짝이다. */
const CONTRAST_PAIRS = {
  "--sidebar-text": "--sidebar-bg",
  "--sidebar-muted": "--sidebar-bg",
  "--sidebar-active-fg": "--sidebar-active-bg",
  "--color-text": "--color-bg",
  "--color-muted": "--color-bg",
};

function block(selector, map, indent = "  ") {
  const lines = Object.entries(map).map(([k, v]) => {
    const decl = `${indent}${k}: ${v};`;
    const on = CONTRAST_PAIRS[k];
    if (!on) return decl;
    const ratio = contrastRatio(v, map[on]);
    if (ratio == null) return decl;
    // 숫자는 주석에 **하나만** 둔다 — 회귀 시험이 정확히 하나를 기대한다.
    return `${decl}   /* ${on} 위 ${ratio.toFixed(2)}:1 */`;
  });
  return `${selector} {\n${lines.join("\n")}\n}`;
}

function header(target) {
  return [
    "/* 생성 파일이다. 손으로 고치지 마라.",
    " *",
    ` * 정본: frontend/src/ui/theme.js  (source-hash ${SOURCE_HASH})`,
    " * 생성: node scripts/generate_design_tokens.mjs",
    " * 검사: node scripts/generate_design_tokens.mjs --check   (static_checks.sh 가 부른다)",
    " *",
    ` * 대상: ${target}`,
    " *",
    " * 값을 바꾸려면 theme.js 를 고치고 이 스크립트를 다시 돌려라. 여기서 고치면 다음",
    " * 생성에서 조용히 되돌아간다 — 예전에 app/static/css/tokens.css 가 정확히 그렇게",
    " * 낡아서 로그인 화면만 흰 사이드바에 56px 상단바로 남아 있었다.",
    " */",
    "",
  ].join("\n");
}

function renderSpa() {
  const light = tokensFor("light");
  const dark = tokensFor("dark");
  return [
    header("frontend/src/styles/tokens.css — SPA 레거시 클래스(.k-* / .c-* / .dash-*)용"),
    block(":root", { ...STATIC_TOKENS, ...light }),
    "",
    "/* 다크는 색만 덮는다. 치수·굵기·모션은 모드와 무관하다. */",
    block('[data-theme="dark"]', dark),
    "",
  ].join("\n");
}

function renderJinja() {
  const light = tokensFor("light");
  const dark = tokensFor("dark");
  /* Jinja 화면(로그인·비밀번호)은 배지 카테고리와 사이드바가 필요 없다. 다만 **같은 램프**를
   * 써야 SPA 와 한 제품으로 보인다 — 예전 fork 가 갈라진 지점이 정확히 여기다. */
  const drop = (m) =>
    Object.fromEntries(
      Object.entries(m).filter(
        ([k]) => !k.startsWith("--badge-purple") && !k.startsWith("--badge-teal") &&
                 !k.startsWith("--badge-pink") && !k.startsWith("--badge-indigo"),
      ),
    );
  return [
    header("app/static/css/tokens.css — Jinja 서버 렌더 화면(로그인·비밀번호)용"),
    block(":root", { ...STATIC_TOKENS, ...drop(light) }),
    "",
    block('[data-theme="dark"]', drop(dark)),
    "",
    "@media (prefers-color-scheme: dark) {",
    /* `:not([data-theme])` — 사용자가 명시적으로 고르지 않았을 때만 OS 선호를 따른다.
       고른 경우는 위 `[data-theme="..."]` 블록이 이미 답한다. 저장소의 회귀 시험
       (tests/regression/test_css_says_what_it_does.py)이 이 선택자로 두 블록이 정확히
       같은 값을 갖는지 대조한다. */
    block("  :root:not([data-theme])", drop(dark), "    "),
    "}",
    "",
  ].join("\n");
}

const targets = [
  [SPA_OUT, renderSpa()],
  [JINJA_OUT, renderJinja()],
];

const check = process.argv.includes("--check");
let drifted = 0;
for (const [path, want] of targets) {
  let have = "";
  try {
    have = readFileSync(path, "utf8");
  } catch {
    have = "";
  }
  const same = have.replace(/\r\n/g, "\n") === want;
  if (check) {
    if (!same) {
      drifted += 1;
      console.error(`[DRIFT] ${path.replace(REPO, "").replace(/\\/g, "/")} 가 theme.js 와 다르다`);
    }
  } else if (!same) {
    writeFileSync(path, want, "utf8");
    console.log(`wrote ${path.replace(REPO, "").replace(/\\/g, "/")}`);
  } else {
    console.log(`unchanged ${path.replace(REPO, "").replace(/\\/g, "/")}`);
  }
}

if (check) {
  if (drifted) {
    console.error("theme.js 를 고쳤으면 `node scripts/generate_design_tokens.mjs` 를 돌려라.");
    process.exit(1);
  }
  console.log(`design tokens fresh (source-hash ${SOURCE_HASH})`);
}
