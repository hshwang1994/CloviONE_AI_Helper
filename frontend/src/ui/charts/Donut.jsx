import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { ChartEmpty, capSeries, resolveChartColor, useTrackColor } from "./base.jsx";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../theme.js";

/* 도넛 — 전체가 무엇으로 이루어져 있는지(구성비)를 보여준다. 크기 비교는 BarSeries가 낫다.
 *
 * segments: [{ label, value, color? }]. value가 0 이하인 조각은 그리지 않는다(0%짜리 조각은
 * 테두리 한 줄로만 남아 '아주 작은 값'처럼 오해된다).
 *
 * 반지름을 15.91549431(= 100 / 2π)로 잡으면 원둘레가 정확히 100이 되어, strokeDasharray에
 * 백분율을 그대로 써 넣을 수 있다. 각도 계산·arc 경로가 통째로 사라진다.
 *
 * 가운데 합계와 범례는 SVG가 아니라 HTML이다 — SVG <text>는 px 단위라 4K에서 혼자 작게 남는다.
 * 범례가 곧 이 그림의 텍스트 대체물이라서, 도넛을 못 보는 사람도 같은 수치를 그대로 읽는다.
 */
export function Donut({
  segments, size = "9rem", unit = "", centerLabel, emptyLabel = "데이터 없음", thickness = 5,
  total: totalProp, restLabel = "기타",
}) {
  const theme = useTheme();
  const track = useTrackColor();
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

  // size가 도넛 자체의 폭·높이를 정하는 값이라(기본 9rem), 빈 상태도 그대로 넘겨야 카드가
  // 로딩→빈 전환에서 ChartEmpty의 기본값(4rem)으로 훅 줄어들지 않는다 — LineSeries/Sparkline이
  // 자신의 height를 ChartEmpty에 그대로 넘기는 것과 같은 이유다.
  if (!rows.length || total <= 0) return <ChartEmpty label={emptyLabel} height={size} />;

  const R = 15.91549431;
  let acc = 0;
  const arcs = rows.map((s, idx) => {
    const pct = (s.value / total) * 100;
    // dashoffset 25는 12시 방향에서 시작하게 만든다(기본은 3시 방향 — 사람은 시계처럼 위에서 읽는다).
    // 색을 **안 준** 조각은 시리즈 슬롯을 받는다. 예전에는 전부 `primary.main` 하나여서
    // «계획 4건»과 «진행 2건»의 스와치 픽셀이 문자 그대로 같았다 — 구성비 차트가 구성을
    // 못 보여 주던 자리다.
    const arc = { key: s.label, pct, offset: 25 - acc, color: resolveChartColor(theme, s.color, idx) };
    acc += pct;
    return arc;
  });

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: { xs: 2, sm: 3 }, flexWrap: "wrap" }}>
      <Box sx={{ position: "relative", width: size, height: size, flex: "0 0 auto" }}>
        <Box
          component="svg"
          viewBox="0 0 42 42"
          aria-hidden="true"
          focusable="false"
          sx={{ display: "block", width: "100%", height: "100%" }}
        >
          <circle cx="21" cy="21" r={R} fill="none" stroke={track} strokeWidth={thickness} />
          {arcs.map((a) => (
            <circle
              key={a.key} cx="21" cy="21" r={R} fill="none"
              stroke={a.color} strokeWidth={thickness}
              strokeDasharray={`${a.pct.toFixed(2)} ${(100 - a.pct).toFixed(2)}`}
              strokeDashoffset={a.offset.toFixed(2)}
            />
          ))}
        </Box>
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
          <Box component="li" key={s.label} sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
            {/* 색 조각은 장식이다(aria-hidden). 옆의 글자만으로도 뜻이 완전해야 한다(WCAG 1.4.1). */}
            <Box
              aria-hidden="true"
              sx={{ width: "0.75rem", height: "0.75rem", borderRadius: 0.5, flex: "0 0 auto", bgcolor: arcs[i].color }}
            />
            <Typography variant="body2" sx={{ minWidth: 0, ...KO_WORD_BREAK }}>
              {s.label} <Box component="span" sx={{ fontWeight: FONT_WEIGHT.extrabold, fontVariantNumeric: "tabular-nums" }}>{s.value}{unit}</Box>
              <Box component="span" sx={{ color: "text.secondary" }}> ({Math.round((s.value / total) * 100)}%)</Box>
            </Typography>
          </Box>
        ))}
        {/* 모수와 조각 합이 다르면 그 차이를 **말한다**. 링의 빈 호는 트랙 색으로 이미 보이지만,
            그것을 글자로 말하지 않으면 도넛을 못 보는 사람에게는 없는 사실이 된다. */}
        {missing > 0 ? (
          <Box component="li" sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
            <Box
              aria-hidden="true"
              sx={{ width: "0.75rem", height: "0.75rem", borderRadius: 0.5, flex: "0 0 auto", bgcolor: track }}
            />
            <Typography variant="body2" color="text.secondary" sx={{ minWidth: 0, ...KO_WORD_BREAK }}>
              분류 없음 <Box component="span" sx={{ fontWeight: FONT_WEIGHT.extrabold, fontVariantNumeric: "tabular-nums" }}>{missing}{unit}</Box>
              <Box component="span"> ({Math.round((missing / total) * 100)}%)</Box>
            </Typography>
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}

export default Donut;
