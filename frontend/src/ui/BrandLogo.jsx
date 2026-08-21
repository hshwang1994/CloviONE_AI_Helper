import React from "react";
import Box from "@mui/material/Box";
import { useTheme } from "@mui/material/styles";
import { FONT_WEIGHT } from "./theme.js";

/* 브랜드 로고 — 인라인 SVG다. <img src>로 넣지 않는다.
 *
 * 이 저장소는 같은 함정을 두 번 밟았다: 흰 글자 워드마크를 흰 카드에 얹어 안 보였고,
 * 어두운 글자 파일로 바꿨더니 이번엔 잉크색 카드에서 묻혔다. 원인은 색이 아니라 구조였다 —
 * <img>로 넣은 SVG는 CSS가 안쪽에 닿지 못해 면이 바뀔 때마다 사람이 파일을 골라야 한다.
 * 고르는 한 세 번째가 온다. (tests/regression/test_wordmark_follows_its_surface.py)
 *
 * 그래서 글자는 currentColor를 따르고, 강조어와 잎 그라디언트만 테마가 정한다.
 * 원본 자산(clovirassist-logo-horizontal.svg / -dark.svg)은 정확히 그 '파일 고르기' 방식이라
 * 런타임에서 쓰지 않는다. 보존은 되어 있다.
 *
 * 원본에서 고친 것이 하나 더 있다: 원본 viewBox가 0 0 760 156인데 실제 내용은 x=508에서
 * 끝난다(헤드리스 브라우저로 getBBox 측정). 오른쪽 36%가 빈 채라 같은 CSS 폭을 줘도 로고가
 * 작고 왼쪽으로 쏠려 보였다. 내용에 맞춰 528로 좁혔다.
 *
 * 글자 폭은 textLength로 고정한다. 원본은 Inter/Pretendard를 전제로 좌표를 박아 뒀는데,
 * 폰트가 아직 안 받아졌거나(font-display: swap) 폴백으로 떨어지면 시스템 폰트로 그려진다 —
 * 고정하지 않으면 장비마다 두 단어가 붙거나 벌어진다.
 */

const CLOVER_PATH =
  "M64 64C56 54 38 50 34 33C30 17 42 7 54 11C60 13 63 18 64 24C65 18 68 13 74 11C86 7 98 17 94 33C90 50 72 54 64 64Z";

/* 잎 그라디언트 — 어두운 면에서는 한 단계 밝게 쓴다(원본 -dark.svg와 같은 값).
 * 파일을 고르는 게 아니라 테마가 색을 정한다는 점이 중요하다. */
const LEAF = {
  light: {
    top: ["#8FA2F0", "#536CD6"],
    right: ["#9B82E8", "#8E75E1"],
    bottom: ["#435CBE", "#536CD6"],
    left: ["#7FD6C9", "#62C7BD"],
  },
  dark: {
    top: ["#B7C4FA", "#758AE1"],
    right: ["#B9A7F4", "#9B82E8"],
    bottom: ["#758AE1", "#536CD6"],
    left: ["#A1E7DE", "#62C7BD"],
  },
};

/* 어두운 면(상단바) 위의 글자색. 기준선은 이 자리에서 파일을 바꿔 끼운다 —
 * brandLockup({inverse:true}) → app/static/brand/logo/clovirassist-logo-horizontal-dark.svg.
 * 그 파일이 쓰는 값 그대로다: Clovir #FFFFFF, Assist #B7C4FA, 부제 #D4DAF0.
 *
 * Clovir 는 currentColor 로 두면 상단바가 물려주는 흰색이 그대로 오므로 여기 없다.
 * 강조어만 따로 두는 이유: 라이트 면의 브랜드 인디고(#536CD6)는 딥 인디고 상단바 위에서
 * 배경에 묻힌다. 사용자가 "흰바탕이 너무 크다"고 한 그 흰 판은 이 대비를 흰 면으로
 * 억지로 만들어 낸 것이었다. 자산이 이미 답을 갖고 있었다. */
