import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

/* H-2 회귀 고정: fmtDuration import 누락으로 '세션 정책' 편집기가 ReferenceError로
 * 크래시했다(ErrorBoundary가 화면 전체를 오류로 덮었다) — StructuredObjectFields.jsx가
 * 같은 디렉터리에 export된 fmtDuration을 import하지 않았다. 이 테스트는 렌더가 던지지
 * 않는 것과, 초 단위 값이 사람이 읽는 시간으로 옆에 나오는 것 둘 다 고정한다.
 */
import { StructuredObjectFields } from "./StructuredObjectFields.jsx";

describe("StructuredObjectFields — session_policy", () => {
  it("크래시 없이 렌더되고 fmtDuration으로 값을 사람이 읽는 단위로 보여준다", () => {
    const val = JSON.stringify({ idle_timeout_seconds: 1800, absolute_timeout_seconds: 28800 });
    render(
      <StructuredObjectFields
        settingKey="session_policy"
        val={val}
        onChange={() => {}}
        canWrite={true}
        describedBy={undefined}
        invalid={false}
      />,
    );
    expect(screen.getByText("= 30분")).toBeInTheDocument();
    expect(screen.getByText("= 8시간")).toBeInTheDocument();
  });
});
