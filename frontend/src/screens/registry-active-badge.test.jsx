import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { REGISTRY } from "./registry.js";
import { DataTable } from "../ui/kit.jsx";

/* WF1 R1 — 템플릿(templates) 화면의 '활성' 열이 badgeCol("enabled", ...)이라 원시 불리언이
 * statusText를 타 "예"/"아니오"로 떴다. 바로 위 filters의 '활성'/'비활성' 어휘와 어긋났고,
 * 비활성(생성 직후 기본값 — 이 상태면 프롬프트·정책·입력값 바인딩·승인 정책이 전부 적용되지
 * 않는다)이 중립(회색) 톤이라 훑어보다 놓치기 쉬웠다. org-tree의 activeCol과 같은 이유로
 * 이 화면 자신의 필터와 같은 어휘 + 비활성=주의(warning) 톤을 쓰도록 고쳤다.
 */
function renderCol(spec, row) {
  return render(<div>{spec.render(row)}</div>);
}

describe("templates 목록의 '활성' 배지", () => {
  const col = REGISTRY.templates.columns.find((c) => c.key === "enabled");

  it("필터와 같은 어휘(활성/비활성)를 쓴다 — 원시 예/아니오가 아니다", () => {
    const { container: onC } = renderCol(col, { enabled: true });
    expect(onC).toHaveTextContent("활성");
    expect(onC).not.toHaveTextContent("예");

    const { container: offC } = renderCol(col, { enabled: false });
    expect(offC).toHaveTextContent("비활성");
    expect(offC).not.toHaveTextContent("아니오");
  });

  it("비활성은 중립이 아니라 주의(warning) 톤이다 — 프롬프트/정책/승인이 전부 안 먹는 상태다", () => {
    const { container: offC } = renderCol(col, { enabled: false });
    expect(offC.querySelector('[data-tone="warn"]')).toBeTruthy();
    expect(offC.querySelector('[data-tone="neutral"]')).toBeFalsy();

    const { container: onC } = renderCol(col, { enabled: true });
    expect(onC.querySelector('[data-tone="ok"]')).toBeTruthy();
  });
});

/* VIS-13 — templates(위)가 이미 고쳐 둔 이 패턴이 같은 저장소 안에서 4곳 더(스케줄·연동·
 * 러너·워크플로) badgeCol("enabled", ...)로 남아 있었다 — "활성"이 가장 중요한 사실인 화면인데
 * 원시 예/아니오 + 중립 톤이라 훑어보다 놓치기 쉬웠다. enabledCol 헬퍼로 한 번에 통일한다.
 */
describe.each([
  ["schedules", "스케줄"],
  ["integrations", "연동"],
  ["runners", "러너"],
  ["workflows", "워크플로"],
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
