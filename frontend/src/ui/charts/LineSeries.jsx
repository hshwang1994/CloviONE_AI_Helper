import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { ChartEmpty, resolveChartColor } from "./base.jsx";

// base.jsx의 finiteValues는 null/undefined/NaN을 배열에서 통째로 들어낸다 — 값만 볼 때는
// 맞는 동작이지만, 여기서는 원래 인덱스(=x좌표)가 살아 있어야 한다. finiteValues를 그대로
// 쓰면 중간에 뚫린 null 하나 때문에 그 뒤 점들이 전부 한 칸씩 당겨져(압축) 그려진다 — 실제
// 시간축 위의 위치가 아니라 "null이 없었다면의 위치"가 나가는 것이다. 원본 배열의 인덱스를
// {i, v} 쌍으로 붙여 들고 다녀서, null 자리는 값 없이 인덱스만 소비하고(=선이 끊긴 채로
// 자기 x좌표를 지키고) 뒤따르는 값은 자기 원래 자리에 그대로 남게 한다.
function indexedFiniteValues(list) {
  const arr = Array.isArray(list) ? list : [];
  const out = [];
  arr.forEach((v, i) => {
    if (typeof v === "number" && Number.isFinite(v)) out.push({ i, v });
  });
  return out;
}

/* 여러 꺾은선을 **같은 눈금** 위에 겹쳐 그린다 — 두 값을 비교하는 그림(번다운의 계획선/잔여선).
 *
 * Sparkline 과 나눈 이유: 스파크라인은 '값 하나의 흐름'이고 축·범례·0선이 없다. 두 선을 각각
 * 스파크라인으로 그리면 **선마다 눈금이 달라져** 위아래 관계가 뒤집혀 보인다 — 비교하려고
 * 만든 그림에서 그건 치명적이다. 여기서는 모든 선이 하나의 min/max 를 공유한다.
 *
 * charts/base.jsx 의 규칙을 그대로 지킨다:
 *   1. 크기는 viewBox + width:100%. 높이는 rem이라 4K 폰트 레버를 따라 함께 커진다.
 *   2. <svg>는 aria-hidden이고 같은 사실을 반드시 옆의 글자로 한 번 더 말한다(범례 + summary).
 *   3. 값이 없으면 빈 그림 대신 '데이터 없음'.
 *   4. <svg> 안에 <text>를 쓰지 않는다(px 단위라 4K에서 혼자 작게 남는다).
 *
 * series: [{ label, points: number[], color? }] — 모든 선의 points 길이가 같아야 한다
 *         (같은 x축 위의 값이라는 뜻이다). labels: x축 눈금 글자(양 끝만 쓴다).
 */
export function LineSeries({
  series, labels, height = "9rem", unit = "", summary, emptyLabel = "데이터 없음",
}) {
  const theme = useTheme();
  const rows = (Array.isArray(series) ? series : [])
    .map((s) => {
      const rawPoints = Array.isArray(s && s.points) ? s.points : [];
      return {
        label: (s && s.label) || "",
        color: resolveChartColor(theme, s && s.color),
        // 원본 배열 길이(null 포함). x축 전체 칸 수는 "값이 있는 점의 개수"가 아니라
        // "슬롯의 개수"로 정해야 null 뒤의 점들이 앞으로 밀리지 않는다.
        slotCount: rawPoints.length,
        points: indexedFiniteValues(rawPoints),
      };
    })
    .filter((s) => s.points.length >= 2);

  // 선 하나짜리(또는 점 하나짜리) '추세'는 없는 추세를 있는 것처럼 보이게 한다.
  if (!rows.length) return <ChartEmpty label={emptyLabel} height={height} />;

  const W = 100;
  const H = 32;
  const PAD = 2;
  const n = Math.max(...rows.map((r) => r.slotCount));
  const peak = Math.max(...rows.flatMap((r) => r.points.map((p) => p.v)), 0);
  // 값이 전부 0이면(할 일이 없는 주) 나눌 수 없다 — 바닥에 붙은 평평한 선으로 그린다.
  const scale = peak > 0 ? (H - PAD * 2) / peak : 0;
  const x = (i) => (n > 1 ? (i * W) / (n - 1) : 0);
  const y = (v) => H - PAD - v * scale;
  // points는 이미 null 슬롯이 빠진 목록이다. 원래 인덱스(p.i)가 바로 앞 점의 인덱스+1이
  // 아니면 그 사이에 null이 있었다는 뜻이다 — 이어 그리지 않고(M) 새로 띄워서 끊긴 선으로
  // 보여 준다. 이어 그리면(L) null을 건너뛴 직선 보간이 되어 "값이 있었다"는 착각을 준다.
  const path = (points) =>
    points
      .map((p, i) => {
        const prev = points[i - 1];
        const gap = i === 0 || !prev || p.i !== prev.i + 1;
        return `${gap ? "M" : "L"}${x(p.i).toFixed(2)} ${y(p.v).toFixed(2)}`;
      })
      .join(" ");

  const ticks = Array.isArray(labels) && labels.length >= 2
    ? [labels[0], labels[labels.length - 1]]
    : null;
  const fmt = (v) => `${Math.round(v * 10) / 10}${unit}`;

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
        {/* 0선 — 번다운은 '0으로 내려가는 것'이 요점이라 바닥이 어디인지 보여야 한다. */}
        <line
          x1="0" y1={H - PAD} x2={W} y2={H - PAD}
          stroke={theme.palette.divider} strokeWidth={1} vectorEffect="non-scaling-stroke"
        />
        {rows.map((r, idx) => (
          <path
            key={r.label || idx}
            d={path(r.points)} fill="none" stroke={r.color} strokeWidth={2.5}
            // 두 번째 선부터는 파선 — 색을 못 보는 사람도 두 선을 구분할 수 있어야 한다.
            strokeDasharray={idx === 0 ? undefined : "4 3"}
            strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"
          />
        ))}
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
                borderTop: idx === 0 ? "0.1875rem solid" : "0.1875rem dashed",
                borderColor: r.color,
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {r.label}: 시작 {fmt(r.points[0].v)} → 끝 {fmt(r.points[r.points.length - 1].v)}
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
