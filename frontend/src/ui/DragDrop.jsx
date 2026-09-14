import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { KO_WORD_BREAK, RADIUS } from "./theme.js";
import { LANE_SURFACE, TILE_PADDING } from "./density.js";
import { VirtualRows } from "./VirtualRows.jsx";

/* 끌어 놓기 공통 부품 (S6). **저장소에서 DnD 를 쓰는 자리는 전부 여기를 지난다.**
 *
 * ## 왜 하나로 두는가
 *
 * 칸반과 백로그는 화면이 다르지만 어려운 부분이 같다: 포인터와 키보드를 함께 받아야 하고,
 * 스크린리더에 무슨 일이 일어났는지 말해야 하고, 드롭 위치를 「어느 칸의 몇 번째」로 정확히
 * 계산해야 한다. 화면마다 다시 만들면 그중 하나가 반드시 빠지고, 빠지는 것은 대개
 * **키보드**다 — 마우스로 시험하면 안 빠진 것처럼 보이기 때문이다.
 *
 * ## 키보드가 1급이다
 *
 * 끌어 놓기만 되는 목록은 마우스 없이 못 쓰는 화면이다. `KeyboardSensor` 를 기본으로 켜고
 * (스페이스로 집고, 화살표로 옮기고, 스페이스로 놓는다) 각 단계를 `announcements` 로
 * 말한다. 손잡이에 `tabIndex` 가 붙는 것도 그래서다.
 *
 * ## 낙관적 갱신을 여기서 하지 않는다
 *
 * 카드가 먼저 움직이고 서버가 거절하면 화면이 되돌아가야 하는데, 그 되돌림을 부품이
 * 하면 부르는 쪽은 자기 목록이 언제 진실인지 알 수 없게 된다. 여기서는 **어디서 어디로**
 * 만 알려 주고, 목록의 정본은 부르는 쪽이 든다. */

// 포인터가 이만큼 움직여야 끌기로 본다. 0 이면 카드를 클릭해 상세로 들어가려던 손짓이
// 전부 끌기가 되고, 그러면 카드를 열 방법이 없어진다.
const DRAG_START_DISTANCE_PX = 6;

export const DRAG_HANDLE_LABEL = "끌어서 옮기기";

function useDragSensors() {
  return useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: DRAG_START_DISTANCE_PX },
    }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );
}

/* 스크린리더 안내. 끌어 놓기는 **보이는 변화가 전부**라, 말해 주지 않으면 화면을 못 보는
 * 사람에게는 아무 일도 안 일어난 것과 같다. */
function announcements(labelOf) {
  const name = (id) => labelOf(id) || "항목";
  return {
    onDragStart: ({ active }) => `${name(active.id)}을 집었습니다.`,
    onDragOver: ({ active, over }) =>
      over ? `${name(active.id)}을 ${name(over.id)} 위치로 옮기는 중입니다.` : "",
    onDragEnd: ({ active, over }) =>
      over
        ? `${name(active.id)}을 ${name(over.id)} 위치에 놓았습니다.`
        : `${name(active.id)} 옮기기를 취소했습니다.`,
    onDragCancel: ({ active }) => `${name(active.id)} 옮기기를 취소했습니다.`,
  };
}

/* 끌 수 있는 한 칸. `children` 은 카드 내용이고, 손잡이 속성은 카드 전체에 붙는다 —
 * 작은 손잡이 아이콘만 잡게 하면 터치 화면에서 사실상 못 쓴다. */
export function DragItem({ id, label, disabled, children }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
    disabled,
  });
  return (
    <Box
      ref={setNodeRef}
      role="listitem"
      aria-label={label}
      sx={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.4 : 1,
        cursor: disabled ? "default" : "grab",
        touchAction: "none",
        "&:focus-visible": { outline: "2px solid", outlineColor: "primary.main", outlineOffset: 2 },
      }}
      {...attributes}
      {...listeners}
    >
      {children}
    </Box>
  );
}

