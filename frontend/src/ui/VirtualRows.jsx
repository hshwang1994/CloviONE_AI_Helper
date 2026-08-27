import React from "react";
import Box from "@mui/material/Box";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import { useVirtualizer } from "@tanstack/react-virtual";

/* `@tanstack/react-virtual` 얇은 감싸개 (§15.1 재검수).
 *
 * ## 왜 이 파일이 있는가
 *
 * 백로그 181행 · 판 열 200장 절단 · 문서 목록 25행×5쪽를 **서버가 쪽/커서로 이미
 * 낸다**(§8.5, `app/work/service.py`). 여기서는 그 위에 얹는 **렌더링**만 맡는다.
 *
 * 🔴 **가상화는 조회 상한의 해결책이 아니다.** 서버가 200건에서 잘라 보내는 자리에
 * 이것만 얹으면 200건을 빠르게 그릴 뿐 나머지는 여전히 없다 — 그래서 이 파일은 스스로
 * 쪽 요청을 하지 않는다. 호출부가 이미 받아 둔 `items` 를 빠르게 그리는 것 하나만 한다.
 *
 * ## 형태가 둘인 이유
 *
 * - `VirtualRows` — `div` 목록(백로그 · 판 열). 헤드리스라 DOM 을 통째로 우리가 그린다.
 * - `VirtualTableBody` — 실제 `<table>` 안(문서 목록 · 내 티켓 · 팀 티켓, `DataTable`).
 *   `<tr style="position:absolute">` 는 표 레이아웃을 깨뜨린다(셀이 열 폭을 잃는다) —
 *   그래서 앞뒤 **여백 `<tr>` 둘**로 창을 표현한다. 보이는 행은 평범한 문서 흐름이라
 *   `table-layout:auto` 와 열 정렬 계약(`columnTypes.js`)이 그대로 산다.
 *
 * ## 주의 셋 — 소비처가 지켜야 한다 (§15.1)
 *
 * 1. **dnd-kit 과 함께 쓸 때** `SortableContext` 의 `items` 는 이 컴포넌트가 보여 주는
 *    범위가 아니라 **전체 id 배열**이어야 한다 — 창 밖 항목도 끌기 대상이다.
 * 2. **브라우저 찾기(Ctrl+F)가 렌더 안 된 행을 못 찾는다.** 가상화한 목록에는 자체
 *    검색 상자가 반드시 함께 있어야 한다.
 * 3. **표 접근성**(`scope="colgroup"` 등)은 그대로 둔다 — 그룹 머리행은 가상화하지 않고
 *    그룹 **안쪽 행만** `VirtualTableBody` 로 감싼다.
 */

const DEFAULT_OVERSCAN = 8;

/** div 기반 목록 — 백로그·판 열.
 *
 * props
 *   `items`         지금 받아 둔 행 배열(서버가 이미 쪽으로 잘라 준 것)
 *   `estimateSize`  행 하나의 예상 높이(px). 실제 높이는 `measureElement` 가 다시 잰다
 *   `renderItem`    `(item, index) => ReactNode`
 *   `getItemKey`    `(item, index) => key`. 안 주면 index
 *   `height`        스크롤 창의 높이(문자열, 예: "60vh" · "32rem")
 *   `overscan`      창 밖에 미리 그려 둘 행 수(스크롤 튐 방지)
 *   `footer`        끝에 닿았을 때 그릴 것(더 보기 단추 등) — 가상 목록 **다음**에 온다
 */
export function VirtualRows({
  items, estimateSize, renderItem, getItemKey, height = "32rem", overscan = DEFAULT_OVERSCAN,
  ariaLabel, footer, sx,
}) {
  const parentRef = React.useRef(null);
  const list = Array.isArray(items) ? items : [];
  const virtualizer = useVirtualizer({
    count: list.length,
    getScrollElement: () => parentRef.current,
    estimateSize: typeof estimateSize === "function" ? estimateSize : () => estimateSize || 56,
    overscan,
  });
  const virtualItems = virtualizer.getVirtualItems();

  return (
    <Box
      ref={parentRef}
      role="list"
      aria-label={ariaLabel}
      /* 총 건수는 QA 프로브·시험이 「그려진 행 수」 대신 보는 자리다(§18.2) —
         가상화는 그려진 DOM 행 수를 줄이는 것이 목적이라, 그 수로 판정하면
         가상화 자체가 결함(「행이 사라졌다」)으로 오탐된다. */
      data-virtual-total={list.length}
      sx={{ height, overflowY: "auto", overflowX: "hidden", position: "relative", minHeight: 0, ...sx }}
    >
      <Box sx={{ height: virtualizer.getTotalSize(), width: "100%", position: "relative" }}>
        {virtualItems.map((row) => {
          const item = list[row.index];
          return (
            <Box
              key={getItemKey ? getItemKey(item, row.index) : row.key}
              data-index={row.index}
              ref={virtualizer.measureElement}
              role="listitem"
              sx={{
                position: "absolute", top: 0, left: 0, width: "100%",
                transform: `translateY(${row.start}px)`,
              }}
            >
              {renderItem(item, row.index)}
            </Box>
          );
        })}
      </Box>
      {footer ? <Box sx={{ position: "sticky", bottom: 0 }}>{footer}</Box> : null}
    </Box>
  );
}

/** `<table>` 안의 가상 행 — 문서 목록 · 내 티켓 · 팀 티켓(`DataTable`).
 *
 * `<TableBody>` 안에서 평범한 `rows.map(...)` 대신 이것을 쓴다. 창 밖 행은 그리지 않고,
 * 그 자리를 **여백 `<tr>` 둘**(위·아래)로 채운다 — 실제 `<tr>` 만 문서 흐름에 남아
 * `table-layout:auto` 의 열 폭 계산이 본문 그대로 유지된다.
 *
 * `colSpan` 은 여백 행의 `<td>` 하나가 표 전체 폭을 차지하게 한다 — 안 주면 여백 행이
 * 첫 열 폭만큼만 좁게 그려지고 표 모양이 깨진다.
 */
export function VirtualTableBody({
  items, estimateSize, renderRow, getItemKey, colSpan, scrollElementRef, overscan = DEFAULT_OVERSCAN,
}) {
  const list = Array.isArray(items) ? items : [];
  const virtualizer = useVirtualizer({
    count: list.length,
    getScrollElement: () => scrollElementRef.current,
    estimateSize: typeof estimateSize === "function" ? estimateSize : () => estimateSize || 44,
    overscan,
  });
  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();
  const topSpace = virtualItems.length ? virtualItems[0].start : 0;
  const bottomSpace = virtualItems.length ? totalSize - virtualItems[virtualItems.length - 1].end : 0;

  return (
    <>
      {topSpace > 0 ? (
        <TableRow aria-hidden="true" sx={{ "& > td": { border: 0, p: 0 } }}>
          <TableCell colSpan={colSpan} sx={{ height: topSpace, p: "0 !important" }} />
        </TableRow>
      ) : null}
      {virtualItems.map((row) => {
        const item = list[row.index];
        return (
          <React.Fragment key={getItemKey ? getItemKey(item, row.index) : row.key}>
            {renderRow(item, row.index)}
          </React.Fragment>
        );
      })}
      {bottomSpace > 0 ? (
        <TableRow aria-hidden="true" sx={{ "& > td": { border: 0, p: 0 } }}>
          <TableCell colSpan={colSpan} sx={{ height: bottomSpace, p: "0 !important" }} />
        </TableRow>
      ) : null}
    </>
  );
}
