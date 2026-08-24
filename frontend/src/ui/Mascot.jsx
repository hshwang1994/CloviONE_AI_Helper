import React from "react";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { keyframes } from "@mui/system";
import { alpha } from "@mui/material/styles";
import { MASCOT } from "../lib/assets.js";
import { hfracOf } from "./mascotBounds.js";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, RADIUS } from "./theme.js";

/* 마스코트 '클로비'.
 *
 * 디자인 원본에는 상태가 10종 정의돼 있었지만 어디에도 연결돼 있지 않았다 — 그냥 장식이었다.
 * 여기서는 앱의 실제 상태(대화 단계, 오류 종류, 세션 만료 등)에 붙일 수 있게 mode를 받는다.
 *
 * 애니메이션은 CSS 키프레임이다(애니메이션 라이브러리 없음). 모션 축소는 theme.js의
 * 전역 규칙이 처리하므로 여기서 따로 분기하지 않는다 — 분기를 컴포넌트마다 넣으면
 * 새로 만들 때마다 빠뜨린다.
 *
 * 런타임에는 완성된 포즈 PNG만 교체한다. frames/·layers/ 합성은 금지
 * (docs/mascot-animation-spec.md §5).
 */

const enter = keyframes`
  from { opacity: .18; transform: translateY(5px) scale(.97); }
  to { opacity: 1; transform: none; }
`;
const float = keyframes`
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
`;
const talk = keyframes`
  0%, 100% { transform: translateY(0) rotate(0); }
  50% { transform: translateY(-2px) rotate(-.7deg); }
`;
const celebrate = keyframes`
  0% { opacity: .2; transform: translateY(8px) scale(.95); }
  58% { opacity: 1; transform: translateY(-4px) scale(1.025); }
  100% { transform: none; }
`;
const shake = keyframes`
  25% { transform: translateX(-2px); }
  60% { transform: translateX(2px); }
`;
const ring = keyframes`
  0% { opacity: .75; transform: scale(.9); }
  75%, 100% { opacity: 0; transform: scale(1.2); }
`;
const spin = keyframes`to { transform: rotate(360deg); }`;
const breathe = keyframes`
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.015); }
`;

/* 상태 → 포즈 파일. 상태 이름은 앱 쪽 의미(듣는 중/생각 중/응답 중)를 쓴다. */
const POSE = {
  idle: MASCOT.idle,
  listening: MASCOT.idle,
  welcome: MASCOT.wave,
  wave: MASCOT.wave,
  thinking: MASCOT.think,
  responding: MASCOT.talking,
  success: MASCOT.happy,
  error: MASCOT.error,
  love: MASCOT.love,
  sleep: MASCOT.sleep,
  /* 웃는 얼굴. `clovi-idle` 은 **눈을 감은 졸린 얼굴**이라 이 자리에 쓰면 상단바가 자는
     로봇을 보여 준다(PLAN «발견된 버그»). 사용자가 우상단에 원한 얼굴은 이쪽이다. */
  greeting: MASCOT.avatar,
};

/* ── 화면은 «보이는 크기» 를 말한다 — 박스가 아니라 (지시 71 · PLAN «Clovi 계약») ──────
 *
 * 포즈 PNG 는 전부 1024² 인데 캐릭터가 차지하는 세로 비율(`hfrac`)이 자산마다 0.666~0.850
 * 으로 벌어진다. 그래서 **호출부가 박스 픽셀을 적으면 같은 숫자가 자산마다 다른 크기로
 * 보인다** — `size={48}` 이 `clovi-avatar` 면 40px, `clovi-button` 이면 32px 짜리 캐릭터다.
 * 지시 71 이 "실제 브라우저에서 클로비가 너무 작다" 고 지적한 것의 정확한 메커니즘이고,
 * 박스를 재는 어떤 검사로도 안 보인다. S16 이 표의 열에서 폭 숫자를 걷어낸 것과 같은
 * 수리다: **호출부는 뜻(자리)을 말하고 치수는 한 자리에서 파생한다.**
 *
 * `visible` 은 PLAN «Clovi 계약» 표가 정한 «보이는 캐릭터 크기» 다. 박스는 렌더할 때
 * `visible / hfrac(포즈)` 로 계산하므로, 자산을 다시 출력해 여백이 바뀌면 박스가 **따라
 * 움직인다** — 숫자를 다시 적지 않는다.
 *
 * `context` 는 QA 프로브(`scripts/ui_qa/mascot.py`)가 이 자리를 어느 밴드로 판정하는가다.
 * 그 값은 DOM 에 `data-mascot-context` 로 나간다 — **추론이 아니라 선언**이라야 한다.
 * 선언이 없으면 프로브가 DOM 모양으로 자리를 짐작하고, 분류가 곧 판정이라 짐작이 틀리면
 * 통과·실패가 통째로 뒤집힌다(드로어 머리의 마스코트가 FAB 으로 분류되던 자리).
 *
 * FAB 과 사이드바 카드는 이 표에 없다. PLAN 표에는 있지만 그 두 진입점은 **PA-RC-0019/0020
 * 이 이미 없앴다** — FAB 이 표 마지막 행의 클릭을 가로챘고, 진입점 셋을 상단바 하나로 모았다.
 * 없앤 자리를 계약표를 채우려고 되살리지 않는다. */
