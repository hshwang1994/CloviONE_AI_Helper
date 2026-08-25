import React from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import TableCell from "@mui/material/TableCell";
import FilterListRoundedIcon from "@mui/icons-material/FilterListRounded";
import { FONT_SIZE } from "./theme.js";
import { ColumnFilterPopover } from "./columnFilter.jsx";

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
      title={c.help || undefined}
      aria-sort={sortable ? (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none") : undefined}
      sx={cellSx}
    >
      <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.25, whiteSpace: "nowrap", maxWidth: "100%" }}>
        {sortable ? (
          <Box
            component="button"
            type="button"
            onClick={() => onSort(c.key)}
            sx={{
              font: "inherit", color: "inherit", border: 0, background: "none", p: 0,
              display: "inline-flex", alignItems: "center", gap: 0.5, cursor: "pointer",
              whiteSpace: "nowrap", minWidth: 0,
              "&:hover": { color: "text.primary" },
              "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
            }}
          >
            {c.label}
            <Box component="span" aria-hidden="true" sx={{ fontSize: FONT_SIZE.caption, opacity: active ? 1 : 0.35 }}>
              {dir === "desc" ? "\u2193" : dir === "asc" ? "\u2191" : "\u2195"}
            </Box>
          </Box>
        ) : (c.label || null)}
        {filterable ? (
          <IconButton
            size="small"
            aria-label={`${c.label || "열"} 필터`}
            aria-pressed={filtered}
            onClick={(e) => setAnchor(e.currentTarget)}
            sx={{ color: filtered ? "primary.main" : "text.secondary" }}
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
