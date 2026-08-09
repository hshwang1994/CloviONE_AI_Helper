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

function renderField(settingKey, val, extra = {}) {
  return render(
    <StructuredObjectFields
      settingKey={settingKey}
      val={val}
      onChange={() => {}}
      canWrite={true}
      describedBy={undefined}
      invalid={false}
      {...extra}
    />,
  );
}

describe("StructuredObjectFields — session_policy", () => {
  it("크래시 없이 렌더되고 fmtDuration으로 값을 사람이 읽는 단위로 보여준다", () => {
    const val = JSON.stringify({ idle_timeout_seconds: 1800, absolute_timeout_seconds: 28800 });
    renderField("session_policy", val);
    expect(screen.getByText("= 30분")).toBeInTheDocument();
    expect(screen.getByText("= 8시간")).toBeInTheDocument();
  });
});

// SONNET_HANDOFF §5 완료 기준: STRUCTURED_OBJECT_KEYS 4개를 각각 렌더하는 스모크 테스트
// (이 화면군에 렌더 테스트가 0개였다). session_policy는 위에서 이미 다뤘으니 나머지 셋.
describe("StructuredObjectFields — 나머지 STRUCTURED_OBJECT_KEYS 3종 (스모크)", () => {
  it("password_policy: 크래시 없이 렌더되고 저장된 값을 보여준다", () => {
    renderField("password_policy", JSON.stringify({ min_length: 12, min_classes: 3 }));
    expect(screen.getByLabelText("최소 글자 수(8~128자)")).toHaveValue(12);
    expect(screen.getByLabelText("문자 종류 수(1~4)")).toHaveValue(3);
  });

  it("allowed_email_domains: 도메인이 있으면 칩으로, 비어 있으면 빈 상태 문구를 보여준다", () => {
    const { unmount } = renderField("allowed_email_domains", JSON.stringify(["goodmit.co.kr"]));
    expect(screen.getByText("goodmit.co.kr")).toBeInTheDocument();
    unmount();
    renderField("allowed_email_domains", JSON.stringify([]));
    expect(screen.getByText("제한 없음(모든 이메일 도메인 허용)")).toBeInTheDocument();
  });

  it("ui_branding: 크래시 없이 렌더되고 저장된 값을 보여준다", () => {
    renderField("ui_branding", JSON.stringify({ product_name: "ClovirAssist", support_email: "help@goodmit.co.kr" }));
    expect(screen.getByLabelText("제품명")).toHaveValue("ClovirAssist");
    expect(screen.getByLabelText("지원 이메일")).toHaveValue("help@goodmit.co.kr");
  });

  it("파싱 실패(잘못된 JSON)에도 크래시하지 않고 빈 값으로 안전 폴백한다", () => {
    // advanced(raw JSON) 모드에서 편집 중일 때 이 컴포넌트가 잠깐 유효하지 않은 val을 받을 수
    // 있다 - obj=null 폴백(safe={})이 실제로 렌더를 막지 않는지 네 타입 전부에서 확인한다.
    for (const key of ["password_policy", "session_policy", "ui_branding"]) {
      const { unmount } = renderField(key, "{ not valid json");
      unmount();
    }
    renderField("allowed_email_domains", "{ not valid json");
    expect(screen.getByText("제한 없음(모든 이메일 도메인 허용)")).toBeInTheDocument();
  });
});
