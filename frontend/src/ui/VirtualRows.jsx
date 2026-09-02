import React from "react";
import Box from "@mui/material/Box";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import { useVirtualizer, useWindowVirtualizer } from "@tanstack/react-virtual";

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
 *
 *    🔴 **다만 `GroupedTickets`(내 티켓·팀 티켓)에는 이 설계로 그대로 못 얹는다.** 그
 *    화면은 그룹(프로젝트·담당자)마다 **자기 `<tbody>`** 를 갖되 하나의 `<table>` 을
 *    공유해 열 폭을 맞춘다 — 그런데 `VirtualTableBody` 는 "스크롤 창 하나 = 가상화기
 *    하나"를 전제해서, 그룹마다 독립된 `VirtualTableBody` 를 여러 개 두면 각자 "내가
 *    스크롤 창의 유일한 내용"이라고 착각해 서로 앞 그룹들의 누적 높이를 모른 채 자기
 *    위치를 계산한다(뒤 그룹일수록 어긋난다). 제대로 하려면 모든 그룹의 행을 "그룹 머리
 *    행"까지 포함해 **하나의 평평한 목록**으로 합쳐 가상화하는 새 설계가 필요하다 — 지금
 *    있는 API 로 억지로 끼워 맞추지 않는다(REAUDIT §17 bundle 1, 2026-08 판단).
 * 4. **`VirtualTableBody` 는 조상의 스크롤 창을 읽는다 — 그 조상 ref 는 `useState` +
 *    콜백 ref 로 쥔다, 평범한 `useRef` 가 아니다.** React 는 커밋을 자손→조상 순서로
 *    처리하므로(레이아웃 이펙트도 같다), 평범한 ref 라면 이 부품의 첫 레이아웃 이펙트가
 *    도는 시점에 조상 ref 가 아직 안 붙어 있어 react-virtual 이 그 null 을 그대로
 *    확정해 버린다(행이 하나도 안 그려진 채 영원히 멈춘다 — 실제로 겪은 결함). 자세한
 *    이유는 `VirtualTableBody` 의 `scrollElement` 파라미터 주석, 실제 배선은
 *    `ui/kit.jsx::DataTable` 참고.
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
 *   `itemRole`      각 행 감싸개의 role. 기본은 "listitem". `renderItem` 이 돌려주는
 *                   것(예: dnd-kit `DragItem`)이 **자기 스스로** `listitem` 을 이미 달면
 *                   `null` 을 준다 — 안 그러면 listitem 이 listitem 을 감싸는 이중 구조가
 *                   된다(§15.1 가상화 · dnd-kit 공존).
 */
