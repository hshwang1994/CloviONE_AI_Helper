import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { paletteAt, statusKind } from "./kit.jsx";
import { fixedTileTrack, KPI_TILE_TRACK, TILE_GRID_GAP, TILE_PADDING } from "./density.js";
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

export function StatusKpiTile({ label, value, kind, pct, primary, reservePct = false }) {
  const k = kind || (primary ? "indigo" : statusKind(label));
  const accent = accentOf(k);
  const showPct = pct != null && Number.isFinite(pct);
  const pctSlot = showPct ? `${pct}%` : "\u00a0";
  return (
    <Box
      sx={{
        minWidth: 0,
        height: "100%",
        p: TILE_PADDING,
        borderRadius: `${RADIUS.md}px`,
        bgcolor: "background.plate",
        border: 1,
        borderColor: "divider",
        /* 논리 이름에는 MUI 가 팔레트 경로를 안 풀어 주고, `border-style` 이 없으면
           CSS 기본값 `none` 이라 **폭 3px 짜리 보이지 않는 머리 띠**가 된다
           (`CommandPalette.jsx` 가 같은 함정을 이미 한 번 적었다). 셋을 다 쓴다. */
        borderBlockStartStyle: "solid",
        borderBlockStartWidth: 3,
        borderBlockStartColor: (theme) => paletteAt(theme, accent),
        display: "grid",
        gridTemplateRows: reservePct ? "auto auto 1.25rem" : "auto auto",
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
      {reservePct ? (
        <Typography
          variant="caption"
          color="text.secondary"
          aria-hidden={!showPct}
          sx={{ ...NUMERIC, minHeight: "1.25rem", lineHeight: 1.25 }}
        >
          {pctSlot}
        </Typography>
      ) : showPct ? (
        <Typography variant="caption" color="text.secondary" sx={{ ...NUMERIC }}>
          {`${pct}%`}
        </Typography>
      ) : null}
    </Box>
  );
}

const KO_KEEP = { wordBreak: "keep-all", overflowWrap: "break-word" };

/** KPI 타일 줄. 칸 수가 정해져 있으면 그 수만큼만 트랙을 만든다 — `auto-fill` 은 빈
 * 트랙을 오른쪽에 남긴다. */
export function StatusKpiStrip({ items, ariaLabel, revealKey, sx }) {
  const list = (items || []).filter(Boolean);
  const shown = useRevealOnce(revealKey == null ? null : String(revealKey));
  if (!list.length) return null;

  const wideTrack = fixedTileTrack(list.length);
  const reservePct = list.some((it) => it.pct != null && Number.isFinite(it.pct));

  return (
    <Box
      role="group"
      aria-label={ariaLabel}
      sx={{
        display: "grid",
        width: "100%",
        alignItems: "stretch",
        gridTemplateColumns: {
          xs: KPI_TILE_TRACK,
          md: wideTrack,
        },
        gap: TILE_GRID_GAP,
        ...sx,
      }}
    >
      {list.map((it, i) => (
        <Box
          key={it.key || it.label || i}
          sx={{
            height: "100%",
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
            reservePct={reservePct}
          />
        </Box>
      ))}
    </Box>
  );
}