export const MASCOT_PLACE = {
  /* 상단바만 «보이는 크기» 가 뷰포트를 탄다. PLAN 표는 이 자리에 40px(박스 48)을 적었는데,
     같은 PLAN 이 상단바 높이를 **52/60/68 로 유지**한다고 적어 두었다 — 48px 박스에 패딩과
     테두리를 더하면 52px 짜리 막대에 들어가지 않는다. 두 조항이 충돌하므로 숫자를 하나 고르는
     대신 **비율**을 고정한다: 박스는 언제나 자기 하우징의 79% 다(41/47/54). 4K 레버가 막대를
     키우면 클로비가 같이 큰다. 1920 에서 보이는 캐릭터는 22px 에서 **34px** 가 되고,
     2200 이상에서 PLAN 의 40px 에 닿는다. */
  topbar:        { visible: { xs: 34, xxl: 40, uhd: 46 }, context: "topbar" },
  assistantHead: { visible: 40,  context: "inline" },
  assistantHero: { visible: 144, context: "hero" },
  chatStatus:    { visible: 40,  context: "inline" },
  chatWelcome:   { visible: 132, context: "inline" },
  loginHandoff:  { visible: 144, context: "hero" },
  gameCelebrate: { visible: 96,  context: "inline" },
  /* 빈 화면·오류 화면의 그림. 마스코트 포즈가 아니라 `ART` 일러스트가 앉는 자리지만
     여백 문제도 판정 밴드도 같아서 같은 표에서 다룬다(`kit.jsx` 가 쓴다).
     `emptyPage` 만 `empty_state` 밴드다 — 그 밴드의 위쪽 절반("빈 공간을 캐릭터로 때우는가")은
     **컨테이너 높이를 그림이 아닌 것이 정할 때만** 성립한다. 그림이 그 구획에서 가장 큰
     요소이면 컨테이너 높이가 곧 그림 높이라 어떤 비율 규칙도 통과할 수 없다(순환이다).
     `layout="page"` 는 `minHeight: min(28rem, 55vh)` 를 레이아웃이 정하므로 순환이 아니고,
     그 자리가 바로 지시 18 이 지목한 자리다(4K 에서 세로 450px 를 마스코트가 차지하던 화면).
     구획·팝오버의 빈 상태는 본문 안 그림이라 `inline` 이다. */
  emptyPage:     { visible: 132, context: "empty_state" },
  emptyRegion:   { visible: 84,  context: "inline" },
  emptyCompact:  { visible: 84,  context: "inline" },
  errorState:    { visible: 112, context: "empty_state" },
};

/** 자리 이름 + 자산 경로 → CSS 박스 픽셀. 자산의 투명 여백을 보정한 값이다.
 *
 * `visible` 이 뷰포트별 객체면 박스도 같은 키의 객체로 나온다 — MUI `sx` 가 그대로 받는다.
 */
export function mascotBoxPx(place, src) {
  const spec = MASCOT_PLACE[place];
  if (!spec) return null;
  const hfrac = hfracOf(src) > 0 ? hfracOf(src) : 1;
  const box = (v) => Math.round(v / hfrac);
  if (typeof spec.visible === "number") return box(spec.visible);
  const out = {};
  for (const key of Object.keys(spec.visible)) out[key] = box(spec.visible[key]);
  return out;
}

