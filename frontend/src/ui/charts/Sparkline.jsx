import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { ChartEmpty, finiteValues, useChartColor } from "./base.jsx";

/* 스파크라인 — 값 흐름 하나를 축·눈금 없이 보여주는 작은 꺾은선.
 *
 * points: 숫자 배열 또는 {value} 객체 배열. summary: 그림 옆에 반드시 나가는 글자 요약.
 *
 * 점이 2개 미만이면 그리지 않는다. 점 하나짜리 '추세선'은 없는 추세를 있는 것처럼 보이게 하는
 * 거짓말이라, 그런 경우엔 차라리 숫자만 남긴다(ChartEmpty).
 *
 * preserveAspectRatio="none"으로 컨테이너 폭·높이를 그대로 채우되, 선에는
 * vectorEffect="non-scaling-stroke"를 준다 — 없으면 가로로 늘어난 만큼 선 굵기도 축마다 달라져
 * 세로 구간은 굵고 가로 구간은 가늘게 보인다.
 */
export function Sparkline({
  points, color = "primary", height = "4rem", summary, emptyLabel = "데이터 없음",
}) {
  const stroke = useChartColor(color);
  const values = finiteValues(points, (p) => (typeof p === "number" ? p : p && p.value));

  if (values.length < 2) return <ChartEmpty label={emptyLabel} height={height} />;

  const W = 100;
  const H = 32;
  const PAD = 3;              // 위아래 여백 — 최대·최소점이 테두리에 딱 붙으면 잘린 것처럼 보인다.
  const min = Math.min(...values);
  const max = Math.max(...values);
  const flat = max === min;   // 값이 전부 같으면 (max-min)이 0이라 나눌 수 없다 — 가운데 수평선으로.
  const x = (i) => (i * W) / (values.length - 1);
  const y = (v) => (flat ? H / 2 : H - PAD - ((v - min) / (max - min)) * (H - PAD * 2));
  const line = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(2)} ${y(v).toFixed(2)}`).join(" ");
  // 면적은 선 아래를 옅게 채운다 — 선 하나만 있으면 4K 큰 화면에서 존재감이 사라진다.
  const area = `${line} L${W} ${H} L0 ${H} Z`;
  const last = values[values.length - 1];
  const text = summary != null
    ? summary
    : `최근 ${last}, 최대 ${max}, 최소 ${min} (${values.length}개 구간)`;

  return (
    <Box>
      <Box
        component="svg"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        aria-hidden="true"
        focusable="false"
        /* overflow:visible — 선 굵기의 절반이 viewBox 밖으로 나가 첫/끝 점이 잘리는 걸 막는다. */
        sx={{ display: "block", width: "100%", height, overflow: "visible" }}
      >
        <path d={area} fill={stroke} fillOpacity={0.14} />
        <path
          d={line} fill="none" stroke={stroke} strokeWidth={2.5}
          strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"
        />
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
        {text}
      </Typography>
    </Box>
  );
}

export default Sparkline;
