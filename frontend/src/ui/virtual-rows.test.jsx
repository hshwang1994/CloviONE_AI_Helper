import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

/* `@tanstack/react-virtual` 감싸개의 계약 (§15.1 · §18.2).
 *
 * 가상화한 목록의 QA 프로브는 「그려진 행 수」 대신 「총 건수 표시」와 「스크롤 뒤 마지막
 * 행이 온전히 보인다」를 본다 — 안 그러면 가상화가 "행이 사라졌다"로 오탐된다. 여기서는
 * 그 계약이 실제로 성립하는지 본다: 총 건수는 렌더된 행 수와 무관하게 정확하고, 목록
 * 전체 높이는 행 수 × 예상 높이와 일치한다(끝까지 스크롤하면 마지막 행이 실제로 있다).
 *
 * jsdom 레이아웃 mock(`offsetHeight`/`offsetWidth` — 행 40px·그 외 400px)은
 * `test-setup.js` 가 전역으로 준다 — 이 부품 하나만의 사정이 아니라 `VirtualRows`/
 * `VirtualTableBody` 를 쓰는 모든 화면 시험이 같은 문제를 겪는다(WorkBoard 등). 아래
 * 숫자(500건 중 <50 렌더, 총 높이 = 행수×40)는 그 전역 값을 그대로 전제한다.
 */

import { VirtualRows } from "./VirtualRows.jsx";

const ROW_HEIGHT = 40;
const ITEMS = Array.from({ length: 500 }, (_, i) => ({ id: `r-${i}`, label: `행 ${i}` }));

describe("VirtualRows — 총 건수와 목록 전체 높이", () => {
  it("500건 중 눈에 보이는 것만 그리지만 총 건수는 500 그대로다", () => {
    render(
      <VirtualRows
        items={ITEMS}
        estimateSize={ROW_HEIGHT}
        getItemKey={(it) => it.id}
        renderItem={(it) => <div>{it.label}</div>}
        ariaLabel="시험 목록"
      />,
    );
    const list = screen.getByRole("list", { name: "시험 목록" });
    expect(list).toHaveAttribute("data-virtual-total", "500");
    // 뷰포트(400px)를 크게 넘는 행만 실제로 DOM 에 있다 — 500장을 전부 그리지 않는다.
    expect(screen.getAllByRole("listitem").length).toBeLessThan(50);
  });

  it("목록 전체 높이가 행 수 × 예상 높이와 같다 — 끝까지 스크롤하면 마지막 행이 실제로 있다", () => {
    const { container } = render(
      <VirtualRows
        items={ITEMS}
        estimateSize={ROW_HEIGHT}
        getItemKey={(it) => it.id}
        renderItem={(it) => <div>{it.label}</div>}
      />,
    );
    const inner = container.querySelector('[role="list"] > div');
    expect(getComputedStyle(inner).height).toBe(`${ITEMS.length * ROW_HEIGHT}px`);
  });

  it("행이 0건이면 총 건수도 0이고 목록 행이 없다(빈 상태는 호출부가 그린다)", () => {
    render(
      <VirtualRows
        items={[]}
        estimateSize={ROW_HEIGHT}
        renderItem={(it) => <div>{it.label}</div>}
        ariaLabel="빈 목록"
      />,
    );
    const list = screen.getByRole("list", { name: "빈 목록" });
    expect(list).toHaveAttribute("data-virtual-total", "0");
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });
});
