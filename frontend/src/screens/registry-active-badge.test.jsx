/* qa-contract-change: S11 이 templates·runners·workflows 화면을 걷어내 이 규칙(활성 배지는 필터와 같은 어휘를 쓰고 비활성은 주의 톤이다)의 소비자가 다섯에서 둘로 줄었다. 규칙 자체와 남은 둘(스케줄·연동)에 거는 단언은 한 글자도 안 약해졌다 — 사라진 것은 규칙이 아니라 그것을 지나던 화면이다. */
import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { REGISTRY } from "./registry.js";
import { DataTable } from "../ui/kit.jsx";

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

/* WF1 R1 — 백업(backup) 목록의 '크기' 열이 숫자인데도 align:"right"가 없어 문자열처럼
 * 왼쪽 정렬됐다 — governance.js·authoring.js 등 8곳이 이미 쓰는 관례(숫자는 자릿수를 눈으로
 * 비교할 수 있게 오른쪽 정렬)에서 이 화면만 빠져 있었다. DataTable 자체의 align 배선은
 * 이미 여러 화면이 실사용 중이지만 정작 그 배선을 직접 검증하는 시험이 저장소에 없었다 —
 * 이 김에 REGISTRY의 실제 설정으로 렌더링까지 확인한다(값만 보는 정적 검사가 아니라). */
describe("backup 목록의 '크기' 열", () => {
  it("REGISTRY 설정이 오른쪽 정렬이고, 실제로 그렇게 렌더된다", () => {
    const cols = REGISTRY.backup.columns;
    const sizeCol = cols.find((c) => c.key === "size_bytes");
    expect(sizeCol.align).toBe("right");

    const { container } = render(
      <DataTable columns={cols} rows={[{ path: "web-20260101.sqlite3", status: "verified", size_bytes: 1024 }]} rowKey={(r) => r.path} />,
    );
    const headerCell = container.querySelector("th:nth-child(3)");
    const bodyCell = container.querySelector("td:nth-child(3)");
    expect(headerCell).toHaveTextContent("크기");
    expect(headerCell.className).toMatch(/alignRight/);
    expect(bodyCell.className).toMatch(/alignRight/);
  });
});
