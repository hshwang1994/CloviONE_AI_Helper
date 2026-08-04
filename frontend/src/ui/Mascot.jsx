import React from "react";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Fab from "@mui/material/Fab";
import Paper from "@mui/material/Paper";
import Tooltip from "@mui/material/Tooltip";
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
        /* 22px 둥근 사각형 — 기준 파일의 .ai-fab 과 같은 형태다.
           예전에는 borderRadius:5.5(=테마 14px × 5.5 = 77px)라 70px 상자에서 **완전한 원**으로
           잘렸고, 그 안에 64px 정사각 포즈를 넣어 마스코트 모서리가 원 밖으로 나갔다.
           Chromium 은 버튼 콘텐츠를 안 자르지만 Firefox 는 자른다 — 브라우저마다 다르게 보였다. */
        borderRadius: "22px",
        overflow: "hidden",
        bgcolor: "background.paper",
        border: 1,
        borderColor: "divider",
        p: 0.5,
        // 바깥 래퍼(AppShell의 fixed Box)가 pointerEvents:none 이라 실제로 눌리는 것은 이 Fab
        // 하나다. 브라우저는 border-radius 를 히트 테스트에도 적용하므로, 이렇게 두면 둥근
        // 모서리 바깥의 빈 공간은 아래 콘텐츠가 그대로 받는다 — 안 보이는 사각형이 클릭을 먹지 않는다.
        pointerEvents: "auto",
        "&:hover": { bgcolor: "background.paper", transform: "translateY(-2px)" },
      }}
    >
      {/* 70px 상자 - 좌우 패딩 8px = 54px 이 안전한 최대치다(둥근 모서리 여유 포함). */}
      <MascotPose mode={mode} size={54} decorative />
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
          display: "inline-flex", alignItems: "center", gap: 0.75,
          height: 42, pl: 0.5, pr: { xs: 0.5, sm: 1.25 },
          border: 1, borderColor: "rgba(255,255,255,.18)", borderRadius: "14px",
          background: "rgba(8,14,42,.22)", color: "common.white",
          "&:hover": { background: "rgba(255,255,255,.16)" },
        }}
      >
        <Box sx={{ bgcolor: "rgba(255,255,255,.92)", borderRadius: "10px", display: "grid", placeItems: "center", width: 34, height: 34 }}>
          <MascotPose mode={mode} size={30} decorative />
        </Box>
        <Box component="span" sx={{ display: { xs: "none", sm: "block" }, fontSize: "0.75rem", fontWeight: 750 }}>
          클로비
        </Box>
      </ButtonBase>
    </Tooltip>
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
        // mx 로 이미 양옆을 3rem 비우는데 width 를 calc(100% - 1.5rem) 로 또 줄여서 폭이
        // 1.5rem 어긋나 있었다. 블록 요소는 mx 만으로 남는 폭을 채운다.
        width: "auto",
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
        <Typography color="common.white" fontSize="0.8125rem" fontWeight={800}>
          클로비에게 물어보기
        </Typography>
        {/* wordBreak:"keep-all" — 한글 기본값은 아무 데서나 끊어서 "도와드/려요"처럼 단어
            중간에 줄이 바뀐다. 좁은 사이드바에서는 반드시 두 줄이 되므로 띄어쓰기에서만
            끊기게 한다(한국어 조판의 기본 설정이다). */}
        <Typography color="rgba(237,240,255,.7)" fontSize="0.75rem" lineHeight={1.35}
          sx={{ wordBreak: "keep-all" }}>
          현재 화면을 기준으로 도와드려요
        </Typography>
      </Box>
    </Paper>
  );
}
