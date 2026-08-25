import React from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import TableCell from "@mui/material/TableCell";
import FilterListRoundedIcon from "@mui/icons-material/FilterListRounded";
import { FONT_SIZE } from "./theme.js";
import { ColumnFilterPopover } from "./columnFilter.jsx";

/* 이름 자리 — 넘치면 한 줄로 자르고 전체는 `th` 의 `title` 에 남는다. */
const LABEL_SX = { minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

/* DataTable 과 GroupedTickets 가 같이 쓰는 머리글 칸.
 * 정렬 화살표는 onSort 가 있을 때만, 필터 단추는 onFilter 가 있을 때만 그린다.
 * 호출부가 안 넘기면 예전 머리글과 같다. */

export function TableHeaderCell({
  column, sort, onSort, filterValue, onFilter, filterOptions, entityOptions, cellSx, colRole, align,
}) {
  const c = column || {};
  const sortable = !!(c.sortable && onSort);
  const filterable = !!(c.filter && onFilter);
  const active = sortable && sort && sort.key === c.key;
  const dir = active ? sort.dir : null;
  const [anchor, setAnchor] = React.useState(null);
  const filtered = hasFilterValue(filterValue);

  return (
    <TableCell
      scope="col"
      align={align}
      data-col-role={colRole}
      /* 이름이 잘렸을 때 전체를 볼 길 — 본문 칸이 `title` 로 하는 것과 같다.
         도움말이 있으면 그것이 이긴다(그쪽이 더 많은 것을 말한다). */
      title={c.help || (typeof c.label === "string" ? c.label : undefined)}
      aria-sort={sortable ? (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none") : undefined}
      sx={cellSx}
    >
      {/* 🔴 머리글이 자기 칸 밖으로 나가지 않는다 (S19).
          예전에는 `maxWidth: 100%` 만 걸려 있어서, 열이 이름보다 좁아지면 글자가 상자를
          넘어 **옆 머리글 위에 그려졌다**. 「카테고리」·「상태」·「작성자」가 한 자리에서
          겹쳐 읽을 수 없던 것이 그것이다. 이름은 잘리고 정렬 화살표·필터 단추는 안 줄어든다
          — 조작기가 먼저 사라지면 그 열은 정렬도 필터도 할 수 없게 된다. */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.25, minWidth: 0, maxWidth: "100%", overflow: "hidden" }}>
        {sortable ? (
          <Box
            component="button"
            type="button"
            onClick={() => onSort(c.key)}
            sx={{
              font: "inherit", color: "inherit", border: 0, background: "none", p: 0,
              display: "inline-flex", alignItems: "center", gap: 0.5, cursor: "pointer",
              whiteSpace: "nowrap", minWidth: 0, maxWidth: "100%", overflow: "hidden",
              "&:hover": { color: "text.primary" },
              "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
            }}
          >
            <Box component="span" sx={LABEL_SX}>{c.label}</Box>
            <Box component="span" aria-hidden="true" sx={{ flexShrink: 0, fontSize: FONT_SIZE.caption, opacity: active ? 1 : 0.35 }}>
              {dir === "desc" ? "\u2193" : dir === "asc" ? "\u2191" : "\u2195"}
            </Box>
          </Box>
        ) : (c.label ? <Box component="span" sx={LABEL_SX}>{c.label}</Box> : null)}
        {filterable ? (
          <IconButton
            size="small"
            aria-label={`${c.label || "열"} 필터`}
            aria-pressed={filtered}
            onClick={(e) => setAnchor(e.currentTarget)}
            sx={{ flexShrink: 0, color: filtered ? "primary.main" : "text.secondary" }}
          >
            <FilterListRoundedIcon fontSize="inherit" />
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
