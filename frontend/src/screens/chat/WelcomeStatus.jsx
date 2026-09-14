import React from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { MascotPose } from "../../ui/Mascot.jsx";
import { Button, EmptyState } from "../../ui/kit.jsx";
import { FONT_SIZE } from "../../ui/theme.js";
import { MASCOT_PHASE_TEXT, QUICK_PROMPTS } from "../chat-helpers.js";

/* 시작 예시 칩, 누르면 그 문장을 컴포저에 채운다(빈 화면 막다른 길 방지). */
export function QuickPrompts({ onPick, busy }) {
  return (
    <Stack direction="row" flexWrap="wrap" gap={1} justifyContent="center" role="group" aria-label="시작 예시" sx={{ mt: 2 }}>
      {QUICK_PROMPTS.map((p, i) => (
        /* 누르는 시작 예시는 단추다(30) — 예전의 32 칩은 버튼 높이 집합 밖이었고(핸드오프 C1), hover 에서만
           강조색 글자로 바뀌어 대비를 따로 맞춰야 했다(QAH-07). 단추의 글자·테두리 대비는 부품이 지킨다. */
        <Button key={i} size="sm" disabled={busy} onClick={() => onPick(p)}>{p}</Button>
      ))}
    </Stack>
  );
}

/* 빈 화면 — 마스코트는 여기서 장식(decorative)이다. 상태를 말하는 마스코트는 상단바에 하나뿐이고,
   같은 상태를 두 번 낭독시키지 않는다. */
export function Welcome({ title, help, onPick, busy, mode }) {
  /* 대화가 없는 AI 도우미는 화면 전체가 비어 있는 자리다 — 화면 빈 상태(page)이고 클로비는 화면 계약
     크기(132, 짧은 화면 112)다(D-485 · 계획 P-12). 다음 행동은 시작 예시다. */
  return (
    <Box sx={{ m: "auto", width: "100%", maxWidth: "38rem" }}>
      <EmptyState
        layout="page"
        icon={<MascotPose mode={mode} place="emptyPage" decorative />}
        title={title}
        help={help}
        action={<QuickPrompts onPick={onPick} busy={busy} />}
      />
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
