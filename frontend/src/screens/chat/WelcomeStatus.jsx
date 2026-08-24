import React from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { MascotPose } from "../../ui/Mascot.jsx";
import { FONT_SIZE } from "../../ui/theme.js";
import { MASCOT_PHASE_TEXT, QUICK_PROMPTS } from "../chat-helpers.js";

/* 시작 예시 칩, 누르면 그 문장을 컴포저에 채운다(빈 화면 막다른 길 방지). */
export function QuickPrompts({ onPick, busy }) {
  return (
    <Stack direction="row" flexWrap="wrap" gap={1} justifyContent="center" role="group" aria-label="시작 예시" sx={{ mt: 2 }}>
      {QUICK_PROMPTS.map((p, i) => (
        <Chip key={i} clickable disabled={busy} label={p} onClick={() => onPick(p)} variant="outlined"
          // QAH-07 — 이 칩은 Chat.jsx의 background.default 위에 뜬다(Card의 background.paper가
          // 아니다) — light 모드도 accent 4개 중 2개가 미달(4.37/4.38), dark는 전량 미달(최저
          // 3.07) 실측. borderColor는 텍스트가 아니라 손대지 않고 color만 primary.dark로 교체.
          sx={{ fontSize: FONT_SIZE.bodySm, height: "2rem", "&:hover": { borderColor: "primary.main", color: "primary.dark" } }} />
      ))}
    </Stack>
  );
}

/* 빈 화면 — 마스코트는 여기서 장식(decorative)이다. 상태를 말하는 마스코트는 상단바에 하나뿐이고,
   같은 상태를 두 번 낭독시키지 않는다. */
export function Welcome({ title, help, onPick, busy, mode }) {
  return (
    <Box sx={{ m: "auto", textAlign: "center", color: "text.secondary", maxWidth: "38rem", px: 2, py: 4 }}>
      <Box sx={{ display: "grid", justifyItems: "center", mb: 1 }}>
        <MascotPose mode={mode} place="chatWelcome" decorative />
      </Box>
      {/* PA-RC-0001: MUI 기본 h5(24px)보다 의도적으로 작게 한 22px — pageTitle(20px)·statValue(30px)
          사이라 기존 토큰과 안 맞는다. 실측 없이 스냅하지 않는다(의도된 예외). */}
      <Typography variant="h5" component="h2" color="text.primary" sx={{ fontSize: "1.375rem", mb: 1 }}>{title}</Typography>
      <Typography sx={{ fontSize: "0.9375rem", lineHeight: 1.6 }}>{help}</Typography>
      <QuickPrompts onPick={onPick} busy={busy} />
    </Box>
  );
}

// ── 마스코트 상태 표시 ──────────────────────────────────────────────────────

/* 마스코트를 대화 단계에 붙인다 — 지금까지 이 컴포넌트는 어디서나 'listening' 한 포즈로 고정돼
 * 있어서, 상태를 전한다고 주장하면서 아무 상태도 전하지 않는 장식이었다. 포즈 결정은 순수 함수
 * mascotMode(chat-helpers.js)가 하고 여기서는 그리기만 한다(그래야 매핑을 테스트할 수 있다).
 * 그림만으로 상태를 전하지 않는다 — 옆의 한 줄 문구가 같은 정보를 글자로 준다. */
export function MascotStatus({ mode }) {
  return (
    <Stack direction="row" alignItems="center" gap={1} sx={{ flexShrink: 0, minWidth: 0 }}>
      <MascotPose mode={mode} place="chatStatus" />
      <Typography
        role="status" aria-live="polite"
        sx={{ display: { xs: "none", lg: "block" }, fontSize: FONT_SIZE.bodySm, color: "text.secondary", whiteSpace: "nowrap" }}
      >
        {MASCOT_PHASE_TEXT[mode]}
      </Typography>
    </Stack>
  );
}
