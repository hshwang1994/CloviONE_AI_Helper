import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { paletteAt } from "./kit.jsx";
import { DISCUSS_TILE_TRACK, TILE_GRID_GAP, TILE_PADDING } from "./density.js";
import { FONT_SIZE, FONT_WEIGHT, MOTION, NUMERIC, RADIUS } from "./theme.js";

/* 회의 「오늘 논의할 항목」의 갈래 카드. 탭 막대 대신 **건수 카드**다.
 *
 * 접근 이름은 `"지연 1"` 처럼 라벨과 건수가 한 덩어리다. `role="tab"` 을 유지해서
 * 서로 하나만 고르는 자리라는 뜻이 시험과 스크린리더에 같이 남는다. */

export function DiscussBucket({ label, count, selected, tone, onClick }) {
  const name = `${label} ${count}`;
  const accent =
    tone === "danger" ? "error.main"
      : tone === "warn" ? "warning.main"
        : selected ? "brand.core" : "divider";
  return (
    <Box
      component="button"
      type="button"
      role="tab"
      aria-selected={selected}
      aria-label={name}
      onClick={onClick}
      sx={(t) => ({
        minWidth: 0,
        p: TILE_PADDING,
        textAlign: "start",
        font: "inherit",
        color: "inherit",
        cursor: "pointer",
        borderRadius: `${RADIUS.md}px`,
        bgcolor: "background.plate",
        border: "1px solid",
        borderColor: selected ? "brand.core" : "divider",
        /* 논리 이름에는 MUI 가 팔레트 경로를 안 풀어 주고, `border-style` 이 없으면
           CSS 기본값 `none` 이라 **폭 3px 짜리 보이지 않는 머리 띠**가 된다
           (`CommandPalette.jsx` 가 같은 함정을 이미 한 번 적었다). 셋을 다 쓴다. */
        borderBlockStartStyle: "solid",
        borderBlockStartWidth: 3,
        borderBlockStartColor: (theme) => paletteAt(theme, accent),
        display: "grid",
        gap: 0.25,
        transition: `border-color ${MOTION.fast} ${MOTION.ease}, background-color ${MOTION.fast} ${MOTION.ease}`,
        "&:hover": { borderColor: selected ? t.palette.brand.core : t.palette.text.faint },
        "&:focus-visible": { outline: `2px solid ${t.palette.brand.core}`, outlineOffset: 2 },
      })}
    >
      <Typography
        component="span"
        sx={{
          fontSize: FONT_SIZE.title,
          fontWeight: FONT_WEIGHT.extrabold,
          lineHeight: 1.1,
          ...NUMERIC,
        }}
      >
        {count}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
    </Box>
  );
}

export function DiscussBucketRow({ items, value, onChange, ariaLabel = "논의 항목 선택" }) {
  return (
    <Box
      role="tablist"
      aria-label={ariaLabel}
      sx={{
        display: "grid",
        width: "100%",
        gridTemplateColumns: {
          xs: "repeat(auto-fill, minmax(8rem, 1fr))",
          sm: DISCUSS_TILE_TRACK,
        },
        gap: TILE_GRID_GAP,
        mb: 1.5,
      }}
    >
      {items.map((it) => (
        <DiscussBucket
          key={it.key}
          label={it.label}
          count={it.count}
          tone={it.tone}
          selected={it.key === value}
          onClick={() => onChange(it.key)}
        />
      ))}
    </Box>
  );
}
