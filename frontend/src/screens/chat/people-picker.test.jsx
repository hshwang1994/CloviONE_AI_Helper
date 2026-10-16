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

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
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

/* 목록 줄은 이름 옆에 부서 · 직급을 함께 보여 준다(`affiliation`). 보이는 글자로 찾을 수 있어야 하고, 대조는 서버 검색과
 * 같은 접기다(`lib/search.js`) — 공백 · 대소문자 · 전각 표기가 결과를 바꾸지 않는다. */
const STAFF = [
  { user_id: "u1", display_name: "김담당", email: "kim@example.com", dept: "플랫폼 개발팀", title: "책임" },
  { user_id: "u2", display_name: "이설계", email: "lee@example.com", dept: "디자인팀", title: "팀장" },
  { user_id: "u3", name: "Park Woon", email: "park@corp.co.kr", dept: "ClovirONE 운영", title: "매니저" },
];
const ids = (list) => list.map((u) => u.user_id);

describe("filterPeople — 부서 · 직급으로도 찾고, 공백 · 대소문자 · 전각 표기를 가리지 않는다", () => {
  it("🔴 부서의 일부로 좁힌다", () => {
    expect(ids(filterPeople(STAFF, "개발팀"))).toEqual(["u1"]);
    expect(ids(filterPeople(STAFF, "디자인"))).toEqual(["u2"]);
  });

  it("🔴 직급으로도 좁힌다", () => {
    expect(ids(filterPeople(STAFF, "팀장"))).toEqual(["u2"]);
    expect(ids(filterPeople(STAFF, "매니저"))).toEqual(["u3"]);
  });

  it("공백을 붙이든 띄우든 같은 사람이 남는다 — 부서 이름 쪽 공백도 접는다", () => {
    for (const q of ["플랫폼개발", "플랫폼 개발", " 플랫폼   개발 ", "플랫폼\u{3000}개발"]) {
      expect(ids(filterPeople(STAFF, q)), q).toEqual(["u1"]);
    }
  });

  it("대소문자 · 전각 표기가 달라도 같은 사람이 남는다", () => {
    for (const q of ["clovirone", "CLOVIRONE", "ＣｌｏｖｉｒＯＮＥ", "park woon", "PARKWOON"]) {
      expect(ids(filterPeople(STAFF, q)), q).toEqual(["u3"]);
    }
  });

  it("칸을 이어 붙여 찾지 않는다 — 이름 끝과 부서 머리를 붙인 글자는 안 걸린다", () => {
    expect(filterPeople(STAFF, "담당플랫폼")).toEqual([]);
  });

  it("공백 · 제로폭 문자만 친 조건은 조건이 아니다", () => {
    expect(filterPeople(STAFF, "\u{3000}")).toHaveLength(3);
    expect(filterPeople(STAFF, "\u{200B}")).toHaveLength(3);
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

  it("칸 안내 글자는 자리마다 받는다 — 기본은 「이름, 이메일로 좁히기」이고 대조 규칙은 한 벌이다", () => {
    const { unmount } = render(<PeopleFilter value="" onChange={() => {}} count={3} total={3} />);
    expect(screen.getByRole("searchbox", { name: "사람 검색" })).toHaveAttribute("placeholder", "이름, 이메일 검색");
    unmount();
    // 채팅방 참여자 명단은 줄에 이메일이 없고 부서가 보인다(`ChatRoomMembers.jsx::MemberRoster`).
    render(<PeopleFilter value="" onChange={() => {}} count={9} total={9} placeholder="이름, 부서 검색" />);
    expect(screen.getByRole("searchbox", { name: "사람 검색" })).toHaveAttribute("placeholder", "이름, 부서 검색");
  });

  it("검색 상자에는 이름이 있다 — 스크린리더가 부를 수 있어야 한다", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<PeopleFilter value="" onChange={onChange} count={3} total={3} />);
    const box = screen.getByRole("searchbox", { name: "사람 검색" });
    await user.type(box, "김");
    expect(onChange).toHaveBeenCalledWith("김");
  });
});
