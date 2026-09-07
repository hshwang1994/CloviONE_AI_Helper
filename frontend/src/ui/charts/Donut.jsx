import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { ChartNoData, ChartQuestion, capSeries, CHART_MOTION, resolveChartColor, useTrackColor } from "./base.jsx";
import { baseOption, useEChart } from "./useEChart.js";
import { useRevealOnce } from "../motion.js";
import { FONT_WEIGHT, NUMERIC } from "../theme.js";

/* 도넛 — 전체가 무엇으로 이루어져 있는지(구성비)를 보여준다 (REAUDIT §15.2 — ECharts 재구현).
 * 크기 비교는 BarSeries가 낫다.
 *
 * segments: [{ label, value, color? }]. value가 0 이하인 조각은 그리지 않는다(0%짜리 조각은
 * 테두리 한 줄로만 남아 '아주 작은 값'처럼 오해된다).
 *
 * 가운데 합계와 범례는 SVG가 아니라 HTML이다 — SVG <text>는 px 단위라 4K에서 혼자 작게 남는다
 * (ECharts 자신의 라벨·범례·툴팁은 끈다 — `useEChart.js` 문서). 범례가 곧 이 그림의 텍스트
 * 대체물이라서, 도넛을 못 보는 사람도 같은 수치를 그대로 읽는다.
 */
/* `revealKey` — BarSeries 와 같은 규약이다. 처음 보거나 값이 바뀐 링만 한 번 그려지고,
 * 같은 값으로 다시 마운트되면 최종 상태로 선다(`ui/motion.js::useRevealOnce`). ECharts 는
 * 자기 자신의 데이터 전환 애니메이션으로 "0 → 실제 값" 을 그린다 — `drawn` 이 그 스위치다. */

/** 옵션 — **순수 함수**다(§18.2). `arcs` 는 컴포넌트가 이미 계산해 둔 조각(색 포함)이고,
 * `missing` 은 모수와 조각 합의 차이(트랙 색 몫)다. */
export function donutOption({ arcs, missing, thickness, size, trackColor, drawn, gapColor }) {
  const data = arcs.map((a) => ({
    name: a.key,
    value: drawn ? a.value : 0,
    itemStyle: { color: a.color },
  }));
  if (missing > 0) {
    data.push({ name: "분류 없음", value: drawn ? missing : 0, itemStyle: { color: trackColor } });
  }
  return {
    ...baseOption(),
    tooltip: { trigger: "item" },
    series: [
      {
        type: "pie",
        // ECharts 는 반지름을 %면 컨테이너 기준으로, 값이면 px 로 읽는다 — 두께는 안·바깥
        // 반지름의 차이로만 표현할 수 있어 %를 쓴다(고정 두께 px 대신 size 에 비례한다).
        radius: ["70%", "100%"],
        startAngle: 90,
        clockwise: true,
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        emphasis: { scale: false },
        itemStyle: {
          borderWidth: gapColor ? 2 : 0,
          borderColor: gapColor || "transparent",
        },
        data,
        animationDuration: CHART_MOTION.duration,
        animationEasing: CHART_MOTION.easing,
      },
    ],
  };
}

/* 범례 한 줄 — **점 · 낱말 · 건수 · 비율** 네 칸 고정 격자.
 *
 * 예전에는 넷이 한 문장으로 흘렀다(「검증 5건 (26%)」). 그러면 낱말 길이에 따라 건수와
 * 비율의 시작점이 줄마다 달라져, 세로로 훑으며 크기를 견주는 일이 안 된다 — 범례가
 * 존재하는 이유가 그 비교인데. 낱말 칸만 늘어나고 나머지 셋은 자기 자리를 지킨다. */
const LEGEND_ROW = {
  display: "grid", gridTemplateColumns: "auto minmax(0,1fr) auto auto",
  columnGap: 1, alignItems: "center", minWidth: 0,
};
const LEGEND_DOT = { width: 7, height: 7, borderRadius: "999px", flex: "0 0 auto" };
const LEGEND_LABEL = { minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };
const LEGEND_VALUE = { fontWeight: FONT_WEIGHT.bold, whiteSpace: "nowrap", ...NUMERIC };
const LEGEND_PCT = { width: "2.75rem", textAlign: "end", whiteSpace: "nowrap", ...NUMERIC };

