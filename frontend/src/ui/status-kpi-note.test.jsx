import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";

/* 요약 줄이 **무엇을 세는가**를 한 줄로 말한다 (D-484).
 *
 * 회의의 요약 타일은 누르는 단추가 아니다 — 예전에는 눌리는 타일과 안 눌리는 타일이 같은
 * 얼굴이라 사용자가 규칙을 못 배웠고, 누르면 작업 보드로 튕겼다. 이제 타일은 읽는 것이고
 * 줄 아래 캡션이 「회차 전체의 숫자」라고 말한다. */

import { ThemeModeProvider } from "./ThemeModeProvider.jsx";
import { StatusKpiStrip } from "./StatusKpi.jsx";

describe("StatusKpiStrip 의 note", () => {
  it("캡션이 줄 아래 서고, onClick 없는 타일은 단추가 아니다", () => {
    render(
      <ThemeModeProvider>
        <StatusKpiStrip
          ariaLabel="이번 회차 요약"
          note="회차 전체의 숫자입니다."
          items={[
            { label: "전체", value: "4", primary: true },
            { label: "완료", value: "1", kind: "ok", pct: 25 },
          ]}
        />
      </ThemeModeProvider>,
    );
    const group = screen.getByRole("group", { name: "이번 회차 요약" });
    expect(within(group).queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByText("회차 전체의 숫자입니다.")).toBeTruthy();
    expect(group.textContent).toContain("25%");
  });

  it("note 가 없으면 예전과 같다 — 캡션 없이 줄만 선다", () => {
    render(
      <ThemeModeProvider>
        <StatusKpiStrip ariaLabel="요약" items={[{ label: "전체", value: "4" }]} />
      </ThemeModeProvider>,
    );
    expect(screen.getByRole("group", { name: "요약" })).toBeTruthy();
    expect(screen.queryByText(/숫자입니다/)).toBeNull();
  });
});
