import React from "react";
import Box from "@mui/material/Box";

import { BASELINE_TRACKS, GRID_GAP } from "./density.js";

/* 상세 화면의 폭 계약 — **한 곳**이다 (지시 8 · 14 · 16 · 63).
 *
 * ## 무엇이 문제였나
 *
 * 「본문이 왼쪽에 몰리고 오른쪽이 빈다」는 지적은 한 종류가 아니라 둘이었다.
 *
 * **곁열이 있는 화면**(티켓 상세)은 두 트랙을 `fr` 로 둬서 남는 폭이 비율대로 배분된다.
 *
 * **곁열이 없는 화면**(게시글 · 프로젝트 개요)은 열 전체를 46rem 기둥으로 줄이고 가운데
 * (또는 왼쪽)에 세웠다. 콘텐츠 영역은 넓은데 카드·제목·댓글이 그 기둥 안에만 서서
 * 오른쪽이 통째로 비었다. 지시 63 은 「가운데 좁은 기둥을 만들지 않는다」이다.
 *
 * ## 정하는 것
 *
 * 상세 화면의 **상자**는 콘텐츠 영역 전폭이다. 곁열이 있으면 두 `fr` 트랙이 그 폭을 나누고,
 * 없으면 한 열이 그 폭을 그대로 쓴다. 산문 줄 길이는 그 열이 정한다 — 상자 안에 72ch 를
 * 다시 걸면 열은 넓은데 글만 왼쪽에 붙는다.
 *
 * `DETAIL_SOLO_WIDTH` 는 「혼자 서는 한 열」의 폭이고, 지금은 전폭이다. 옛 46rem 기둥을
 * 부르는 자리가 남아 있지 않게 이름을 유지한다.
 */
export const DETAIL_SOLO_WIDTH = "100%";

/* 곁열이 있을 때의 두 트랙. 둘 다 `fr` 이라 남는 폭이 비율대로 배분된다 — 어느 폭에서도
 * 오른쪽이 안 비고, 곁열에는 300px 하한이 있어 짜부라지지도 않는다.
 *
 * 한 열로 접히는 지점은 `lg`(1200)다. 기준선은 960 이하에서 접는데 이 제품의 셸은
 * 사이드바를 더 빼므로 한 단 위에서 접는 것이 같은 여유가 된다. */
export const DETAIL_GRID = {
  display: "grid", gap: GRID_GAP, alignItems: "start",
  gridTemplateColumns: { xs: "1fr", lg: BASELINE_TRACKS.detail },
};

/** 상세 화면 한 판. `aside` 를 주면 두 열, 안 주면 전폭 한 열이다.
 *
 * 좁은 화면에서는 두 열도 한 열로 흐른다. 곁열을 **본문 위**에 두는 화면(티켓)은 그쪽에서
 * `order` 를 정한다 — 담당자·마감을 보려고 본문 전체를 스크롤해 지나갈 이유가 없다. */
export function DetailLayout({ aside, children, sx, ...rest }) {
  if (!aside) {
    return (
      <Box
        data-detail-layout="solo"
        sx={{
          display: "grid", rowGap: 3, minWidth: 0, width: "100%",
          maxWidth: DETAIL_SOLO_WIDTH,
          ...sx,
        }}
        {...rest}
      >
        {children}
      </Box>
    );
  }
  return (
    <Box data-detail-layout="split" sx={{ ...DETAIL_GRID, ...sx }} {...rest}>
      {children}
      {aside}
    </Box>
  );
}

/** 상세 화면 한 판 — **머리글까지 같은 축**에 세운다 (C1 재검수).
 *
 * `PageHeader` 는 자기 폭을 모른다(콘텐츠 영역 전체를 그대로 받는다). 머리글과 본문을
 * **한 상자**로 감싸 같은 왼쪽 모서리에서 시작하게 한다. 상자는 전폭이라 제목만 넓고
 * 본문만 좁은 기둥이 되지 않는다. */
export function DetailPage({ header, aside, children, sx }) {
  if (!aside) {
    return (
      <Box
        data-detail-layout="solo-page"
        sx={{
          display: "grid", rowGap: 3, minWidth: 0, width: "100%",
          maxWidth: DETAIL_SOLO_WIDTH,
          ...sx,
        }}
      >
        {header}
        {children}
      </Box>
    );
  }
  return (
    <Box data-detail-layout="split-page" sx={{ display: "grid", rowGap: 3, minWidth: 0, ...sx }}>
      {header}
      <DetailLayout aside={aside}>{children}</DetailLayout>
    </Box>
  );
}