const INVERSE_INK = { accent: "#B7C4FA", subtitle: "#D4DAF0" };

const GRADS = [
  { key: "top", x1: 64, y1: 10, x2: 64, y2: 64, rotate: 0 },
  { key: "right", x1: 118, y1: 64, x2: 64, y2: 64, rotate: 90 },
  { key: "bottom", x1: 64, y1: 118, x2: 64, y2: 64, rotate: 180 },
  { key: "left", x1: 10, y1: 64, x2: 64, y2: 64, rotate: 270 },
];

/* 네잎클로버 마크. 그라디언트 id는 인스턴스마다 유일해야 한다 — 상단바와 사이드바에 동시에
 * 그려지므로, 고정 id를 쓰면 DOM에 중복 id가 생기고(접근성·QA 검사 위반) 브라우저가 먼저 만난
 * 정의만 참조해 색이 어긋난다. */
function CloverMark({ uid, mode }) {
  const leaf = LEAF[mode] || LEAF.light;
  return (
    <>
      <defs>
        {GRADS.map((g) => (
          <linearGradient
            key={g.key}
            id={`${uid}-${g.key}`}
            x1={g.x1}
            y1={g.y1}
            x2={g.x2}
            y2={g.y2}
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor={leaf[g.key][0]} />
            <stop offset="1" stopColor={leaf[g.key][1]} />
          </linearGradient>
        ))}
      </defs>
      {GRADS.map((g) => (
        <path
          key={g.key}
          d={CLOVER_PATH}
          fill={`url(#${uid}-${g.key})`}
          transform={g.rotate ? `rotate(${g.rotate} 64 64)` : undefined}
        />
      ))}
      <circle cx="64" cy="64" r="17" fill="#FFFFFF" />
      <path
        d="M64 51.5L67.2 59.1L74.8 62.3L67.2 65.5L64 73.1L60.8 65.5L53.2 62.3L60.8 59.1L64 51.5Z"
        fill="#536CD6"
      />
      <circle cx="75.5" cy="49.5" r="3.5" fill="#F7A8C4" />
    </>
  );
}

/* ── 락업 치수 ───────────────────────────────────────────────────────────────
 * 치수를 **하나의 단위(BRAND_UNIT)에서 전부 파생**시킨다. 마크·간격·워드마크 폭·부제가
 * 전부 그 단위의 em 이라, 한 값을 바꾸면 락업 전체가 같은 비율로 움직인다. 해상도별 px 표를
 * 두지 않는 이유이자, 어느 하나만 어긋나 균형이 깨지는 일을 구조적으로 막는 방법이다.
 *
 * BRAND_UNIT = 부제의 글자 크기다. 왜 이것이 기준인가 — 두 줄 중 크기를 **마음대로 못 정하는
 * 쪽**이 부제이기 때문이다. QA 의 tiny_text 검사(scripts/ui_qa/assertions.py:319)는 뷰포트
 * 2200px 이상에서 12px 미만 글자를 실패로 잡고, aria-hidden 예외가 없다. 그 폭에서는
 * styles/root.css 의 루트 폰트사이즈가 18px 이므로 `0.68rem = 12.24px` 로 하한을 넘긴다.
 * 워드마크는 그 부제에 맞춰 따라가는 쪽이다.
 *
 * `min(0.68rem, 12.4px)` 의 두 번째 항이 상한이다. rem 만 쓰면 4K(루트 20px)에서 락업이
 * 25% 커져 "해상도가 올라갈수록 로고만 계속 커지는" 상태가 된다(사용자 지적). 상한을 두면
 * 실제 크기는 10.88px(≤2199) → 12.24px(2200~2999) → 12.4px(≥3000) 로 **+14% 안에서** 멈춘다.
 * 브라우저 배율을 바꿔 유효 뷰포트가 오가도 이 세 값 사이에서만 움직인다.
 *
 * 폭은 눈대중이 아니라 실측이다(PIL/FreeType 으로 폰트 파일에서 진행폭 측정):
 *   "SMART WORKSPACE ASSISTANT" — Pretendard Variable 600, 자간 없이 **15.58em**.
 *   letter-spacing 0.01em × 25자를 더해 **15.83em** → 1080p 기준 172px.
 *   워드마크도 같은 15.83em 으로 둔다. 두 줄이 왼쪽(C와 S)과 오른쪽 끝을 같이 쓴다.
 *   폴백 폰트는 전부 이보다 좁아(Segoe UI Semibold 14.85em, Malgun 14.84em) 넘치지 않는다.
 *
 * 예전 값과 비교: 워드마크 192px → 163px(-15%), 락업 전체 240×41px → 216×37px.
 * 부제 글자 크기는 10.88px 그대로다 — **줄인 것은 부제의 letter-spacing(0.08em → 0.01em)이지
 * 글자 크기가 아니다.** 워드마크만 작아지고 부제는 읽을 수 있는 크기를 지킨다. */