/* 끌 수 있는 카드 **안의** 단추 자리 (D-483).
 *
 * `DragItem` 은 손잡이 속성을 카드 전체에 붙인다 — 포인터 누름은 끌기의 시작이고, 스페이스
 * 키는 「집기」다. 카드 안에 단추(빠른 수정 · 현재 회차에서 빼기)가 있으면 그 단추를 누르는
 * 손짓·스페이스가 그대로 카드로 올라가 끌기가 시작되고, 단추의 클릭은 카드의 클릭(미리
 * 열기)으로도 번진다. 포인터 끌기는 dnd-kit 이 6px 문턱으로 이미 가르지만 **키보드는 그
 * 문턱이 없다** — 이 감싸개가 세 사건을 카드까지 안 보내는 것으로 단추를 단추로 남긴다. */
export function DragItemActions({ children, sx }) {
  const stop = (e) => e.stopPropagation();
  return (
    <Box
      onPointerDown={stop}
      onMouseDown={stop}
      onTouchStart={stop}
      onKeyDown={stop}
      onClick={stop}
      sx={{ display: "inline-flex", alignItems: "center", ...sx }}
    >
      {children}
    </Box>
  );
}

/* 카드를 받는 칸. 비어 있어도 **높이를 유지한다** — 빈 칸이 사라지면 그 칸으로 옮길
 * 방법이 없어진다(칸반에서 마지막 카드를 뺀 순간 정확히 그 상태가 된다). */
/* `virtualized` — §15.1. `VirtualRows` 는 자기 자신의 스크롤 창(`height`+`overflowY:auto`)을
 * 갖는다 — 이 칸의 `bodyMaxHeight` 스크롤 상자 **안에** 그것을 또 두면 스크롤 상자가
 * 둘 겹친다. 그래서 켜져 있으면 이 칸은 자기 스크롤·역할(role="list")·레이아웃을 접고
 * `children` 을 그대로 낸다 — 그 자리를 `VirtualRows` 가 통째로 맡는다. */
/* 🔴 **판이 세 겹이 아니다** — 칸은 조용한 함몰면이고 카드가 그 위의 판이다.
 *
 * 예전에는 바깥에 한 겹(`WorkBoard` 의 `LANE_SURFACE` 래퍼), 칸마다 한 겹, 카드마다 한 겹
 * 이라 흰 상자가 세 번 겹쳐 보였다. 사용자가 「칸반 카드 뒤에 다시 깔린 흰 배경은 없어도
 * 될 것 같다」고 한 자리다. 바깥 겹은 화면이 지웠고, 칸은 **상시 테두리를 버린다** —
 * 배경 하나로도 「여기가 한 칸이다」는 충분히 읽히고, 테두리는 카드에만 남아 무엇이
 * 집을 수 있는 것인지 말한다. 끌어 놓는 동안에만 테두리가 살아나 목표를 가리킨다. */
