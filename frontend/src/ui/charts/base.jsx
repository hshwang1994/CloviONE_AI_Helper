import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import { CHART_DASH } from "../theme.js";

/* 차트 공통 바탕 — Sparkline/BarSeries/Donut 세 컴포넌트가 공유하는 색 해석과 '데이터 없음' 표시.
 *
 * 차트 라이브러리를 들이지 않는다. 이 앱이 실제로 그리는 그림은 꺾은선, 막대, 도넛 셋뿐인데
 * recharts/chart.js류는 초기 번들을 100kB 넘게 불린다(scripts/check_bundle_size.sh의 예산이
 * gzip 280kB다). 손으로 그린 <svg>는 파일당 100줄이 안 되고, 테마 팔레트, 다크모드, 4K 스케일을
 * 별도 설정 없이 그대로 따라간다.
 *
 * ── 2026-08-04: recharts 를 설치하고도 이 셋을 바꾸지 않기로 한 이유 ──────────────
 *
 * 사용자가 외부 라이브러리를 허용했고 recharts 도 설치했다. 그런데 실제로 갈아 끼우려고
 * 세 파일을 다시 읽어 보니, 이 컴포넌트들이 지키는 성질을 recharts 가 **깬다**:
 *   - recharts 는 축 눈금과 라벨을 SVG <text> 로 그린다. 폰트 크기가 px 라 4K 레버를 안 따르고,
 *     바로 아래 규칙(그리고 QA 의 tiny_text 검사)에 정면으로 어긋난다.
 *   - 값을 툴팁(hover)으로 보여 준다. 키보드·스크린리더·흑백 인쇄에서는 아무것도 안 보인다.
 *     지금은 범례가 "계획: 시작 12 → 끝 0" 처럼 **숫자를 글자로** 함께 낸다.
 *   - BarSeries 는 애초에 차트가 아니라 '이름·값·막대' 목록이다. 값을 왼쪽에 둔 것도 이유가
 *     있다(오른쪽 끝에 두면 우하단 고정 클로비 버튼에 숫자가 가려진다 — 1920 캡처에서 실제로
 *     '3건'이 통째로 덮였다). recharts 로 옮기면 그 배치를 다시 만들 수 없다.
 *
 * 그래서 **되는 것을 더 나쁘게 바꾸지 않는다**. recharts 는 지금 형태로 만들기 어려운 그림
 * (산점도, 누적 영역, 축이 정말 필요한 시계열)이 새로 필요할 때 쓴다 — 그때는 위 세 가지를
 * 어떻게 지킬지 함께 정해야 한다.
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

/* 키트의 톤 어휘(ok/danger/warn/neutral — Badge·MetricStrip 의 kind와 같은 말)를 MUI 팔레트 이름으로.
 * 화면 쪽 코드가 배지엔 kind="danger", 차트엔 color="error"라고 서로 다른 단어를 쓰게 되면
 * 같은 심각도가 두 이름으로 갈라져 언젠가 어긋난다 — 양쪽 다 받아 준다. */
const TONE_ALIAS = { ok: "success", danger: "error", warn: "warning" };

/* ── 시리즈 슬롯 — Brand 고정 팔레트 ───────────────────────────────────────
 *
 * `theme.js::CHART_SERIES` 와 `CHART_DASH` 는 W1 이 만들었지만 **소비처가 한 곳도
 * 없었다.** 정의만 있고 화면에 도달하지 않는 토큰은 D-179 가 `palette.brand` 에서
 * 이미 한 번 겪은 실패이고, 그때 세운 가드(`check_brand_tokens.py`)가 chart 에는
 * 없었다. 그 사이 실제로 화면에 나간 색은 아래 `resolveChartColor` 의 옛 기본값
 * `primary.main` — 즉 **사용자 Accent** 였다. 결과가 둘이다:
 *
 *   ① 사용자가 청록을 고르면 제품의 모든 차트가 청록이 된다 (D-179 가 Identity 와
 *      Interaction 을 갈라 놓은 바로 그 경계를 차트가 혼자 넘고 있었다).
 *   ② Dark 에서 `#5A4FCF` 는 plate 대비 **2.90:1** 로 비텍스트 3:1 을 깬다.
 *      `theme-contract.test.js` 는 아무도 안 쓰는 `palette.chart`(6.81:1)를 재고
 *      초록이었다 — 통과하지만 제품과 무관한 표본을 재던 검사다(F-W4-15 와 같은 형태).
 *
 * 그래서 **색을 지정하지 않은 시리즈는 여기서 슬롯을 받는다.** 슬롯은 색 하나가
 * 아니라 색 + 선 스타일 쌍이다: 인접 슬롯의 휘도 분리 최대치가 1.26:1 이라 색만으로는
 * 두 시리즈도 못 나른다(theme.js:320 주석).
 */
export const SERIES_SLOTS = 6;      // 0~4 가 시리즈, 5번이 '기타'
export const SERIES_MAX = 5;        // 이보다 많으면 나머지를 '기타' 한 줄로 묶는다
export const SERIES_REST = SERIES_SLOTS - 1;

