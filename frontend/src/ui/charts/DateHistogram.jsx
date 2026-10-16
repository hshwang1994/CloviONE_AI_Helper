import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

import { ChartNoData, ChartQuestion, CHART_MOTION, resolveChartColor, useTrackColor } from "./base.jsx";
import { baseOption, useEChart } from "./useEChart.js";
import { useRevealOnce } from "../motion.js";
import { rootFontPx } from "../columnTypes.js";
import { FONT_SIZE, FONT_WEIGHT } from "../theme.js";
import { subjectParticle } from "../../lib/format.js";

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
 * ## 🔴 날짜 눈금만은 ECharts 가 그린다 (2026-09-01)
 *
 * 이 저장소의 규칙은 「글자는 SVG 밖 HTML 이 낸다」이고(`useEChart.js` 문서), 이 그림도
 * 그 규칙대로 눈금 줄을 HTML `flex` 로 그렸다. **그 줄이 두 가지로 틀렸다.**
 *
 *   ① **글자가 잘렸다.** 90 칸을 `flex:1 1 0` 으로 등분하면 한 칸이 1920 에서 17px 이고
 *      390 에서 3px 이다 — `overflow:hidden` + `textOverflow:clip` 이라 「6/14」가
 *      「6/1」로, 「8/23」이 「8/2」로 **말줄임표도 없이** 잘려 나갔다. 6월 14일이 6월
 *      1일로 읽히는 눈금은 없는 것보다 나쁘다.
 *   ② **그림이 보여 주는 구간과 다른 날짜를 말했다.** 위 `initialZoomRange` 가 자료가
 *      있는 구간만 열어 주는데, HTML 줄은 언제나 **90 일 전체**를 등분해 그렸다. 실측:
 *      막대는 8/29~9/1 네 칸인데 눈금은 6/4~8/23 을 말하고 있었다. 휠로 확대하면 그
 *      어긋남이 더 커졌고, HTML 줄은 그 사실을 알 방법 자체가 없다.
 *
 * 그래서 이 축만 ECharts 에 넘긴다. 축은 **지금 보이는 카테고리**를 알고 있으므로 확대·
 * 이동을 따라가고, `hideOverlap` 이 자리가 모자란 눈금을 **자르는 대신 뺀다**. HTML 을
 * 떠나며 잃는 것 하나(4K 폰트 레버)는 `fontSize` 를 루트 폰트에서 계산해 넘겨 되찾는다 —
 * dataZoom 미니맵이 이미 받은 것과 같은 성격의 예외이고, 이유를 여기 적어 둔다.
 *
 * 막대는 `aria-hidden` 이다 — 그림을 못 보는 사람을 위해 **가장 몰린 날과 합계**를 글자로
 * 함께 낸다. 막대 90 개를 하나씩 읽어 주는 것은 정보가 아니라 소음이다.
 */

/** 막대가 서는 높이 + 그 아래 날짜 눈금이 앉을 자리. */
const PLOT_HEIGHT = "9.5rem";

/** 가장 높은 막대 위에 남기는 여백(px). 0 이면 최댓값 막대가 판 위쪽에 **딱 붙어** 잘린
 *  것처럼 보인다 — 예전 값은 4px 이었고 실측에서 실제로 그렇게 보였다. */
const HEADROOM_PX = 12;