export function DropColumn({ id, title, count, hint, children, sx, bodyMaxHeight, action, footer, virtualized, droppable, highlight }) {
  // 받지 않는 칸은 드롭 대상 등록 자체를 끈다 — 하이라이트가 「놓을 수 있다」고
  // 거짓말하지 않는다(분류되지 않음 칸이 그랬다). 칸 안의 카드는 여전히 끌어낼 수 있다.
  const { setNodeRef, isOver } = useDroppable({ id, disabled: droppable === false });
  return (
    <Box
      ref={setNodeRef}
      component="section"
      aria-label={`${title} (${count}건)`}
      /* 판독 줄에서 「진행 중 12」를 누르면 이 칸으로 데려가는 데 쓴다. 이름이 아니라
         열쇠로 찾는다 — 이름은 어휘가 바뀌면 달라지지만 열쇠는 서버와 같은 값이다. */
      data-col-key={id}
      /* 가리켜진 상태를 DOM 에 적어 둔다. 시험이 계산 CSS 를 훔쳐보지 않게 하려는 것이다 —
         jsdom 은 `outline` 단축을 안 풀어서 「보이는가」를 그쪽으로는 못 잰다. 여기 적힌
         것과 아래 `outline` 은 같은 하나(`highlight`)에서 나오므로 갈라지지 않는다. */
      data-col-highlight={highlight ? "true" : undefined}
      /* 판독 줄이 이 칸을 「여기다」라고 가리킬 때 초점도 함께 온다(`highlight` 참고).
         -1 이라 Tab 순서에는 안 들어가고, 프로그램 초점만 받는다 — 낭독기는 위
         `aria-label`("계획 (132건)")을 읽어 주므로 눈에 보이는 테두리와 같은 것을 듣는다. */
      tabIndex={-1}
      sx={{
        display: "flex",
        flexDirection: "column",
        gap: 1,
        minWidth: 0,
        /* 바닥을 낮춘다. 12rem 은 **빈 칸이 큰 흰 상자로 보이던** 높이다 — 카드가 없어도
           그만큼의 빈 면이 서 있었다. 놓을 자리는 유지해야 하므로 0 으로는 안 간다. */
        minHeight: "7rem",
        p: TILE_PADDING,
        ...LANE_SURFACE,
        border: 0,
        borderRadius: `${RADIUS.md}px`,
        bgcolor: isOver ? "action.hover" : LANE_SURFACE.bgcolor,
        /* 점선은 「놓을 수 있다」, 실선은 「네가 찾던 칸이 이거다」다. 두 표시가 같은 자리를
           쓰지만 뜻이 다르므로 모양을 다르게 둔다. 실선은 움직이지 않는다 — 동작 줄이기를
           켠 사람에게도 그대로 보여야 하는 신호라 깜빡임이 아니라 켜짐이다. */
        outline: isOver ? "2px dashed" : highlight ? "2px solid" : "none",
        outlineColor: "primary.main",
        outlineOffset: -1,
        transition: "background-color 120ms ease, outline-color 120ms ease",
        ...sx,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
        <Typography component="h3" variant="subtitle2" sx={{ ...KO_WORD_BREAK }}>
          {title}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {count}
        </Typography>
        {action ? <Box sx={{ marginInlineStart: "auto" }}>{action}</Box> : null}
      </Box>
      {hint ? (
        <Typography variant="caption" color="text.secondary" sx={{ ...KO_WORD_BREAK }}>
          {hint}
        </Typography>
      ) : null}
      {/* 🔴 **칸 안에서만 굴러간다** (지시 5).
          티켓이 늘어도 판은 자기 높이에 그대로 선다 — 안 그러면 한 열이 백 장이 되는 날
          판 전체가 그 열만큼 아래로 자라고, 옆 열들은 그 아래 빈 자리를 지키느라 화면
          하나를 통째로 쓴다. 그때 사용자가 하는 일은 페이지를 굴려 다른 열의 카드를
          찾는 것이고, 그 순간 칸반은 목록 넷과 다르지 않다.
          `bodyMaxHeight` 를 안 주면 예전처럼 자란다(회귀 0). */}
      {virtualized ? children : (
        <Box
          role="list"
          sx={{
            display: "flex", flexDirection: "column", gap: 1, minHeight: "2.5rem",
            ...(bodyMaxHeight ? { maxHeight: bodyMaxHeight, overflowY: "auto", pr: 0.5 } : null),
          }}
        >
          {children}
        </Box>
      )}
      {/* 빈 칸은 **큰 빈 상자가 아니라 한 줄**이다. 놓을 수 있다는 사실만 말한다 —
          받지 않는 칸에는 그 말을 하지 않는다. */}
      {count === 0 && droppable !== false ? (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{
            border: "1px dashed", borderColor: "divider", borderRadius: `${RADIUS.sm}px`,
            px: 1, py: 0.75, textAlign: "center",
          }}
        >
          여기로 카드를 옮길 수 있습니다.
        </Typography>
      ) : null}
      {footer ? <Box sx={{ mt: "auto" }}>{footer}</Box> : null}
    </Box>
  );
}

/* 세로 목록 하나를 끌어 정렬한다(백로그).
 *
 * `onReorder({ id, beforeId, afterId })` 로 **놓인 자리의 두 이웃**을 준다. 서버가
 * 소수 순위로 그 사이 값을 계산하므로(app/work/rank.py) 목록 전체를 다시 보낼 필요가 없다.
 * 인덱스를 주지 않는 이유도 같다 — 인덱스는 다른 사람이 그 사이에 한 줄 넣는 순간 뜻이
 * 달라지지만, 이웃 두 개는 그렇지 않다. */
/* 목록 안에서 옮겼을 때의 두 이웃. **순수 함수라 시험이 직접 본다.**
 *
 * 이 계산이 틀리면 카드가 한 칸 어긋난 자리에 앉는데 **화면은 정상으로 보인다** —
 * 순서가 하나 밀렸을 뿐이라 눈으로는 못 잡고, 사용자는 같은 카드를 두 번 끈다. */
export function neighboursForList(ids, activeId, overId) {
  const from = ids.indexOf(activeId);
  const to = ids.indexOf(overId);
  if (from < 0 || to < 0 || from === to) return null;
  // 위로 옮기면 대상의 **앞**, 아래로 옮기면 대상의 **뒤**에 놓인다.
  const movingDown = from < to;
  return {
    beforeId: movingDown ? ids[to] : ids[to - 1] || null,
    afterId: movingDown ? ids[to + 1] || null : ids[to],
  };
}

/* 칸 사이로(또는 칸 안에서) 옮겼을 때의 두 이웃.
 *
 * qa-contract-change: 같은 칸 안의 이동이 **방향을 본다.** 예전에는 방향을 무시하고
 * 항상 대상 카드 앞에 넣어서, 한 칸 아래로 끌기가 제자리 no-op 이었다 — 요청은 나가고
 * version 만 올랐으며, 사용자는 「끌어도 안 움직인다」며 같은 카드를 두 번 세 번 끌었다.
 * 같은 칸이면 목록과 같은 계산(`neighboursForList`)을 쓴다 — 같은 동작이 화면(백로그)
 * 마다 다르게 굴면 안 된다. 같은 자리에 놓으면 `null` 이다(호출부가 요청을 안 보낸다).
 *
 * 칸을 건너온 카드는 자기 자신이 대상 목록에 없으므로 방향이 없다 — 놓은 카드 앞에 선다. */
export function neighboursForBoard(targetIds, activeId, overId) {
  if (targetIds.indexOf(activeId) >= 0) {
    return neighboursForList(targetIds, activeId, overId);
  }
  const at = targetIds.indexOf(overId);
  // 카드가 아니라 **빈 칸** 위에 놓았으면 맨 뒤로 간다.
  if (at < 0) return { beforeId: targetIds[targetIds.length - 1] || null, afterId: null };
  return { beforeId: targetIds[at - 1] || null, afterId: targetIds[at] };
}

/* `virtualize` — §15.1 재검수. opt-in 이다(안 주면 예전과 한 픽셀도 안 다르다,
 * `Knowledge.jsx` 폴더 목록은 8개라 안 켠다). 켜면 창 밖 항목은 DOM에 없지만
 * `SortableContext` 의 `items`(바로 아래 `ids`)는 **항상 전체 배열**이라 dnd-kit 은
 * 그 카드들이 "지금 안 보일 뿐 목록에는 있다"로 안다 — 끌어다 창 밖에 가까이 가면
 * dnd-kit `PointerSensor` 의 기본 자동 스크롤이 창을 옮겨 그 카드를 보이게 한다
 * (§15.1 주의 1). `VirtualRows` 자신의 `role="listitem"` 은 끈다 — `children(it)` 이
 * 돌려주는 `DragItem` 이 이미 그 role 을 스스로 단다(이중 listitem 방지). */
export function SortableList({ items, labelOf, onReorder, disabled, children, virtualize, overlay }) {
  const sensors = useDragSensors();
  const [activeId, setActiveId] = React.useState(null);
  const ids = items.map((it) => it.id);

  function handleEnd(event) {
    setActiveId(null);
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const where = neighboursForList(ids, active.id, over.id);
    if (!where) return;
    onReorder({ id: active.id, ...where });
  }

  const list = virtualize ? (
    <VirtualRows
      items={items}
      getItemKey={(it) => it.id}
      estimateSize={virtualize.estimateSize}
      height={virtualize.height}
      ariaLabel={virtualize.ariaLabel}
      overscan={virtualize.overscan}
      onEndReached={virtualize.onEndReached}
      rowGap={virtualize.rowGap}
      scrollKey={virtualize.scrollKey}
      itemRole={null}
      renderItem={(it) => children(it)}
      sx={virtualize.sx}
    />
  ) : (
    <Box role="list" sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {items.map((it) => children(it))}
    </Box>
  );

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      accessibility={{ announcements: announcements(labelOf) }}
      onDragStart={({ active }) => setActiveId(active.id)}
      onDragCancel={() => setActiveId(null)}
      onDragEnd={handleEnd}
    >
      <SortableContext items={ids} strategy={verticalListSortingStrategy} disabled={disabled}>
        {list}
      </SortableContext>
      {/* 끌리는 것의 얼굴. `overlay` 를 주면 실제 카드 모양이 따라온다 — 맨 텍스트가
          떠다니면 「깨진 것」으로 읽힌다. `DragItem` 으로 감싸지 않는다(useSortable id
          이중 등록 방지). 안 주면 예전 라벨 그대로다(소비처 회귀 0). */}
      <DragOverlay>
        {activeId
          ? (overlay && overlay(activeId)) || <Box sx={{ opacity: 0.9 }}>{labelOf(activeId)}</Box>
          : null}
      </DragOverlay>
    </DndContext>
  );
}

