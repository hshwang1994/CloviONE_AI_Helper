import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import { Button, Callout } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "../../ui/theme.js";

/* 메일 설정의 진행 띠 (기능 개선 회차 P4 ②, D-560) — 서버가 계산한 일곱 단계(`progress.steps`)와 「다음 할 일」 한 문장.
 *
 * 단계 칩은 상태 넷을 모양으로 가른다: 끝남(체크 · 옅은 면) · 지금(브랜드 테두리 · 굵게) · 아직(흐린 글자) · 막힘(오류색 테두리). 숫자
 * 배지가 순서를 말한다. 좁은 칸에서는 두 줄로 접힌다(`flexWrap`). 「다음 할 일」은 서버의 문장 그대로이고, [이동] 은 서버가 준 자리
 * (`anchor` — 구획 또는 머리 단추)로 간다. 화면이 단계를 지어내지 않는다 - 서버가 네트워크 없이 저장된 사실에서 계산한 값이다.
 * 「다음 할 일」 상자는 제목 없이 한 줄(굵은 꼬리표 + 문장)에 [이동]이다 — 동작이 든 상자의 계약(D-528: 아이콘 · 첫 줄 · 동작이 한 가운데선, 한 줄 56)은 제목 줄을 세지 않는다.
 */

export const STEP_STATE_LABEL = { done: "끝남", current: "지금 할 일", todo: "아직", blocked: "막힘" };

function chipSx(state) {
  const base = {
    display: "inline-flex", alignItems: "center", gap: 0.75, minHeight: 28, px: 1.25, borderRadius: `${RADIUS.pill || 999}px`,
    border: 1, borderColor: "divider", fontSize: FONT_SIZE.bodySm, color: "text.secondary", whiteSpace: "nowrap",
  };
  if (state === "done") return { ...base, bgcolor: "action.selected", color: "text.primary" };
  if (state === "current") return { ...base, borderColor: "primary.main", color: "text.primary", fontWeight: FONT_WEIGHT.semibold };
  if (state === "blocked") return { ...base, borderColor: "error.main", color: "error.main", fontWeight: FONT_WEIGHT.semibold };
  return base;
}

function Chip({ step, index }) {
  const done = step.state === "done";
  return (
    <Box component="li" sx={chipSx(step.state)} data-step={step.key} data-step-state={step.state}
      aria-current={step.state === "current" ? "step" : undefined} title={step.hint || undefined}>
      <Box component="span" aria-hidden="true" sx={{
        display: "inline-flex", alignItems: "center", justifyContent: "center", width: 18, height: 18, borderRadius: "50%",
        fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold,
        bgcolor: done ? "primary.main" : "transparent", color: done ? "primary.contrastText" : "inherit",
        border: done ? 0 : 1, borderColor: "currentColor",
      }}>
        {done ? <CheckRoundedIcon sx={{ fontSize: FONT_SIZE.caption }} /> : index + 1}
      </Box>
      <span>{step.label}</span>
      <span className="sr-only">{`, ${STEP_STATE_LABEL[step.state] || step.state}`}</span>
    </Box>
  );
}

export function ProgressStrip({ progress, onGo }) {
  if (!progress || !Array.isArray(progress.steps) || !progress.steps.length) return null;
  const next = progress.next;
  return (
    <Box data-testid="mail-progress" sx={{ display: "grid", gap: 1.25, minWidth: 0 }}>
      <Box component="ol" aria-label="메일 설정 단계" sx={{ listStyle: "none", m: 0, p: 0, display: "flex", flexWrap: "wrap", gap: 0.75 }}>
        {progress.steps.map((step, i) => <Chip key={step.key} step={step} index={i} />)}
      </Box>
      {next ? (
        <Callout
          tone={next.state === "blocked" ? "warn" : "info"} className="k-mail-next"
          action={onGo ? <Button size="sm" variant="primary" onClick={() => onGo(next)}>이동</Button> : null}
        >
          <Typography component="span" variant="body2" sx={KO_WORD_BREAK}>
            <Box component="strong" sx={{ fontWeight: FONT_WEIGHT.semibold, mr: 0.75 }}>다음 할 일</Box>
            {next.hint || next.label}
          </Typography>
        </Callout>
      ) : (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK} data-testid="mail-progress-complete">
          일곱 단계가 모두 끝났습니다. 설정을 바꾸면 연결 확인부터 다시 합니다.
        </Typography>
      )}
    </Box>
  );
}

export default ProgressStrip;
