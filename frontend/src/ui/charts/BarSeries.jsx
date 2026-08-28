import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { ChartNoData, ChartQuestion, CHART_MOTION, resolveChartColor, useTrackColor } from "./base.jsx";
import { Badge } from "../kit.jsx";
import { baseOption, useEChart } from "./useEChart.js";
import { useRevealOnce } from "../motion.js";
import { FONT_WEIGHT } from "../theme.js";

/* 가로 막대 묶음 — 항목별 크기를 서로 비교하는 용도(담당자별 업무량, 큐 상태 등)
 * (REAUDIT §15.2 — ECharts 재구현).
 *
 * items: [{ label, value, color?, note? }]. color는 팔레트 이름(위험한 항목만 'error' 등).
 * max: 기준 최대값. 안 주면 값들의 최대값을 100%로 잡는다. 백분율처럼 상한이 정해진 지표는
 *      반드시 max=100을 넘겨라 — 안 그러면 '가장 큰 값'이 항상 꽉 찬 막대가 되어, 82%와 8%가
 *      똑같이 꽉 찬 막대로 보인다.
 *
 * ## 이름·값·막대가 여전히 **한 CSS 격자**인 이유
 *
 * ECharts 의 카테고리 축으로 옮기면 이름·값·막대가 차트 라이브러리의 좌표계 안에 갇혀
 * 이 배치 규칙 둘을 잃는다:
 *   1) 값을 막대 **왼쪽**(이름 옆)에 둔다 — 오른쪽 끝에 두면 화면 우하단 고정 클로비
 *      버튼에 숫자가 가려진다(1920 캡처 실측: "3건"이 통째로 덮였다).
 *   2) `note`(행마다 붙는 보조 문장)가 격자 전체 폭을 쓰는 자유 행(`gridColumn:"1 / -1"`)
 *      이다 — 카테고리 축에는 그런 자유 행이 없다.
 * 그래서 **막대 자체**만 ECharts 로 그린다 — 행 하나짜리 미니 차트를 항목 수만큼 만들어
 * 이름·값 칸은 그대로 HTML 격자에 남긴다. 값은 여전히 항상 숫자로 함께 나간다(aria-hidden).
 */

/** 옵션 — **순수 함수**다(§18.2). `pct` 는 0~100, `grown` 은 `useRevealOnce` 값이다. */
export function barRowOption({ pct, fillColor, trackColor, grown }) {
  return {
    ...baseOption(),
    grid: { left: 0, right: 0, top: 0, bottom: 0 },
    xAxis: { type: "value", min: 0, max: 100, show: false },
    yAxis: { type: "category", data: [""], show: false },
    series: [
      {
        type: "bar",
        data: [{ value: grown ? pct : 0, itemStyle: { color: fillColor, borderRadius: [0, 4, 4, 0] } }],
        barWidth: "100%",
        backgroundStyle: { color: trackColor, borderRadius: [0, 4, 4, 0] },
        showBackground: true,
        z: 2,
        animationDuration: CHART_MOTION.duration,
        animationEasing: CHART_MOTION.easing,
      },
    ],
  };
}

function BarRow({ pct, fill, track, grown }) {
  const option = React.useMemo(
    () => barRowOption({ pct, fillColor: fill, trackColor: track, grown }),
    [pct, fill, track, grown],
  );
  const containerRef = useEChart(option);
  return (
    <Box
      ref={containerRef}
      aria-hidden="true"
      sx={{ width: "100%", height: "0.75rem", borderRadius: 1, overflow: "hidden" }}
    />
  );
}

export function BarSeries({
  items, color, max, unit = "", emptyLabel = "데이터 없음", formatValue, relativeNote,
  question, revealKey,
}) {
  const theme = useTheme();
  const track = useTrackColor();
  const grown = useRevealOnce(revealKey);
  const rows = (Array.isArray(items) ? items : []).filter(
    (it) => it && typeof it.value === "number" && Number.isFinite(it.value)
  );

  if (!rows.length) return <ChartNoData label={emptyLabel} />;

  const relative = !(typeof max === "number" && max > 0);
  const peak = relative
    ? Math.max(...rows.map((r) => Math.max(0, r.value)))
    : max;
  const fmt = formatValue || ((v) => String(v));

  /* 기준을 안 주면 «가장 큰 값 = 꽉 찬 막대» 다. 그 사실을 화면에 적지 않으면 82% 와 8% 가
     둘 다 꽉 찬 막대로 보이는 것을 읽는 사람이 알 방법이 없다. */
  const scaleNote = relative && rows.length > 1 && peak > 0
    ? (relativeNote || `가장 큰 값 ${fmt(peak)}${unit}을 100%로 본 상대 비교입니다.`)
    : null;

  const grid = (
    <Box sx={{
      display: "grid", alignItems: "center", columnGap: 1.5, rowGap: 1.25,
      gridTemplateColumns: {
        xs: "minmax(0, 6rem) auto minmax(0, 1fr)",
        sm: "minmax(0, 9rem) auto minmax(0, 1fr)",
        xxl: "minmax(0, 12rem) auto minmax(0, 1fr)",
      },
    }}>
      {rows.map((r) => {
        // 음수는 이 막대 형태로 표현할 수 없다(왼쪽으로 자랄 곳이 없다) — 폭 0으로 눕히고
        // 값 글자로만 알린다. peak가 0이면(전부 0) 모든 막대가 0폭이다 — 그것도 사실이다.
        const pct = peak > 0 ? Math.max(0, Math.min(100, (r.value / peak) * 100)) : 0;
        const fill = resolveChartColor(theme, r.color || color, 0);
        return (
          <React.Fragment key={r.label}>
            {/* 이름이 길면 줄바꿈 대신 말줄임 — 줄이 늘면 막대들의 세로 리듬이 깨져 비교가 어려워진다.
                전체 이름은 title로 남긴다. */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, minWidth: 0 }}>
              <Typography
                variant="body2" title={r.label}
                sx={{ fontWeight: FONT_WEIGHT.bold, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {r.label}
              </Typography>
              {r.badge ? <Badge value={r.badge.label} kind={r.badge.kind} /> : null}
            </Box>
            <Typography
              variant="body2"
              sx={{ fontWeight: FONT_WEIGHT.extrabold, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", textAlign: "right" }}
            >
              {fmt(r.value)}{unit}
            </Typography>
            <BarRow pct={pct} fill={fill} track={track} grown={grown} />
            {r.note ? (
              <Typography variant="caption" color="text.secondary" sx={{ gridColumn: "1 / -1" }}>
                {r.note}
              </Typography>
            ) : null}
          </React.Fragment>
        );
      })}
    </Box>
  );

  if (!scaleNote && !question) return grid;
  return (
    <Box>
      <ChartQuestion>{question}</ChartQuestion>
      {grid}
      {scaleNote ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
          {scaleNote}
        </Typography>
      ) : null}
    </Box>
  );
}

export default BarSeries;