/* 여러 칸 사이로 카드를 옮긴다(칸반).
 *
 * `onMove({ id, fromColumn, toColumn, beforeId, afterId })`. 칸이 안 바뀌었으면
 * `fromColumn === toColumn` 이고, 그때는 순서만 바뀐 것이다 — 부르는 쪽이 그 둘을 다른
 * 요청으로 보낼지 한 요청으로 보낼지 정한다. */
/* `virtualize` — §15.1, `SortableList` 위 주석과 같은 계약(opt-in · `SortableContext`
 * 의 `items` 는 항상 전체 배열 · dnd-kit 기본 자동 스크롤이 창 밖 이동을 처리한다).
 * 켜지면 `columnMaxHeight` 는 각 칸의 `VirtualRows` `height` 로 넘어간다 — 칸 자신의
 * `overflowY:auto` 상자는 접는다(스크롤 상자 이중화 방지, `DropColumn` 위 주석 참고). */
/* `highlightId` — 판독 타일이 가리킨 칸. `columns` 안에 넣지 않는 이유가 있다: 그 배열은
 * memo 로 만들고 카드가 안 바뀌면 같은 객체를 되돌려 주는 계약인데(가상화 재측정 방지),
 * 표시 하나 때문에 매번 새 배열이 나오면 그 계약이 깨진다. */