const BRAND_UNIT = "min(0.68rem, 12.4px)";
const WORDMARK_WIDTH = "15.83em";
const SUBTITLE_TRACKING = "0.01em";
const SUBTITLE_LINE_HEIGHT = 1.2;
/* 마크는 2줄 텍스트 블록과 같은 높이의 정사각형이다(아이콘이 2줄 블록과 균형).
 * 블록 높이 = 15.83em × 50/346(아래 viewBox 비율) + 1.2em = 3.49em. */
const MARK_SIZE = "3.49em";
/* 부제 없이 한 줄로 놓을 때(좁은 화면 마크만 쓰는 자리는 이 값을 안 탄다). 워드마크 잉크
 * 상자 높이가 15.83em × 50/346 = 2.29em 이고, 마크는 그보다 약간 커야 광학적으로 같은
 * 크기로 보인다(캡 하이트 대비 아이콘의 통상 비율). */
const MARK_SIZE_ONE_LINE = "2.45em";
const MARK_GAP = "0.65em";
/* 글자에 맞춰 자른 워드마크 viewBox. 원본 좌표계(0 0 528 156)에서 글자는 x 160..506,
 * 베이스라인 y=86 이고 잉크는 베이스라인 위 0.752em·아래 0.010em 까지다(같은 방법으로 측정,
 * weight 800) — fontSize 62 기준 y 39.4..86.6. 위아래 1~2유닛만 남기고 자른다.
 * 자르지 않으면 상자 아래쪽 70유닛(=상자 높이의 45%)이 빈 채로 남고, 그 빈 칸이 부제를
 * 상단바 바닥까지 밀어 내렸다. */
const WORDMARK_VIEWBOX = "160 38 346 50";

