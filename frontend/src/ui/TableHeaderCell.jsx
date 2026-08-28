import React from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import TableCell from "@mui/material/TableCell";
import FilterListRoundedIcon from "@mui/icons-material/FilterListRounded";
import { CONTROL, FONT_SIZE, remPx } from "./theme.js";
import { HEADER_ALIGN } from "./columnTypes.js";
import { ColumnFilterPopover } from "./columnFilter.jsx";

/* 이름 자리 — **잘리지 않는다** (A4 재검수). 예전엔 `min-width:0` + `overflow:hidden` 으로
 * 좁으면 조용히 자르고 `title` 로만 전체를 남겼는데, 실측(「예상 WD」 client 40 / scroll 49)은
 * 그 잘림이 실제로 일어난다는 것을 보여줬다 — 이름은 짧은 고정 어휘라 접어서 지킬 이유가
 * 없다. `table-layout:auto` 표에서 이 칸이 자기 내용 폭을 그대로 요구하면(`minWidth:0` 을
 * 안 주면) 그 요구가 열 폭 계산에 들어가 열 자체가 넓어진다 — 잘리는 대신 칸이 넓어지는
 * 쪽으로 옮긴다. */
const LABEL_SX = { whiteSpace: "nowrap", lineHeight: 1.5 };

/* 🔴 머리글 칸의 두 조작기는 **같은 높이**로 선다 (S22 · `control_baseline_mismatch`).
 *
 * 정렬 단추는 글자 줄 높이 그대로였고 필터 단추는 MUI `IconButton size="small"` 의 자기
 * 높이를 썼다 — 같은 줄에 선 같은 종류(버튼) 둘이 6px 어긋났고, 실측에서 「내 티켓」·
 * 「팀 티켓」·「미할당 티켓」 세 화면이 그 하나 때문에 42페이지에서 실패했다.
 *
 * 높이는 `CONTROL.tableCellDense`(32) 다. 이 토큰은 **표 안의 조작기**를 위해 이미 있었고
 * (theme.js 주석: 「배선은 W6 이 한다」) 여기가 그 배선이다 — 새 리터럴을 만들지 않는다.
 *
 * 아이콘 단추 쪽은 `minHeight` 만으로는 안 줄어든다 — 테마가 `MuiIconButton.root` 에 34 를
 * 이미 걸어 두었기 때문이다. 그래서 그쪽만 `height` 로 못 박는다. **손가락 목표는 안
 * 줄어든다**: 테마의 `::after` 가 40px 를 상자 밖에서 잡는다(WCAG 2.2 Target Size). */
const HEADER_CONTROL_SX = { minHeight: remPx(CONTROL.tableCellDense) };
const HEADER_ICON_SX = {
  minHeight: remPx(CONTROL.tableCellDense),
  minWidth: remPx(CONTROL.tableCellDense),
  height: remPx(CONTROL.tableCellDense),
  width: remPx(CONTROL.tableCellDense),
};

/* DataTable 과 GroupedTickets 가 같이 쓰는 머리글 칸.
 * 정렬 화살표는 onSort 가 있을 때만, 필터 단추는 onFilter 가 있을 때만 그린다.
 * 호출부가 안 넘기면 예전 머리글과 같다. */

/* 🔴 머리글 이름은 **언제나 칸 가운데**다 — 몸통 칸의 정렬과 따로다 (지시 6 · 13).
 *
 * 격자를 쓰는 이유가 여기 있다. `justifyContent: center` 만 주면 정렬 화살표와 필터
 * 단추가 같은 줄을 차지하는 만큼 이름이 왼쪽으로 밀린다 — 조작기가 있는 열과 없는 열의
 * 이름이 서로 다른 자리에 서고, 그 어긋남은 열마다 다르다.
 *
 * `1fr auto 1fr` 은 가운데 칸을 **컨테이너의 정중앙**에 세운다. 이름이 그 칸에 들어가고
 * 조작기는 오른쪽 1fr 칸 안에서 왼쪽에 붙는다 — 보기에는 예전처럼 이름 바로 옆이지만,
 * 이름의 중심은 조작기가 몇 개든 안 움직인다.
 *
 * 몸통 칸의 정렬을 안 받는다. 예전에는 호출부가 `align` 을 넘겼는데, 그러면 왼쪽에 붙은
 * 이름 옆에 가운데 이름이 서고 그 옆에 오른쪽 이름이 서서 머리글 줄을 한 줄로 못 읽었다. */
