import React from "react";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Fab from "@mui/material/Fab";
import Paper from "@mui/material/Paper";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { keyframes } from "@mui/system";
import { alpha } from "@mui/material/styles";
import { MASCOT } from "../lib/assets.js";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "./theme.js";

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

/* 우하단 플로팅 버튼. 모바일에서는 본문을 가리므로 숨기고 상단바 버튼을 쓴다. */
export function MascotButton({ onClick, mode = "listening", badge = 0 }) {
  const fab = (
    <Fab
      aria-label="클로비 AI 도우미 열기"
      onClick={onClick}
      sx={{
        /* 기준선 `.ai-fab { width:70px; height:70px; border-radius:23px; padding:6px;
           background:rgba(255,255,255,.96); }` 와 `.ai-fab .mascot-mini { width:58px }`.
           예전 값(반지름 22, 패딩 4, 포즈 54)은 눈대중이었다. */
        width: "70px",
        height: "70px",
        borderRadius: "23px",
        /* 기준선은 overflow:visible 이다 — 고리와 상태 점이 상자 밖으로 3~4px 나가야 한다.
           hidden 으로 두면 그 둘이 잘려 아예 안 보인다. */
        overflow: "visible",
        bgcolor: "rgba(255,255,255,.96)",
        border: 1,
        borderColor: (t) => alpha(t.palette.primary.main, 0.28),
        p: "6px",
        boxShadow: (t) => t.shadowTokens?.md,
        // 바깥 래퍼(AppShell의 fixed Box)가 pointerEvents:none 이라 실제로 눌리는 것은 이 Fab
        // 하나다. 브라우저는 border-radius 를 히트 테스트에도 적용하므로, 이렇게 두면 둥근
        // 모서리 바깥의 빈 공간은 아래 콘텐츠가 그대로 받는다 — 안 보이는 사각형이 클릭을 먹지 않는다.
        pointerEvents: "auto",
        "&:hover": {
          bgcolor: "rgba(255,255,255,.96)",
          transform: "translateY(-2px)",
          boxShadow: (t) => t.shadowTokens?.lg,
        },
      }}
    >
      <MascotMini mode={mode} size={58} plateRadius={18} plateOpacity={0.96} />
    </Fab>
  );
  return (
    /* 기준선은 960px 이하에서 FAB 을 숨긴다(그 아래에서는 상단바 버튼이 그 일을 한다). */
    <Box sx={{ "@media (max-width:960px)": { display: "none" } }}>
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
          /* 기준선 `.top-clovi-btn { min-height:44px; padding:3px 9px 3px 4px; gap:7px;
             border:1px solid rgba(255,255,255,.18); border-radius:14px;
             background:rgba(8,14,42,.22); }` 와 `.top-clovi-btn .mascot-mini { width:36px }`.
             예전에는 34px 흰 판 안에 30px 포즈를 넣어 마스코트가 실제보다 작았다. */
          display: "inline-flex", alignItems: "center", gap: "7px",
          minHeight: "44px", pt: "3px", pb: "3px", pl: "4px", pr: "9px",
          border: 1, borderColor: "rgba(255,255,255,.18)", borderRadius: "14px",
          background: "rgba(8,14,42,.22)", color: "common.white",
          "&:hover": { background: "rgba(255,255,255,.16)" },
        }}
      >
        <MascotMini mode={mode} size={36} plateRadius={10} ringInset={-2} ringRadius={12} />
        <Box component="span" sx={{ display: { xs: "none", sm: "block" }, fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.bold }}>
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
        /* 기준선 `.sidebar-clovi { width:calc(100% - 12px); margin:18px 6px 4px;
           grid-template-columns:52px minmax(0,1fr) auto; gap:10px; padding:9px 10px;
           border:1px solid rgba(255,255,255,.11); border-radius:15px;
           background:linear-gradient(135deg,rgba(117,138,225,.18),rgba(142,117,225,.08)) }`.
           예전 값(여백 16, 좌우 24, 반지름 18, 단색 바탕)은 눈대중이었다. */
        width: "calc(100% - 12px)",
        mt: "18px", mx: "6px", mb: "4px",
        px: "10px", py: "9px",
        display: "grid",
        gridTemplateColumns: "52px minmax(0,1fr) auto",
        gap: "10px",
        alignItems: "center",
        textAlign: "left",
        color: "inherit",
        borderRadius: "15px",
        borderColor: "rgba(255,255,255,.11)",
        background: "linear-gradient(135deg,rgba(117,138,225,.18),rgba(142,117,225,.08))",
        cursor: "pointer",
        "&:hover": {
          borderColor: "rgba(216,208,255,.45)",
          background: "linear-gradient(135deg,rgba(117,138,225,.28),rgba(142,117,225,.14))",
        },
      }}
    >
      <MascotMini mode="listening" size={48} plateRadius={13} plateOpacity={0.94}
        label="클로비가 질문을 기다리는 모습" />
      <Box minWidth={0}>
        {/* QA-하네스: 4K(>=3840px)에서 tiny_text 검사가 절대 px 글자 크기는 잡는다 — 루트
            글자 크기 레버(16→18→20px)가 커져도 px로 박힌 크기는 그대로다. DS-32가 같은
            원인의 다른 자리(TopSearch.jsx·kit.css)를 고치며 세운 관례(px→rem, 12px
            하한 밑이면 0.75rem으로 올림)를 그대로 따른다 — 이 자리는 그 스윕에서 빠져
            있었다(실측: 3840×2160에서 사용자 콘솔 66개 화면 전부 실패, 하나의 공용
            컴포넌트라 한 곳만 고치면 전부 해소된다). */}
        <Typography color="common.white" fontSize="0.8125rem" fontWeight={800}>
          클로비에게 물어보기
        </Typography>
        {/* wordBreak:"keep-all" — 한글 기본값은 아무 데서나 끊어서 "도와드/려요"처럼 단어
            중간에 줄이 바뀐다. 좁은 사이드바에서는 반드시 두 줄이 되므로 띄어쓰기에서만
            끊기게 한다(한국어 조판의 기본 설정이다). */}
        <Typography color="sidebar.muted" fontSize="0.75rem" lineHeight={1.35} mt="3px"
          sx={KO_WORD_BREAK}>
          현재 화면을 기준으로 도와드려요
        </Typography>
      </Box>
      {/* 기준선의 `.sidebar-clovi-arrow` — 누르면 무언가 열린다는 것을 알리는 홑화살표다. */}
      <Box component="span" aria-hidden="true" sx={{ fontSize: "24px", opacity: 0.7, lineHeight: 1 }}>
        ›
      </Box>
    </Paper>
  );
}
