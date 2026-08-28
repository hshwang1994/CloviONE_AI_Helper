import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

/* 머리글은 잘리지 않는다 (A4 재검수).
 *
 * 실측: 「예상 WD」·「실제 WD」 머리글이 client 40 / scroll 49 로 잘렸다(내 티켓·팀 티켓).
 * 원인은 열의 최소 폭이 아니라 `TableHeaderCell` 이 이름과 정렬 버튼의 감싸는 사슬에
 * `min-width:0` + `overflow:hidden` 을 걸어 둔 것이었다 — 칸(`th`)에는 자리가 있었는데
 * 안쪽 사슬이 스스로 줄어들며 글자를 지웠다. 되돌린 코드(옛 `LABEL_SX`/사슬)로 이 시험이
 * 깨지는 것으로 회귀를 고정한다. */

import { DataTable } from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

function draw(ui) {
  return render(<ThemeModeProvider>{ui}</ThemeModeProvider>);
}

describe("표 머리글 — 두 단어 이름도 잘리지 않는다", () => {
  it("정렬 가능한 number 열의 머리글이 overflow:hidden/텍스트 말줄임을 안 받는다", () => {
    draw(
      <DataTable
        columns={[
          { key: "est_wd", label: "예상 WD", type: "number", sortable: true },
          { key: "act_wd", label: "실제 WD", type: "number", sortable: true },
        ]}
        rows={[{ est_wd: 3, act_wd: 2 }]}
        rowKey={() => "r"}
        sort={{ key: "est_wd", dir: "asc" }}
        onSort={() => {}}
      />,
    );
    for (const name of ["예상 WD", "실제 WD"]) {
      const label = screen.getByText(name);
      expect(getComputedStyle(label).overflow).not.toBe("hidden");
      expect(getComputedStyle(label).textOverflow).not.toBe("ellipsis");
      // 감싸는 정렬 버튼도 스스로 줄어들지 않는다 — 칸에 자리가 있으면 이름 전체가 보인다.
      const button = label.closest("button");
      expect(button).not.toBeNull();
      expect(getComputedStyle(button).minWidth).toBe("max-content");
      // 칸 자체에 overflow:hidden 을 걸면 한글 받침과 정렬 아이콘이 아래로 잘린다.
      const th = label.closest("th");
      expect(th).not.toBeNull();
      expect(getComputedStyle(th).overflow).not.toBe("hidden");
      expect(getComputedStyle(th).verticalAlign).toBe("middle");
    }
  });

  it("정렬 없는 열의 머리글도 같은 계약이다", () => {
    draw(
      <DataTable
        columns={[{ key: "title", label: "아주 긴 두 단어 제목", type: "title" }]}
        rows={[{ title: "가" }]}
        rowKey={() => "r"}
      />,
    );
    const label = screen.getByText("아주 긴 두 단어 제목");
    expect(getComputedStyle(label).overflow).not.toBe("hidden");
    expect(getComputedStyle(label).textOverflow).not.toBe("ellipsis");
  });
});
