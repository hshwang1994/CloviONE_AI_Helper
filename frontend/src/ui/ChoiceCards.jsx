import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "./theme.js";

/* 선택 카드 — 설정 값 하나를 고르는 같은 높이의 카드 줄 (계획 M1, D-548).
 *
 * 세그먼티드는 **보기 전환**(표 · 달력, HTML · 텍스트)의 부품이다(RULES §3). 「외부 SMTP 사용」 · 「ClovirAssist 로컬 릴레이」처럼
 * 저장되는 **설정 값**을 고르는 자리에 세그먼티드를 쓰면 누르는 순간 무엇이 저장되는지가 안 보이고, 선택지마다 한 문장 설명을 둘
 * 자리도 없다. 그래서 설정 값은 이 부품으로 고른다: 카드마다 이름 + 한 문장, 같은 높이(격자 행이 정한다), 고른 카드는 보라 테두리 ·
 * 옅은 면(선택 상태에만 보라를 쓴다, F7).
 *
 * 접근성: `role="radiogroup"` 안의 `role="radio"` 다. Tab 정지는 고른 카드 하나(없으면 첫 카드)이고, 화살표 키가 고른 값을 옮긴다
 * (WAI-ARIA 라디오 그룹 규칙). 꺼진 선택지는 건너뛴다.
 */
export function ChoiceCards({ ariaLabel, value, options, onChange, disabled = false, name }) {
  const refs = React.useRef([]);
  const enabled = options.map((o) => !disabled && !o.disabled);
  const selectedIndex = options.findIndex((o) => o.value === value);
  const tabIndexOf = (i) => {
    if (selectedIndex >= 0) return i === selectedIndex ? 0 : -1;
    const first = enabled.indexOf(true);
    return i === first ? 0 : -1;
  };

  function move(from, step) {
    const n = options.length;
    for (let k = 1; k <= n; k += 1) {
      const i = (from + step * k + n * k) % n;
      if (enabled[i]) {
        onChange(options[i].value);
        refs.current[i] && refs.current[i].focus();
        return;
      }
    }
  }

  function onKeyDown(e, i) {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(i, 1); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(i, -1); }
    else if ((e.key === " " || e.key === "Enter") && enabled[i]) { e.preventDefault(); onChange(options[i].value); }
  }

  return (
    <Box
      role="radiogroup" aria-label={ariaLabel} data-choice-cards={name || ""}
      sx={{
        display: "grid", gap: 1.5, minWidth: 0,
        gridTemplateColumns: { xs: "minmax(0,1fr)", md: `repeat(${Math.max(1, options.length)}, minmax(0,1fr))` },
        gridAutoRows: "1fr",
      }}
    >
      {options.map((o, i) => {
        const checked = o.value === value;
        const off = !enabled[i];
        const descId = o.description || o.note ? `${name || "choice"}-${o.value}-desc` : undefined;
        return (
          <Box
            key={o.value}
            ref={(el) => { refs.current[i] = el; }}
            role="radio"
            aria-checked={checked}
            aria-disabled={off || undefined}
            aria-describedby={descId}
            tabIndex={tabIndexOf(i)}
            data-choice={o.value}
            onClick={() => { if (!off) onChange(o.value); }}
            onKeyDown={(e) => onKeyDown(e, i)}
            sx={(t) => ({
              position: "relative", minWidth: 0, display: "flex", flexDirection: "column", gap: 0.5,
              px: 2, py: 1.5, borderRadius: `${RADIUS.sm}px`, cursor: off ? "not-allowed" : "pointer",
              border: `1px solid ${checked ? t.palette.primary.main : t.palette.divider}`,
              bgcolor: checked ? "primary.soft" : "background.paper",
              opacity: off ? 0.6 : 1,
              "&:hover": off || checked ? null : { borderColor: t.palette.text.secondary },
              "&:focus-visible": { outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 },
            })}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
              <Box
                aria-hidden="true"
                sx={(t) => ({
                  flexShrink: 0, width: 16, height: 16, borderRadius: "50%",
                  border: `2px solid ${checked ? t.palette.primary.main : t.palette.text.secondary}`,
                  display: "grid", placeItems: "center",
                })}
              >
                {checked ? <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "primary.main" }} /> : null}
              </Box>
              <Typography component="span" sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
                {o.label}
              </Typography>
              {o.badge ? (
                <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>{o.badge}</Typography>
              ) : null}
            </Box>
            {o.description || o.note ? (
              <Typography id={descId} component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", pl: 3, ...KO_WORD_BREAK }}>
                {o.description}
                {o.note ? <Box component="span" sx={{ display: "block", mt: 0.5 }}>{o.note}</Box> : null}
              </Typography>
            ) : null}
          </Box>
        );
      })}
    </Box>
  );
}

export default ChoiceCards;
