import React from "react";
import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";

/* `@tanstack/react-virtual` 감싸개의 계약 (§15.1 · §18.2).
 *
 * 가상화한 목록의 QA 프로브는 「그려진 행 수」 대신 「총 건수 표시」와 「스크롤 뒤 마지막
 * 행이 온전히 보인다」를 본다 — 안 그러면 가상화가 "행이 사라졌다"로 오탐된다. 여기서는
 * 그 계약이 실제로 성립하는지 본다: 총 건수는 렌더된 행 수와 무관하게 정확하고, 목록
 * 전체 높이는 행 수 × 예상 높이와 일치한다(끝까지 스크롤하면 마지막 행이 실제로 있다).
 *
 * jsdom 은 레이아웃이 없어 `ResizeObserver`/`clientHeight` 를 손으로 준다 — 그러지
 * 않으면 가상화 계산 자체가 항상 빈 뷰포트(0px)로 떨어진다.
 */

import { VirtualRows } from "./VirtualRows.jsx";

beforeAll(() => {
  global.ResizeObserver = global.ResizeObserver || class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  // jsdom 은 레이아웃이 없어 `offsetWidth`/`offsetHeight` 가 항상 0 이다 — react-virtual
  // 의 초기 측정(`getRect`)과 행별 재측정(`measureElement`)이 이 값을 그대로 읽는다.
  // 스크롤 창 자신은 400px(뷰포트), 각 행(`data-index` 를 가진 요소)은 이 시험의
  // `ROW_HEIGHT`(40px) 를 돌려준다 — 실제 브라우저에서 글자 한 줄짜리 행이 재는 값과
  // 같은 크기다. 다르게 주면 `measureElement` 의 재측정이 예상 높이를 덮어써 총 높이가
  // 어긋난다.
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get() { return this.hasAttribute("data-index") ? 40 : 400; },
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get() { return this.hasAttribute("data-index") ? 800 : 800; },
  });
});

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
