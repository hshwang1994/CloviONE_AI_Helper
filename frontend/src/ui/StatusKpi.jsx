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

/** 판독 하나가 **누를 수 있는가**. `onClick` 을 주면 단추가 된다.
 *
 * 🔴 예전에는 이 부품이 순수 `Box` 였다. 그래서 「지연 3」을 보고도 **그래서 어떤
 * 티켓인지** 알 방법이 없었다 — 숫자가 죽은 픽셀이었다. 회의 화면과 작업 보드가 같은
 * 부품을 쓰므로 여기 한 곳에서 열면 두 화면이 함께 얻는다.
 *
 * 접근 이름은 「라벨 값」 한 덩어리다(`지연 3`). 목록을 고르는 자리면 `aria-pressed` 로
 * 지금 고른 칸을 말한다.
 */
export function StatusKpiTile({
  label, value, kind, pct, primary, reservePct = false,
  onClick, selected, ariaLabel,
}) {
  const k = kind || (primary ? "indigo" : statusKind(label));
  const accent = accentOf(k);
  const showPct = pct != null && Number.isFinite(pct);
  const pctSlot = showPct ? `${pct}%` : "\u00a0";
  const pressable = typeof onClick === "function";
  return (
    <Box
      component={pressable ? "button" : "div"}
      type={pressable ? "button" : undefined}
      onClick={onClick}
      aria-pressed={pressable && selected != null ? !!selected : undefined}
      aria-label={pressable ? (ariaLabel || `${label} ${value}`) : undefined}
      sx={{
        minWidth: 0,
        width: "100%",
        height: "100%",
        p: TILE_PADDING,
        borderRadius: `${RADIUS.md}px`,
        bgcolor: "background.plate",
        border: 1,
        borderColor: selected ? "brand.core" : "divider",
        font: "inherit",
        color: "inherit",
        textAlign: "start",
        cursor: pressable ? "pointer" : "default",
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
        transition: `border-color ${MOTION.fast} ${MOTION.ease}, background-color ${MOTION.fast} ${MOTION.ease}`,
        ...(pressable ? {
          "&:hover": { bgcolor: "action.hover" },
          "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.brand.core}`, outlineOffset: 2 }),
        } : null),
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
/** KPI 타일 줄. 누를 수 있는 칸이 하나라도 있으면 **고르는 줄**이 된다.
 *
 * `value`(고른 키)와 `onSelect` 를 주면 각 항목의 `key` 가 선택 값이 된다 — 회의 화면의
 * 「오늘 논의할 항목」이 이 줄과 아래 목록을 같은 상태로 잇는다. 항목이 `href` 를 가지면
 * 다른 화면으로 간다(작업 보드의 그 조건으로).
 */
export function StatusKpiStrip({ items, ariaLabel, revealKey, sx, value, onSelect }) {
  const list = (items || []).filter(Boolean);
  const shown = useRevealOnce(revealKey == null ? null : String(revealKey));
  if (!list.length) return null;

  const wideTrack = fixedTileTrack(list.length);
  const reservePct = list.some((it) => it.pct != null && Number.isFinite(it.pct));
  const selectable = typeof onSelect === "function";

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
            onClick={it.onClick || (selectable && it.key ? () => onSelect(it.key) : undefined)}
            selected={it.key != null && value != null ? it.key === value : undefined}
            ariaLabel={it.ariaLabel}
          />
        </Box>
      ))}
    </Box>
  );
}
