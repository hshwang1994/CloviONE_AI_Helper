import React from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import TableCell from "@mui/material/TableCell";
import ArrowDownwardRoundedIcon from "@mui/icons-material/ArrowDownwardRounded";
import ArrowUpwardRoundedIcon from "@mui/icons-material/ArrowUpwardRounded";
import FilterListRoundedIcon from "@mui/icons-material/FilterListRounded";
import HeightRoundedIcon from "@mui/icons-material/HeightRounded";
import { CONTROL, ICON, RADIUS, remPx } from "./theme.js";
import { headerAlignOf } from "./columnTypes.js";
import { ColumnFilterPopover } from "./columnFilter.jsx";

/* 이름 자리 — **잘리지 않는다** (A4 재검수). 예전엔 `min-width:0` + `overflow:hidden` 으로
 * 좁으면 조용히 자르고 `title` 로만 전체를 남겼는데, 실측(「예상 WD」 client 40 / scroll 49)은
 * 그 잘림이 실제로 일어난다는 것을 보여줬다 — 이름은 짧은 고정 어휘라 접어서 지킬 이유가
 * 없다. `table-layout:auto` 표에서 이 칸이 자기 내용 폭을 그대로 요구하면(`minWidth:0` 을
 * 안 주면) 그 요구가 열 폭 계산에 들어가 열 자체가 넓어진다 — 잘리는 대신 칸이 넓어지는
 * 쪽으로 옮긴다. */
const LABEL_SX = { whiteSpace: "nowrap", lineHeight: 1.5 };

/* ── 머리 칸 표지 — 정렬 · 필터 (핸드오프 README §4 · 공통 컴포넌트 시안 데이터 표 · UI 3차 조합 계약 C-3) ────
 *
 * 표지는 **이름 옆 4px 에 붙는 글리프**다. 크기는 글 옆 표지 슬롯(`ICON.mark`)이고, 활성 열은 이름이 잉크로 서고 표지가
 * 강조색(`primary.dark`)이다. 정렬 표지는 정렬할 수 있는 열에 **항상** 서고(↕ → ↑ / ↓), 필터 표지는 조건이 걸릴 수 있는
 * 열에만 선다.
 *
 * 예전에는 정렬 표지가 글자 화살표(「↕」, 35% 불투명)였고 필터는 30px 아이콘 단추라, 필터 글리프가 칸 안에서 이름과
 * 떨어져 따로 선 조작기로 읽혔다(단추 상자 가운데에 선 글리프가 이름에서 12px 밖). 지금 필터 단추는 **글리프를 감싸는
 * 폭**(표지 + 4)이고 누르는 높이만 30 이다 — 손가락 목표는 테마의 `::after` 가 상자 밖에서 넓힌다(WCAG 2.2 Target Size).
 *
 * 🔴 머리글 칸의 두 조작기는 **같은 높이**로 선다 (S22 · `control_baseline_mismatch`). 높이는
 * `CONTROL.tableCellDense`(30, 작은 단추와 같은 값)다. 테마가 `MuiIconButton.root` 에 34 를 걸어 두었으므로 필터 단추는
 * `height` 로 못 박는다. */
const HEADER_CONTROL_SX = { minHeight: remPx(CONTROL.tableCellDense) };
const GLYPH_SX = { fontSize: remPx(ICON.mark), flexShrink: 0, display: "block" };
const FILTER_BUTTON_SX = {
  minHeight: remPx(CONTROL.tableCellDense),
  height: remPx(CONTROL.tableCellDense),
  minWidth: remPx(ICON.mark + 4),
  width: remPx(ICON.mark + 4),
  p: 0,
  borderRadius: `${RADIUS.sm}px`,
};

/* 정렬 표지. 방향이 없으면(정렬할 수 있지만 지금 그 축이 아니면) ↕ 이고 흐린 잉크, 지금 축이면 방향 화살표에 강조색이다.
   글리프는 뜻을 말하지 않는다 — 방향은 칸의 `aria-sort` 가 말한다(`aria-hidden`). */
