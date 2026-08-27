import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

import { ChartNoData, ChartQuestion, resolveChartColor, useTrackColor } from "./base.jsx";
import { baseOption, useEChart } from "./useEChart.js";
import { useRevealOnce } from "../motion.js";
import { FONT_SIZE, FONT_WEIGHT } from "../theme.js";

/* 날짜별 건수 — **세로 막대**, 그리고 **자기 안에서만 굴러간다** (지시 16 · REAUDIT §15.2).
 *
 * ## 왜 `BarSeries` 가 아닌가
 *
 * 그쪽은 **항목끼리 비교**하는 그림이라 가로 막대다(담당자별 남은 일). 시간은 다르다 —
 * 왼쪽에서 오른쪽으로 흐르는 축이 있고, 사람이 읽는 것은 「어느 시점에 몰렸나」다.
 *
 * ## §16 — dataZoom 이 이 그림을 ECharts 로 옮긴 핵심 이유
 *
 * 90 일 × 막대 하나가 화면 폭을 넘으면 예전엔 **이 상자 자신이 `overflow-x:auto`** 로
 * 옆으로 굴렀다. 이제는 `dataZoom(type:"inside")` 가 같은 성질(페이지가 아니라 그림
 * 안에서 탐색)을 휠·드래그로 준다 — §16 이 요구한 그대로다.
 *
 * ## 0 인 날도 자리를 갖는다
 *
 * 값이 있는 날만 그리면 「사흘 연속 없었다」와 「사흘이 하루로 붙었다」가 같은 그림이 된다.
 * 서버가 빈 날까지 보내고(`app/projects/service.py::ticket_trend`) x축 카테고리에
 * 전부 올리면 0건인 날도 자기 자리(높이 0인 막대)를 그대로 지킨다.
 *
 * 막대는 `aria-hidden` 이다 — 그림을 못 보는 사람을 위해 **가장 몰린 날과 합계**를 글자로
 * 함께 낸다. 막대 90 개를 하나씩 읽어 주는 것은 정보가 아니라 소음이다.
 */

const PLOT_HEIGHT = "7.5rem";

/** 'YYYY-MM-DD' → 'M/D'. 축에 연도를 반복해 적지 않는다. */
function shortDay(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  return m ? `${Number(m[2])}/${Number(m[3])}` : "";
}

/* C10 — 서버는 **항상 최근 90일**을 낸다(`TREND_DEFAULT_DAYS`, 프로젝트 나이·활동
 * 기간과 무관하다 — 「빈 날도 낸다」는 계약을 지키려면 창 자체는 고정이어야 한다).
 * 자료가 그 창의 좁은 한 구석(예: 초반 이틀)에만 몰려 있으면 처음 보이는 그림이 「막대
 * 두 개 + 텅 빈 축」이 된다 — dataZoom 이 있어도 처음 펼치는 화면이 그렇다는 것을 아무도
 * 모르면 없는 것과 같다. 그래서 실제 값이 있는 구간을 앞뒤로 며칠 여유를 두고 **처음부터
 * 그 구간으로** 연다. 활동이 창 전체에 고르게 퍼져 있으면(흔한 경우) 이 계산은 사실상
 * 0~끝을 그대로 돌려주므로 오늘과 같은 그림이다 — 몰려 있을 때만 달라진다. */
function initialZoomRange(days) {
  const last = days.length - 1;
  const populated = [];
  days.forEach((d, i) => { if (d.count > 0) populated.push(i); });
  if (!populated.length) return { startValue: 0, endValue: last };
  const PAD = 3;
  return {
    startValue: Math.max(0, populated[0] - PAD),
    endValue: Math.min(last, populated[populated.length - 1] + PAD),
  };
}

/** 옵션 — **순수 함수**다(§18.2). `days` 는 `{date, count}` 배열, 0건인 날도 포함된다. */
export function dateHistogramOption({ days, fillColor, trackColor, drawn }) {
  const zoom = initialZoomRange(days);
  return {
    ...baseOption(),
    grid: { left: 2, right: 2, top: 4, bottom: 2 },
    xAxis: { type: "category", data: days.map((d) => d.date), show: false },
    yAxis: { type: "value", show: false },
    dataZoom: [{ type: "inside", zoomOnMouseWheel: true, ...zoom }],
    series: [
      {
        type: "bar",
        data: days.map((d) => ({
          value: drawn ? d.count : 0,
          itemStyle: { color: d.count > 0 ? fillColor : trackColor },
        })),
        barCategoryGap: "25%",
        animationDuration: 400,
      },
    ],
  };
}

export function DateHistogram({ days, question, color, emptyLabel = "만든 티켓이 없습니다", unit = "건", revealKey }) {
  const theme = useTheme();
  const track = useTrackColor();
  const drawn = useRevealOnce(revealKey);
  const rows = Array.isArray(days) ? days.filter((d) => d && typeof d.count === "number") : [];
  const total = rows.reduce((sum, d) => sum + d.count, 0);

  const fill = resolveChartColor(theme, color, 0);
  const option = React.useMemo(
    () => (rows.length ? dateHistogramOption({ days: rows, fillColor: fill, trackColor: track, drawn }) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(rows), fill, track, drawn],
  );
  const containerRef = useEChart(option);

  if (!rows.length || total === 0) return <ChartNoData label={emptyLabel} />;

  const busiest = rows.reduce((best, d) => (d.count > best.count ? d : best), rows[0]);
  const labelEvery = Math.max(1, Math.ceil(rows.length / 9));

  return (
    <Box sx={{ minWidth: 0 }}>
      <ChartQuestion>{question}</ChartQuestion>
      <Box
        role="group"
        aria-label={question || "날짜별 생성량"}
        sx={{ minWidth: 0 }}
      >
        <Box ref={containerRef} aria-hidden="true" sx={{ width: "100%", height: PLOT_HEIGHT, borderBottom: 1, borderColor: "divider" }} />
        {/* 날짜 눈금 — SVG 밖 HTML. 전체 폭을 막대 수만큼 등분해 라벨 위치를 맞춘다. */}
        <Box aria-hidden="true" sx={{ display: "flex", mt: 0.5 }}>
          {rows.map((d, i) => (
            <Box
              key={d.date}
              sx={{
                flex: "1 1 0", minWidth: 0, textAlign: "center",
                fontSize: FONT_SIZE.micro, color: "text.secondary", whiteSpace: "nowrap", overflow: "hidden",
              }}
            >
              {i % labelEvery === 0 ? shortDay(d.date) : ""}
            </Box>
          ))}
        </Box>
      </Box>
      {/* 그림의 글자 대체물. 막대 아흔 개를 읽어 주는 대신 **읽을 만한 두 사실**을 말한다. */}
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        {`${rows[0].date}부터 ${rows[rows.length - 1].date}까지 `}
        <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, color: "text.primary" }}>
          {`${total}${unit}`}
        </Box>
        {`을 만들었습니다. 가장 많았던 날은 ${busiest.date}(${busiest.count}${unit})입니다.`}
      </Typography>
    </Box>
  );
}
