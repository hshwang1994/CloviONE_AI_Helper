import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

import { ChartNoData, ChartQuestion, resolveChartColor, useTrackColor } from "./base.jsx";
import { FONT_SIZE, FONT_WEIGHT, MOTION } from "../theme.js";

/* 날짜별 건수 — **세로 막대**, 그리고 **자기 안에서만 굴러간다** (지시 16).
 *
 * ## 왜 `BarSeries` 가 아닌가
 *
 * 그쪽은 **항목끼리 비교**하는 그림이라 가로 막대다(담당자별 남은 일). 시간은 다르다 —
 * 왼쪽에서 오른쪽으로 흐르는 축이 있고, 사람이 읽는 것은 「어느 시점에 몰렸나」다.
 * 그 모양을 가로 막대로 그리면 날짜가 세로로 늘어서서 90 일이 화면 세 개가 된다.
 *
 * ## 페이지가 아니라 그림이 굴러간다
 *
 * 90 일 × 막대 하나가 화면 폭을 넘으면 **이 상자 안에서** 좌우로 민다. 페이지 전체에
 * 가로 스크롤을 만들지 않는다 — 그렇게 되면 표도 머리글도 같이 밀려서, 그림 하나 때문에
 * 화면 전체가 못 읽는 상태가 된다.
 *
 * ## 0 인 날도 자리를 갖는다
 *
 * 값이 있는 날만 그리면 「사흘 연속 없었다」와 「사흘이 하루로 붙었다」가 같은 그림이 된다.
 * 서버가 빈 날까지 보내고(`app/projects/service.py::ticket_trend`) 여기서는 그대로 세운다.
 *
 * 막대는 `aria-hidden` 이다 — 그림을 못 보는 사람을 위해 **가장 몰린 날과 합계**를 글자로
 * 함께 낸다. 막대 90 개를 하나씩 읽어 주는 것은 정보가 아니라 소음이다.
 */

/* 막대 하나의 폭과 사이. 좁히면 90 일이 한 화면에 들어오지만 6px 짜리 막대는 높이 차이를
 * 못 읽는다 — 굴리는 편이 낫다. */
const BAR = 10;
const GAP = 3;
const PLOT_HEIGHT = 120;

/** 'YYYY-MM-DD' → 'M/D'. 축에 연도를 반복해 적지 않는다. */
function shortDay(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  return m ? `${Number(m[2])}/${Number(m[3])}` : "";
}

export function DateHistogram({ days, question, color, emptyLabel = "만든 티켓이 없습니다", unit = "건" }) {
  const theme = useTheme();
  const track = useTrackColor();
  const rows = Array.isArray(days) ? days.filter((d) => d && typeof d.count === "number") : [];
  const peak = rows.reduce((m, d) => Math.max(m, d.count), 0);
  const total = rows.reduce((sum, d) => sum + d.count, 0);

  if (!rows.length || total === 0) return <ChartNoData label={emptyLabel} />;

  const fill = resolveChartColor(theme, color, 0);
  const busiest = rows.reduce((best, d) => (d.count > best.count ? d : best), rows[0]);
  /* 축 이름을 모든 막대에 적으면 글자가 겹친다. 열흘에 한 번만 적는다 — 그 사이는 막대
     자체가 흐름을 말하고, 정확한 날짜는 각 막대의 `title` 이 든다. */
  const labelEvery = Math.max(1, Math.ceil(rows.length / 9));

  return (
    <Box sx={{ minWidth: 0 }}>
      <ChartQuestion>{question}</ChartQuestion>
      <Box
        /* **이 상자만** 굴러간다. 페이지에 가로 스크롤을 만들지 않는다. */
        sx={{ overflowX: "auto", overflowY: "hidden", pb: 0.5, minWidth: 0 }}
        tabIndex={0}
        role="group"
        aria-label={question || "날짜별 생성량"}
      >
        <Box
          aria-hidden="true"
          sx={{
            display: "flex", alignItems: "flex-end", gap: `${GAP}px`,
            height: PLOT_HEIGHT, minWidth: "100%", width: "max-content",
            borderBottom: 1, borderColor: "divider",
          }}
        >
          {rows.map((d) => {
            const h = peak ? Math.max(d.count > 0 ? 2 : 0, (d.count / peak) * PLOT_HEIGHT) : 0;
            return (
              <Box
                key={d.date}
                title={`${d.date} ${d.count}${unit}`}
                sx={{
                  width: BAR, flexShrink: 0, height: "100%",
                  display: "flex", alignItems: "flex-end",
                }}
              >
                <Box
                  sx={{
                    width: "100%", height: h, minHeight: d.count > 0 ? 2 : 0,
                    bgcolor: d.count > 0 ? fill : track,
                    borderRadius: "2px 2px 0 0",
                    transition: `height ${MOTION.base} ${MOTION.ease}`,
                  }}
                />
              </Box>
            );
          })}
        </Box>
        <Box
          aria-hidden="true"
          sx={{ display: "flex", gap: `${GAP}px`, width: "max-content", minWidth: "100%", mt: 0.5 }}
        >
          {rows.map((d, i) => (
            <Box
              key={d.date}
              sx={{
                width: BAR, flexShrink: 0, textAlign: "center",
                fontSize: FONT_SIZE.micro, color: "text.secondary", whiteSpace: "nowrap",
                overflow: "visible",
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