export default function BrandLogo({
  markOnly = false,
  subtitle = true,
  width,
  title = "ClovirAssist",
  // 어두운 면(상단바) 위에 놓을 때. 흰 판을 깔지 않고 자산의 반전 색을 쓴다.
  inverse = false,
  sx = {},
}) {
  const theme = useTheme();
  const uid = React.useId().replace(/[:]/g, "");
  // 반전은 잎 그라디언트도 한 단계 밝은 세트를 쓴다(-dark.svg 와 같은 값).
  const mode = inverse ? "dark" : theme.palette.mode;
  /* 워드마크는 **Brand 고정**이다. 예전에는 `primary.main`(사용자 Accent)이라 청록을
     고른 사용자의 화면에서는 로고가 청록으로 나왔다 — 사용자 설정이 제품 정체성을 덮었다.
     `theme-contract.test.js` 와 `brand-logo.test.jsx` 가 이 불변식을 단언한다.
     값이 **변수를 통해** 오는 이유는 포커스 링과 같다: 이 로고는 밝은 Canvas 위에도 앉고
     인디고 Shell 위에도 앉는데, Canvas 용 잉크(`#5A4FCF`)를 Shell 위에 그리면 light 에서
     2.32:1 로 "Assist" 가 배경에 묻힌다(실측). Shell 컨테이너가 `--clovir-wordmark` 를
     한 번 덮으면 상속으로 해결된다 — 호출부마다 `inverse` 를 손으로 넘기지 않아도 된다. */
  const accent = inverse
    ? INVERSE_INK.accent
    : `var(--clovir-wordmark, ${theme.palette.brand.wordmark})`;
  const w = width != null ? width : markOnly ? 40 : WORDMARK_WIDTH;
  /* 부제가 없으면 텍스트 블록이 두 줄에서 한 줄로 줄어든다 — 마크가 2줄 높이 그대로면
     아이콘만 홀로 커 보인다. 두 값 중 하나를 고르는 것이 아니라 **블록 높이를 따라간다**. */
  const markSize = subtitle ? MARK_SIZE : MARK_SIZE_ONE_LINE;

  if (markOnly) {
    return (
      <Box
        component="svg"
        viewBox="0 0 128 128"
        role="img"
        aria-label={title}
        sx={{ display: "block", width: w, height: "auto", flexShrink: 0, ...sx }}
      >
        <CloverMark uid={uid} mode={mode} />
      </Box>
    );
  }

  /* ── 락업 구조 ──────────────────────────────────────────────────────────────
   *   BrandRoot(가로)
   *     ├─ Symbol    : 네잎클로버 마크 — 정사각 SVG, 텍스트 블록과 같은 높이
   *     └─ TextBlock(세로)
   *          ├─ MainWordmark : "ClovirAssist" 만 담은 SVG(글자에 맞춰 자른 viewBox)
   *          └─ Subtitle     : "SMART WORKSPACE ASSISTANT" — 일반 HTML span
   *
   * 예전에는 마크·글자·빈 여백까지 전부 든 528×156 SVG 하나를 그려 놓고 부제를 그 위에
   * 절대위치(left 31% / top 74%)로 얹었다. 그 상자는 글자 베이스라인(y=86) 아래로 70유닛이
   * 빈 채였고, 부제는 그 빈 칸 안에 떠 있었다 — 화면에서는 부제만 상단바 바닥으로 떨어져
   * 나온 것처럼 보였다. 여백·음수마진·좌표로는 못 고친다(그 절대위치를 다른 숫자로 미는
   * 것일 뿐이고, 폭이 다른 두 줄은 여전히 한 덩어리가 아니다). 두 줄을 진짜 형제로 만들고
   * 폭을 맞추는 것이 답이다 — 위 '락업 치수' 주석이 그 폭을 어떻게 맞췄는지 적어 뒀다.
   *
   * 부제를 SVG <text> 로 되돌리지 않는다: charts/base.jsx 가 같은 이유로 금지해 둔
   * 패턴이다. SVG 텍스트의 fontSize 는 viewBox→CSS 폭 축소 배율을 그대로 먹어서 실제로는
   * 6~8px 로 그려지는데, QA 의 tiny_text 검사는 렌더 크기가 아니라 마크업의 명목값을 읽어
   * 통과로 오판한다(검사의 사각지대이지, 검사를 고칠 문제가 아니다).
   *
 * 높이: 이 락업은 3.49em(1080p 기준 ≈38px)이다. Toolbar 의 `minHeight: APPBAR_HEIGHT`
 * (52px)를 밀어 올리지 않는다 — AppBar 가 position:fixed 라 실제 높이가 본문의
 * `pt: APPBAR_HEIGHT` 오프셋과 어긋나면 본문 위쪽이 가려진다.
   *
 * 정렬: 바깥 상자에 `fontSize: BRAND_UNIT` 을 한 번 주고 안쪽 치수는 전부 em 이다.
 * 두 줄은 같은 폭이고 **왼쪽을 맞춘다** — 부제가 ClovirAssist 바로 아래에 붙는다. */
  return (
    <Box
      component="span"
      role="img"
      aria-label={`${title} Smart Workspace Assistant`}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: MARK_GAP,
        fontSize: BRAND_UNIT,
        maxWidth: "100%",
        flexShrink: 0,
        ...sx,
      }}
    >
      <Box
        component="svg"
        viewBox="0 0 128 128"
        aria-hidden="true"
        sx={{ display: "block", width: markSize, height: markSize, flexShrink: 0 }}
      >
        <CloverMark uid={uid} mode={mode} />
      </Box>

      <Box
        component="span"
        sx={{ display: "flex", flexDirection: "column", alignItems: "stretch", minWidth: 0, width: w }}
      >
        <Box
          component="svg"
          viewBox={WORDMARK_VIEWBOX}
          aria-hidden="true"
          className="wordmark"
          sx={{ display: "block", width: w, maxWidth: "100%", height: "auto" }}
        >
          {/* 글자는 놓인 면의 색을 따른다(currentColor). 강조어만 테마 액센트.
              y·총 textLength 는 원본 좌표계 그대로다 — viewBox 만 글자에 맞춰 잘랐다.

              ── 왜 `<text>` 하나에 `<tspan>` 둘인가 (F-W1R-34) ──────────────────
              예전에는 `<text>` **두 개**가 각각 절대 x 와 자기 textLength 를 들고 있었다:
              `x=160 textLength=167` 로 Clovir 가 x=327 에서 끝나는데 Assist 는 x=338 에서
              시작해 **11 유닛(화면에서 6px)의 구멍**이 생겼다. 그래서 셸의 제품명이
              "Clovir Assist" 두 단어로 읽혔다 — 같은 세션의 로그인 화면(원본 자산, 절대 x
              없음)은 한 단어로 붙어 있어 같은 제품이 두 이름을 갖고 있었다. CLAUDE.md §0 의
              Canonical Product Name 은 `ClovirAssist` **한 단어**다.

              고치는 방법은 좌표를 다시 재는 것이 아니라 **좌표를 없애는 것**이다. 하나의
              text 안에서 두 tspan 은 자연 진행폭으로 이어지므로 구멍이 생길 자리가 없고,
              다음에 폰트나 자간이 바뀌어도 다시 어긋나지 않는다. 폰트 폴백 보호(이 파일
              머리 주석)는 **총 textLength** 가 그대로 맡는다.

              총 폭은 원본과 같은 346(=506−160)이다. 실제 자연 진행폭은 342.3 이므로
              (fontTools 로 PretendardVariable 서브셋에서 wght 800/850 인스턴스화해 실측:
              Clovir@800 163.45 + Assist@850 178.85, letter-spacing −2.2 포함) 늘어남은
              **+1.1%** 다 — 락업 상자와 다른 시험이 보는 치수는 하나도 바뀌지 않는다. */}
          <text
            x="160"
            y="86"
            fontSize="62"
            letterSpacing="-2.2"
            textLength="346"
            lengthAdjust="spacingAndGlyphs"
          >
            <tspan fill="currentColor" fontWeight="800">Clovir</tspan>
            <tspan fill={accent} fontWeight="850">Assist</tspan>
          </text>
        </Box>
        {subtitle ? (
          // aria-hidden — 바깥 상자의 role="img" aria-label 이 이미 "Smart Workspace
          // Assistant"를 포함한다. 여기서 또 노출하면 같은 문구를 두 번 읽는다.
          <Box
            component="span"
            aria-hidden="true"
            sx={{
              whiteSpace: "nowrap",
              // 크기는 바깥 상자의 BRAND_UNIT 그대로다 — 이 글자가 락업의 기준 단위다.
              fontSize: "1em",
              lineHeight: SUBTITLE_LINE_HEIGHT,
              fontWeight: FONT_WEIGHT.semibold,
              letterSpacing: SUBTITLE_TRACKING,
              textAlign: "justify",
              textAlignLast: "justify",
              width: "100%",
              color: inverse ? INVERSE_INK.subtitle : "currentColor",
              opacity: inverse ? undefined : 0.62,
            }}
          >
            SMART WORKSPACE ASSISTANT
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}
