import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { statusKind } from "./kit.jsx";
import { KPI_TILE_TRACK, TILE_GRID_GAP, TILE_PADDING } from "./density.js";
import { useRevealOnce } from "./motion.js";
import { FONT_SIZE, FONT_WEIGHT, MOTION, NUMERIC, RADIUS } from "./theme.js";

/* 보드·회의의 상태 숫자. 홈의 세로선 `MetricStrip` 과 **다른 부품**이다.
 *
 * 칸마다 위색 띠 · 숫자 · 라벨 · (있으면) 비율이 선다. 숫자는 처음부터 최종값이다 —
 * 세어 올라가는 연출은 값을 늦게 읽게 만든다. 등장만 짧게 한 번 한다. */

const KIND_ACCENT = {
  ok: "success.main",
  danger: "error.main",
  warn: "warning.main",
  info: "info.main",
  indigo: "var(--badge-indigo-fg)",
  purple: "var(--badge-purple-fg)",
  teal: "var(--badge-teal-fg)",
  primary: "brand.core",
  brand: "brand.core",
};

function accentOf(kind) {
  return KIND_ACCENT[kind] || "brand.core";
}

export function StatusKpiTile({ label, value, kind, pct, primary }) {
  const k = kind || (primary ? "indigo" : statusKind(label));
  const accent = accentOf(k);
  return (
    <Box
      sx={{
        minWidth: 0,
        p: TILE_PADDING,
        borderRadius: `${RADIUS.md}px`,
        bgcolor: "background.plate",
        border: 1,
        borderColor: "divider",
        borderBlockStartWidth: 3,
        borderBlockStartColor: accent,
        display: "grid",
        gap: 0.25,
        alignContent: "start",
      }}
    >
      <Typography
        component="span"
        sx={{
          fontSize: FONT_SIZE.title,
          fontWeight: FONT_WEIGHT.extrabold,
          lineHeight: 1.1,
          color: accent,
          ...NUMERIC,
        }}
      >
        {value}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ ...KO_KEEP }}>
        {label}
      </Typography>
      {pct != null && Number.isFinite(pct) ? (
        <Typography variant="caption" color="text.secondary" sx={{ ...NUMERIC }}>
          {`${pct}%`}
        </Typography>
      ) : null}
    </Box>
  );
}

const KO_KEEP = { wordBreak: "keep-all", overflowWrap: "break-word" };

/** KPI 타일 줄. `auto-fill` 격자라 마지막 줄이 2~3칸만 남아 커지지 않는다. */
export function StatusKpiStrip({ items, ariaLabel, revealKey, sx }) {
  const list = (items || []).filter(Boolean);
  const shown = useRevealOnce(revealKey == null ? null : String(revealKey));
  if (!list.length) return null;

  return (
    <Box
      role="group"
      aria-label={ariaLabel}
      sx={{
        display: "grid",
        gridTemplateColumns: KPI_TILE_TRACK,
        gap: TILE_GRID_GAP,
        ...sx,
      }}
    >
      {list.map((it, i) => (
        <Box
          key={it.key || it.label || i}
          sx={{
            opacity: shown ? 1 : 0,
            transform: shown ? "none" : "translateY(8px)",
            transition: `opacity ${MOTION.base} ${MOTION.ease}, transform ${MOTION.base} ${MOTION.ease}`,
            transitionDelay: shown ? `${i * 40}ms` : "0ms",
          }}
        >
          <StatusKpiTile
            label={it.label}
            value={it.value}
            kind={it.kind}
            pct={it.pct}
            primary={it.primary}
          />
        </Box>
      ))}
    </Box>
  );
}