/** 시리즈 index → Brand 고정 색. 범위를 넘으면 '기타' 슬롯. */
export function seriesColor(theme, index) {
  const palette = (theme && theme.palette) || {};
  const list = palette.chart;
  const i = Number.isFinite(index) && index >= 0 ? Math.floor(index) : 0;
  if (Array.isArray(list) && list.length) return list[Math.min(i, list.length - 1)];
  /* 이 제품 테마가 아닌 곳(맨 MUI 테마로 렌더하는 시험 등)에서도 색은 나와야 한다.
     Brand → primary 순으로 물러난다. 값이 없다고 렌더가 죽으면 그건 색 문제가 아니다. */
  return (palette.brand && palette.brand.core)
    || (palette.primary && palette.primary.main)
    || "currentColor";
}

/** 시리즈 index → 선 스타일(`strokeDasharray`). 빈 문자열은 solid 다. */
export function seriesDash(index) {
  const i = Number.isFinite(index) && index >= 0 ? Math.floor(index) : 0;
  return CHART_DASH[Math.min(i, CHART_DASH.length - 1)] || "";
}

/* 시리즈가 상한을 넘으면 나머지를 '기타' 하나로 접는다 (PLAN «Data Visualization» ⑥).
 * 6번째부터는 색으로도 선 스타일로도 구분이 안 되므로, 구분되는 척하는 대신 합친다. */
export function capSeries(rows, { label = "기타", merge } = {}) {
  const list = Array.isArray(rows) ? rows : [];
  if (list.length <= SERIES_MAX) return list;
  const head = list.slice(0, SERIES_MAX);
  const tail = list.slice(SERIES_MAX);
  return head.concat([merge ? merge(tail, label) : { ...tail[0], label }]);
}

// 팔레트 이름('primary'·'success'·'danger'…) → 실제 색. 이름이 아니면(예: '#4058BD') 그대로 쓴다.
// 훅이 아니라 순수 함수다 — 세그먼트 개수만큼 반복 호출해야 하는데 훅은 루프에서 못 쓴다.
//
// `color` 를 **안 주면 시리즈 슬롯**이다(`index` 가 그 슬롯 번호). 옛 기본값이었던
// `primary.main`(사용자 Accent)으로는 절대 되돌아가지 않는다 — 위 주석 참조.
export function resolveChartColor(theme, color, index) {
  if (!color) return seriesColor(theme, index);
  /* `"brand"` — 톤 이름 어휘를 쓰는 호출부(DevReport 의 상태 5색 같은 자리)가 사용자 Accent
     대신 **제품 고정색**을 지목할 수 있어야 한다. PLAN §Data Visualization 이 이 이름을
     그대로 쓴다("`Home.jsx:137`의 `남음 → "primary"` 를 `"brand"` 로 바꾼다"). */
  if (color === "brand") return seriesColor(theme, 0);
  // 'neutral'(비활성·해당 없음)은 팔레트에 없다. 라이트/다크 양쪽에서 '꺼져 있음'으로 읽히는
  // 유일한 색이 text.disabled라 여기로 보낸다(고정 회색은 다크에서 배경에 묻힌다).
  if (color === "neutral") return theme.palette.text.disabled;
  const slot = theme.palette[TONE_ALIAS[color] || color];
  // palette 슬롯이 {main,...} 객체가 아니라 문자열 그 자체인 경우가 있다(cyan은
  // theme.palette.cyan = "#58A9C4"/"#72C0D7"처럼 직접 색 문자열이다 - primary·success처럼
  // .main을 감싸지 않는다). slot.main만 보면 이 경우 undefined가 되어 마지막 폴백인 원래
  // color 인자("cyan"이라는 글자 그대로)로 새 버린다. 우연히 CSS 네임드 컬러와 철자가 같아
  // 화면에는 뭔가 칠해지지만, 라이트/다크에서 값이 다른 테마 cyan 대신 두 모드에서 항상 같은
  // 고정색이 나가 다크 모드에서 대비가 깨진다.
  if (typeof slot === "string") return slot;
  return (slot && slot.main) || color;
}

export function useChartColor(color, index) {
  const theme = useTheme();
  return resolveChartColor(theme, color, index);
}

// 막대·도넛의 '아직 안 채워진' 부분. divider는 라이트/다크 양쪽에서 배경과 대비가 확보된 유일한
// 중립색이라(팔레트의 grey는 다크에서 배경보다 밝아 트랙이 값처럼 보인다) 트랙 색으로 쓴다.
export function useTrackColor() {
  return useTheme().palette.divider;
}

/* ── 이 그림이 답하는 업무 질문 (W6) ──────────────────────────────────────
 *
 * 차트 소비처 열셋 가운데 «왜 이 그림이 여기 있나» 에 답할 수 있는 자리가 절반이 안 됐다.
 * 제목(«상태 구성»)은 **무엇을 그렸는지**를 말하지 그림이 답하는 질문을 말하지 않는다 —
 * 그래서 그림을 보고 무슨 판단을 해야 하는지가 화면에 없었다(지시 62: 행동으로 이어지지
 * 않는 지표는 두지 않는다).
 *
 * `question` 은 그 한 문장이고 **그림 바로 위**에 놓인다. 새로 문장을 늘리는 것이 아니라,
 * 화면들이 이미 그림 옆에 흩어 놓았던 설명 문장을 이 자리로 모은 것이다.
 * 선언이 빠진 소비처는 `charts/chart-question.test.js` 가 소스에서 직접 센다 — 부품이
 * 런타임에 던지면 그림 하나 때문에 화면이 죽는다.
 */
export function ChartQuestion({ children }) {
  if (!children) return null;
  return (
    <Typography
      variant="caption" color="text.secondary" data-chart-question="declared"
      sx={{ display: "block", mb: 1 }}
    >
      {children}
    </Typography>
  );
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
