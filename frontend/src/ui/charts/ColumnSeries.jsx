import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { ChartNoData, ChartQuestion, resolveChartColor } from "./base.jsx";
import { useRevealOnce } from "../motion.js";
import { FONT_SIZE, FONT_WEIGHT, MOTION, NUMERIC } from "../theme.js";

/* 세로 막대 — **시간축이 있는 값**을 위한 그림.
 *
 * ## `BarSeries` 와 무엇이 다른가
 *
 * `BarSeries` 는 한 줄이 [이름 | 값 | 막대] 인 **가로** 목록이다. 항목끼리 크기를 비교하는
 * 자리에는 그 모양이 맞다 — 「남은 일의 우선순위」처럼 순서에 뜻이 없는 목록.
 *
 * 그런데 달·주처럼 **왼쪽에서 오른쪽으로 흐르는 축**이 있으면 가로 막대는 그 흐름을 세로로
 * 눕힌다. 읽는 사람은 시간을 위에서 아래로 따라가면서 크기는 옆으로 재야 한다 — 두 축이
 * 직교하지 않는다. 세로 막대는 시간을 x 에, 크기를 y 에 둬서 그 둘을 갈라 준다.
 *
 * ## y축 라벨은 **자기 트랙**을 갖는다
 *
 * 축 라벨을 막대 칸 안에 넣으면 막대 폭이 라벨 길이에 따라 달라진다. 왼쪽에 40px 트랙을
 * 따로 두고 그 오른쪽 격자를 막대와 x축 라벨이 **함께** 쓴다 — 그래야 축 라벨과 막대가
 * 같은 세로선 위에 선다(핸드오프 「정렬 규약」 5).
 *
 * ## 0 과 「모른다」는 다르다
 *
 * 길이 0 인 막대는 「하나도 못 했다」로 읽힌다. 값이 없는 칸(배정이 0건이라 완료율의 분모가
 * 없는 달)은 **막대를 안 그리고** 값 글자를 `valueText` 로 적는다 — 그림으로 못 가르는 것을
 * 글자가 가른다(`BarSeries` 의 같은 prop 과 한 뜻이다).
 *
 * items: `[{ key, label, value, valueText?, color?, hint? }]`
 */
const AXIS_TRACK = "2.5rem";   // 40px — y축 라벨 자리
const PLOT_HEIGHT = "9.25rem"; // 148px — 격자 높이
/* 막대가 쓸 수 있는 최대 높이. 격자 높이에서 **값 글자 줄과 그 간격**을 뺀 값이다 —
   값은 막대 위에 붙으므로 꽉 찬 막대도 그 글자가 설 자리를 남겨야 격자를 안 넘는다. */
const BAR_MAX = "7.5rem";      // 120px

export function ColumnSeries({
  items, max, unit = "", question, color, revealKey,
  emptyLabel = "데이터 없음", barWidth = "1.75rem",
}) {
  const theme = useTheme();
  const grown = useRevealOnce(revealKey);
  const rows = (Array.isArray(items) ? items : []).filter(
    (it) => it && typeof it.value === "number" && Number.isFinite(it.value)
  );
  if (!rows.length) return <ChartNoData label={emptyLabel} />;

  const peak = typeof max === "number" && max > 0
    ? max
    : Math.max(1, ...rows.map((r) => Math.max(0, r.value)));
  /* 눈금 셋(꼭대기·가운데·0)이면 격자선이 둘이다. 값 축이 무엇을 세는지는 라벨이 말하고,
     격자는 눈이 높이를 견주는 자리만 만든다 — 촘촘하면 막대보다 격자가 먼저 읽힌다. */
  const ticks = [peak, Math.round(peak / 2), 0];
  const track = `repeat(${rows.length}, minmax(0, 1fr))`;

  return (
    <Box>
      <ChartQuestion>{question}</ChartQuestion>
      <Box sx={{ display: "grid", gridTemplateColumns: `${AXIS_TRACK} minmax(0,1fr)`, columnGap: 1.25, alignItems: "end" }}>
        <Box
          aria-hidden="true"
          sx={{
            display: "grid", height: PLOT_HEIGHT, alignContent: "space-between", justifyItems: "end",
            fontSize: FONT_SIZE.micro, color: "text.secondary", ...NUMERIC,
          }}
        >
          {ticks.map((t) => <Box component="span" key={t}>{t}</Box>)}
        </Box>
        <Box
          sx={{
            display: "grid", gridTemplateColumns: track, columnGap: 2, alignItems: "end",
            height: PLOT_HEIGHT,
            borderBottom: 1, borderColor: "divider",
            backgroundImage: (t) => `linear-gradient(${t.palette.rule} 1px, transparent 1px)`,
            backgroundSize: `100% calc(${PLOT_HEIGHT} / ${ticks.length - 1})`,
          }}
        >
          {rows.map((r) => {
            const known = r.valueText == null;
            const pct = known ? Math.max(0, Math.min(100, (r.value / peak) * 100)) : 0;
            return (
              /* 🔴 칸은 **자기 높이를 갖는다**(`height: 100%` + 두 행 트랙).
                 막대 높이가 `%` 라서 그렇다 — 백분율 높이는 부모의 높이가 확정일 때만 풀리고,
                 아니면 `auto` 가 되어 0 이 된다. 값 줄은 `auto`, 막대 줄은 `minmax(0,1fr)` 로
                 두면 막대가 서는 칸의 높이가 「격자 높이 − 값 줄」로 확정된다. */
              <Box
                key={r.key || r.label}
                sx={{
                  height: "100%", display: "grid", alignContent: "end",
                  rowGap: 1, justifyItems: "center", minWidth: 0,
                }}
              >
                <Typography
                  component="span"
                  sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.bold, ...NUMERIC }}
                >
                  {known ? `${r.value}${unit}` : r.valueText}
                </Typography>
                {/* 값이 없는 칸은 막대 자체를 안 만든다 — 0px 막대는 「0」으로 읽힌다. */}
                {known ? (
                  <Box
                    aria-hidden="true"
                    data-column-bar=""
                    sx={{
                      width: barWidth, maxWidth: "100%",
                      /* 높이를 **확정 단위로** 센다. 백분율 높이는 부모 높이가 확정일 때만
                         풀리는데, 값 글자가 막대 위에 붙으려면 두 줄이 다 `auto` 여야 하고
                         그러면 부모가 확정이 아니게 된다. 두 요구를 같이 만족시키는 길은
                         막대가 쓸 최대 높이를 알고 거기서 비율을 재는 것이다. */
                      height: grown ? `calc(${BAR_MAX} * ${pct} / 100)` : 0,
                      borderRadius: "4px 4px 0 0",
                      bgcolor: resolveChartColor(theme, r.color || color, 0),
                      transition: `height ${MOTION.base} ${MOTION.ease}`,
                    }}
                  />
                ) : null}
              </Box>
            );
          })}
        </Box>
        <Box component="span" />
        <Box
          sx={{
            display: "grid", gridTemplateColumns: track, columnGap: 2, pt: 1,
            fontSize: FONT_SIZE.micro, color: "text.secondary", textAlign: "center", ...NUMERIC,
          }}
        >
          {rows.map((r) => (
            <Box
              component="span"
              key={r.key || r.label}
              title={r.hint || undefined}
              sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {r.label}
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  );
}
