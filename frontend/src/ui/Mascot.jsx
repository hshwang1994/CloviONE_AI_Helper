import React from "react";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Fab from "@mui/material/Fab";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { keyframes } from "@mui/system";
import { MASCOT } from "../lib/assets.js";

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

/* 우하단 플로팅 버튼. 모바일에서는 본문을 가리므로 숨기고 상단바 버튼을 쓴다. */
export function MascotButton({ onClick, mode = "listening", badge = 0 }) {
  const fab = (
    <Fab
      aria-label="클로비 AI 도우미 열기"
      onClick={onClick}
      sx={{
        width: 70,
        height: 70,
        borderRadius: 5.5,
        bgcolor: "background.paper",
        border: 1,
        borderColor: "divider",
        p: 0.25,
        "&:hover": { bgcolor: "background.paper", transform: "translateY(-2px)" },
      }}
    >
      <MascotPose mode={mode} size={64} decorative />
    </Fab>
  );
  return (
    <Box sx={{ display: { xs: "none", md: "block" } }}>
      {badge > 0 ? (
        <Badge badgeContent={badge} color="error" overlap="circular">
          {fab}
        </Badge>
      ) : (
        fab
      )}
    </Box>
  );
}

/* 사이드바 하단 CTA. */
export function MascotSidebarCard({ onClick }) {
  return (
    <Paper
      component="button"
      type="button"
      onClick={onClick}
      variant="outlined"
      sx={{
        width: "calc(100% - 1.5rem)",
        mx: 3,
        mt: 4,
        p: 2,
        display: "grid",
        gridTemplateColumns: "52px minmax(0,1fr)",
        gap: 2,
        alignItems: "center",
        textAlign: "left",
        color: "inherit",
        borderColor: "rgba(255,255,255,.12)",
        bgcolor: "rgba(117,138,225,.12)",
        cursor: "pointer",
        "&:hover": { bgcolor: "rgba(117,138,225,.2)" },
      }}
    >
      <MascotPose mode="listening" size={50} />
      <Box minWidth={0}>
        <Typography color="common.white" fontSize="0.75rem" fontWeight={800}>
          클로비에게 물어보기
        </Typography>
        <Typography color="rgba(237,240,255,.64)" fontSize="0.625rem" lineHeight={1.35}>
          현재 화면을 기준으로 도와드려요
        </Typography>
      </Box>
    </Paper>
  );
}
