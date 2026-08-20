import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { PeopleFilter, filterPeople } from "./peoplePicker.jsx";

/* W5 — 사람 고르기에 **검색이 먼저** 있어야 한다 (F-W5D-129 ①).
 *
 * 예전에는 `/api/team-chat/directory` 전량을 스크롤 상자에 그대로 쏟았다. 서른 명일 때는
 * 훑을 수 있지만 삼백 명이면 이름을 알면서도 눈으로 찾아야 한다 — `EntityCombobox` 를 만든
 * 것과 정확히 같은 이유다. 여기서 Combobox 를 쓰지 않는 이유는 **여러 명**을 고르는 자리라
 * 고른 사람이 목록에 체크로 남아야 하기 때문이다. 문제는 같고 답의 모양만 다르다.
 */

const PEOPLE = [
  { user_id: "u1", display_name: "김담당", email: "kim@example.com" },
  { user_id: "u2", display_name: "이설계", email: "lee@example.com" },
  { user_id: "u3", name: "박운영", email: "park@corp.co.kr" },
];

describe("filterPeople — 이름으로도 이메일로도 찾는다", () => {
  it("🔴 이름의 일부로 좁힌다", () => {
    expect(filterPeople(PEOPLE, "담당").map((u) => u.user_id)).toEqual(["u1"]);
  });

  it("🔴 이메일의 일부로도 좁힌다 — 동명이인은 이메일로만 갈린다", () => {
    expect(filterPeople(PEOPLE, "corp").map((u) => u.user_id)).toEqual(["u3"]);
  });

  it("대소문자를 가리지 않는다", () => {
    expect(filterPeople(PEOPLE, "KIM@")).toHaveLength(1);
  });

  it("조건이 비면 전부 그대로 준다 — 빈 조건은 조건이 아니다", () => {
    expect(filterPeople(PEOPLE, "   ")).toHaveLength(3);
    expect(filterPeople(PEOPLE, "")).toHaveLength(3);
  });

  it("후보가 없어도 죽지 않는다(아직 안 온 목록)", () => {
    expect(filterPeople(undefined, "김")).toEqual([]);
  });
});

describe("PeopleFilter — 조건과 결과의 관계를 말한다", () => {
  it("🔴 조건이 없으면 건수 줄을 그리지 않는다 — 「전체 12명 / 12명」은 소음이다", () => {
    render(<PeopleFilter value="" onChange={() => {}} count={12} total={12} />);
    expect(screen.queryByText(/전체 12명/)).toBeNull();
  });

  it("🔴 조건이 있으면 몇 명 중 몇 명인지 말한다", () => {
    render(<PeopleFilter value="김" onChange={() => {}} count={1} total={12} />);
    expect(screen.getByText("1명 / 전체 12명")).toBeInTheDocument();
  });

  it("검색 상자에는 이름이 있다 — 스크린리더가 부를 수 있어야 한다", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<PeopleFilter value="" onChange={onChange} count={3} total={3} />);
    const box = screen.getByRole("searchbox", { name: "사람 좁히기" });
    await user.type(box, "김");
    expect(onChange).toHaveBeenCalledWith("김");
  });
});
