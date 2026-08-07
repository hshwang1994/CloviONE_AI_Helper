import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { MembersList } from "./MembersList.jsx";

/* 참여자 줄의 소속 표기 순서 — 앱 전체가 "부서 직책" 순서를 쓴다.
 *
 * `lib/people.js::affiliation` / `lib/format.js::affiliationOf` / `app/core/people.py::affiliation`
 * 모두 dept 를 먼저, title 을 나중에 붙인다("개발본부 팀장"). 이 파일만 배열을 손으로
 * `[m.title, m.dept]` 순서로 만들고 그 순서 그대로 그려서, 같은 두 값이 게임방에서만
 * "팀장 개발본부"로 뒤집혀 보였다 — 다른 화면을 보다가 게임방에 들어오면 소속 표기가
 * 이 화면만 거꾸로 읽힌다. */

const ROOM = { host_user_id: "h1" };
const YOU = { user_id: "u9" };

function renderList(members) {
  return render(
    <MembersList members={members} room={ROOM} you={YOU} submissionActive={false} submittedSet={new Set()} />
  );
}

describe("참여자 목록 소속 표기 순서", () => {
  it("부서가 직책보다 먼저 나온다(다른 화면과 같은 순서)", () => {
    const { container } = renderList([
      { user_id: "u1", name: "김하나", dept: "개발본부", title: "팀장", role: "player" },
    ]);
    const text = container.textContent;
    // "개발본부"가 "팀장"보다 앞에 와야 한다 — 뒤집히면 이 인덱스 비교가 실패한다.
    expect(text.indexOf("개발본부")).toBeGreaterThanOrEqual(0);
    expect(text.indexOf("팀장")).toBeGreaterThanOrEqual(0);
    expect(text.indexOf("개발본부")).toBeLessThan(text.indexOf("팀장"));
  });
});