export function Donut({
  segments, size = "9rem", unit = "", centerLabel, emptyLabel = "데이터 없음", thickness = 5,
  total: totalProp, restLabel = "기타", question, revealKey,
}) {
  const theme = useTheme();
  const track = useTrackColor();
  const drawn = useRevealOnce(revealKey);
  const visible = (Array.isArray(segments) ? segments : []).filter(
    (s) => s && typeof s.value === "number" && Number.isFinite(s.value) && s.value > 0
  );
  /* 조각 상한 5 — 6번째부터는 색으로도 구분되지 않는다(인접 슬롯 휘도 분리 최대 1.26:1).
     구분되는 척하는 대신 합쳐서 «기타» 하나로 말한다. */
  const rows = capSeries(visible, {
    label: restLabel,
    merge: (tail, label) => ({ label, value: tail.reduce((sum, s) => sum + s.value, 0) }),
  });
  const shown = rows.reduce((sum, s) => sum + s.value, 0);
  /* **모수는 입력이다.** 예전에는 «그려진 조각의 합»을 모수라고 불렀는데, 값 0 이하인 상태와
     호출부가 걸러 낸 것이 조용히 빠져 도넛이 전체를 설명한다고 착각하게 만들었다(호출부 셋 중
     하나만 손으로 «기타»를 보정하고 있었다). 모수를 안 주면 그려진 합이 곧 전체라는 **주장**이
     되므로, 그 주장을 호출부가 명시적으로 하게 한다. */
  const total = (typeof totalProp === "number" && Number.isFinite(totalProp) && totalProp > 0)
    ? totalProp
    : shown;
  const missing = Math.max(0, total - shown);

  const arcs = rows.map((s, idx) => ({
    key: s.label, value: s.value, color: resolveChartColor(theme, s.color, idx),
  }));
  const option = React.useMemo(
    () => (rows.length && total > 0 ? donutOption({
      arcs, missing, thickness, size, trackColor: track, drawn,
      gapColor: theme.palette.background.plate,
    }) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(arcs), missing, thickness, size, track, drawn, total, rows.length, theme.palette.background.plate],
  );
  const containerRef = useEChart(option);

  // 값이 없으면 **도넛을 통째로 접는다** — 빈 원을 그리지도, 도넛 높이만큼 빈 상자를
  // 남기지도 않는다(PLAN «빈 데이터 규칙» ⓑ).
  if (!rows.length || total <= 0) return <ChartNoData label={emptyLabel} />;

  return (
    <Box>
    <ChartQuestion>{question}</ChartQuestion>
    <Box sx={{ display: "flex", alignItems: "center", gap: { xs: 2, sm: 3 }, flexWrap: "wrap" }}>
      <Box data-chart-frame="donut" sx={{ position: "relative", width: size, height: size, flex: "0 0 auto" }}>
        <Box ref={containerRef} aria-hidden="true" sx={{ width: "100%", height: "100%" }} />
        {/* 가운데 합계 — 도넛의 구멍은 비워 두면 아깝고, 구성비만 있고 모수가 없으면 해석이 안 된다. */}
        <Box sx={{ position: "absolute", inset: 0, display: "grid", placeContent: "center", textAlign: "center" }}>
          {/* PA-RC-0001: 24px — ProjectWbs.jsx·game-room/GameStage.jsx와 같은 값+굵기(의도된
              예외, 세부 사유는 GameStage.jsx 참고 — 전용 토큰 신설은 검토 후 보류함, D-78). */}
          <Typography sx={{ fontSize: "1.5rem", fontWeight: FONT_WEIGHT.extrabold, lineHeight: 1.1 }}>
            {total}{unit}
          </Typography>
          {centerLabel ? (
            <Typography variant="caption" color="text.secondary">{centerLabel}</Typography>
          ) : null}
        </Box>
      </Box>
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5, minWidth: 0 }}>
        {rows.map((s, i) => (
          <Box component="li" key={s.label} sx={LEGEND_ROW}>
            {/* 색 조각은 장식이다(aria-hidden). 옆의 글자만으로도 뜻이 완전해야 한다(WCAG 1.4.1).
                모양은 **7px 점**이다 — 이 제품에서 색을 나르는 자리는 전부 그 점이다(배지·
                상태 칩·KPI). 범례만 네모면 같은 색이 두 모양으로 나온다. */}
            <Box aria-hidden="true" sx={{ ...LEGEND_DOT, bgcolor: arcs[i].color }} />
            <Typography variant="body2" color="text.secondary" sx={LEGEND_LABEL}>{s.label}</Typography>
            <Typography variant="body2" sx={LEGEND_VALUE}>{s.value}{unit}</Typography>
            <Typography variant="body2" color="text.secondary" sx={LEGEND_PCT}>
              ({Math.round((s.value / total) * 100)}%)
            </Typography>
          </Box>
        ))}
        {/* 모수와 조각 합이 다르면 그 차이를 **말한다**. 링의 빈 호는 트랙 색으로 이미 보이지만,
            그것을 글자로 말하지 않으면 도넛을 못 보는 사람에게는 없는 사실이 된다. */}
        {missing > 0 ? (
          <Box component="li" sx={LEGEND_ROW}>
            <Box aria-hidden="true" sx={{ ...LEGEND_DOT, bgcolor: track }} />
            <Typography variant="body2" color="text.secondary" sx={LEGEND_LABEL}>분류 없음</Typography>
            <Typography variant="body2" color="text.secondary" sx={LEGEND_VALUE}>{missing}{unit}</Typography>
            <Typography variant="body2" color="text.secondary" sx={LEGEND_PCT}>
              ({Math.round((missing / total) * 100)}%)
            </Typography>
          </Box>
        ) : null}
      </Box>
    </Box>
    </Box>
  );
}

export default Donut;
