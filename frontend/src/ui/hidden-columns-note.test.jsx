import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { HiddenColumnsNote, columnShouldTruncate } from "./kit.jsx";
import { selectionColumn } from "./bulkSelect.jsx";

/* 좁은 칸에서 표가 열을 뺄 때 **하는 말이 사실인가**.
 *
 * 「행을 열면 전체 정보를 볼 수 있습니다」는 행을 열 수 있는 표에서만 사실이다. 이 저장소에는
 * `onRow` 를 안 주는 표가 여럿 있고(휴지통이 그렇다) 거기서는 열 방법이 아예 없다 —
 * 그 문장을 읽은 사람은 없는 길을 찾아다닌다. 안내가 없는 것보다 **없는 길을 가리키는
 * 안내**가 더 나쁘다.
 *
 * 같은 파일에서 `columnShouldTruncate` 의 가드도 함께 잰다. 두 결함의 뿌리가 같다 —
 * 공용 부품이 호출부의 사정을 안 물어보고 한 가지 답만 내는 것.
 */

const HIDDEN = [{ key: "deleted_by", label: "삭제한 사람" }, { key: "deleted_at", label: "삭제일" }];

describe("숨긴 열 안내", () => {
  it("행을 열 수 있는 표에서는 그렇게 말한다", () => {
    render(<HiddenColumnsNote columns={HIDDEN} openable />);
    expect(screen.getByText(/행을 열면 전체 정보를 볼 수 있습니다/)).toBeInTheDocument();
  });

  it("🔴 행을 열 수 없는 표에서는 **없는 길을 가리키지 않는다**", () => {
    render(<HiddenColumnsNote columns={HIDDEN} />);
    expect(screen.queryByText(/행을 열면/)).toBeNull();
    expect(screen.getByText(/창을 넓히면 다시 보입니다/)).toBeInTheDocument();
  });

  it("어느 쪽이든 **무엇이** 빠졌는지는 이름으로 말한다", () => {
    const { unmount } = render(<HiddenColumnsNote columns={HIDDEN} />);
    expect(screen.getByText(/삭제한 사람, 삭제일/)).toBeInTheDocument();
    unmount();
    render(<HiddenColumnsNote columns={HIDDEN} openable />);
    expect(screen.getByText(/삭제한 사람, 삭제일/)).toBeInTheDocument();
  });

  it("뺀 열이 없으면 아무 말도 안 한다", () => {
    const { container } = render(<HiddenColumnsNote columns={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("자르기 가드", () => {
  /* 🔴 `ellipsis` prop 이 「행 동작·선택 열은 안 자른다」는 규칙을 통째로 우회했다.
     자르기 갈래는 `maxWidth: 0; overflow: hidden` 을 무조건 걸어서, 표 전체에 `ellipsis`
     를 건 화면(휴지통)에서 「복원 / 영구 삭제」 단추와 체크박스가 칸이 좁아지면 잘렸다. */
  it("🔴 행 동작 열은 `ellipsis` 를 걸어도 안 자른다", () => {
    expect(columnShouldTruncate({ key: "_actions", type: "actions", render: () => null }, true)).toBe(false);
  });

  /* 🔴 **제품이 실제로 만드는 열**로 잰다.
   *
   * 처음에는 `{ key: "_sel", type: "select" }` 라는 손으로 지은 객체를 넣었는데, 이
   * 저장소에서 선택 열을 만드는 유일한 자리(`selectionColumn`)는 그때 `type` 을 안 붙이고
   * 있었다 — 즉 시험은 **앱이 한 번도 만들지 않는 모양**을 재고 있었고 가드의 그쪽 갈래는
   * 죽은 코드였다. 합성 객체로 재면 이런 것이 안 보인다. */
  it("🔴 선택 열도 안 자른다 — 진짜 `selectionColumn` 이 돌려준 열로 잰다", () => {
    const sel = { selected: new Set(), toggle: () => {}, setAll: () => {}, clear: () => {} };
    const col = selectionColumn(sel, ["a", "b"]);
    expect(col.type).toBe("select");
    expect(columnShouldTruncate(col, true)).toBe(false);
  });

  it("반례 — 글자 열은 그대로 자른다(가드를 전부로 넓히면 말줄임이 사라진다)", () => {
    expect(columnShouldTruncate({ key: "title", type: "title" }, false)).toBe(true);
    expect(columnShouldTruncate({ key: "space", type: "name", render: () => null }, true)).toBe(true);
    // `render` 가 있는 날짜 열은 `ellipsis` 없이는 안 자른다 — 알약·배지가 중간에서 깨진다.
    expect(columnShouldTruncate({ key: "deleted_at", type: "datetime", render: () => null }, false)).toBe(false);
  });
});
