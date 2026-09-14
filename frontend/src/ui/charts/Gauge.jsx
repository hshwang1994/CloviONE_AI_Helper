import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

import { CHART_MOTION, resolveChartColor, useTrackColor } from "./base.jsx";
import { baseOption, useEChart } from "./useEChart.js";
import { useRevealOnce } from "../motion.js";
import { FONT_SIZE, FONT_WEIGHT } from "../theme.js";

/* 점수 하나를 **원으로** 그린다 (지시 10 · 16 · REAUDIT §15.2 — ECharts 재구현).
 *
 * ## 왜 도넛이 아니라 따로 있나
 *
 * `Donut` 은 **여럿의 구성**을 그린다 — 조각마다 이름이 있고 범례가 그 이름을 읽어 준다.
 * 점수는 구성이 아니라 **한 값이 상한의 몇 분의 몇인가**다. 도넛으로 그리면 「남은 점수」
 * 라는 이름 없는 조각이 범례에 서고, 그 조각은 아무 뜻도 없다.
 *
 * ## 숫자가 먼저다
 *
 * 가운데 글자가 그림 없이도 읽히는 값이고, 원은 그것을 거든다. 그림을 못 보는 사람이
 * 잃는 것이 없어야 한다 — 그래서 원은 `aria-hidden` 이고 점수는 글자로 나간다(ECharts
 * 자신의 `detail`/`title` 은 끈다 — 이 컴포넌트의 HTML `<Typography>` 가 그 자리를 대신한다,
 * `useEChart.js` 문서 참고).
 *
 * ## ECharts 로 다시 그린 이유(§15.2)
 *
 * 게이지가 **1급 차트**다(회차 건강·프로젝트 Health). 손으로 만든 원(`stroke-dasharray`
 * 트릭)을 유지하는 대신 ECharts 의 `gauge` 시리즈를 쓴다 — 이 저장소의 대비·마스코트
 * 프로브가 DOM 을 읽으므로 `SVGRenderer` 로 실제 `<path>` 를 그린다.
 *
 * `startAngle:90, endAngle:-270` 로 **완전한 원**을 만든다(기본 게이지는 반원이다) —
 * 이 제품의 게이지는 처음부터 12시에서 시작해 시계 방향으로 도는 온전한 원이었다.
 */

/** 옵션 — **순수 함수**다. 시험이 이 함수를 직접 불러 렌더 없이 값만 잰다(§18.2). */
export function gaugeOption({ pct, thickness, trackColor, strokeColor, drawn }) {
  return {
    ...baseOption(),
    series: [
      {
        type: "gauge",
        startAngle: 90,
        endAngle: -270,
        min: 0,
        max: 100,
        radius: "100%",
        pointer: { show: false },
        anchor: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        title: { show: false },
        detail: { show: false },
        axisLine: { lineStyle: { width: thickness, color: [[1, trackColor]] } },
        progress: {
          show: true,
          overlap: false,
          width: thickness,
          roundCap: true,
          itemStyle: { color: strokeColor },
        },
        // 0 -> 실제 값으로 자라는 것은 ECharts 자신의 데이터 전환 애니메이션이다 —
        // `drawn` 이 false 인 동안은 0을 그려 두고, true 로 바뀌면 실제 값으로 다시
        // `setOption` 되어 그 사이를 ECharts 가 채운다(`useRevealOnce` 와 같은 지문 규약).
        data: [{ value: drawn ? pct : 0 }],
        animationDuration: CHART_MOTION.duration,
        animationEasing: CHART_MOTION.easing,
      },
    ],
  };
}

/* 가운데 글자의 크기 — `centerSize="readout"` 은 판독값(회차 건강처럼 한 화면의 주인 숫자)이고,
 * 기본은 카드 안의 작은 링이다. 크기는 링 크기와 별개로 부르는 쪽이 고른다: 큰 링에 작은
 * 글자는 비고, 작은 링에 큰 글자는 링에 닿는다. 두 값 다 `FONT_SIZE` 토큰이다. */

