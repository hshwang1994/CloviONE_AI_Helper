import React from "react";
import Box from "@mui/material/Box";

import { BASELINE_TRACKS, GRID_GAP } from "./density.js";

/* 상세 화면의 폭 계약 — **한 곳**이다 (지시 8 · 14 · 16).
 *
 * ## 무엇이 문제였나
 *
 * 「본문이 왼쪽에 몰리고 오른쪽이 빈다」는 지적은 한 종류가 아니라 둘이었다.
 *
 * **곁열이 있는 화면**(티켓 상세)은 이미 고쳐져 있었다. 옛 격자가 두 트랙 모두 고정
 * 상한(`minmax(0, 78ch) minmax(18rem, 26rem)`)이라 격자가 컨테이너보다 좁게 멈추고
 * 오른쪽을 빈 채로 남겼는데, 두 트랙을 다 `fr` 로 바꿔서 남는 폭이 비율대로 배분된다.
 *
 * **곁열이 없는 화면**(게시글 · 기능 개선 제안)은 안 고쳐져 있었다. 거기서는 왼쪽 쏠림이
 * **세 겹**이었다: 산문 본문이 72ch(약 39rem), 그것을 감싼 열이 68rem, 그 열을 담은 본문
 * 영역이 1920 에서 약 104rem — 셋이 전부 왼쪽에 붙어서 오른쪽 절반이 통째로 비었다.
 *
 * ## 정하는 것
 *
 * 곁열이 없으면 **열이 곧 글줄이고, 그 열이 가운데에 선다.** 겹쳐 거는 상한을 없앤다 —
 * 산문에 다시 72ch 를 걸지 않는다. 열 하나가 글줄 길이를 정하므로 본문 · 반응 · 댓글이
 * 같은 왼쪽 모서리에서 시작하고, 남는 폭은 양쪽에 **똑같이** 남는다. 한쪽에만 남은 여백은
 * 고장으로 읽히고 양쪽에 똑같이 남은 여백은 여백으로 읽힌다.
 *
 * 46rem(기본 루트에서 736px)은 한국어 본문이 실제로 서는 폭이다. 더 넓히면 눈이 다음 줄
 * 첫 글자를 못 찾고, 더 좁히면 댓글의 답글 들여쓰기에서 한 줄에 몇 글자 안 들어간다.
 * 4K 에서는 rem 이 루트 폰트사이즈 레버를 함께 타서 글자와 같은 비율로 넓어진다.
 */
export const DETAIL_SOLO_WIDTH = "min(100%, 46rem)";

/* 곁열이 있을 때의 두 트랙. 둘 다 `fr` 이라 남는 폭이 비율대로 배분된다 — 어느 폭에서도
 * 오른쪽이 안 비고, 곁열에는 300px 하한이 있어 짜부라지지도 않는다.
 *
 * 한 열로 접히는 지점은 `lg`(1200)다. 기준선은 960 이하에서 접는데 이 제품의 셸은
 * 사이드바를 더 빼므로 한 단 위에서 접는 것이 같은 여유가 된다. */
export const DETAIL_GRID = {
  display: "grid", gap: GRID_GAP, alignItems: "start",
  gridTemplateColumns: { xs: "1fr", lg: BASELINE_TRACKS.detail },
};

/** 상세 화면 한 판. `aside` 를 주면 두 열, 안 주면 가운데 선 한 열이다.
 *
 * 좁은 화면에서는 두 열도 한 열로 흐른다. 곁열을 **본문 위**에 두는 화면(티켓)은 그쪽에서
 * `order` 를 정한다 — 담당자·마감을 보려고 본문 전체를 스크롤해 지나갈 이유가 없다. */
export function DetailLayout({ aside, children, sx, ...rest }) {
  if (!aside) {
    return (
      <Box
        data-detail-layout="solo"
        sx={{
          display: "grid", rowGap: 3, minWidth: 0,
          maxWidth: DETAIL_SOLO_WIDTH, marginInline: "auto",
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
 * `PageHeader` 는 자기 폭을 모른다(콘텐츠 영역 전체를 그대로 받는다). 곁열 없는 상세는
 * `DetailLayout` 이 그 아래 `children` 만 46rem 으로 좁혀 가운데 세우는데, 머리글은 그
 * 밖에 남아 폭 전체 왼쪽에 선다 — 2560 에서 제목 x≈0, 본문 x≈820(§5 C1 실측). 「제목 →
 * 본문 → 반응 → 댓글이 같은 왼쪽 모서리에서 시작한다」는 `DetailLayout` 자신의 계약을
 * 머리글이 어기고 있었다.
 *
 * `DetailPage` 는 `header` 와 `children`(그리고 있으면 `aside`)을 **한 상자**로 감싼다 —
 * 곁열이 없으면 그 상자 전체가 46rem 으로 가운데 서서 머리글도 같은 왼쪽 모서리에서
 * 시작한다. 곁열이 있으면(두 열이 이미 컨테이너 전체 폭을 쓴다) 머리글도 그 폭 그대로
 * 두면 되므로 감싸기만 하고 폭은 건드리지 않는다. */
export function DetailPage({ header, aside, children, sx }) {
  if (!aside) {
    return (
      <Box
        data-detail-layout="solo-page"
        sx={{
          display: "grid", rowGap: 3, minWidth: 0,
          maxWidth: DETAIL_SOLO_WIDTH, marginInline: "auto",
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
