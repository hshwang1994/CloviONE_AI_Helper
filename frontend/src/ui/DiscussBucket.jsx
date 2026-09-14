import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { paletteAt, TONE_ACCENT } from "./kit.jsx";
import { StatusDot } from "./StatusKpi.jsx";
import { FONT_SIZE, FONT_WEIGHT, MOTION, NUMERIC, RADIUS } from "./theme.js";

/* 회의 「오늘 논의할 항목」의 갈래 — **칩 한 줄**이다 (D-484).
 *
 * 예전에는 여덟 갈래가 큰 타일 여덟 장이었다. 숫자 하나에 카드 한 장이면 줄이 두 장을
 * 먹고, 정작 그 아래 티켓 목록이 접힌 채 시작했다 — 회의에서 보는 것은 갈래의 크기가
 * 아니라 **어느 갈래에 몇 건이 있고 지금 어느 갈래를 보고 있는가**다. 칩 한 줄이면 1366
 * 폭에서도 여덟이 한 줄에 서고, 목록이 곧바로 그 아래 선다.
 *
 * 접근 이름은 `"지연 1"` 처럼 라벨과 건수가 한 덩어리다. `role="tab"` 과 roving tabindex 를
 * 유지해서 서로 하나만 고르는 자리라는 뜻이 시험과 스크린리더에 같이 남는다. 신호 색은
 * 요약 줄과 같은 점(`StatusDot`)이 단다 — 색을 못 봐도 라벨 글자가 언제나 함께 있다. */

export function DiscussBucket({ label, count, selected, tone, onClick, id, ariaControls, tabIndex, buttonRef }) {
  const name = `${label} ${count}`;
  /* 톤 표는 `ui/kit.jsx` 한 곳이다(KPI 타일과 같은 표). 톤이 없는 갈래(미할당·마감 없음
     같은 회의 준비 항목)는 점을 안 단다 — 점은 신호에만 붙는다. */
  const accent = TONE_ACCENT[tone];
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
        display: "inline-flex",
        alignItems: "center",
        gap: 0.75,
        minWidth: 0,
        px: 1.25,
        py: 0.625,
        font: "inherit",
        color: "inherit",
        cursor: "pointer",
        whiteSpace: "nowrap",
        borderRadius: `${RADIUS.pill != null ? RADIUS.pill : 999}px`,
        bgcolor: selected ? "primary.soft" : "background.plate",
        border: "1px solid",
        borderColor: selected ? "brand.core" : "divider",
        transition: `border-color ${MOTION.fast} ${MOTION.ease}, background-color ${MOTION.fast} ${MOTION.ease}`,
        "&:hover": { borderColor: selected ? t.palette.brand.core : t.palette.text.faint },
        "&:focus-visible": { outline: `2px solid ${t.palette.brand.core}`, outlineOffset: 2 },
      })}
    >
      {accent ? <StatusDot accent={accent} /> : null}
      <Typography component="span" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: selected ? FONT_WEIGHT.semibold : FONT_WEIGHT.medium }}>
        {label}
      </Typography>
      <Typography
        component="span"
        sx={{
          fontSize: FONT_SIZE.bodySm,
          fontWeight: FONT_WEIGHT.bold,
          lineHeight: 1,
          px: 0.625,
          py: 0.25,
          borderRadius: "999px",
          bgcolor: (theme) => (count ? paletteAt(theme, "background.inset") : "transparent"),
          color: count ? "text.primary" : "text.secondary",
          ...NUMERIC,
        }}
      >
        {count}
      </Typography>
    </Box>
  );
}

export function DiscussBucketRow({ items, value, onChange, ariaLabel = "논의 항목 선택", idBase = "discuss" }) {
  /* tablist 의 키보드 계약 — 화살표로 옮기고 Tab 은 한 번에 지나간다(roving tabindex).
     role="tab" 만 달고 이 계약이 없으면 여덟 칩을 Tab 여덟 번으로 지나야 하고,
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
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: 0.75,
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