/* 상태 → 본체 애니메이션. */
function bodyAnimation(mode) {
  switch (mode) {
    case "responding":
      return `${talk} 780ms ease-in-out infinite`;
    case "success":
    case "welcome":
    case "wave":
      return `${celebrate} 900ms cubic-bezier(.2,.8,.2,1) both`;
    case "thinking":
      return `${float} 1.8s ease-in-out infinite`;
    case "error":
      return `${shake} 420ms ease both`;
    case "sleep":
      return `${breathe} 3.4s ease-in-out infinite`;
    default:
      return `${enter} 280ms cubic-bezier(.2,.8,.2,1) both`;
  }
}

/* 상태 → 뒤쪽 후광 애니메이션(듣는 중은 파장, 생각/응답 중은 회전). */
function haloAnimation(mode) {
  if (mode === "listening") return `${ring} 1.8s ease-out infinite`;
  if (mode === "thinking" || mode === "responding") return `${spin} 1.5s linear infinite`;
  return "none";
}

/* 상태별 낭독 라벨 — 애니메이션만으로 상태를 전하지 않는다(마스코트 사양서 접근성 규칙). */
const LABEL = {
  idle: "클로비",
  listening: "클로비가 질문을 기다리고 있습니다",
  welcome: "클로비가 인사합니다",
  wave: "클로비가 인사합니다",
  thinking: "클로비가 생각하는 중입니다",
  responding: "클로비가 답하는 중입니다",
  success: "완료되었습니다",
  error: "문제가 발생했습니다",
  love: "클로비가 기뻐합니다",
  sleep: "클로비가 쉬고 있습니다",
  greeting: "클로비",
};

/* `place` 를 주면 박스는 그 자리의 «보이는 크기» 에서 파생한다 — 호출부는 숫자를 안 적는다.
 * `size` 는 자리 이름이 없는 호출부(시험 등)를 위해 남긴다. 둘 다 주면 `place` 가 이긴다. */
export function MascotPose({ mode = "idle", place, size = 96, label, decorative = false }) {
  const src = POSE[mode] || POSE.idle;
  const name = label || LABEL[mode] || LABEL.idle;
  const spec = place ? MASCOT_PLACE[place] : null;
  const box = spec ? mascotBoxPx(place, src) : size;
  return (
    <Box
      role={decorative ? undefined : "img"}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : name}
      data-mascot-context={spec ? spec.context : undefined}
      sx={{
        position: "relative",
        width: box,
        height: box,
        display: "inline-grid",
        placeItems: "center",
        flexShrink: 0,
        isolation: "isolate",
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          position: "absolute",
          inset: "24%",
          borderRadius: "50%",
          zIndex: 0,
          /* Halo 는 **Brand 보라**다. 예전에는 `rgba(83,108,214,.26)` 이 박혀 있었는데 그것은
             구 기본 Accent 값이었다 — 기본 Accent 가 바뀐 순간 이 색은 제품 어디에도 없는
             색이 됐고, 사용자가 Accent 를 바꾸면 Clovi 만 옛 색으로 남았다. Clovi 는 Brand
             자산이므로 Brand 토큰에서 색을 받아야 하고 사용자 Accent 를 따라가면 안 된다. */
          background: (t) =>
            `radial-gradient(circle, ${alpha(t.palette.brand.purple, 0.26)}, transparent 70%)`,
          filter: "blur(12px)",
          animation: haloAnimation(mode),
        }}
      />
      <Box
        component="img"
        src={src}
        alt=""
        loading="lazy"
        decoding="async"
        sx={{
          position: "relative",
          zIndex: 1,
          width: "100%",
          height: "100%",
          objectFit: "contain",
          transformOrigin: "50% 84%",
          animation: bodyAnimation(mode),
        }}
      />
    </Box>
  );
}

