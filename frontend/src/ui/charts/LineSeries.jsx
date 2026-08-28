import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { ChartNoData, ChartQuestion, areaFill, capSeries, CHART_MOTION, resolveChartColor, seriesDash } from "./base.jsx";
import { baseOption, useEChart } from "./useEChart.js";
import { useRevealOnce } from "../motion.js";
import { FONT_WEIGHT } from "../theme.js";

/* 여러 꺾은선을 **같은 눈금** 위에 겹쳐 그린다 — 두 값을 비교하는 그림(번다운의 계획선/잔여선)
 * (REAUDIT §15.2 — ECharts 재구현).
 *
 * Sparkline 과 나눈 이유: 스파크라인은 '값 하나의 흐름'이고 축·범례·0선이 없다. 두 선을 각각
 * 스파크라인으로 그리면 **선마다 눈금이 달라져** 위아래 관계가 뒤집혀 보인다.
 *
 * ## `null` 은 이제 ECharts 가 직접 처리한다
 *
 * 예전 판은 null 을 걸러낸 배열에서 원래 인덱스를 `{i,v}` 쌍으로 다시 붙여 다녔다(압축
 * 방지, `line-series-null-x.test.jsx` 가 그 계약을 지켰다). ECharts 의 라인 시리즈는
 * `connectNulls:false` 가 기본이라 **원본 배열을 그대로**(null 포함) `data` 에 넘기면
 * 그 자리만 끊기고 나머지 인덱스는 안 밀린다 — 손으로 인덱스를 다시 계산할 필요가 없다.
 *
 * ## §16 이 요구한 것 — `dataZoom`
 *
 * 긴 기간은 그림 **안에서** 좌우로 훑는다(휠·드래그). 페이지에 가로 스크롤을 만들지 않는다.
 * `type:"inside"` 는 짧은 시리즈(2주 스프린트 번다운)에서는 아무 일도 안 한다 — 확대할
 * 여백 자체가 없기 때문이다.
 *
 * ## 글자는 여전히 바깥 HTML
 *
 * y 눈금·끝점 직접 라벨·범례·요약 문장은 그대로 SVG 밖 HTML 이다(4K 폰트 레버, WCAG 1.4.1).
 * ECharts 는 **선·채움·확대**만 그린다.
 *
 * series: [{ label, points: number[], color? }] — 모든 선의 points 길이가 같아야 한다.
 * labels: x축 눈금 글자(양 끝만 쓴다).
 */

function toDashType(dash) {
  if (!dash) return "solid";
  return dash.split(/\s+/).map(Number);
}

/** 옵션 — **순수 함수**다(§18.2). `rows` 는 컴포넌트가 이미 계산해 둔 시리즈
 * (색·선 스타일 포함, `points` 는 null 을 그대로 둔 원본 길이 배열). */
export function lineSeriesOption({ rows, peak, drawn }) {
  const n = Math.max(...rows.map((r) => r.points.length), 0);
  return {
    ...baseOption(),
    grid: { left: 2, right: 2, top: 4, bottom: 4 },
    xAxis: {
      type: "category", data: Array.from({ length: n }, (_, i) => i),
      show: false, boundaryGap: false,
    },
    yAxis: { type: "value", show: false, min: 0, max: peak > 0 ? peak : undefined },
    tooltip: { trigger: "axis" },
    dataZoom: [{ type: "inside", zoomOnMouseWheel: true }],
    series: rows.map((r, idx) => ({
      type: "line",
      data: drawn ? r.points : r.points.map(() => null),
      showSymbol: false,
      smooth: 0.35,
      connectNulls: false,
      lineStyle: { color: r.color, width: 2.5, type: r.dashType },
      itemStyle: { color: r.color },
      areaStyle: idx === 0 ? { color: areaFill(r.color) } : undefined,
      emphasis: { focus: "series" },
      animation: drawn,
      animationDuration: CHART_MOTION.duration,
      animationEasing: CHART_MOTION.easing,
    })),
  };
}

/** 이 배열에서 마지막 숫자 값(null 이 아닌 것). 없으면 `undefined`. */
function lastFinite(points) {
  for (let i = points.length - 1; i >= 0; i--) {
    if (typeof points[i] === "number" && Number.isFinite(points[i])) return points[i];
  }
  return undefined;
}
function firstFinite(points) {
  for (let i = 0; i < points.length; i++) {
    if (typeof points[i] === "number" && Number.isFinite(points[i])) return points[i];
  }
  return undefined;
}

