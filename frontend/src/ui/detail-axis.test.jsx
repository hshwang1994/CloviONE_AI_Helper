import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

/* 곁열 없는 상세에서 제목과 본문이 같은 왼쪽 모서리에서 시작한다 (C1 재검수).
 *
 * 실측: `/board/{id}` 에서 `PageHeader` 가 `DetailLayout` **밖**에 있어, 2560 에서
 * 제목은 x≈0(콘텐츠 영역 전체 폭), 본문은 x≈820(46rem 으로 좁혀 가운데 선 열)에 섰다.
 * jsdom 은 실제 좌표를 재지 못하므로, 여기서는 **그 좌표 차이를 만드는 구조**를 본다 —
 * 머리글과 본문이 폭 제약을 공유하는 같은 상자의 자손인가.
 */

import { DetailPage, DetailLayout, DETAIL_SOLO_WIDTH } from "./DetailLayout.jsx";

describe("DetailPage — 곁열 없을 때 머리글과 본문이 같은 상자를 공유한다", () => {
  it("header 와 children 이 같은 maxWidth 상자의 형제 자손이다(다른 상자에 있지 않다)", () => {
    const { container } = render(
      <DetailPage header={<h1 data-testid="head">제목</h1>}>
        <p data-testid="body">본문</p>
      </DetailPage>,
    );
    const solo = container.querySelector('[data-detail-layout="solo-page"]');
    expect(solo).not.toBeNull();
    expect(getComputedStyle(solo).maxWidth).toBe(DETAIL_SOLO_WIDTH);
    // 제목과 본문 **모두** 이 상자의 직계 자손이다 — 상자 밖(그래서 폭 제약을 안 받는)에
    // 있으면 옛 결함(제목 x≈0, 본문 x≈820)이 그대로 재현된다.
    expect(solo.querySelector('[data-testid="head"]')).not.toBeNull();
    expect(solo.querySelector('[data-testid="body"]')).not.toBeNull();
  });

  it("곁열이 있으면 머리글은 폭 제약 밖에서 전체 폭을 그대로 쓴다(두 열 자체가 이미 폭 전체다)", () => {
    const { container } = render(
      <DetailPage header={<h1 data-testid="head">제목</h1>} aside={<aside data-testid="aside">곁열</aside>}>
        <p data-testid="body">본문</p>
      </DetailPage>,
    );
    const split = container.querySelector('[data-detail-layout="split-page"]');
    expect(split).not.toBeNull();
    expect(getComputedStyle(split).maxWidth).not.toBe(DETAIL_SOLO_WIDTH);
    const grid = container.querySelector('[data-detail-layout="split"]');
    expect(grid).not.toBeNull();
    expect(grid.querySelector('[data-testid="body"]')).not.toBeNull();
    expect(grid.querySelector('[data-testid="aside"]')).not.toBeNull();
  });

  it("기존 DetailLayout(머리글 없이 감싸기만 하는 자리)은 그대로 산다 — 회귀 0", () => {
    const { container } = render(
      <DetailLayout>
        <p data-testid="body">본문</p>
      </DetailLayout>,
    );
    const solo = container.querySelector('[data-detail-layout="solo"]');
    expect(solo).not.toBeNull();
    expect(getComputedStyle(solo).maxWidth).toBe(DETAIL_SOLO_WIDTH);
  });
});
