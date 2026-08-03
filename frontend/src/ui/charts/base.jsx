import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

/* 차트 공통 바탕 — Sparkline/BarSeries/Donut 세 컴포넌트가 공유하는 색 해석과 '데이터 없음' 표시.
 *
 * 차트 라이브러리를 들이지 않는다. 이 앱이 실제로 그리는 그림은 꺾은선·막대·도넛 셋뿐인데
 * recharts/chart.js류는 초기 번들을 100kB 넘게 불린다(scripts/check_bundle_size.sh의 예산이
 * gzip 280kB다). 손으로 그린 <svg>는 파일당 100줄이 안 되고, 테마 팔레트·다크모드·4K 스케일을
 * 별도 설정 없이 그대로 따라간다.
 *
 * 세 컴포넌트가 전부 지키는 규칙:
 *   1) 크기는 viewBox + width:100%로 컨테이너가 정한다. 높이는 rem이라 styles/root.css의
 *      4K 폰트 레버(16→18→20px)를 타고 같이 커진다 — px로 박으면 3840×2160에서 주변이
 *      다 커지는 동안 차트만 작게 남는다(96개 px 값을 rem으로 옮긴 것과 같은 이유).
 *   2) <svg>는 aria-hidden이고, 같은 사실을 반드시 옆의 '글자'로 한 번 더 말한다. 읽을 수 없는
 *      그림은 숫자보다 나쁘다 — 스크린리더·색각 이상·흑백 인쇄에서 그림만 있으면 정보가 0이 된다.
 *   3) 값이 없으면 빈 그림 대신 '데이터 없음'이라고 쓴다. 0선짜리 빈 차트는 '아직 안 불러왔다'와
 *      '정말 없다'를 구분해 주지 않는다(화면 전체의 EmptyState 규칙과 같은 취지).
 *
 * <svg> 안에는 <text>를 쓰지 않는다. SVG 텍스트는 px 단위라 루트 폰트사이즈 레버를 안 따르고,
 * 4K에서 12px 미만으로 남아 QA의 tiny_text 검사에 걸린다. 글자는 전부 바깥 HTML로 낸다.
 */

/* 키트의 톤 어휘(ok/danger/warn/neutral — Badge·StatCard의 kind와 같은 말)를 MUI 팔레트 이름으로.
 * 화면 쪽 코드가 배지엔 kind="danger", 차트엔 color="error"라고 서로 다른 단어를 쓰게 되면
 * 같은 심각도가 두 이름으로 갈라져 언젠가 어긋난다 — 양쪽 다 받아 준다. */
const TONE_ALIAS = { ok: "success", danger: "error", warn: "warning" };

// 팔레트 이름('primary'·'success'·'danger'…) → 실제 색. 이름이 아니면(예: '#4058BD') 그대로 쓴다.
// 훅이 아니라 순수 함수다 — 세그먼트 개수만큼 반복 호출해야 하는데 훅은 루프에서 못 쓴다.
export function resolveChartColor(theme, color) {
  if (!color) return theme.palette.primary.main;
  // 'neutral'(비활성·해당 없음)은 팔레트에 없다. 라이트/다크 양쪽에서 '꺼져 있음'으로 읽히는
  // 유일한 색이 text.disabled라 여기로 보낸다(고정 회색은 다크에서 배경에 묻힌다).
  if (color === "neutral") return theme.palette.text.disabled;
  const slot = theme.palette[TONE_ALIAS[color] || color];
  return (slot && slot.main) || color;
}

export function useChartColor(color) {
  const theme = useTheme();
  return resolveChartColor(theme, color);
}

// 막대·도넛의 '아직 안 채워진' 부분. divider는 라이트/다크 양쪽에서 배경과 대비가 확보된 유일한
// 중립색이라(팔레트의 grey는 다크에서 배경보다 밝아 트랙이 값처럼 보인다) 트랙 색으로 쓴다.
export function useTrackColor() {
  return useTheme().palette.divider;
}

/* 값이 없을 때의 자리 — 높이를 차트와 비슷하게 잡아 로딩→빈 상태 전환에서 레이아웃이 튀지 않게 한다.
 * 점선 테두리는 '여기 무언가 들어올 자리인데 지금은 비어 있다'는 관습적 신호다. */
export function ChartEmpty({ label = "데이터 없음", height = "4rem" }) {
  return (
    <Box
      sx={{
        display: "grid", placeItems: "center", minHeight: height, px: 2, py: 1,
        border: 1, borderStyle: "dashed", borderColor: "divider", borderRadius: 2,
      }}
    >
      <Typography variant="caption" color="text.secondary">{label}</Typography>
    </Box>
  );
}

// 숫자만 골라낸다. null/undefined/NaN을 0으로 바꾸면 없는 값이 '0'이라는 사실로 둔갑한다 —
// 버리고, 남은 개수가 부족하면 호출부가 빈 상태로 떨어지게 한다.
export function finiteValues(list, pick) {
  const arr = Array.isArray(list) ? list : [];
  const out = [];
  for (const item of arr) {
    const v = pick ? pick(item) : item;
    if (typeof v === "number" && Number.isFinite(v)) out.push(v);
  }
  return out;
}
