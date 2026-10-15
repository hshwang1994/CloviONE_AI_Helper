import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "../../ui/theme.js";

/* 메일 설정의 일곱 단계 (D-560 · D-574) — 서버가 계산한 단계(`progress.steps`)를 번호 목록 하나로 세운다.
 *
 * 예전 진행 띠(`ProgressStrip`)는 칩 일곱 개를 한 줄에 흘렸다. 칩 안에는 상태 낱말이 화면 낭독용으로만 있어 눈으로는 색과 테두리로
 * 상태를 짐작해야 했고, 좁은 칸에서는 칩이 제멋대로 접혀 순서가 흐트러졌다. 이제는 격자 목록이다: 판이 좁으면 한 열, 보통 폭은
 * 4 + 3, 넓으면 일곱이 한 줄이다(칸 폭을 보는 컨테이너 질의). 처음에는 `auto-fill minmax(14rem, 1fr)` 이었는데 1920 에서 여섯 칸
 * + 외톨이 한 칸으로 섰고, 같은 폭으로 나눈 칸에서 「보내는 사람과 방식별 정보 입력」만 두 줄로 접혔다(캡처 m4-1 · 프로브
 * equal_column_split). 그래서 열 수는 판 폭이 정하고, 칸은 `auto` 라 긴 이름이 제 폭을 받는다. 줄마다 번호 또는 체크 · 이름 ·
 * 상태 낱말(끝남 · 지금 할 일 · 아직 · 막힘)이 보이고, 지금 할 일과 막힌 줄은 서버의 한 문장을 이름 아래에 단다.
 *
 * 「지금 할 일」 상자(상태 요약 면)가 이미 말한 단계(`quietKey`)는 그 문장을 다시 쓰지 않는다 — 같은 문장이 한 판에 두 번 서면 읽는
 * 사람은 두 가지 할 일로 읽는다. 단계를 지어내지 않는다: 이름 · 상태 · 문장은 전부 서버 값이다.
 */

/* 열 수의 문턱 — 4 + 3 은 칸마다 이름 한 줄(약 15rem)이 들어갈 때부터, 일곱 한 줄은 일곱 이름이 접히지 않고 서는 폭부터다. */
const STEPS_FOUR_REM = 40;
const STEPS_SEVEN_REM = 82;

export const STEP_STATE_LABEL = { done: "끝남", current: "지금 할 일", todo: "아직", blocked: "막힘" };

/* 작은 글자는 강한 쪽 잉크다 — `primary.main` 은 두 모드가 같은 값이라 어두운 면 위 「지금 할 일」이 2.54:1 이었다(캡처 m4-1 대비
   프로브). `primary.dark` 는 모드마다 강한 쪽으로 민 값이다(light 는 더 어둡게, dark 는 더 밝게). */
function stateColor(state) {
  if (state === "current") return "primary.dark";
  if (state === "blocked") return "error.strong";
  return "text.secondary";
}

function Marker({ state, index }) {
  const done = state === "done";
  return (
    <Box
      component="span"
      aria-hidden="true"
      sx={(t) => ({
        display: "inline-flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, borderRadius: "50%",
        fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold, lineHeight: 1,
        bgcolor: done ? "primary.main" : "transparent",
        color: done ? "primary.contrastText" : (state === "todo" ? "text.secondary" : stateColor(state)),
        border: done ? 0 : `1px solid ${state === "todo" ? t.palette.divider : "currentColor"}`,
      })}
    >
      {done ? <CheckRoundedIcon sx={{ fontSize: FONT_SIZE.bodySm }} /> : index + 1}
    </Box>
  );
}

function Step({ step, index, quiet }) {
  const state = step.state;
  const emphasised = state === "current" || state === "blocked";
  const hint = emphasised && !quiet && step.hint ? step.hint : null;
  return (
    <Box
      component="li"
      data-step={step.key}
      data-step-state={state}
      aria-current={state === "current" ? "step" : undefined}
      sx={(t) => ({
        display: "grid", gridTemplateColumns: "1.375rem minmax(0,1fr)", columnGap: 1, alignItems: "start", minWidth: 0,
        px: 1, py: 0.75, borderRadius: `${RADIUS.sm}px`,
        border: `1px solid ${state === "current" ? t.palette.primary.main : state === "blocked" ? t.palette.error.main : "transparent"}`,
        bgcolor: state === "current" ? "primary.soft" : "transparent",
      })}
    >
      <Box sx={{ pt: "0.0625rem" }}><Marker state={state} index={index} /></Box>
      {/* 한 열(좁은 판)에서는 이름과 상태 낱말이 한 줄이다 — 일곱 줄이 각각 두 줄이면 모바일에서 단계 목록만 화면 반을 먹었다(캡처
          m4-1 390). 여러 열에서는 칸이 좁아 낱말이 이름 아래로 간다. */}
      <Box sx={{
        display: "flex", flexWrap: "wrap", alignItems: "baseline", columnGap: 1, rowGap: 0.125, minWidth: 0,
        [`@container mail-steps (min-width: ${STEPS_FOUR_REM}rem)`]: { display: "grid", gap: 0.125 },
      }}>
        <Typography
          component="span"
          sx={{
            flex: "1 1 auto", minWidth: 0,
            fontSize: FONT_SIZE.bodySm, lineHeight: 1.45, ...KO_WORD_BREAK,
            fontWeight: emphasised ? FONT_WEIGHT.semibold : FONT_WEIGHT.regular,
            color: state === "todo" ? "text.secondary" : "text.primary",
          }}
        >
          {step.label}
        </Typography>
        <Typography component="span" sx={{ flex: "0 0 auto", fontSize: FONT_SIZE.caption, lineHeight: 1.4, color: stateColor(state) }} data-step-word="">
          {STEP_STATE_LABEL[state] || state}
        </Typography>
        {hint ? (
          <Typography component="span" sx={{ flexBasis: "100%", fontSize: FONT_SIZE.caption, lineHeight: 1.45, color: "text.secondary", ...KO_WORD_BREAK }}>
            {hint}
          </Typography>
        ) : null}
      </Box>
    </Box>
  );
}

export function MailSteps({ steps, quietKey = null }) {
  const list = Array.isArray(steps) ? steps : [];
  if (!list.length) return null;
  return (
    <Box sx={{ containerType: "inline-size", containerName: "mail-steps", minWidth: 0 }}>
      <Box
        component="ol"
        aria-label="메일 설정 단계"
        data-testid="mail-steps"
        sx={{
          listStyle: "none", m: 0, p: 0, minWidth: 0,
          display: "grid", gridTemplateColumns: "minmax(0, 1fr)", columnGap: 1, rowGap: 0.5,
          [`@container mail-steps (min-width: ${STEPS_FOUR_REM}rem)`]: { gridTemplateColumns: "repeat(4, auto)" },
          [`@container mail-steps (min-width: ${STEPS_SEVEN_REM}rem)`]: { gridTemplateColumns: "repeat(7, auto)" },
        }}
      >
        {list.map((step, i) => <Step key={step.key} step={step} index={i} quiet={quietKey === step.key} />)}
      </Box>
    </Box>
  );
}

export default MailSteps;