const HEADER_GRID_SX = {
  display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center",
};

export function TableHeaderCell({
  column, sort, onSort, filterValue, onFilter, filterOptions, entityOptions, cellSx, colRole,
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
      align={HEADER_ALIGN}
      data-col-role={colRole}
      /* 이름이 잘렸을 때 전체를 볼 길 — 본문 칸이 `title` 로 하는 것과 같다.
         도움말이 있으면 그것이 이긴다(그쪽이 더 많은 것을 말한다). */
      title={c.help || (typeof c.label === "string" ? c.label : undefined)}
      aria-sort={sortable ? (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none") : undefined}
      sx={cellSx}
    >
      {/* 🔴 머리글이 잘리지 않는다 (S19 → A4 재검수로 계약이 바뀌었다).
          예전 해법은 `overflow:hidden` 으로 이름을 자르는 것이었다 — 그런데 그 잘림 자체가
          실측된 결함이 됐다(「예상 WD」 client 40 / scroll 49). 지금은 이름·버튼 모두
          `min-width` 를 스스로 0으로 낮추지 않는다 — `table-layout:auto` 표에서는 칸이
          자기 내용 폭을 그대로 요구하면 그 요구가 열 폭 계산에 들어가 **열 자체가 넓어진다**
          (박스가 내용보다 좁아지는 그 순간이 없으니, S19 가 겪은 "박스는 좁은데 글자만
          삐져나온다"도 다시 생기지 않는다). 정렬 화살표·필터 단추는 여전히 `flexShrink:0`
          로 따로 보호된다. */}
      <Box sx={HEADER_GRID_SX}>
        {/* 왼쪽 저울추. 오른쪽 조작기 칸과 같은 무게(1fr)라 가운데 칸이 정중앙에 선다. */}
        <Box aria-hidden="true" />
        {sortable ? (
          <Box
            component="button"
            type="button"
            onClick={() => onSort(c.key)}
            sx={{
              font: "inherit", color: "inherit", border: 0, background: "none", p: 0,
              display: "inline-flex", alignItems: "center", cursor: "pointer",
              whiteSpace: "nowrap", minWidth: "max-content",
              ...HEADER_CONTROL_SX,
              "&:hover": { color: "text.primary" },
              "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
            }}
          >
            <Box component="span" sx={LABEL_SX}>{c.label}</Box>
          </Box>
        ) : (c.label ? <Box component="span" sx={LABEL_SX}>{c.label}</Box> : <Box aria-hidden="true" />)}
        {/* 조작기는 이름의 중심을 안 민다 — 오른쪽 칸 안에서 왼쪽에 붙어 이름 바로 옆에 선다. */}
        <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.25, justifySelf: "start", minWidth: 0 }}>
          {sortable ? (
            <Box component="span" aria-hidden="true" sx={{ flexShrink: 0, pl: 0.5, fontSize: FONT_SIZE.caption, opacity: active ? 1 : 0.35 }}>
                {dir === "desc" ? "\u2193" : dir === "asc" ? "\u2191" : "\u2195"}
            </Box>
          ) : null}
          {filterable ? (
            <IconButton
              size="small"
              aria-label={`${c.label || "열"} 필터`}
              aria-pressed={filtered}
              onClick={(e) => setAnchor(e.currentTarget)}
              sx={{ flexShrink: 0, color: filtered ? "primary.main" : "text.secondary", ...HEADER_ICON_SX }}
            >
              <FilterListRoundedIcon fontSize="inherit" />
            </IconButton>
          ) : null}
        </Box>
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