export function VirtualRows({
  items, estimateSize, renderItem, getItemKey, height = "32rem", overscan = DEFAULT_OVERSCAN,
  ariaLabel, footer, sx, itemRole = "listitem", onEndReached, rowGap = 0,
}) {
  const parentRef = React.useRef(null);
  const list = Array.isArray(items) ? items : [];
  const virtualizer = useVirtualizer({
    count: list.length,
    getScrollElement: () => parentRef.current,
    estimateSize: typeof estimateSize === "function" ? estimateSize : () => estimateSize || 56,
    overscan,
    /* 🔴 크기 캐시를 **id 로** 잡는다. 안 넘기면 캐시 키가 index 라, 이동·재조회로 순서가
       바뀌면 캐시된 높이가 엉뚱한 카드에 붙어 전 행이 다시 측정된다(그 재측정 하나가
       아래 style 재배치를 연쇄로 부른다). React key(getItemKey)와 축을 맞춘다. */
    getItemKey: getItemKey ? (index) => getItemKey(list[index], index) : undefined,
  });
  const virtualItems = virtualizer.getVirtualItems();

  /* `onEndReached` (opt-in) — 창 안의 마지막 행이 그려지면 **행 수당 한 번** 알린다.
   * 이 창(60vh overflow)을 소유한 것은 이 부품뿐이라, 바깥에 둔 교차 관찰 센티넬은
   * 이 창을 못 보고 뷰포트를 기준으로 잰다 — 그러면 목록을 열자마자 끝까지 자동으로
   * 끌어온다(백로그 전량 연쇄 로드 — 실제로 그랬다). overscan 이 섞여 조금 일찍
   * 울리는 것은 무한 목록의 정상 성질이다. */
  const endNotifiedFor = React.useRef(0);
  const lastVisibleIndex = virtualItems.length ? virtualItems[virtualItems.length - 1].index : -1;
  React.useEffect(() => {
    if (!onEndReached || list.length === 0) return;
    if (lastVisibleIndex < list.length - 1) return;
    // 이 길이에서 이미 알렸으면 다시 안 부른다. `>=` 로 잠가 **길이가 줄어도**(무효화로
    // 무한 목록이 첫 쪽으로 되감겨도) 재무장되지 않는다 — 그때 다시 발화하면 서버가
    // 안 움직이는 커서를 주는 순간 무한 연쇄 로드가 된다.
    if (list.length <= endNotifiedFor.current) return;
    endNotifiedFor.current = list.length;
    onEndReached();
  }, [onEndReached, list.length, lastVisibleIndex]);

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
      {/* 🔴 전체 높이·행 위치는 **매 측정마다 값이 바뀌는** 동적 값이라 `sx` 로 그리면
          안 된다 — emotion 이 값마다 새 클래스를 <style> 에 삽입하고, 그 삽입 하나가
          문서 전체 스타일 재계산을 부른다. 165행짜리 열에서는 그것이 O(행수²) 로 불어
          스크린샷·스크롤이 30초 넘게 멈췄다. `style`(인라인 DOM 속성)은 클래스를 안
          만든다 — 정적인 것만 sx 에, transform/height 만 style 에 둔다. */}
      <div style={{ height: virtualizer.getTotalSize(), width: "100%", position: "relative" }}>
        {virtualItems.map((row) => {
          const item = list[row.index];
          return (
            <div
              key={getItemKey ? getItemKey(item, row.index) : row.key}
              data-index={row.index}
              ref={virtualizer.measureElement}
              role={itemRole || undefined}
              style={{
                position: "absolute", top: 0, left: 0, width: "100%",
                transform: `translateY(${row.start}px)`,
                // 카드 사이 간격. 가상화 목록은 flex `gap` 을 쓸 수 없어(행이 absolute)
                // 여백을 각 행에 담는다 — estimateSize 에 이 값을 포함해 소비처가 넘긴다.
                paddingBottom: rowGap || undefined,
              }}
            >
              {renderItem(item, row.index)}
            </div>
          );
        })}
      </div>
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
 *
 * 🔴 `scrollElement` 는 **DOM 노드 값**이지 `useRef` 객체가 아니다 — 이 부품의 호출부가
 * 조상(`TableContainer`)이고, 여기(자손)에서 그 조상의 ref 를 읽는 구조라서다. React 는
 * 커밋을 자손→조상 순서로 처리하는데(레이아웃 이펙트도 같은 순서), **평범한 `useRef`
 * 라면** 이 부품(자손)의 첫 레이아웃 이펙트가 실행되는 시점에 조상의 ref 는 **아직 안
 * 붙어 있다** — react-virtual 은 그 순간 `getScrollElement()` 가 준 값(null)을 그대로
 * 확정해 버리고, 그 뒤로는 스스로 다시 확인하지 않는다(제 라이브러리 소스 확인함). 값이
 * 있는 척 렌더되다가 실제로는 행이 하나도 안 그려지는 상태로 영원히 멈춘다 — 다른 이유로
 * 우연히 다시 렌더되는 화면(비동기로 자료가 늦게 오는 화면)에서만 안 드러났을 뿐이다.
 * 호출부가 `useState` + 콜백 ref 로 조상 노드를 쥐면(`DataTable` 참고), 그 노드가 실제로
 * 붙는 순간 **state 갱신 → 리렌더**가 일어나 이 문제 자체가 생기지 않는다. */
/* 여백 행 둘 + 보이는 행 — **두 모드가 같은 몸통을 쓴다.**
 *
 * 행 하나를 모드마다 다르게 그리면 그 자체가 회귀다(`kit.jsx::renderDataRow` 가 가상화와
 * 평범한 렌더에 같은 함수를 쓰는 것과 같은 이유).
 *
 * `offset` 은 «항목 좌표의 원점». 창 가상화기는 항목의 `start` 를 **문서 맨 위**부터 재므로
 * 목록이 시작하는 지점(`scrollMargin`)을 빼야 여백 높이가 나온다. 요소 가상화기는 0 이다.
 * (`virtual-core` 의 `getTotalSize()` 자체가 `end - scrollMargin` 이라 아래 뺄셈과 짝이 맞는다.) */
function SpacerRows({ virtualizer, items, renderRow, getItemKey, colSpan, offset = 0 }) {
  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();
  const topSpace = virtualItems.length ? virtualItems[0].start - offset : 0;
  const bottomSpace = virtualItems.length
    ? totalSize - (virtualItems[virtualItems.length - 1].end - offset)
    : 0;

  return (
    <>
      {topSpace > 0 ? (
        <TableRow aria-hidden="true" sx={{ "& > td": { border: 0, p: 0 } }}>
          {/* 여백 높이는 스크롤마다 바뀌는 동적 값 — sx 로 그리면 값마다 emotion 클래스가
              쌓여 전체 스타일 재계산을 부른다(위 div 경로와 같은 이유). style 로 준다. */}
          <TableCell colSpan={colSpan} style={{ height: topSpace, padding: 0 }} />
        </TableRow>
      ) : null}
      {virtualItems.map((row) => {
        const item = items[row.index];
        return (
          <React.Fragment key={getItemKey ? getItemKey(item, row.index) : row.key}>
            {renderRow(item, row.index)}
          </React.Fragment>
        );
      })}
      {bottomSpace > 0 ? (
        <TableRow aria-hidden="true" sx={{ "& > td": { border: 0, p: 0 } }}>
          <TableCell colSpan={colSpan} style={{ height: bottomSpace, padding: 0 }} />
        </TableRow>
      ) : null}
    </>
  );
}

export function VirtualTableBody({
  items, estimateSize, renderRow, getItemKey, colSpan, scrollElement, overscan = DEFAULT_OVERSCAN,
}) {
  const list = Array.isArray(items) ? items : [];
  const virtualizer = useVirtualizer({
    count: list.length,
    getScrollElement: () => scrollElement,
    estimateSize: typeof estimateSize === "function" ? estimateSize : () => estimateSize || 44,
    overscan,
    // div 경로와 같은 이유 — 크기 캐시를 id 로 잡는다(순서 바뀜에 전 행 재측정 방지).
    getItemKey: getItemKey ? (index) => getItemKey(list[index], index) : undefined,
  });
  return (
    <SpacerRows
      virtualizer={virtualizer} items={list} renderRow={renderRow}
      getItemKey={getItemKey} colSpan={colSpan}
    />
  );
}

/** `<table>` 안의 가상 행 — **윈도가 스크롤 창인 경우.**
 *
 * 이 앱의 셸은 문서를 굴린다(`AppShell` 은 `main` 에 `overflow` 를 안 준다). 그래서 목록의
 * 기본 모드는 이쪽이고, 안쪽 상자(`VirtualTableBody`)는 스스로 높이를 가진 자리 — 작업 보드
 * 레인·모달 안 하위 목록 — 만 쓴다.
 *
 * 안쪽 상자를 기본으로 두면 잃는 것이 셋이다: ① 스크롤바가 둘이 되어 휠이 어느 것을 움직이는지
 * 사용자가 매번 추측한다 ② `maxHeight: 32rem` 은 4K 에서 목록을 문틈으로 만든다(이 저장소의
 * 루트 폰트사이즈는 2200/3000 에서 커진다) ③ **`lib/listReturn.js` 는 `window.scrollY` 만
 * 안다** — 행이 안쪽 상자에 있으면 상세에서 돌아왔을 때 아무것도 복원되지 않는다.
 *
 * `scrollMargin` 은 «문서 맨 위에서 이 목록까지의 거리» 다. 안 주면 창 가상화기가 목록이
 * 화면 맨 위에 있다고 믿어 엉뚱한 구간을 그린다 — `useScrollMargin` 이 그 값을 잰다. */
export function WindowVirtualTableBody({
  items, estimateSize, renderRow, getItemKey, colSpan, scrollMargin = 0, overscan = DEFAULT_OVERSCAN,
}) {
  const list = Array.isArray(items) ? items : [];
  const virtualizer = useWindowVirtualizer({
    count: list.length,
    estimateSize: typeof estimateSize === "function" ? estimateSize : () => estimateSize || 44,
    overscan,
    scrollMargin,
  });
  return (
    <SpacerRows
      virtualizer={virtualizer} items={list} renderRow={renderRow}
      getItemKey={getItemKey} colSpan={colSpan} offset={scrollMargin}
    />
  );
}

/** 이 노드가 문서 어디서 시작하는가 — 창 가상화기의 `scrollMargin`.
 *
 * `getBoundingClientRect().top + window.scrollY` 는 **스크롤 위치와 무관한 값**이라 언제 재도
 * 같다. 다시 재야 하는 때는 위쪽 것이 늘거나 줄 때다 — 필터 줄이 접히거나 배너가 뜨거나
 * 창 폭이 바뀌어 줄바꿈이 달라지는 순간.
 *
 * 🔴 노드는 **`useState` + 콜백 ref** 로 받는다(D-353). 평범한 `useRef` 를 넘기면 이 훅의
 * 레이아웃 이펙트가 도는 시점에 아직 `null` 이고, 그 값이 그대로 확정된다. */
export function useScrollMargin(node) {
  const [margin, setMargin] = React.useState(0);
  React.useLayoutEffect(() => {
    if (!node || typeof window === "undefined") return undefined;
    const measure = () => {
      const rect = node.getBoundingClientRect();
      setMargin(Math.max(0, Math.round(rect.top + window.scrollY)));
    };
    measure();
    window.addEventListener("resize", measure);
    let ro = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(measure);
      /* 목록 **위쪽**이 자라면 시작점이 내려간다 — 목록 자신이 아니라 문서를 본다. */
      if (document.body) ro.observe(document.body);
    }
    return () => {
      window.removeEventListener("resize", measure);
      if (ro) ro.disconnect();
    };
  }, [node]);
  return margin;
}