function SortGlyph({ dir, active }) {
  const Glyph = dir === "desc" ? ArrowDownwardRoundedIcon : dir === "asc" ? ArrowUpwardRoundedIcon : HeightRoundedIcon;
  return (
    <Glyph
      aria-hidden="true"
      data-head-glyph="sort"
      sx={{ ...GLYPH_SX, color: active ? "primary.dark" : "text.secondary" }}
    />
  );
}

/* DataTable 과 GroupedTickets 가 같이 쓰는 머리글 칸.
 * 정렬 표지는 onSort 가 있을 때만, 필터 단추는 onFilter 가 있을 때만 그린다.
 * 호출부가 안 넘기면 예전 머리글과 같다.
 *
 * 칸의 **안쪽**(이름 · 정렬 단추 · 정렬 표지 · 필터 단추 · 필터 팝오버)은 `HeaderCellContent` 한 벌이다. 표 머리는
 * 그것을 `TableCell` 로 감싸고(`TableHeaderCell`), 표가 아닌 격자 머리는 `role="columnheader"` 상자로 감싼다
 * (`GridHeaderCell.jsx` — 끌어 옮기는 작업 보드 백로그, D-497). 머리 칸의 조작을 두 벌로 만들지 않는다 — 격자만
 * 다른 정렬 단추 · 다른 필터 창을 가지면 같은 열 이름이 화면마다 다른 조작기로 읽힌다. */

/* 🔴 머리글은 **이름+조작기를 한 덩어리로** 칸 가운데에 둔다 (지시 6 · 13).
 *
 * 예전 `1fr auto 1fr` 격자는 이름의 중심을 조작기와 따로 지키려다 좁은 숫자 열에서
 * 옆 칸 위로 글자가 겹쳤다. `table-layout:fixed` 에서 「예상 WD」 칸은 4rem 인데, 왼쪽
 * 저울추와 오른쪽 화살표가 같은 폭을 요구하면 이름 자리가 사라져 두 줄이 한 줄 위에
 * 그려진다. 이름과 화살표를 한 flex 로 묶으면 칸이 모자랄 때도 한 덩어리로 잘리고,
 * 옆 머리글과 겹치지 않는다. 몸통 칸의 정렬은 여전히 안 받는다.
 *
 * 간격: 정렬 단추 안 이름 → 표지 4, 줄 안 이름(또는 정렬 단추) → 필터 단추 2 + 단추 안쪽 2 = 표지 사이 4. */
/* 열의 축(left · center · right) → 한 덩어리(이름 + 조작기)를 세우는 자리. 몸통과 같은 축이다(D-506). */
export const JUSTIFY_OF = { left: "flex-start", center: "center", right: "flex-end" };

const HEADER_ROW_SX = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 0.25,
  width: "100%",
  minWidth: 0,
  whiteSpace: "nowrap",
};

