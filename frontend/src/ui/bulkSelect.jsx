import React from "react";
import { Button } from "./kit.jsx";

/* 목록 다중선택 + 일괄 삭제 공용. 체크박스는 클릭이 행 클릭(상세 이동)으로 번지지 않게 막는다.
 * 표에 '선택' 열 하나를 추가하고(BulkBar와 함께) 부모가 선택 상태를 들고 있으면 된다. */

export function useRowSelection() {
  const [selected, setSelected] = React.useState(() => new Set());
  const toggle = React.useCallback((id) => setSelected((s) => {
    const n = new Set(s);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  }), []);
  const setAll = React.useCallback((ids, on) => setSelected((s) => {
    const n = new Set(s);
    (ids || []).forEach((id) => { if (on) n.add(id); else n.delete(id); });
    return n;
  }), []);
  const clear = React.useCallback(() => setSelected(new Set()), []);
  return { selected, toggle, setAll, clear };
}

export function SelectCheckbox({ checked, onChange, label }) {
  return (
    <input type="checkbox" className="k-selbox" checked={!!checked} aria-label={label}
      onClick={(e) => e.stopPropagation()} onChange={(e) => onChange(e.target.checked)} />
  );
}

/* 행 체크박스의 접근 이름. 스크린리더로 표를 훑으면 이 이름만 들린다 — 예전에는 모든 행이
 * "이 항목 선택" 이라, 스무 줄짜리 목록에서 무엇을 고르는지 알 방법이 없었다.
 * 값은 표가 준다(DataTable → ctx.rowName). 어느 열에서 오는지는 그 화면의 **열 정의**가
 * `rowName` 으로 정한다(ui/rowName.js) — 화면마다 라벨을 손으로 적으면 반드시 빠진다. */
function selectLabel(rowName) {
  return rowName ? rowName + " 선택" : "이 항목 선택";
}

// 표에 넣을 좁은 '선택' 열 정의. selection = { selected, toggle, setAll } + ids(현재 보이는 행 id 목록).
// eligible(id)=false 인 행(권한 없음 등)은 체크박스를 감추고 전체선택 대상에서도 뺀다.
export function selectionColumn(selection, ids, { eligible } = {}) {
  const all = ids || [];
  const pick = eligible ? all.filter((id) => eligible(id)) : all;
  const allOn = pick.length > 0 && pick.every((id) => selection.selected.has(id));
  return {
    // 폭을 여기서 못 박는다. DataTable을 fixed 레이아웃으로 쓰는 화면(문서·게시판·휴지통)에서
    // 폭이 없으면 체크박스 칸이 남은 공간을 제목 칸과 똑같이 나눠 가져, 체크박스 하나가
    // 표의 10% 넘게 차지했다. 호출부마다 따로 지정하면 새로 쓰는 화면에서 또 빠진다.
    key: "_sel", align: "center", className: "k-col-check", width: "3.5rem",
    // 이 열은 행을 구별하는 값의 출처가 아니다. 선택 열은 거의 항상 columns[0] 이라, 걸러
    // 내지 않으면 '첫 열' 폴백이 체크박스 열을 집어 이름이 통째로 비어 버린다.
    rowName: false,
    label: pick.length
      ? <SelectCheckbox checked={allOn} onChange={(on) => selection.setAll(pick, on)} label="전체 선택" />
      : null,
    render: (row, ctx) => (
      !eligible || eligible(row.id)
        ? <SelectCheckbox checked={selection.selected.has(row.id)} onChange={() => selection.toggle(row.id)}
            label={selectLabel(ctx && ctx.rowName)} />
        : null
    ),
  };
}

// 선택된 개수 + 동작 버튼(들)을 헤더 액션에 놓기 위한 래퍼. children 은 <Button>들.
export function BulkActions({ count, onClear, children }) {
  if (!count) return null;
  return (
    <span className="k-bulkactions">
      <span className="k-bulkactions-count">{count}개 선택</span>
      {children}
      <Button size="sm" variant="ghost" onClick={onClear}>해제</Button>
    </span>
  );
}