/* 기준선의 `.mascot-mini` — 상단바·사이드바·FAB 세 자리가 공유하는 작은 클로비.
 *
 * MascotPose 와 구조가 다르다. MascotPose 는 뒤에 흐린 후광을 깔지만, 기준선의 mascot-mini 는
 *   1) 뒤에 **테두리 고리**(.mascot-mini-ring) 를 두고,
 *   2) 마스코트 그림 자체에 반투명 흰 판을 깔며(어두운 면에서 흰 몸체가 묻히지 않게),
 *   3) 오른쪽 아래에 상태 점(.mascot-mini-status) 을 찍는다.
 * 세 자리 모두 사용자가 "이거 바꾸자고 했는데 왜 적용 안 돼있음" 이라고 한 자리다.
 *
 * 치수는 부르는 쪽이 정한다 — 기준선도 자리마다 다르다(상단바 36, 사이드바 48, FAB 58).
 */
export function MascotMini({
  mode = "idle",
  place,
  size = 48,
  label,
  // 그림에 깔 흰 판의 반지름·불투명도. 기준선이 자리마다 다르게 준다.
  plateRadius = 14,
  plateOpacity = 0.95,
  ringInset = -4,
  ringRadius = 18,
  status = true,
}) {
  const src = POSE[mode] || POSE.idle;
  const name = label || LABEL[mode] || LABEL.idle;
  const spec = place ? MASCOT_PLACE[place] : null;
  const box = spec ? mascotBoxPx(place, src) : size;
  /* 상태 점의 크기는 가장 작은 단계를 따른다 — 뷰포트마다 점만 커졌다 작아지면 그 점이
     상태가 아니라 크기를 말하게 된다. */
  const boxFloor = typeof box === "number" ? box : Math.min(...Object.values(box));
  return (
    <Box
      role="img"
      aria-label={name}
      data-testid="mascot-mini"
      data-mascot-context={spec ? spec.context : undefined}
      sx={{
        position: "relative", display: "inline-grid", placeItems: "center",
        width: box, height: box, flex: "0 0 auto", isolation: "isolate",
      }}
    >
      <Box
        aria-hidden="true"
        sx={{
          position: "absolute", zIndex: 0, inset: `${ringInset}px`,
          border: 2, borderStyle: "solid",
          /* Ring 도 Brand 다 — Halo 와 같은 이유로 사용자 Accent 를 따라가지 않는다.
             Clovi 는 사용자 취향이 아니라 제품 정체성이 소유한다. */
          borderColor: (t) => alpha(t.palette.brand.violetInk, 0.42),
          borderRadius: `${ringRadius}px`, opacity: 0.55,
          /* 기준선의 .mascot-mini-ring 애니메이션과 같은 뜻이다 — 듣는 중은 파장,
             생각/응답 중은 회전. 모션 축소는 theme.js 의 전역 규칙이 처리한다. */
          animation: haloAnimation(mode),
        }}
      />
      <Box
        component="img"
        src={src}
        alt=""
        decoding="async"
        sx={{
          position: "relative", zIndex: 2,
          width: "100%", height: "100%", objectFit: "contain",
          borderRadius: `${plateRadius}px`,
          /* 판 없이 놓을 수 있어야 한다. 인디고 하우징(상단바) 위에서는 흰 판이 캐릭터를
             돕는 것이 아니라 **하우징에 구멍을 낸다** — 클로비 자산의 몸체가 이미 밝아
             인디고 위에서 충분히 읽힌다(F-W1R-13 이 '순백 원판' 으로 잡은 자리). */
          bgcolor: plateOpacity > 0 ? `rgba(255,255,255,${plateOpacity})` : "transparent",
          transformOrigin: "50% 84%",
          animation: bodyAnimation(mode),
        }}
      />
      {status ? (
        <Box
          aria-hidden="true"
          sx={{
            position: "absolute", zIndex: 3, right: "-3px", bottom: "-3px",
            width: boxFloor >= 48 ? "14px" : "10px", height: boxFloor >= 48 ? "14px" : "10px",
            border: boxFloor >= 48 ? "2px solid" : "1.5px solid",
            borderColor: "background.paper", borderRadius: "50%",
            bgcolor: "success.main",
          }}
        />
      ) : null}
    </Box>
  );
}

