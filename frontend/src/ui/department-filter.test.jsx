/* 부서 필터 (0060 §32) — 목록을 어느 팀 것으로 좁힐 것인가.
 *
 * 세 가지를 못박는다:
 *
 *  1. **후보는 서버가 준다.** 프런트가 조직도를 스스로 훑어 만들면 서버 검증
 *     (`app/org/context.py`)과 갈라지고, 갈라진 쪽이 넓으면 사용자는 고를 수는 있는데
 *     404 만 보는 상자를 얻는다.
 *  2. **경로로 보여 준다.** '개발팀' 하나로는 어느 줄기인지 알 수 없고, 조직 개편으로
 *     같은 이름이 다른 자리에 생기면 구분이 아예 불가능해진다.
 *  3. **고를 것이 하나면 안 그린다.** 선택지가 하나인 선택기는 정보가 아니라 소음이다.
 */
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DepartmentFilter } from "./filters.jsx";

const TWO = {
  options: [
    { id: "d1", name: "A-1팀", path: [{ id: "d0", name: "A본부" }, { id: "d1", name: "A-1팀" }] },
    { id: "d2", name: "A-2팀", path: [{ id: "d0", name: "A본부" }, { id: "d2", name: "A-2팀" }] },
  ],
};

describe("부서 필터", () => {
  it("후보를 **경로로** 보여 준다 — 이름 하나로는 어느 줄기인지 알 수 없다", async () => {
    render(<DepartmentFilter departments={TWO} value="" onChange={() => {}} />);
    await userEvent.click(screen.getByRole("combobox"));
    expect(await screen.findByRole("option", { name: "A본부 › A-1팀" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "A본부 › A-2팀" })).toBeTruthy();
  });

  it("고른 값을 그대로 올려 보낸다", async () => {
    const onChange = vi.fn();
    render(<DepartmentFilter departments={TWO} value="" onChange={onChange} />);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.click(await screen.findByRole("option", { name: "A본부 › A-2팀" }));
    expect(onChange).toHaveBeenCalledWith("d2");
  });

  it("전체로 되돌릴 수 있다 — 되돌릴 길이 없으면 필터가 함정이 된다", async () => {
    render(<DepartmentFilter departments={TWO} value="d1" onChange={() => {}} />);
    await userEvent.click(screen.getByRole("combobox"));
    expect(await screen.findByRole("option", { name: "내 범위 전체" })).toBeTruthy();
  });

  it("빈 값의 「내 범위 전체」는 포커스해도 자리표시자로 남는다", async () => {
    render(<DepartmentFilter departments={TWO} value="" onChange={() => {}} />);
    const input = screen.getByRole("combobox");
    expect(input.getAttribute("placeholder")).toBe("내 범위 전체");
    expect(input.value).toBe("");
    await userEvent.click(input);
    expect(input.getAttribute("placeholder")).toBe("내 범위 전체");
    expect(input.value).toBe("");
  });

  it("고를 것이 하나뿐이면 아무것도 안 그린다", () => {
    const one = { options: [TWO.options[0]] };
    const { container } = render(
      <DepartmentFilter departments={one} value="" onChange={() => {}} />
    );
    expect(container.querySelector("[role=combobox]")).toBeNull();
  });

  it("서버가 후보를 아직 안 줬으면 안 그린다 — 빈 상자는 고장으로 읽힌다", () => {
    const { container } = render(
      <DepartmentFilter departments={undefined} value="" onChange={() => {}} />
    );
    expect(container.querySelector("[role=combobox]")).toBeNull();
  });
});
