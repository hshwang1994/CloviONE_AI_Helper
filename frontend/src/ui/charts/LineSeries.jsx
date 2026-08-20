import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { ChartEmpty, capSeries, resolveChartColor, seriesDash } from "./base.jsx";
import { FONT_WEIGHT } from "../theme.js";

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
 * ── W5: PLAN «Data Visualization» 의 필수 업그레이드를 실제로 그린다 ──────────
 * 이전 판은 0선 하나뿐이라 "이 점이 대략 얼마인가"를 눈으로 읽을 수 없었고, 두 선의 색이
 * 사용자 Accent 와 상태색이라 **같은 갈색이 다른 화면에서 다른 뜻**이었다. 바뀐 것 넷:
 *   ① 눈금선 — `background.sunken` 수평선 3개 + 0선. 눈금 **글자는 SVG 밖 HTML** 이라
 *      4K 폰트 레버를 그대로 탄다(SVG <text> 였다면 12px 밑으로 떨어진다).
 *   ② 1번 시리즈 아래 14% alpha 영역 채움 — 선 하나는 넓은 화면에서 존재감이 사라진다.
 *   ③ 시리즈가 3개 이하면 **끝점 직접 라벨**(HTML 절대배치). 범례는 지우지 않는다 —
 *      직접 라벨은 눈이 빠른 경로고 범례는 스크린리더·흑백 인쇄의 유일한 경로다.
 *   ④ 단위는 y축 머리에 **한 번만**. 범례 안에서 값마다 반복하지 않는다.
 *   ⑤ 시리즈 상한 5(`capSeries`) — 6번째부터는 색으로도 선 스타일로도 구분되지 않는다.
 * 색은 `resolveChartColor(theme, s.color, idx)` 가 준다: 색을 안 주면 Brand 고정 슬롯이다.
 *
 * **키보드 도달(PLAN ④의 `<circle tabindex>`)은 넣지 않는다.** 그 조항은 값을 hover
 * 툴팁으로만 주는 라이브러리 차트를 전제로 쓰였는데 이 부품은 애초에 툴팁이 없고 모든 값을
 * 글자로 낸다(범례 + 직접 라벨 + summary). 점마다 탭 정지를 만들면 번다운 하나가 탭 16번을
 * 먹으면서 새 정보는 0이다 — 접근성 개선이 아니라 탭 소음이다. 근거는 D-186 에 적었다.
 *
 * series: [{ label, points: number[], color? }] — 모든 선의 points 길이가 같아야 한다
 *         (같은 x축 위의 값이라는 뜻이다). labels: x축 눈금 글자(양 끝만 쓴다).
 */
export function LineSeries({
  series, labels, height = "9rem", unit = "", summary, emptyLabel = "데이터 없음",
}) {
  const theme = useTheme();
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
        dash: seriesDash(idx),
        slot: idx,
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

  /* 1번 시리즈 아래 채움. 선이 끊긴 구간까지 이어 칠하면 없는 값을 있는 것처럼 만든다 —
     끊기지 않은 **연속 구간마다** 따로 닫는다. */
  const areaPath = (points) => {
    const runs = [];
    let cur = [];
    points.forEach((p, i) => {
      const prev = points[i - 1];
      if (i === 0 || !prev || p.i !== prev.i + 1) { if (cur.length > 1) runs.push(cur); cur = [p]; }
      else cur.push(p);
    });
    if (cur.length > 1) runs.push(cur);
    return runs
      .map((run) => {
        const head = run.map((p, i) => `${i ? "L" : "M"}${x(p.i).toFixed(2)} ${y(p.v).toFixed(2)}`).join(" ");
        const x0 = x(run[0].i).toFixed(2);
        const x1 = x(run[run.length - 1].i).toFixed(2);
        return `${head} L${x1} ${(H - PAD).toFixed(2)} L${x0} ${(H - PAD).toFixed(2)} Z`;
      })
      .join(" ");
  };

  const ticks = Array.isArray(labels) && labels.length >= 2
    ? [labels[0], labels[labels.length - 1]]
    : null;
  const round1 = (v) => Math.round(v * 10) / 10;
  const fmt = (v) => `${round1(v)}`;

  /* 눈금 — 0 · 1/2 · 1(최댓값). 셋이면 "대략 얼마인가"에 답하고, 그보다 촘촘하면
     한글 라벨이 서로 붙는다. 값이 전부 0인 주에는 눈금이 정보가 아니라 소음이라 뺀다. */
  const gridValues = peak > 0 ? [peak, peak / 2, 0] : [];
  const topPct = (v) => (y(v) / H) * 100;

  /* 끝점 직접 라벨은 시리즈 3개 이하일 때만 — 그 이상이면 라벨끼리 겹쳐 서로를 가린다. */
  const direct = rows.length <= 3
    ? rows.map((r) => {
      const last = r.points[r.points.length - 1];
      return { label: r.label, color: r.color, value: last.v, top: topPct(last.v) };
    })
    : [];

  return (
    <Box>
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
          <Box
            component="svg"
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            aria-hidden="true"
            focusable="false"
            /* overflow:visible — 선 굵기의 절반이 viewBox 밖으로 나가 첫/끝 점이 잘리는 걸 막는다. */
            sx={{ display: "block", width: "100%", height, overflow: "visible" }}
          >
            {/* 눈금선. 0선은 divider(번다운은 '0으로 내려가는 것'이 요점이라 바닥이 또렷해야
                한다), 중간선은 함몰면 색이라 데이터와 경쟁하지 않는다. */}
            {gridValues.map((v, i) => (
              <line
                key={i}
                x1="0" y1={y(v).toFixed(2)} x2={W} y2={y(v).toFixed(2)}
                stroke={i === gridValues.length - 1 ? theme.palette.divider : theme.palette.background.sunken}
                strokeWidth={1} vectorEffect="non-scaling-stroke"
              />
            ))}
            {peak <= 0 ? (
              <line
                x1="0" y1={(H - PAD).toFixed(2)} x2={W} y2={(H - PAD).toFixed(2)}
                stroke={theme.palette.divider} strokeWidth={1} vectorEffect="non-scaling-stroke"
              />
            ) : null}
            {/* 1번 시리즈만 채운다 — 둘 이상 채우면 겹친 자리의 색이 세 번째 색처럼 읽힌다. */}
            {rows[0] ? (
              /* `stroke` 속성을 아예 걸지 않는다 — 채움 전용 path 다. `stroke="none"` 으로
                 적으면 `path[stroke]` 로 선을 찾는 시험·프로브가 이 면을 첫 선으로 집는다. */
              <path d={areaPath(rows[0].points)} fill={rows[0].color} fillOpacity={0.14} />
            ) : null}
            {rows.map((r, idx) => (
              <path
                key={r.label || idx}
                d={path(r.points)} fill="none" stroke={r.color} strokeWidth={2.5}
                // 색만으로는 시리즈를 못 나른다(인접 슬롯 휘도 분리 최대 1.26:1) — 선 스타일이
                // 장식이 아니라 필수다. 슬롯 번호가 색과 선 스타일을 함께 정한다.
                strokeDasharray={r.dash || undefined}
                strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"
              />
            ))}
          </Box>
          {/* 끝점 직접 라벨 — 눈이 범례를 거치지 않고 선에서 바로 값을 읽는다. */}
          {direct.map((d, i) => (
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
                borderTop: r.dash ? "0.1875rem dashed" : "0.1875rem solid",
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
