import React from "react";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { keyframes } from "@mui/system";
import { alpha } from "@mui/material/styles";
import { MASCOT } from "../lib/assets.js";
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
};

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
};

export function MascotPose({ mode = "idle", size = 96, label, decorative = false }) {
  const src = POSE[mode] || POSE.idle;
  const name = label || LABEL[mode] || LABEL.idle;
  return (
    <Box
      role={decorative ? undefined : "img"}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : name}
      sx={{
        position: "relative",
        width: size,
        height: size,
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
  return (
    <Box
      role="img"
      aria-label={name}
      data-testid="mascot-mini"
      sx={{
        position: "relative", display: "inline-grid", placeItems: "center",
        width: size, height: size, flex: "0 0 auto", isolation: "isolate",
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
            width: size >= 48 ? "14px" : "10px", height: size >= 48 ? "14px" : "10px",
            border: size >= 48 ? "2px solid" : "1.5px solid",
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
 * 표정은 평상시(idle) 포즈를 쓴다 — 그 자산이 이미 웃는 얼굴이다(§5).
 *
 * **판은 깔지 않는다**(W2). 예전 주석은 "딥 인디고 위에서 마스코트의 흰 몸체가 묻힌다"고
 * 적었지만 실측은 반대였다 — 인디고 셸 위에서 클로비 자산은 그대로 읽히고, 흰 판이 오히려
 * 하우징에 뚫린 순백 원판이 되어 화면에서 가장 밝은 면을 만든다(F-W1R-13, 배포본 픽셀
 * 실측 (1690,25)=#FFFFFF on shell #1E2758). 자리를 감싸는 알약은 chrome 자신의 반전 컨트롤
 * 토큰(`chrome.track`/`edge`)을 쓰고, 그 안의 잉크는 AI Wash 하드 룰에 따라 `onShell` 이다.
 * 클로비 자산의 크기·프레이밍(`mascot_visible_size`)은 W7 소유라 여기서 건드리지 않는다. */
export function MascotTopButton({ onClick, mode = "listening", label = "AI 도우미" }) {
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
        <MascotMini
          mode={mode} size={28} plateOpacity={0}
          plateRadius={RADIUS.sm} ringInset={-2} ringRadius={RADIUS.sm}
        />
        <Box component="span" sx={{ display: { xs: "none", sm: "block" }, fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold }}>
          클로비
        </Box>
      </ButtonBase>
    </Tooltip>
  );
}

