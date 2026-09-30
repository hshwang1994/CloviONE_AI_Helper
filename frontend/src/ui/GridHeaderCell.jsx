import React from "react";
import Box from "@mui/material/Box";
import { headerAlignOf } from "./columnTypes.js";
import { HeaderCellContent, headerSortOf, headerTitleOf, JUSTIFY_OF } from "./TableHeaderCell.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "./theme.js";

/* 격자 머리 칸 — 표가 아닌 격자의 머리 줄이 **표 머리와 같은 칸**을 쓴다 (D-497).
 *
 * 작업 보드 백로그는 표가 아니다. 줄을 끌어 순서를 바꾸는 목록이라 `DataTable` 에 담을 수 없다(D-473). 그래서 머리 줄도
 * 따로 그렸고, 거기에는 정렬도 머리 필터도 없었다 — 같은 티켓 열이 티켓 목록 셋에서는 눌리고 백로그에서는 안 눌렸다.
 * 이 부품은 표 머리의 안쪽(`HeaderCellContent`: 이름 · 정렬 단추 · 표지 · 필터 단추 · 필터 창)을 그대로 쓰고 감싸는 칸만
 * 격자의 것으로 바꾼다. 새 조작 모양이 아니다.
 *
 *   role="columnheader"   격자 머리 줄(`role="row"`, 그 위 `role="table"`) 안의 칸이다. 정렬할 수 있는 열이면 `aria-sort`
 *                         가 방향을 말한다 — 표 머리와 같은 판정(`headerSortOf`)이다.
 *   글자                  표 머리 칸과 같은 모양이다(`theme.js::MuiTableCell.head` 의 muted 12 · 600 · 자간 0.03em).
 *                         표 칸은 테마가 그 모양을 주고 격자 칸은 테마 밖이라 여기서 같은 토큰으로 말한다.
 *   정렬(가로)            열 어휘가 정한다(`columnTypes.js::headerAlignOf`) — 제목 열만 왼쪽, 나머지는 가운데다.
 *
 * 폭은 격자 트랙이 정한다. 칸은 `min-width: 0` 이라 트랙보다 넓어지지 않고, 이름 · 표지는 안쪽이 줄바꿈하지 않는다. */
const HEAD_TEXT_SX = {
  color: "text.secondary",
  fontSize: FONT_SIZE.micro,
  fontWeight: FONT_WEIGHT.semibold,
  letterSpacing: "0.03em",
};

export function GridHeaderCell({
  column, sort, onSort, filterValue, onFilter, filterOptions, entityOptions, colRole, sx,
}) {
  const c = column || {};
  const { ariaSort } = headerSortOf(c, sort, onSort);
  const align = headerAlignOf(c);
  return (
    <Box
      role="columnheader"
      aria-sort={ariaSort}
      data-col-role={colRole}
      data-grid-head-cell=""
      title={headerTitleOf(c)}
      sx={{
        ...HEAD_TEXT_SX,
        display: "flex",
        alignItems: "center",
        justifyContent: JUSTIFY_OF[align] || "center",
        minWidth: 0,
        ...sx,
      }}
    >
      <HeaderCellContent
        column={c}
        sort={sort}
        onSort={onSort}
        filterValue={filterValue}
        onFilter={onFilter}
        filterOptions={filterOptions}
        entityOptions={entityOptions}
      />
    </Box>
  );
}
