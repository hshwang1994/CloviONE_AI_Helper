import React from "react";
import Box from "@mui/material/Box";
import { useTheme } from "@mui/material/styles";

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
 * 글자 폭은 textLength로 고정한다. 원본은 Inter/Pretendard를 전제로 좌표를 박아 뒀는데
 * 이 앱은 웹폰트를 쓰지 않아(사내망 CDN 차단, 6.7MB) 시스템 폰트로 대체된다 — 고정하지 않으면
 * 장비마다 두 단어가 붙거나 벌어진다.
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
  const accent = inverse ? INVERSE_INK.accent : theme.palette.primary.main;
  const w = width != null ? width : markOnly ? 40 : 230;

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

  /* 부제("SMART WORKSPACE ASSISTANT")는 SVG <text>로 그리지 않는다 — charts/base.jsx가
   * 이미 같은 이유로 금지해 둔 패턴이다: SVG 텍스트는 px 속성이 이 컴포넌트의
   * viewBox(528×156)→CSS 폭(150~224px) 축소 배율을 그대로 먹는다. fontSize="20"이라고
   * 적어도 실제로는 20 × (w/528) ≈ 6~8px로 그려져 QA의 tiny_text 검사 최소치(12px)에
   * 한참 못 미쳤다 — 그런데 그 검사는 렌더된 크기가 아니라 마크업의 명목값(20)을 읽어서
   * 통과로 오판했다(검사의 사각지대이지, 검사를 고칠 문제가 아니다).
   * 이 컴포넌트의 `markOnly` 변형(AppShell.jsx의 사이드바 헤더가 쓰는 자리)은 부제 자체를
   * 안 그려서 이 함정을 애초에 안 만난다 - 참고할 기존 HTML 렌더 사례는 없었고, 여기서
   * charts/base.jsx의 규칙을 그대로 적용해 새로 만들었다.
   *
   * 바깥 상자에 aspectRatio(528/156, 원본 viewBox 그대로)를 못박아 두는 이유: 이 컴포넌트를
   * 쓰는 TopBrand.jsx의 상단바 Toolbar는 `minHeight: APPBAR_HEIGHT`로 짜여 있고, 그 아래
   * 본문 영역은 `pt: APPBAR_HEIGHT/8`로 고정폭 오프셋을 준다(AppBar가 position:fixed라
   * 실제 높이와 본문 padding-top이 어긋나면 본문 위쪽이 가려진다). 부제를 SVG 밖 HTML로
   * 뺐다고 로고 전체 높이가 늘어나면 이 오프셋이 깨진다 — 그래서 SVG는 마크+"Clovir"+
   * "Assist"만 그대로 그리고, 부제는 그 위에 절대위치로 얹어 바깥 상자의 가로세로 비율을
   * SVG 하나였을 때와 똑같이 유지한다. */
  return (
    <Box
      sx={{
        position: "relative",
        display: "block",
        width: w,
        maxWidth: "100%",
        aspectRatio: "528 / 156",
        flexShrink: 0,
        ...sx,
      }}
    >
      <Box
        component="svg"
        viewBox="0 0 528 156"
        role="img"
        aria-label={`${title} Smart Workspace Assistant`}
        className="wordmark"
        sx={{ position: "absolute", inset: 0, display: "block", width: "100%", height: "100%" }}
      >
        <g transform="translate(10 14)">
          <CloverMark uid={uid} mode={mode} />
        </g>
        {/* 글자는 놓인 면의 색을 따른다(currentColor). 강조어만 테마 액센트. */}
        <text
          x="160"
          y="86"
          fill="currentColor"
          fontSize="62"
          fontWeight="800"
          letterSpacing="-2.2"
          textLength="167"
          lengthAdjust="spacingAndGlyphs"
        >
          Clovir
        </text>
        <text
          x="338"
          y="86"
          fill={accent}
          fontSize="62"
          fontWeight="850"
          letterSpacing="-2.2"
          textLength="168"
          lengthAdjust="spacingAndGlyphs"
        >
          Assist
        </text>
      </Box>
      {subtitle ? (
        // aria-hidden — 위 <svg role="img">의 aria-label이 이미 "Smart Workspace Assistant"를
        // 포함한다(subtitle prop과 무관하게 항상). 이 글자를 스크린리더에도 노출하면 같은
        // 문구를 두 번 읽는다.
        <Box
          component="span"
          aria-hidden="true"
          sx={{
            position: "absolute",
            left: "31%",
            top: "74%",
            whiteSpace: "nowrap",
            fontSize: "0.75rem",
            fontWeight: 600,
            letterSpacing: "0.08em",
            color: inverse ? INVERSE_INK.subtitle : "currentColor",
            opacity: inverse ? undefined : 0.62,
          }}
        >
          SMART WORKSPACE ASSISTANT
        </Box>
      ) : null}
    </Box>
  );
}
