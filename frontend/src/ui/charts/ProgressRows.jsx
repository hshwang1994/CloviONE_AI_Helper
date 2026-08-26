import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { ChartNoData, ChartQuestion, resolveChartColor, useTrackColor } from "./base.jsx";
import { useRevealOnce } from "../motion.js";
import { FONT_WEIGHT, MOTION } from "../theme.js";

/* 기간별 **달성 비율** 묶음 — 줄마다 「기간 · 그 기간의 사실 · 가득 폭 막대」.
 *
 * ## `BarSeries` 와 무엇이 다른가
 *
 * `BarSeries` 는 한 줄이 [이름 | 값 | 막대] 로 **한 행**이다. 항목끼리 크기를 비교하는
 * 자리에는 그 모양이 맞다. 그런데 좁은 레일에서 그 셋을 한 줄에 밀어 넣으면 막대가 칸의
 * 5분의 1로 쪼그라들고, 줄마다 붙는 부연(`note`)이 **어떤 줄에만** 한 줄을 더 만들어 행
 * 높이가 들쭉날쭉해진다. 실측(2026-08-26 · 1920)에서 넉 주 가운데 둘만 아래에 한 줄이
 * 더 있었고, 막대 폭은 110px 였다.
 *
 * 여기서는 한 항목이 **두 줄**이다.
 *
 *     8월 3일 주간                          마감 12건 중 3건 완료
 *     [███████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
 *
 * 첫 줄 왼쪽이 기간, 오른쪽이 그 기간의 사실, 둘째 줄이 칸 폭을 다 쓰는 막대다. 모든
 * 항목이 **같은 구조와 같은 간격**을 갖는다 — 어떤 줄에만 설명이 더 붙지 않는다.
 *
 * ## 막대의 뜻은 «비율» 이다
 *
 * `value / total` 이고 둘은 **같은 모집단**이어야 한다. 그렇지 않은 자료에 이 부품을
 * 쓰면 그림이 거짓말을 한다 — 비교할 수 없는 두 수의 비율은 비율이 아니다.
 *
 * `total` 이 0 인 항목은 **분모가 없는 것**이지 0% 가 아니다. 0% 로 그리면 「아무것도
 * 못 했다」로 읽히는데 사실은 「할 것이 없었다」다. 그래서 그 줄은 중립 트랙으로 두고
 * `emptyRowLabel` 을 오른쪽에 적는다.
 *
 * 막대는 `aria-hidden` 이다 — 바로 위 오른쪽 글자가 **같은 사실을 숫자로** 말하고
 * 있어서, 그림을 못 보는 사람도 정보량이 같다.
 *
 * items: [{ key, label, value, total, color? }]
 */
export function ProgressRows({
  items, color, question, unit = "", revealKey,
  emptyLabel = "데이터 없음",
  emptyRowLabel = "해당 없음",
  formatRow,
}) {
  const theme = useTheme();
  const track = useTrackColor();
  const grown = useRevealOnce(revealKey);
  const rows = (Array.isArray(items) ? items : []).filter(
    (it) => it && typeof it.value === "number" && Number.isFinite(it.value)
  );
  if (!rows.length) return <ChartNoData label={emptyLabel} />;

  const fmt = formatRow || ((r) => `${r.total}${unit} 중 ${r.value}${unit}`);

  return (
    <Box>
      <ChartQuestion>{question}</ChartQuestion>
      <Box sx={{ display: "grid", gap: 1.75 }}>
        {rows.map((r, i) => {
          const total = typeof r.total === "number" && r.total > 0 ? r.total : 0;
          const pct = total ? Math.max(0, Math.min(100, (r.value / total) * 100)) : 0;
          const fill = resolveChartColor(theme, r.color || color, 0);
          return (
            <Box key={r.key || r.label} sx={{ display: "grid", gap: 0.5, minWidth: 0 }}>
              <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 1.5, minWidth: 0 }}>
                <Typography
                  variant="body2" title={r.label}
                  sx={{ fontWeight: FONT_WEIGHT.bold, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                >
                  {r.label}
                </Typography>
                <Typography
                  variant="body2" color={total ? "text.primary" : "text.secondary"}
                  sx={{ whiteSpace: "nowrap", flexShrink: 0, fontVariantNumeric: "tabular-nums" }}
                >
                  {total ? fmt(r) : emptyRowLabel}
                </Typography>
              </Box>
              {/* 모서리 둥글기는 svg 요소에 건다 — viewBox 안에서 rx 를 주면 폭이 늘어난
                  만큼 가로로만 늘어나 한쪽만 찌그러진 모서리가 된다. */}
              <Box
                component="svg"
                viewBox="0 0 100 10"
                preserveAspectRatio="none"
                aria-hidden="true"
                focusable="false"
                sx={{ display: "block", width: "100%", height: "0.625rem", borderRadius: 1, overflow: "hidden" }}
              >
                <rect x="0" y="0" width="100" height="10" fill={track} />
                {/* ⚠️ MUI `Box` 로 감싸지 않는다. `width` 는 MUI 의 sizing system prop 이라
                    0 과 1 사이의 값을 **백분율로** 바꾼다 — 0.8% 짜리 막대가 80% 로 그려진다.
                    전환은 `style` 로 직접 준다(D-339). */}
                {pct > 0 ? (
                  <rect
                    x="0" y="0" height="10" fill={fill}
                    width={grown ? pct : 0}
                    style={{ transition: `width ${MOTION.base} ${MOTION.ease}`, transitionDelay: `${Math.min(i, 5) * 30}ms` }}
                  />
                ) : null}
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

export default ProgressRows;
