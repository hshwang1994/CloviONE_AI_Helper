import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { ChartNoData, ChartQuestion, finiteValues, useChartColor } from "./base.jsx";

/* 스파크라인 — 값 흐름 하나를 축·눈금 없이 보여주는 작은 꺾은선.
 *
 * points: 숫자 배열 또는 {value} 객체 배열. summary: 그림 옆에 반드시 나가는 글자 요약.
 *
 * 점이 2개 미만이면 그리지 않는다. 점 하나짜리 '추세선'은 없는 추세를 있는 것처럼 보이게 하는
 * 거짓말이라, 그런 경우엔 차라리 숫자만 남긴다(ChartNoData).
 *
 * preserveAspectRatio="none"으로 컨테이너 폭·높이를 그대로 채우되, 선에는
 * vectorEffect="non-scaling-stroke"를 준다 — 없으면 가로로 늘어난 만큼 선 굵기도 축마다 달라져
 * 세로 구간은 굵고 가로 구간은 가늘게 보인다.
 */
export function Sparkline({
  points, color, height = "4rem", summary, emptyLabel = "데이터 없음", question,
}) {
  const stroke = useChartColor(color, 0);
  const values = finiteValues(points, (p) => (typeof p === "number" ? p : p && p.value));

  if (values.length < 2) return <ChartNoData label={emptyLabel} />;

  const W = 100;
  const H = 32;
  const PAD = 3;              // 위아래 여백 — 최대·최소점이 테두리에 딱 붙으면 잘린 것처럼 보인다.
  const min = Math.min(...values);
  const max = Math.max(...values);
  /* **바닥은 0 이다.** 예전에는 `min` 을 바닥으로 잡고 면은 viewBox 바닥까지 채웠다 — 두 개를
     같이 하면 칠해진 면적이 어떤 수량에도 비례하지 않는다. 실제로 «실패 7건» 히스토그램이
     1550×56px 붉은 덩어리가 되어 규모를 크게 왜곡했다(/diagnostics). 값이 전부 양수인 지표는
     0 을 바닥으로 잡아야 면적이 값에 비례한다. 음수가 섞이면 그때만 min 을 바닥으로 쓴다. */
  const floor = min < 0 ? min : 0;
  const flat = max === floor;   // 전부 0이거나 전부 같은 값 — (max-floor)가 0이라 나눌 수 없다.
  const x = (i) => (i * W) / (values.length - 1);
  const y = (v) => (flat ? H / 2 : H - PAD - ((v - floor) / (max - floor)) * (H - PAD * 2));
  const line = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(2)} ${y(v).toFixed(2)}`).join(" ");
  /* 면적은 선 아래를 옅게 채운다 — 선 하나만 있으면 4K 큰 화면에서 존재감이 사라진다.
     닫는 자리는 viewBox 바닥이 아니라 **0 선**이다. 바닥까지 채우면 값이 0 인 구간도
     아래 여백만큼 칠해져 «0 이 아닌 것»처럼 보인다. */
  const baseY = (flat ? H / 2 : y(floor)).toFixed(2);
  const area = `${line} L${W} ${baseY} L0 ${baseY} Z`;
  const last = values[values.length - 1];
  const text = summary != null
    ? summary
    : `최근 ${last}, 최대 ${max}, 최소 ${min} (${values.length}개 구간)`;

  return (
    <Box>
      <ChartQuestion>{question}</ChartQuestion>
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