/** 'YYYY-MM-DD' → 'M/D'. 축에 연도를 반복해 적지 않는다. */
export function shortDay(iso) {
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

/** 처음 여는 구간이 창 전체보다 좁은가 — 문장이 「그림은 앞뒤 구간을 먼저 보여 준다」고 덧붙일지 정한다. */
export function zoomedIn(days) {
  if (!Array.isArray(days) || !days.length) return false;
  const zoom = initialZoomRange(days);
  return zoom.startValue > 0 || zoom.endValue < days.length - 1;
}

/** 옵션 — **순수 함수**다(§18.2). `days` 는 `{date, count}` 배열, 0건인 날도 포함된다. */
export function dateHistogramOption({
  days, fillColor, trackColor, drawn, axisColor, axisLineColor, fontSize,
}) {
  const zoom = initialZoomRange(days);
  return {
    ...baseOption(),
    /* `containLabel` 이 켜져 있어야 눈금 글자가 판 안쪽에 자리를 얻는다 — 끄면 글자가
       상자 밖으로 나가 잘린다(HTML 줄이 겪은 것과 같은 결말). 위쪽 여백은 최댓값 막대의
       머리 공간이다. */
    grid: { left: 2, right: 2, top: HEADROOM_PX, bottom: 0, containLabel: true },
    xAxis: {
      type: "category",
      data: days.map((d) => d.date),
      show: true,
      axisLine: { show: true, lineStyle: { color: axisLineColor } },
      axisTick: { show: false },
      axisLabel: {
        show: true,
        color: axisColor,
        fontSize,
        /* 자리가 모자라면 **자르지 않고 뺀다.** 잘린 「6/1」은 6월 1일이라는 거짓말이지만
           빠진 눈금은 아무 말도 하지 않는다 — 후자만 정직하다. */
        hideOverlap: true,
        margin: 8,
        formatter: (value) => shortDay(value),
      },
    },
    yAxis: { type: "value", show: false, min: 0 },
    tooltip: { trigger: "axis" },
    dataZoom: [{ type: "inside", zoomOnMouseWheel: true, ...zoom }],
    series: [
      {
        type: "bar",
        data: days.map((d) => ({
          value: drawn ? d.count : 0,
          itemStyle: { color: d.count > 0 ? fillColor : trackColor, borderRadius: [3, 3, 0, 0] },
        })),
        barCategoryGap: "25%",
        /* 칸이 넓어도 막대는 이 폭까지만 선다 — 자료가 하루에 몰리면 처음 여는 구간이 며칠뿐이라 막대 하나가 300px 로 섰다(r23 #39). */
        barMaxWidth: 40,
        animationDuration: CHART_MOTION.duration,
        animationEasing: CHART_MOTION.easing,
      },
    ],
  };
}

export function DateHistogram({ days, question, color, emptyLabel = "추가된 티켓이 없습니다.", unit = "건", revealKey }) {
  const theme = useTheme();
  const track = useTrackColor();
  const drawn = useRevealOnce(revealKey);
  const rows = Array.isArray(days) ? days.filter((d) => d && typeof d.count === "number") : [];
  const total = rows.reduce((sum, d) => sum + d.count, 0);

  const fill = resolveChartColor(theme, color, 0);
  const axisColor = theme.palette.text.secondary;
  const axisLineColor = theme.palette.divider;
  /* 4K 에서 루트 폰트가 커진다(`styles/root.css` 16→18→20). SVG `<text>` 는 rem 을 안
     받으므로 그 레버를 여기서 px 로 풀어 넘긴다 — 이 축이 HTML 을 떠나며 잃을 뻔한 것. */
  const fontSize = Math.round(rootFontPx() * parseFloat(FONT_SIZE.micro));
  const option = React.useMemo(
    () => (rows.length
      ? dateHistogramOption({
        days: rows, fillColor: fill, trackColor: track, drawn,
        axisColor, axisLineColor, fontSize,
      })
      : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(rows), fill, track, drawn, axisColor, axisLineColor, fontSize],
  );
  const containerRef = useEChart(option);

  if (!rows.length || total === 0) return <ChartNoData label={emptyLabel} />;

  const busiest = rows.reduce((best, d) => (d.count > best.count ? d : best), rows[0]);

  return (
    <Box sx={{ minWidth: 0 }}>
      <ChartQuestion>{question}</ChartQuestion>
      <Box
        role="group"
        aria-label={question || "날짜별 추가 건수"}
        sx={{ minWidth: 0 }}
      >
        {/* 날짜 눈금은 이 상자 **안**에 있다(위 문서 «날짜 눈금만은 ECharts 가 그린다»). */}
        <Box ref={containerRef} aria-hidden="true" sx={{ width: "100%", height: PLOT_HEIGHT }} />
      </Box>
      {/* 그림의 글자 대체물. 막대 아흔 개를 읽어 주는 대신 **읽을 만한 두 사실**을 말한다. 창의 길이(「최근 90일」)를 먼저 밝힌다 —
          그림은 자료가 있는 구간만 먼저 열어서(`initialZoomRange`) 축은 며칠뿐인데 문장은 석 달을 말해 기간이 다르게 읽혔다(r23 #39).
          그림이 창의 일부만 보일 때는 그 사실을 한 문장 더 말한다. */}
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        {`최근 ${rows.length}일 동안(${rows[0].date}부터 ${rows[rows.length - 1].date}까지) `}
        <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, color: "text.primary" }}>
          {`${total}${unit}`}
        </Box>
        {/* 조사는 단위의 받침을 따른다(건이 · 개가). */}
        {`${subjectParticle(unit)} 추가되었습니다. 가장 많았던 날은 ${busiest.date}(${busiest.count}${unit})입니다.`}
        {zoomedIn(rows) ? " 그림은 추가된 날 앞뒤 구간을 먼저 보여 줍니다." : ""}
      </Typography>
    </Box>
  );
}
