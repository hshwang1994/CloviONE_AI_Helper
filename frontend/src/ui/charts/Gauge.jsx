import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

import { resolveChartColor, useTrackColor } from "./base.jsx";
import { useRevealOnce } from "../motion.js";
import { FONT_SIZE, FONT_WEIGHT, MOTION } from "../theme.js";

/* 점수 하나를 **원으로** 그린다 (지시 10 · 16).
 *
 * ## 왜 도넛이 아니라 따로 있나
 *
 * `Donut` 은 **여럿의 구성**을 그린다 — 조각마다 이름이 있고 범례가 그 이름을 읽어 준다.
 * 점수는 구성이 아니라 **한 값이 상한의 몇 분의 몇인가**다. 도넛으로 그리면 「남은 점수」
 * 라는 이름 없는 조각이 범례에 서고, 그 조각은 아무 뜻도 없다.
 *
 * ## 숫자가 먼저다
 *
 * 가운데 글자가 그림 없이도 읽히는 값이고, 원은 그것을 거든다. 그림을 못 보는 사람이
 * 잃는 것이 없어야 한다 — 그래서 원은 `aria-hidden` 이고 점수는 글자로 나간다.
 *
 * 반지름을 15.91549431(= 100 / 2π)로 잡으면 원둘레가 정확히 100 이 되어, `strokeDasharray`
 * 에 백분율을 그대로 써 넣을 수 있다(`Donut` 과 같은 수법이고 같은 이유다).
 */

const R = 15.91549431;

export function Gauge({
  value, max = 100, size = "7rem", thickness = 5,
  label, centerText, color, emptyLabel = "아직 재지 않음", revealKey,
}) {
  const theme = useTheme();
  const track = useTrackColor();
  const drawn = useRevealOnce(revealKey);

  const known = typeof value === "number" && Number.isFinite(value);
  /* **모르는 것과 0 은 다른 값이다.** 안 잰 점수를 0 으로 그리면 한 번도 안 잰 프로젝트가
     화면에서 가장 나쁜 프로젝트가 된다(`app/projects/health.py` 가 같은 판단을 한다). */
  if (!known) {
    return (
      <Box sx={{ display: "grid", gap: 0.5, justifyItems: "center" }}>
        <Box
          aria-hidden="true"
          sx={{
            width: size, height: size, borderRadius: "50%",
            border: `${thickness * 0.6}px dashed`, borderColor: "divider",
            display: "grid", placeItems: "center",
          }}
        />
        <Typography variant="body2" color="text.secondary">{emptyLabel}</Typography>
      </Box>
    );
  }

  const pct = Math.max(0, Math.min(100, (value / (max || 100)) * 100));
  const stroke = resolveChartColor(theme, color, 0);

  return (
    <Box sx={{ display: "grid", gap: 0.5, justifyItems: "center", minWidth: 0 }}>
      <Box sx={{ position: "relative", width: size, height: size }}>
        <Box component="svg" viewBox="0 0 42 42" aria-hidden="true" sx={{ width: "100%", height: "100%", display: "block" }}>
          <circle cx="21" cy="21" r={R} fill="none" stroke={track} strokeWidth={thickness} />
          <circle
            cx="21" cy="21" r={R} fill="none"
            stroke={stroke} strokeWidth={thickness} strokeLinecap="round"
            /* 12시에서 시작해 시계 방향. 기본 원은 3시에서 시작하므로 90도 돌린다. */
            transform="rotate(-90 21 21)"
            strokeDasharray={`${drawn ? pct : 0} ${100 - (drawn ? pct : 0)}`}
            style={{ transition: `stroke-dasharray ${MOTION.base} ${MOTION.ease}` }}
          />
        </Box>
        <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
          <Typography
            component="span"
            sx={{ fontSize: FONT_SIZE.sectionTitle, fontWeight: FONT_WEIGHT.extrabold, lineHeight: 1.1 }}
          >
            {centerText == null ? value : centerText}
          </Typography>
        </Box>
      </Box>
      {label ? <Typography variant="body2" color="text.secondary">{label}</Typography> : null}
    </Box>
  );
}
