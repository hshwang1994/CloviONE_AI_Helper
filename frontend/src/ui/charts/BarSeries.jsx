import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { ChartEmpty, resolveChartColor, useTrackColor } from "./base.jsx";
import { FONT_WEIGHT } from "../theme.js";

/* 가로 막대 묶음 — 항목별 크기를 서로 비교하는 용도(담당자별 업무량, 큐 상태 등).
 *
 * items: [{ label, value, color?, note? }]. color는 팔레트 이름(위험한 항목만 'error' 등).
 * max: 기준 최대값. 안 주면 값들의 최대값을 100%로 잡는다. 백분율처럼 상한이 정해진 지표는
 *      반드시 max=100을 넘겨라 — 안 그러면 '가장 큰 값'이 항상 꽉 찬 막대가 되어, 82%와 8%가
 *      똑같이 꽉 찬 막대로 보인다.
 *
 * 배치는 [이름 | 값 | 막대] 순이고, **전체가 격자 하나**다. 두 가지 이유가 있다:
 *   1) 행마다 따로 격자를 만들면 값 칸 폭이 행마다 달라져(1자리 vs 4자리) 막대 시작점이
 *      들쭉날쭉해진다 — 비교하려고 만든 그림에서 기준선이 어긋나면 그리는 의미가 없다.
 *   2) 값을 막대 오른쪽 끝에 두면 화면 오른쪽 아래에 떠 있는 클로비 버튼(앱 셸의 고정 위젯)에
 *      숫자가 가려진다. 실제로 1920 캡처에서 '3건'이 통째로 덮여 있었다. 그림은 가려도 되지만
 *      숫자는 가려지면 안 된다 — 그래서 숫자를 왼쪽(이름 옆)으로 옮겼다.
 *
 * 막대는 aria-hidden이고 값은 항상 숫자로 함께 나간다. 흑백 인쇄·스크린리더에서도 정보량이 그대로다.
 */
/* 색 기본값은 **Brand 시리즈 슬롯 0** 이다(`color` 를 안 주면 `resolveChartColor` 가 준다).
 * 예전 기본값은 `"primary"` — 즉 사용자 Accent 였다. 그러면 청록을 고른 사용자의 화면에서
 * 모든 막대가 청록이 되고, D-179 가 Identity(제품 고정)와 Interaction(사용자 선택)을 갈라
 * 놓은 경계를 차트가 혼자 넘는다. 행별 `color` 는 그대로 남는다 — 그건 «이 항목이 위험하다»
 * 같은 **강조**지 범주 시리즈가 아니다. */
export function BarSeries({
  items, color, max, unit = "", emptyLabel = "데이터 없음", formatValue, relativeNote,
}) {
  const theme = useTheme();
  const track = useTrackColor();
  const rows = (Array.isArray(items) ? items : []).filter(
    (it) => it && typeof it.value === "number" && Number.isFinite(it.value)
  );

  if (!rows.length) return <ChartEmpty label={emptyLabel} />;

  const relative = !(typeof max === "number" && max > 0);
  const peak = relative
    ? Math.max(...rows.map((r) => Math.max(0, r.value)))
    : max;
  const fmt = formatValue || ((v) => String(v));

  /* 기준을 안 주면 «가장 큰 값 = 꽉 찬 막대» 다. 그 사실을 화면에 적지 않으면 82% 와 8% 가
     둘 다 꽉 찬 막대로 보이는 것을 읽는 사람이 알 방법이 없다 — 이 파일 머리 주석이 그
     함정을 경고만 하고 강제하지는 않고 있었다. 이제 말은 부품이 한다. */
  const scaleNote = relative && rows.length > 1 && peak > 0
    ? (relativeNote || `가장 큰 값 ${fmt(peak)}${unit}을 100%로 본 상대 비교입니다.`)
    : null;

  const grid = (
    <Box sx={{
      display: "grid", alignItems: "center", columnGap: 1.5, rowGap: 1.25,
      gridTemplateColumns: {
        xs: "minmax(0, 6rem) auto minmax(0, 1fr)",
        sm: "minmax(0, 9rem) auto minmax(0, 1fr)",
        xxl: "minmax(0, 12rem) auto minmax(0, 1fr)",
      },
    }}>
      {rows.map((r) => {
        // 음수는 이 막대 형태로 표현할 수 없다(왼쪽으로 자랄 곳이 없다) — 폭 0으로 눕히고
        // 값 글자로만 알린다. peak가 0이면(전부 0) 모든 막대가 0폭이다 — 그것도 사실이다.
        const pct = peak > 0 ? Math.max(0, Math.min(100, (r.value / peak) * 100)) : 0;
        const fill = resolveChartColor(theme, r.color || color, 0);
        return (
          <React.Fragment key={r.label}>
            {/* 이름이 길면 줄바꿈 대신 말줄임 — 줄이 늘면 막대들의 세로 리듬이 깨져 비교가 어려워진다.
                전체 이름은 title로 남긴다. */}
            <Typography
              variant="body2" title={r.label}
              sx={{ fontWeight: FONT_WEIGHT.bold, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            >
              {r.label}
            </Typography>
            <Typography
              variant="body2"
              sx={{ fontWeight: FONT_WEIGHT.extrabold, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", textAlign: "right" }}
            >
              {fmt(r.value)}{unit}
            </Typography>
            <Box
              component="svg"
              viewBox="0 0 100 10"
              preserveAspectRatio="none"
              aria-hidden="true"
              focusable="false"
              /* 모서리 둥글기는 svg 요소 자체에 건다 — viewBox 안에서 rx를 주면 폭이 늘어난
                 만큼 가로로만 늘어나 한쪽만 찌그러진 모서리가 된다. */
              sx={{ display: "block", width: "100%", height: "0.75rem", borderRadius: 1, overflow: "hidden" }}
            >
              <rect x="0" y="0" width="100" height="10" fill={track} />
              {pct > 0 ? <rect x="0" y="0" width={pct} height="10" fill={fill} /> : null}
            </Box>
            {r.note ? (
              <Typography variant="caption" color="text.secondary" sx={{ gridColumn: "1 / -1" }}>
                {r.note}
              </Typography>
            ) : null}
          </React.Fragment>
        );
      })}
    </Box>
  );

  if (!scaleNote) return grid;
  return (
    <Box>
      {grid}
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
        {scaleNote}
      </Typography>
    </Box>
  );
}

export default BarSeries;
