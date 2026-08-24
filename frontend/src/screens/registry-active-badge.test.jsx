/* qa-contract-change: S11 이 templates·runners·workflows 화면을 걷어내 이 규칙(활성 배지는 필터와 같은 어휘를 쓰고 비활성은 주의 톤이다)의 소비자가 다섯에서 둘로 줄었다. 규칙 자체와 남은 둘(스케줄·연동)에 거는 단언은 한 글자도 안 약해졌다 — 사라진 것은 규칙이 아니라 그것을 지나던 화면이다. */
import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { REGISTRY } from "./registry.js";
import { DataTable } from "../ui/kit.jsx";
import { COLUMN_TYPES } from "../ui/columnTypes.js";

function renderCol(spec, row) {
  return render(<div>{spec.render(row)}</div>);
}

/* VIS-13 — "활성"이 가장 중요한 사실인 화면들이 badgeCol("enabled", ...)로 원시 예/아니오
 * + 중립 톤을 쓰고 있었다 — 훑어보다 놓치기 쉬웠다. enabledCol 헬퍼로 한 번에 통일했다.
 *
 * 처음에는 다섯 화면이었다(템플릿·스케줄·연동·러너·워크플로). S11 이 그중 셋을 걷어냈고,
 * 규칙은 남은 둘이 그대로 진다 — 사라진 것은 소비자이지 규칙이 아니다.
 */
describe.each([
  ["schedules", "스케줄"],
  ["integrations", "연동"],
])("%s(%s) 목록의 '활성' 배지", (registryKey) => {
  const col = REGISTRY[registryKey].columns.find((c) => c.key === "enabled");

  it("필터와 같은 어휘(활성/비활성)를 쓴다 — 원시 예/아니오가 아니다", () => {
    const { container: onC } = renderCol(col, { enabled: true });
    expect(onC).toHaveTextContent("활성");

    const { container: offC } = renderCol(col, { enabled: false });
    expect(offC).toHaveTextContent("비활성");
    expect(offC).not.toHaveTextContent("아니오");
  });

  it("비활성은 중립이 아니라 주의(warning) 톤이다", () => {
    const { container: offC } = renderCol(col, { enabled: false });
    expect(offC.querySelector('[data-tone="warn"]')).toBeTruthy();
    expect(offC.querySelector('[data-tone="neutral"]')).toBeFalsy();

    const { container: onC } = renderCol(col, { enabled: true });
    expect(onC.querySelector('[data-tone="ok"]')).toBeTruthy();
  });
});

/* qa-contract-change: S16 이 열의 폭·정렬을 «값»에서 «의미»로 옮겼다(C3) — 열이 이제
 * `align:"right"` 대신 `type:"number"` 를 선언하고 정렬은 어휘표가 준다. 그래서 이 시험의
 * 앞절(REGISTRY 리터럴이 `align` 인가)은 검사할 대상이 사라졌다. 리터럴을 지우는 대신
 * **선언한 의미**를 검사하도록 다시 적고, 동시에 **약하지 않게 강화**한다: 옛 시험은
 * 우정렬만 봤는데 그것만으로는 자릿수가 세로로 안 맞는다 — `numeric_alignment` 8건이
 * 정확히 「우정렬은 맞는데 tabular-nums 가 없다」였다. 이제 셋을 다 본다.
 *
 * WF1 R1 — 백업(backup) 목록의 '크기' 열이 숫자인데도 문자열처럼 왼쪽 정렬됐던 자리다.
 * REGISTRY의 실제 설정으로 렌더링까지 확인한다(값만 보는 정적 검사가 아니라). */
describe("backup 목록의 '크기' 열", () => {
  it("REGISTRY 가 수치라고 선언하고, 우정렬 + 자릿수 고정으로 렌더된다", () => {
    const cols = REGISTRY.backup.columns;
    const sizeCol = cols.find((c) => c.key === "size_bytes");
    expect(sizeCol.type).toBe("number");
    expect(COLUMN_TYPES[sizeCol.type].align).toBe("right");

    const { container } = render(
      <DataTable columns={cols} rows={[{ path: "web-20260101.sqlite3", status: "verified", size_bytes: 1024 }]} rowKey={(r) => r.path} />,
    );
    const headerCell = container.querySelector("th:nth-child(3)");
    const bodyCell = container.querySelector("td:nth-child(3)");
    expect(headerCell).toHaveTextContent("크기");
    expect(headerCell.className).toMatch(/alignRight/);
    expect(bodyCell.className).toMatch(/alignRight/);
    // 🔴 옛 시험이 안 보던 것 — 자릿수가 세로로 맞아야 값을 비교할 수 있다.
    expect(getComputedStyle(bodyCell).fontVariantNumeric).toContain("tabular-nums");
  });
});