export function DragBoard({ columns, labelOf, onMove, disabled, children, sx, columnMaxHeight, virtualize, overlay, highlightId }) {
  const sensors = useDragSensors();
  const [activeId, setActiveId] = React.useState(null);

  const columnOf = React.useCallback(
    (itemId) => {
      const found = columns.find((c) => c.items.some((it) => it.id === itemId));
      return found ? found.id : null;
    },
    [columns]
  );

  function handleEnd(event) {
    setActiveId(null);
    const { active, over } = event;
    if (!over) return;
    const fromColumn = columnOf(active.id);
    // 카드 위에 놓았으면 그 카드의 칸, 빈 칸 위에 놓았으면 그 칸 자신이다. 둘을 구별하지
    // 않으면 **빈 칸으로는 영영 못 옮긴다** — 받을 카드가 없기 때문이다.
    const toColumn = columnOf(over.id) || (columns.some((c) => c.id === over.id) ? over.id : null);
    if (!toColumn) return;
    const target = columns.find((c) => c.id === toColumn);
    // 받지 않는 칸(droppable: false)은 카드 위에 놓아도 무시한다 — 칸 자신은
    // `useDroppable` 이 꺼져 하이라이트도 안 생기지만, 칸 안의 카드들은 여전히
    // (끌어낼 수 있어야 하므로) 등록돼 있어 이 갈래가 필요하다.
    if (target.droppable === false) return;
    const where = neighboursForBoard(
      target.items.map((it) => it.id),
      active.id,
      over.id
    );
    // 같은 자리 — 헛 요청(version 만 오르는 이동)을 만들지 않는다.
    if (!where) return;
    onMove({ id: active.id, fromColumn, toColumn, ...where });
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      accessibility={{ announcements: announcements(labelOf) }}
      onDragStart={({ active }) => setActiveId(active.id)}
      onDragCancel={() => setActiveId(null)}
      onDragEnd={handleEnd}
    >
      {/* 칸반의 칸은 **같아야 한다.** 진행 상태가 나란한 레인이라 사람이 가로로 훑고, 폭을
          내용에 맞추면 카드를 옮길 때마다 판이 재배치된다 — 그래서 `data-equal-grid` 로
          「이 격자는 일부러 균등하다」고 말한다(달력·게임판과 같은 부류다).

          다만 **균등한 것과 좁은 것은 다르다.** 바닥값이 `minmax(0, 1fr)` 이라 레인 여섯이
          1366 폭에서 155px 까지 눌렸고, 그 폭에서는 카드 제목이 스무 줄로 접힌다(실측:
          «굶는 쪽 20줄로 접힘»). 레인에 읽을 수 있는 바닥을 주고, 안 들어가면 판 자신이
          가로로 스크롤한다 — 페이지가 밀리는 것이 아니라 이 상자 안에서다. */}
      <Box
        data-equal-grid="kanban"
        sx={{
          display: "grid",
          width: "100%",
          gridTemplateColumns: {
            xs: "1fr",
            sm: "repeat(2, minmax(0, 1fr))",
            lg:
              columns.length > 6
                ? `repeat(${columns.length}, minmax(14rem, 1fr))`
                : `repeat(${columns.length}, minmax(0, 1fr))`,
          },
          gap: 1.5,
          alignItems: "start",
          overflowX: columns.length > 6 ? "auto" : "visible",
          ...sx,
        }}
      >
        {columns.map((column) => (
          <DropColumn
            key={column.id}
            id={column.id}
            title={column.title}
            count={column.count != null ? column.count : column.items.length}
            hint={column.hint}
            action={column.action}
            footer={column.footer}
            droppable={column.droppable}
            highlight={highlightId != null && highlightId === column.id}
            bodyMaxHeight={virtualize ? undefined : columnMaxHeight}
            virtualized={!!virtualize}
          >
            <SortableContext
              items={column.items.map((it) => it.id)}
              strategy={verticalListSortingStrategy}
              disabled={disabled}
            >
              {virtualize ? (
                <VirtualRows
                  items={column.items}
                  getItemKey={(it) => it.id}
                  estimateSize={virtualize.estimateSize}
                  height={columnMaxHeight || virtualize.height}
                  ariaLabel={`${column.title} 카드 목록`}
                  overscan={virtualize.overscan}
                  rowGap={virtualize.rowGap}
                  // 열마다 자기 스크롤 자리를 기억한다 — 상세에서 돌아왔을 때 열이 맨 위로
                  // 되감기지 않게(`VirtualRows` 의 scrollKey).
                  scrollKey={virtualize.scrollKeyPrefix ? `${virtualize.scrollKeyPrefix}:${column.id}` : undefined}
                  itemRole={null}
                  renderItem={(it) => children(it, column)}
                />
              ) : column.items.map((it) => children(it, column))}
            </SortableContext>
          </DropColumn>
        ))}
      </Box>
      {/* `SortableList` 의 overlay 와 같은 계약 — 실제 카드 얼굴, 없으면 라벨 폴백. */}
      <DragOverlay>
        {activeId
          ? (overlay && overlay(activeId)) || <Box sx={{ opacity: 0.9 }}>{labelOf(activeId)}</Box>
          : null}
      </DragOverlay>
    </DndContext>
  );
}
