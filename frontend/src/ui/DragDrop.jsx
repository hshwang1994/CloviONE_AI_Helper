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
import { KO_WORD_BREAK } from "./theme.js";

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

/* 카드를 받는 칸. 비어 있어도 **높이를 유지한다** — 빈 칸이 사라지면 그 칸으로 옮길
 * 방법이 없어진다(칸반에서 마지막 카드를 뺀 순간 정확히 그 상태가 된다). */
export function DropColumn({ id, title, count, hint, children, sx }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <Box
      ref={setNodeRef}
      component="section"
      aria-label={`${title} (${count}건)`}
      sx={{
        display: "flex",
        flexDirection: "column",
        gap: 1,
        minWidth: 0,
        minHeight: "12rem",
        p: 1,
        borderRadius: 1,
        bgcolor: isOver ? "action.hover" : "transparent",
        outline: isOver ? "2px dashed" : "none",
        outlineColor: "primary.main",
        transition: "background-color 120ms ease",
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
      </Box>
      {hint ? (
        <Typography variant="caption" color="text.secondary" sx={{ ...KO_WORD_BREAK }}>
          {hint}
        </Typography>
      ) : null}
      <Box role="list" sx={{ display: "flex", flexDirection: "column", gap: 1, minHeight: "4rem" }}>
        {children}
      </Box>
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

/* 칸 사이로 옮겼을 때의 두 이웃. 끄는 카드 자신을 목록에서 빼고 센다 — 안 빼면
 * 자기 자신이 자기 이웃이 되어 순위가 제자리에 머문다. */
export function neighboursForBoard(targetIds, activeId, overId) {
  const ids = targetIds.filter((id) => id !== activeId);
  const at = ids.indexOf(overId);
  // 카드가 아니라 **빈 칸** 위에 놓았으면 맨 뒤로 간다.
  if (at < 0) return { beforeId: ids[ids.length - 1] || null, afterId: null };
  return { beforeId: ids[at - 1] || null, afterId: ids[at] };
}

export function SortableList({ items, labelOf, onReorder, disabled, children }) {
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
        <Box role="list" sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {items.map((it) => children(it))}
        </Box>
      </SortableContext>
      <DragOverlay>{activeId ? <Box sx={{ opacity: 0.9 }}>{labelOf(activeId)}</Box> : null}</DragOverlay>
    </DndContext>
  );
}

/* 여러 칸 사이로 카드를 옮긴다(칸반).
 *
 * `onMove({ id, fromColumn, toColumn, beforeId, afterId })`. 칸이 안 바뀌었으면
 * `fromColumn === toColumn` 이고, 그때는 순서만 바뀐 것이다 — 부르는 쪽이 그 둘을 다른
 * 요청으로 보낼지 한 요청으로 보낼지 정한다. */
export function DragBoard({ columns, labelOf, onMove, disabled, children, sx }) {
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
    const where = neighboursForBoard(
      target.items.map((it) => it.id),
      active.id,
      over.id
    );
    if (fromColumn === toColumn && !where.beforeId && !where.afterId) return;
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
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            sm: "repeat(2, minmax(0, 1fr))",
            lg: `repeat(${Math.min(columns.length, 6)}, minmax(0, 1fr))`,
          },
          gap: 1.5,
          alignItems: "start",
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
          >
            <SortableContext
              items={column.items.map((it) => it.id)}
              strategy={verticalListSortingStrategy}
              disabled={disabled}
            >
              {column.items.map((it) => children(it, column))}
            </SortableContext>
          </DropColumn>
        ))}
      </Box>
      <DragOverlay>{activeId ? <Box sx={{ opacity: 0.9 }}>{labelOf(activeId)}</Box> : null}</DragOverlay>
    </DndContext>
  );
}
