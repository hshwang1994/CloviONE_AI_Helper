import React from "react";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { keyframes } from "@mui/system";
import { alpha } from "@mui/material/styles";
import { MASCOT } from "../lib/assets.js";
import { FONT_SIZE, FONT_WEIGHT, RADIUS } from "./theme.js";

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
          background: "radial-gradient(circle, rgba(83,108,214,.26), transparent 70%)",
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
          borderColor: (t) => alpha(t.palette.primary.main, 0.42),
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
          bgcolor: `rgba(255,255,255,${plateOpacity})`,
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
 * 흰 판 위에 얹는 이유: 상단바는 딥 인디고 그라데이션이라 마스코트의 흰 몸체가 배경에 묻힌다.
 * 기준 파일도 같은 이유로 img 에 rgba(255,255,255,.92) 배경을 깐다. */
export function MascotTopButton({ onClick, mode = "listening", label = "AI 도우미" }) {
  return (
    <Tooltip title={label}>
      <ButtonBase
        onClick={onClick}
        aria-label="클로비 AI 도우미 열기"
        sx={{
          /* 색은 테마 토큰에서 온다. 예전 값(흰 글자 + 반투명 남색 바탕)은 어두운 상단바를
             전제한 것이라, chrome 이 캔버스 계열이 된 뒤 대비 1.21 로 떨어졌다(D-141).
             클로비 자체는 사용자가 "제품의 정체성"이라고 확정한 브랜드 요소라 그대로 둔다 —
             바뀌는 것은 그것을 감싼 판의 색뿐이다. */
          display: "inline-flex", alignItems: "center", gap: "6px",
          minHeight: "34px", pt: "2px", pb: "2px", pl: "3px", pr: "8px",
          border: 1, borderColor: "divider", borderRadius: `${RADIUS.sm}px`,
          bgcolor: "background.plate", color: "text.primary",
          "&:hover": { borderColor: "dividerStrong", bgcolor: "background.inset" },
        }}
      >
        <MascotMini mode={mode} size={28} plateRadius={RADIUS.sm} ringInset={-2} ringRadius={RADIUS.sm} />
        <Box component="span" sx={{ display: { xs: "none", sm: "block" }, fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold }}>
          클로비
        </Box>
      </ButtonBase>
    </Tooltip>
  );
}

