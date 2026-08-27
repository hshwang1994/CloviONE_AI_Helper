import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

/* 상태 알약이 자기 라벨보다 작아지지 않는다 (A3 재검수).
 *
 * 실측(내 티켓): 칸 126px 인데 알약 34.4px 로 줄어 「검…」으로 잘렸다. `InlineEdit` 이
 * 감싸는 사슬(`span>button>.k-badge>label`)이 전부 `flex:0 1 auto` + `min-width:0` +
 * `overflow:hidden` 이었던 것이 원인이다. 되돌린 코드로 이 시험이 깨지는 것으로 회귀를
 * 고정한다 — 팀 티켓(InlineEdit 없이 Badge 만 쓰는 화면)은 이 결함이 없었으므로, 사슬의
 * 어느 마디를 고쳐도 이 시험은 Badge 단독 렌더와 InlineEdit 로 감싼 렌더 둘 다를 본다. */

import { Badge } from "./kit.jsx";
import { InlineEdit } from "./InlineEdit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

function draw(ui) {
  return render(<ThemeModeProvider>{ui}</ThemeModeProvider>);
}

describe("Badge — 알약은 줄어들지 않는다", () => {
  it("Badge 자신이 flex-shrink:0 이고 min-width 가 0 이 아니다", () => {
    draw(<Badge value="검증" />);
    const badge = screen.getByText("검증").closest(".k-badge");
    const cs = getComputedStyle(badge);
    expect(cs.flexShrink).toBe("0");
    expect(cs.minWidth).not.toBe("0px");
  });

  it("좁은 flex 부모 안에서도 InlineEdit 이 감싼 Badge 가 줄어들지 않는다", () => {
    draw(
      <div style={{ display: "flex", width: "20px", overflow: "hidden" }}>
        <InlineEdit
          value="검증"
          canEdit
          options={[{ value: "검증", label: "검증" }]}
          label="상태"
          render={(v) => <Badge value={v} />}
        />
      </div>,
    );
    const badge = screen.getByText("검증").closest(".k-badge");
    const button = badge.closest("button");
    expect(getComputedStyle(badge).flexShrink).toBe("0");
    expect(getComputedStyle(button).minWidth).toBe("max-content");
  });
});
