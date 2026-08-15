import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { REGISTRY } from "./registry.js";

/* WF1 R4(단독 결함) — API(app/admin/feature_flags.py _items)가 이미 매 행에 default를
 * 내려주는데 목록 열에는 없고 상세 드로어에만 있었다. 목록만 훑어서는 "지금 값이 안전한
 * 기본값과 같은가"를 알 수 없었다(실사례: game_ai_enabled가 기본 OFF인데 켜져 있어도
 * 목록에서는 다른 플래그와 똑같이 중립으로 보였다). '기본값' 열 추가 + '현재' 열이
 * 어긋나면 warn 톤으로 신호한다.
 */
function findCol(key) {
  return REGISTRY["feature-flags"].columns.find((c) => c.key === key);
}

function renderCol(col, row) {
  return render(<div>{col.render(row)}</div>);
}

describe("기능 플래그 목록 — '기본값' 열과 어긋남 신호 (WF1 R4)", () => {
  it("'기본값' 열이 목록에 존재하고 실제 값을 보여준다", () => {
    const col = findCol("default");
    expect(col).toBeTruthy();
    const { container: onC } = renderCol(col, { default: true });
    expect(onC).toHaveTextContent("활성");
    const { container: offC } = renderCol(col, { default: false });
    expect(offC).toHaveTextContent("비활성");
  });

  it("현재 값이 기본값과 같으면 '현재' 배지가 warn이 아니다", () => {
    const col = findCol("value");
    const { container } = renderCol(col, { value: true, default: true });
    expect(container.querySelector(".MuiChip-colorWarning")).toBeFalsy();
  });

  it("현재 값이 기본값과 어긋나면(위험 플래그가 반대로 켜진 경우 등) '현재' 배지가 warn이다", () => {
    const col = findCol("value");
    // game_ai_enabled 실사례: 기본 OFF인데 켜져 있음.
    const { container: onDeviates } = renderCol(col, { value: true, default: false });
    expect(onDeviates.querySelector(".MuiChip-colorWarning")).toBeTruthy();
    // 반대 방향(기본 ON인데 꺼짐)도 어긋남이다.
    const { container: offDeviates } = renderCol(col, { value: false, default: true });
    expect(offDeviates.querySelector(".MuiChip-colorWarning")).toBeTruthy();
  });
});