/** 머리 칸 하나의 정렬 상태 — 표 머리와 격자 머리가 같은 판정으로 `aria-sort` 를 단다. */
export function headerSortOf(column, sort, onSort) {
  const c = column || {};
  const sortable = !!(c.sortable && onSort);
  const active = sortable && !!sort && sort.key === c.key;
  const dir = active ? sort.dir : null;
  return {
    sortable,
    active,
    dir,
    ariaSort: sortable ? (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none") : undefined,
  };
}

/** 머리 칸의 `title` — 이름이 잘렸을 때 전체를 볼 길이다. 본문 칸이 `title` 로 하는 것과 같고, 도움말이 있으면 그것이
 *  이긴다(그쪽이 더 많은 것을 말한다). */
export function headerTitleOf(column) {
  const c = column || {};
  return c.help || (typeof c.label === "string" ? c.label : undefined);
}

/* 머리 칸의 안쪽 한 벌 — 이름 · 정렬 단추 · 정렬 표지 · 필터 단추 · 필터 팝오버. 감싸는 칸(`TableCell` · 격자 칸)은
   부르는 쪽이 그리고, 칸의 `aria-sort` · `title` 은 `headerSortOf` · `headerTitleOf` 가 같은 값을 준다. */
export function HeaderCellContent({
  column, sort, onSort, filterValue, onFilter, filterOptions, entityOptions,
}) {
  const c = column || {};
  const { sortable, active, dir } = headerSortOf(c, sort, onSort);
  const filterable = !!(c.filter && onFilter);
  const [anchor, setAnchor] = React.useState(null);
  const filtered = hasFilterValue(filterValue);
  const align = headerAlignOf(c);

  return (
    <>
      {/* 🔴 머리글이 잘리지 않는다 (S19 → A4 재검수로 계약이 바뀌었다).
          예전 해법은 `overflow:hidden` 으로 이름을 자르는 것이었다 — 그런데 그 잘림 자체가
          실측된 결함이 됐다(「예상 WD」 client 40 / scroll 49). 지금은 이름·버튼 모두
          `min-width` 를 스스로 0으로 낮추지 않는다 — `table-layout:auto` 표에서는 칸이
          자기 내용 폭을 그대로 요구하면 그 요구가 열 폭 계산에 들어가 **열 자체가 넓어진다**
          (박스가 내용보다 좁아지는 그 순간이 없으니, S19 가 겪은 "박스는 좁은데 글자만
          삐져나온다"도 다시 생기지 않는다). 정렬 표지·필터 단추는 여전히 `flexShrink:0`
          로 따로 보호된다. */}
      <Box sx={{ ...HEADER_ROW_SX, justifyContent: JUSTIFY_OF[align] || "center" }}>
        {sortable ? (
          <Box
            component="button"
            type="button"
            onClick={() => onSort(c.key)}
            sx={{
              font: "inherit", color: active ? "text.primary" : "inherit", border: 0, background: "none", p: 0,
              display: "inline-flex", alignItems: "center", gap: 0.5, cursor: "pointer",
              whiteSpace: "nowrap", flexShrink: 0,
              ...HEADER_CONTROL_SX,
              "&:hover": { color: "text.primary" },
              "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
            }}
          >
            <Box component="span" sx={LABEL_SX}>{c.label}</Box>
            <SortGlyph dir={dir} active={active} />
          </Box>
        ) : (c.label ? <Box component="span" sx={LABEL_SX}>{c.label}</Box> : null)}
        {filterable ? (
          <IconButton
            size="small"
            aria-label={`${c.label || "열"} 필터`}
            aria-pressed={filtered}
            onClick={(e) => setAnchor(e.currentTarget)}
            sx={{ flexShrink: 0, color: filtered ? "primary.dark" : "text.secondary", ...FILTER_BUTTON_SX }}
          >
            <FilterListRoundedIcon data-head-glyph="filter" sx={GLYPH_SX} />
          </IconButton>
        ) : null}
      </Box>
      {filterable ? (
        <ColumnFilterPopover
          open={!!anchor}
          anchorEl={anchor}
          onClose={() => setAnchor(null)}
          column={c}
          value={filterValue}
          onChange={(next) => onFilter(c.filter.field || c.key, next)}
          options={filterOptions}
          entityOptions={entityOptions}
        />
      ) : null}
    </>
  );
}

export function TableHeaderCell({
  column, sort, onSort, filterValue, onFilter, filterOptions, entityOptions, cellSx, colRole,
}) {
  const c = column || {};
  const { ariaSort } = headerSortOf(c, sort, onSort);

  return (
    <TableCell
      scope="col"
      align={headerAlignOf(c)}
      data-col-role={colRole}
      title={headerTitleOf(c)}
      aria-sort={ariaSort}
      sx={cellSx}
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
    </TableCell>
  );
}

/** 같은 열을 다시 누르면 방향을 뒤집고, 다른 열이면 그 열의 기본 방향으로 시작한다. */
export function toggleSort(sort, key, defaultDir = "asc") {
  if (sort && sort.key === key) {
    return { key, dir: sort.dir === "asc" ? "desc" : "asc" };
  }
  return { key, dir: defaultDir };
}

function hasFilterValue(value) {
  if (value == null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") {
    return Object.values(value).some((v) => v != null && v !== "");
  }
  return true;
}