/* 상단바 우측 클로비 버튼 — 기준 파일의 .top-clovi-btn.
 *
 * 예전에는 여기에 MUI 의 일반 로봇 아이콘(SmartToyOutlined)이 있었다. 사용자가 "오른쪽 상단에
 * 표시되는 웃는 클로비"를 유지해 달라고 한 그 자리인데, 실제로는 클로비가 아니라 아무 로봇이었다.
 * 그 뒤로도 한 번 더 틀렸다: 여기 주석이 `clovi-idle` 을 "이미 웃는 얼굴" 이라고 적어 두었는데
 * **그 자산은 눈을 감은 졸린 얼굴**이다(PLAN «발견된 버그»). 상단바가 자는 로봇을 보여 주고
 * 있었다. 웃는 얼굴은 `clovi-avatar` 이고 그것이 `mode="greeting"` 이다.
 *
 * **판은 깔지 않는다**(W2). 예전 주석은 "딥 인디고 위에서 마스코트의 흰 몸체가 묻힌다"고
 * 적었지만 실측은 반대였다 — 인디고 셸 위에서 클로비 자산은 그대로 읽히고, 흰 판이 오히려
 * 하우징에 뚫린 순백 원판이 되어 화면에서 가장 밝은 면을 만든다(F-W1R-13, 배포본 픽셀
 * 실측 (1690,25)=#FFFFFF on shell #1E2758). 자리를 감싸는 알약은 chrome 자신의 반전 컨트롤
 * 토큰(`chrome.track`/`edge`)을 쓰고, 그 안의 잉크는 AI Wash 하드 룰에 따라 `onShell` 이다.
 * 클로비 자산의 크기·프레이밍(`mascot_visible_size`)은 W7 소유라 여기서 건드리지 않는다. */
export function MascotTopButton({ onClick, mode = "greeting", label = "AI 도우미" }) {
  return (
    <Tooltip title={label}>
      <ButtonBase
        onClick={onClick}
        aria-label="클로비 AI 도우미 열기"
        sx={(t) => ({
          /* 색은 테마 토큰에서 온다. 이 자리는 두 번 틀렸다 — 흰 글자 + 반투명 남색 리터럴
             (어두운 상단바 전제, D-141 로 1.21 로 붕괴) → 캔버스 토큰 `background.plate`
             (D-179 로 셸이 인디고가 되자 순백 원판). 값을 또 고르는 대신 **chrome 자신의**
             반전 컨트롤 토큰을 쓴다. 클로비 자체는 사용자가 "제품의 정체성"이라고 확정한
             브랜드 요소라 그대로 둔다. */
          display: "inline-flex", alignItems: "center", gap: "6px",
          /* 오른쪽 패딩은 **라벨을 위한 것**이다. 600px 미만에서는 그 라벨이 숨는데 패딩만
             남아 마스코트가 상자 중심에서 2px 왼쪽으로 밀렸다(390 실측: 왼쪽 4px / 오른쪽 8px).
             라벨이 없으면 패딩도 없다. */
          /* 높이는 rem — 셸의 틀이 4K 에서 1.31× 자라는 동안 컨트롤만 px 로 남으면 비율이
             어긋난다(TopSearch 와 같은 이유). 16 은 root.css 4K 레버의 기본 단계다. */
          minHeight: `${CONTROL.button / 16}rem`, pt: "2px", pb: "2px", pl: "3px",
          pr: { xs: "3px", sm: "8px" },
          border: 1, borderColor: t.palette.chrome.edge, borderRadius: `${RADIUS.sm}px`,
          bgcolor: t.palette.chrome.track, color: t.palette.chrome.onShell,
          "&:hover": { borderColor: t.palette.chrome.edge, bgcolor: t.palette.chrome.trackSelected },
        })}
      >
        {/* 크기를 숫자로 안 적는다 — `place="topbar"` 가 «보이는 캐릭터 40px» 을 말하고
            박스는 그 포즈의 여백에서 파생한다. 예전에는 `size={28}` 이었고 그 박스는
            `clovi-idle` 로 **보이는 캐릭터 22px** 였다(PLAN 이 지목한 자리). */}
        <MascotMini
          mode={mode} place="topbar" plateOpacity={0}
          plateRadius={RADIUS.sm} ringInset={-2} ringRadius={RADIUS.sm}
        />
        <Box component="span" sx={{ display: { xs: "none", sm: "block" }, fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold }}>
          클로비
        </Box>
      </ButtonBase>
    </Tooltip>
  );
}

