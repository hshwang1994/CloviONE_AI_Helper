import React from "react";
import Box from "@mui/material/Box";

/* 필터 줄 격자 — 티켓 필터 바(screens/TicketFilterBar.jsx)와 설정 주도 목록 화면
 * (screens/DataScreen.jsx)이 각자 독립적으로 복제해 오던 그리드를 하나로 모은 것.
 *
 * ## 왜 하나로 모았나
 *
 * 두 화면이 글자 하나 다르지 않은 `gridTemplateColumns` 를 손으로 복사해 갖고 있었다.
 * 같은 뜻의 격자가 두 벌이면 한쪽만 고쳐지는 날이 오고, 그때 증상은 "이 화면 필터 줄만
 * 다르게 줄바꿈된다" 라서 원인이 안 보인다.
 *
 * ## 왜 트랙에 상한을 두나
 *
 * 예전 트랙은 `repeat(auto-fit, minmax(11rem, 1fr))` — 상한이 없는 `1fr` 이었다. auto-fit
 * 은 빈 트랙을 접어 실제 항목 수만큼만 남기므로, 필터가 둘뿐이면 그 두 트랙이 카드 폭을
 * 절반씩 나눠 가져 쓸데없이 넓어졌다. 게다가 sm(11rem)과 xxl(13rem)에서 최소 폭이 달라
 * 브레이크포인트마다 맞는 트랙 수가 바뀌면서 줄바꿈이 예측 불가능했다.
 *
 * 트랙마다 최대 폭을 캡핑하면(16rem/18rem) 필터가 적을 때는 그 폭에서 멈추고 남는
 * 공간은 빈 채로 남으며, 필터가 많을 때는(예: 감사 로그처럼 6개 넘는 화면) 지금처럼
 * 다음 트랙 → 다음 줄로 자연스럽게 넘어간다 — auto-fit 의 반응형 줄바꿈 동작 자체는
 * 그대로 유지한다. */
export const FILTER_GRID_SX = {
  display: "grid",
  gap: 1.5,
  alignItems: "center",
  gridTemplateColumns: {
    xs: "1fr",
    sm: "repeat(auto-fit, minmax(11rem, 16rem))",
    xxl: "repeat(auto-fit, minmax(13rem, 18rem))",
  },
};

/** 필터 줄 격자. children 은 각 필터 입력(검색창·select·자유 입력 등)과 '필터 지우기' 버튼. */
export function FilterBarGrid({ sx, ...props }) {
  return <Box sx={sx ? { ...FILTER_GRID_SX, ...sx } : FILTER_GRID_SX} {...props} />;
}