export function Gauge({
  value, max = 100, size = "7rem", thickness = 5,
  label, centerText, centerCaption, centerSize = "default", color,
  emptyLabel = "아직 재지 않음", revealKey,
}) {
  const theme = useTheme();
  const track = useTrackColor();
  const drawn = useRevealOnce(revealKey);

  const known = typeof value === "number" && Number.isFinite(value);
  const pct = known ? Math.max(0, Math.min(100, (value / (max || 100)) * 100)) : 0;
  const band = pct >= 75 ? "ok" : pct >= 50 ? "warn" : "danger";
  const stroke = resolveChartColor(theme, color || band, 0);

  const option = React.useMemo(
    () => (known
      ? gaugeOption({ pct, thickness, trackColor: track, strokeColor: stroke, drawn })
      : null),
    [known, pct, thickness, track, stroke, drawn],
  );
  const containerRef = useEChart(option);

  /* **모르는 것과 0 은 다른 값이다.** 안 잰 점수를 0 으로 그리면 한 번도 안 잰 프로젝트가
     화면에서 가장 나쁜 프로젝트가 된다(`app/projects/health.py` 가 같은 판단을 한다). */
  if (!known) {
    return (
      <Box sx={{ display: "grid", gap: 0.5, justifyItems: "center" }}>
        <Box
          aria-hidden="true"
          sx={{
            width: size, height: size, borderRadius: "50%",
            border: `${thickness * 0.6}px dashed`, borderColor: "divider",
            display: "grid", placeItems: "center",
          }}
        />
        <Typography variant="body2" color="text.secondary">{emptyLabel}</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "grid", gap: 0.5, justifyItems: "center", minWidth: 0 }}>
      <Box data-chart-frame="gauge" sx={{ position: "relative", width: size, height: size }}>
        <Box ref={containerRef} aria-hidden="true" sx={{ width: "100%", height: "100%" }} />
        {/* `centerText={false}` — 가운데를 **비운다**. 값을 링 옆에 두는 배치가 있어서다:
            작은 링(46~72px)에서 안쪽 지름은 두께를 뺀 만큼이라 두 자리 백분율이 안 들어가고,
            억지로 넣으면 글자가 링에 닿는다. 그때는 숫자와 이름을 링 옆에 세로로 묶는다. */}
        {centerText === false ? null : (
          /* 덮개는 **세 줄 격자**(`1fr auto 1fr`)다 — 가운데 줄에 숫자와 캡션이 한 덩어리로
             서고 위아래 빈 줄이 같은 높이라, 캡션이 있든 없든 덩어리의 중심이 링의 중심과
             맞는다. `placeItems: center` 하나로는 두 줄짜리 내용이 아래로 처졌다. */
          <Box
            data-gauge-center=""
            sx={{
              position: "absolute", inset: 0, display: "grid",
              gridTemplateRows: "1fr auto 1fr", justifyItems: "center", textAlign: "center",
              px: `${thickness * 2}px`,
            }}
          >
            <Box aria-hidden="true" />
            <Box sx={{ display: "grid", gap: 0.25, justifyItems: "center", minWidth: 0 }}>
              <Typography
                component="span"
                sx={{
                  fontSize: centerSize === "readout" ? FONT_SIZE.pageTitle : FONT_SIZE.sectionTitle,
                  fontWeight: FONT_WEIGHT.extrabold, lineHeight: 1.05,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {centerText == null ? value : centerText}
              </Typography>
              {centerCaption ? (
                <Typography component="span" variant="caption" color="text.secondary" sx={{ lineHeight: 1.2 }}>
                  {centerCaption}
                </Typography>
              ) : null}
            </Box>
            <Box aria-hidden="true" />
          </Box>
        )}
      </Box>
      {label ? <Typography variant="body2" color="text.secondary">{label}</Typography> : null}
    </Box>
  );
}
