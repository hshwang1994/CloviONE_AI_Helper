/* 허용 이메일 도메인 칩의 "제거"가 키보드로 되는가 (whole-product 재감사, 2026-08-15).
 *
 * MUI Chip의 onDelete 아이콘은 tabIndex=-1이라 키보드로 못 뗀다(AssistantDrawer.jsx의
 * 첨부 제거 버튼 주석이 이미 이 함정을 적어 뒀다) — StructuredObjectFields만 그 함정에
 * 빠져 있었다. 독립적으로 포커스되는 IconButton으로 바꿨으니, 실제로 Tab이 닿고 클릭(=
 * 키보드 Enter/Space와 동일하게 동작하는 진짜 <button>)으로 지워지는지 확인한다. */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StructuredObjectFields } from "./StructuredObjectFields.jsx";

describe("StructuredObjectFields — allowed_email_domains 칩 제거", () => {
  it("제거 버튼이 독립적으로 포커스되는 진짜 button이고, 누르면 그 도메인만 지운다", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <StructuredObjectFields
        settingKey="allowed_email_domains"
        val={JSON.stringify(["a.example.com", "b.example.com"])}
        onChange={onChange}
        canWrite
      />
    );
    const removeA = screen.getByRole("button", { name: "a.example.com 제거" });
    const removeB = screen.getByRole("button", { name: "b.example.com 제거" });
    // 진짜 <button>이면 그 자체로 탭 순서에 들어간다 — tabIndex를 따로 주지 않아도 된다는 것이
    // 바로 "키보드로 닿는다"는 뜻이다(MUI Chip의 deleteIcon span은 이 속성이 없어서 문제였다).
    expect(removeA.tagName).toBe("BUTTON");
    expect(removeB.tagName).toBe("BUTTON");

    await user.click(removeA);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(JSON.parse(onChange.mock.calls[0][0])).toEqual(["b.example.com"]);
  });

  it("canWrite=false면 제거 버튼 자체가 없다(읽기 전용에서 지울 수 있는 척하지 않는다)", () => {
    render(
      <StructuredObjectFields
        settingKey="allowed_email_domains"
        val={JSON.stringify(["a.example.com"])}
        onChange={() => {}}
        canWrite={false}
      />
    );
    expect(screen.queryByRole("button", { name: "a.example.com 제거" })).not.toBeInTheDocument();
  });
});