export function LineSeries({
  series, labels, height = "9rem", unit = "", summary, emptyLabel = "데이터 없음",
  question, revealKey,
}) {
  const theme = useTheme();
  const drawn = useRevealOnce(revealKey);
  const capped = capSeries(Array.isArray(series) ? series : [], {
    label: "기타",
    merge: (tail, label) => ({
      label,
      points: (tail[0] && tail[0].points ? tail[0].points : []).map((_, i) =>
        tail.reduce((sum, s) => {
          const v = s && Array.isArray(s.points) ? s.points[i] : null;
          return typeof v === "number" && Number.isFinite(v) ? sum + v : sum;
        }, 0)),
    }),
  });
  const rows = capped
    .map((s, idx) => {
      const rawPoints = Array.isArray(s && s.points) ? s.points : [];
      return {
        label: (s && s.label) || "",
        color: resolveChartColor(theme, s && s.color, idx),
        dashType: toDashType(seriesDash(idx)),
        points: rawPoints,
      };
    })
    .filter((s) => s.points.filter((v) => typeof v === "number" && Number.isFinite(v)).length >= 2);

  // 선 하나짜리(또는 점 하나짜리) '추세'는 없는 추세를 있는 것처럼 보이게 한다.
  if (!rows.length) return <ChartNoData label={emptyLabel} />;

  const peak = Math.max(...rows.flatMap((r) => r.points.filter((v) => typeof v === "number")), 0);
  const round1 = (v) => Math.round(v * 10) / 10;
  const fmt = (v) => `${round1(v)}`;

  const ticks = Array.isArray(labels) && labels.length >= 2
    ? [labels[0], labels[labels.length - 1]]
    : null;

  /* 눈금 — 0 · 1/2 · 1(최댓값). 값이 전부 0인 주에는 눈금이 정보가 아니라 소음이라 뺀다. */
  const gridValues = peak > 0 ? [peak, peak / 2, 0] : [];
  const topPct = (v) => (peak > 0 ? ((peak - v) / peak) * 100 : 100);

  /* 끝점 직접 라벨은 시리즈 3개 이하일 때만 — 그 이상이면 라벨끼리 겹쳐 서로를 가린다. */
  const direct = rows.length <= 3
    ? rows.map((r) => {
      const last = lastFinite(r.points);
      return { label: r.label, color: r.color, value: last, top: topPct(last) };
    })
    : [];

  const option = React.useMemo(
    () => lineSeriesOption({ rows, peak, drawn }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(rows.map((r) => [r.color, r.dashType, r.points])), peak, drawn],
  );
  const containerRef = useEChart(option);

  return (
    <Box>
      <ChartQuestion>{question}</ChartQuestion>
      <Box sx={{ display: "grid", gridTemplateColumns: "auto minmax(0, 1fr)", columnGap: 1 }}>
        {/* y 눈금 글자 — SVG 밖 HTML 이라 4K 폰트 레버를 그대로 탄다. 단위는 여기 한 번만. */}
        <Box sx={{ position: "relative", width: "max-content", minWidth: "2.5rem", height }}>
          {gridValues.map((v, i) => (
            <Typography
              key={i}
              variant="caption"
              color="text.secondary"
              sx={{
                position: "absolute", insetInlineEnd: 0, top: `${topPct(v)}%`,
                transform: "translateY(-50%)", whiteSpace: "nowrap",
                fontVariantNumeric: "tabular-nums", lineHeight: 1,
              }}
            >
              {fmt(v)}{i === 0 && unit ? unit : ""}
            </Typography>
          ))}
        </Box>
        <Box sx={{ position: "relative", minWidth: 0 }}>
          <Box ref={containerRef} aria-hidden="true" sx={{ width: "100%", height }} />
          {/* 끝점 직접 라벨 — 눈이 범례를 거치지 않고 선에서 바로 값을 읽는다. */}
          {direct.map((d, i) => (
            d.value == null ? null : (
              <Typography
                key={i}
                aria-hidden="true"
                variant="caption"
                sx={{
                  position: "absolute", insetInlineEnd: 0, top: `${d.top}%`,
                  transform: "translate(0, -50%)", color: d.color, whiteSpace: "nowrap",
                  fontWeight: FONT_WEIGHT.bold, fontVariantNumeric: "tabular-nums", lineHeight: 1,
                  px: 0.5, borderRadius: 0.5, bgcolor: "background.plate",
                }}
              >
                {fmt(d.value)}
              </Typography>
            )
          ))}
        </Box>
      </Box>
      {ticks ? (
        <Box sx={{ display: "flex", justifyContent: "space-between", mt: 0.5 }}>
          {ticks.map((t, i) => (
            <Typography key={i} variant="caption" color="text.secondary">{t}</Typography>
          ))}
        </Box>
      ) : null}
      {/* 범례가 이 그림의 텍스트 대체물이다 — 선을 못 보는 사람도 같은 수치를 그대로 읽는다. */}
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mt: 0.75 }}>
        {rows.map((r, idx) => (
          <Box key={r.label || idx} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            <Box
              component="span" aria-hidden="true"
              sx={{
                width: "1.25rem", height: 0, flexShrink: 0,
                borderTop: r.dashType !== "solid" ? "0.1875rem dashed" : "0.1875rem solid",
                borderColor: r.color,
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {r.label}: 시작 {fmt(firstFinite(r.points))} → 끝 {fmt(lastFinite(r.points))}
            </Typography>
          </Box>
        ))}
      </Box>
      {summary ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
          {summary}
        </Typography>
      ) : null}
    </Box>
  );
}

export default LineSeries;
