import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { paletteAt, TONE_ACCENT } from "./kit.jsx";
import { balancedTileTracks, TILE_GRID_GAP, TILE_PADDING } from "./density.js";
import { FONT_SIZE, FONT_WEIGHT, MOTION, NUMERIC, RADIUS } from "./theme.js";

/* 회의 「오늘 논의할 항목」의 갈래 카드. 탭 막대 대신 **건수 카드**다.
 *
 * 접근 이름은 `"지연 1"` 처럼 라벨과 건수가 한 덩어리다. `role="tab"` 을 유지해서
 * 서로 하나만 고르는 자리라는 뜻이 시험과 스크린리더에 같이 남는다. */

export function DiscussBucket({ label, count, selected, tone, onClick, id, ariaControls, tabIndex, buttonRef }) {
  const name = `${label} ${count}`;
  /* 톤 표는 `ui/kit.jsx` 한 곳이다(KPI 타일과 같은 표). 예전에는 여기 ternary 사슬이
     danger·warn 둘만 알아서, 신호 어휘가 「이슈 있음은 보라」라고 말해도 이 카드만
     그것을 못 듣고 회색 띠를 그렸다. */
  const accent =
    TONE_ACCENT[tone] || (selected ? "brand.core" : "divider");
  return (
    <Box
      component="button"
      type="button"
      ref={buttonRef}
      role="tab"
      id={id}
      aria-selected={selected}
      aria-controls={ariaControls}
      aria-label={name}
      tabIndex={tabIndex}
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

export function DiscussBucketRow({ items, value, onChange, ariaLabel = "논의 항목 선택", idBase = "discuss" }) {
  /* tablist 의 키보드 계약 — 화살표로 옮기고 Tab 은 한 번에 지나간다(roving tabindex).
     role="tab" 만 달고 이 계약이 없으면 여덟 카드를 Tab 여덟 번으로 지나야 하고,
     스크린리더는 「탭」이라고 말해 놓고 화살표가 안 듣는 화면을 만난다. */
  const refs = React.useRef({});
  function onKeyDown(e) {
    const keys = items.map((it) => it.key);
    const at = Math.max(0, keys.indexOf(value));
    let next = null;
    if (e.key === "ArrowRight") next = keys[(at + 1) % keys.length];
    else if (e.key === "ArrowLeft") next = keys[(at - 1 + keys.length) % keys.length];
    else if (e.key === "Home") next = keys[0];
    else if (e.key === "End") next = keys[keys.length - 1];
    if (!next) return;
    e.preventDefault();
    onChange(next);
    const el = refs.current[next];
    if (el && el.focus) el.focus();
  }
  return (
    <Box
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      sx={{
        display: "grid",
        width: "100%",
        /* 트랙은 **지금 그리는 개수**에서 나온다 — 상수로 박아 두면 갈래가 늘어난 날
           마지막 줄이 반만 찬다(실제로 다섯으로 박혀 있었고 갈래는 여덟이었다). */
        gridTemplateColumns: balancedTileTracks(items.length),
        gap: TILE_GRID_GAP,
        mb: 1.5,
      }}
    >
      {items.map((it) => (
        <DiscussBucket
          key={it.key}
          id={`${idBase}-tab-${it.key}`}
          ariaControls={`${idBase}-panel`}
          tabIndex={it.key === value ? 0 : -1}
          buttonRef={(el) => { refs.current[it.key] = el; }}
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
