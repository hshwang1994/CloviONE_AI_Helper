import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

import { resolveChartColor, useTrackColor } from "./base.jsx";
import { useRevealOnce } from "../motion.js";
import { FONT_SIZE, FONT_WEIGHT, MOTION } from "../theme.js";

/* 한 값이 상한의 얼마인가 — **막대 하나** (지시 10 · 15 · 16).
 *
 * ## 왜 `ProgressRows` 가 아닌가
 *
 * 그쪽은 **여러 줄을 서로 비교**하는 그림이다(담당자별 남은 일 같은 것). 줄이 하나뿐이면
 * 그 파일이 하는 일 중 절반(이름 칸 폭 맞추기, 분모 없는 줄 처리)이 낭비가 되고, 반대로
 * 이 자리가 필요로 하는 것(값이 이미 큰 글자로 위에 있고 막대는 거들기만 한다)은 없다.
 *
 * ## 숫자가 먼저다
 *
 * 막대는 `aria-hidden` 이고 값은 언제나 글자로 함께 나간다. 흑백으로 인쇄하거나 그림을
 * 못 보는 사람도 정보량이 같다 — 이 저장소의 다른 그림들과 같은 규약이다.
 *
 * `percent` 가 `null` 이면 **막대를 안 그린다.** 0% 로 그리면 「세어 봤더니 0」이라는
 * 거짓말이 된다(`project-format.js` 의 계약).
 */
export function ProgressBar({ percent, color, height = 8, label, emptyLabel, revealKey }) {
  const theme = useTheme();
  const track = useTrackColor();
  const grown = useRevealOnce(revealKey);

  const known = typeof percent === "number" && Number.isFinite(percent);
  if (!known) {
    return emptyLabel ? (
      <Typography variant="body2" color="text.secondary">{emptyLabel}</Typography>
    ) : null;
  }

  const pct = Math.max(0, Math.min(100, percent));
  const fill = resolveChartColor(theme, color, 0);

  return (
    <Box sx={{ display: "grid", gap: 0.5, minWidth: 0 }}>
      {label ? (
        <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1, alignItems: "baseline" }}>
          <Typography variant="body2" color="text.secondary">{label}</Typography>
          <Typography component="span" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold }}>
            {Math.round(pct * 10) / 10}%
          </Typography>
        </Box>
      ) : null}
      <Box
        aria-hidden="true"
        sx={{ height, borderRadius: height, bgcolor: track, overflow: "hidden", minWidth: 0 }}
      >
        <Box
          sx={{
            height: "100%", borderRadius: height, bgcolor: fill,
            width: `${grown ? pct : 0}%`,
            transition: `width ${MOTION.base} ${MOTION.ease}`,
          }}
        />
      </Box>
    </Box>
  );
}
