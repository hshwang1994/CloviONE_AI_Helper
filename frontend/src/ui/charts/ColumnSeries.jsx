import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { ChartNoData, ChartQuestion, resolveChartColor } from "./base.jsx";
import { useRevealOnce } from "../motion.js";
import { FONT_SIZE, FONT_WEIGHT, MOTION, NUMERIC, remPx } from "../theme.js";

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
 * ## 한 칸에 막대가 여럿일 수 있다
 *
 * `bars: [{ key, value, color }]` 를 주면 그 수만큼 나란히 선다. 값 글자는 **그중 한
 * 막대**의 값이다(`labelBar`) — 둘을 다 적으면 어느 것이 어느 막대의 값인지 다시 찾아야
 * 하고, 그 답은 아래 표가 이미 갖고 있다. 막대 하나짜리는 `value` 만 줘도 된다.
 *
 * items: `[{ key, label, hint?, valueText?, value?, color?, bars? }]`
 */
const AXIS_TRACK = "2.5rem";   // 40px — y축 라벨 자리

/* 격자 높이는 **칸 수가 아니라 값의 수**를 따라간다.
 *
 * 148px 였다. 달이 여섯인데 값이 한 칸에만 있으면 나머지 다섯 칸의 148px 이 통째로 빈
 * 판으로 남는다 — 그림이 차지한 자리의 대부분이 아무 말도 안 하는 상태다. 높이를 줄여도
 * 잃는 것이 없는 이유는 y축 기준이 데이터 최대값이라서다: 가장 큰 막대는 어느 높이에서든
 * 꼭대기에 닿고, 눈이 견주는 것은 절대 길이가 아니라 막대끼리의 **비**다. */
const VALUE_ROW = 28;          // 값 글자 줄 + 그 아래 간격
const PLOT_PX = 120;
export const PLOT_HEIGHT = remPx(PLOT_PX);
/* 막대가 쓸 수 있는 최대 높이. 격자 높이에서 **값 글자 줄과 그 간격**을 뺀 값이다 —
   값은 막대 위에 붙으므로 꽉 찬 막대도 그 글자가 설 자리를 남겨야 격자를 안 넘는다. */
export const BAR_MAX = remPx(PLOT_PX - VALUE_ROW);  // 92px

export function ColumnSeries({
  items, max, unit = "", question, color, revealKey,
  emptyLabel = "데이터 없음", barWidth = "1.75rem", barGap = "0.25rem", labelBar = -1,
}) {
  const theme = useTheme();
  const grown = useRevealOnce(revealKey);
  /** 한 칸의 막대 목록 — `bars` 를 안 주면 `value` 하나짜리로 본다. */
  const barsOf = (it) => (Array.isArray(it.bars) ? it.bars : [{ key: "v", value: it.value, color: it.color }])
    .filter((b) => b && typeof b.value === "number" && Number.isFinite(b.value));
  const rows = (Array.isArray(items) ? items : []).filter((it) => it && barsOf(it).length);
  if (!rows.length) return <ChartNoData label={emptyLabel} />;

  const peak = typeof max === "number" && max > 0
    ? max
    : Math.max(1, ...rows.flatMap((r) => barsOf(r).map((b) => Math.max(0, b.value))));
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
          data-column-plot=""
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
            const bars = barsOf(r);
            const at = labelBar < 0 ? bars.length + labelBar : labelBar;
            const group = `repeat(${bars.length}, ${barWidth})`;
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
                {/* 값 글자는 **자기 막대 바로 위**에 선다 — 칸 가운데가 아니다. 막대가
                    둘이면 가운데는 두 막대 사이의 빈 자리라, 그 위의 숫자가 어느 막대의
                    값인지 눈이 못 정한다. 값이 없는 칸은 칸 전체에 걸쳐 가운데다. */}
                <Box
                  sx={known
                    ? { display: "grid", gridTemplateColumns: group, columnGap: barGap, justifyItems: "center" }
                    : { display: "grid", justifyItems: "center" }}
                >
                  {known ? bars.map((b, i) => (
                    <Typography
                      key={b.key || i}
                      component="span"
                      sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.bold, ...NUMERIC }}
                    >
                      {i === at ? `${b.value}${unit}` : "\u00a0"}
                    </Typography>
                  )) : (
                    <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.bold, ...NUMERIC }}>
                      {r.valueText}
                    </Typography>
                  )}
                </Box>
                {/* 값이 없는 칸은 막대 자체를 안 만든다 — 0px 막대는 「0」으로 읽힌다. */}
                {known ? (
                  <Box sx={{ alignSelf: "end", display: "grid", gridTemplateColumns: group, columnGap: barGap, alignItems: "end" }}>
                    {bars.map((b, i) => (
                      <Box
                        key={b.key || i}
                        aria-hidden="true"
                        data-column-bar=""
                        sx={{
                          width: barWidth, maxWidth: "100%",
                          /* 높이를 **확정 단위로** 센다. 백분율 높이는 부모 높이가 확정일 때만
                             풀리는데, 값 글자가 막대 위에 붙으려면 두 줄이 다 `auto` 여야 하고
                             그러면 부모가 확정이 아니게 된다. 두 요구를 같이 만족시키는 길은
                             막대가 쓸 최대 높이를 알고 거기서 비율을 재는 것이다. */
                          height: grown
                            ? `calc(${BAR_MAX} * ${Math.max(0, Math.min(100, (b.value / peak) * 100))} / 100)`
                            : 0,
                          borderRadius: "4px 4px 0 0",
                          bgcolor: resolveChartColor(theme, b.color || color, i),
                          transition: `height ${MOTION.base} ${MOTION.ease}`,
                        }}
                      />
                    ))}
                  </Box>
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
