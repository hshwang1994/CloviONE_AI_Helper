import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { MembersList } from "./MembersList.jsx";

/* 참여자 명단과 추첨/팀나누기 대상 풀의 어긋남을 미리 알린다(step 9 #7).
 *
 * 명단엔 남아 있어도(active) 90초 넘게 폴링이 없으면 서버 확정 게임(추첨·팀나누기·사다리·
 * 투표)의 대상 풀(app/games/service.py::_present_players)에서는 조용히 빠진다 — 명단이
 * 그 자리비움을 표시할 수단이 없으면 "5명이 보이는데 4명 중에서 뽑힌다"가 결과로만 드러난다.
 */

const ROOM = { host_user_id: "h1" };
const YOU = { user_id: "u9" };

function renderList(members) {
  return render(
    <MembersList members={members} room={ROOM} you={YOU} submissionActive={false} submittedSet={new Set()} />
  );
}

describe("참여자 목록 — 자리 비움 표시", () => {
  it("present:false 인 참여자에게만 '자리 비움' 배지가 붙는다", () => {
    renderList([
      { user_id: "u1", name: "방금폴링", role: "player", present: true },
      { user_id: "u2", name: "오래조용", role: "player", present: false },
    ]);
    expect(screen.getAllByText("자리 비움")).toHaveLength(1);
  });

  it("present 필드가 아예 없으면(구버전 응답 등) 배지를 안 띄운다 — false 로 단정하지 않는다", () => {
    renderList([{ user_id: "u1", name: "김하나", role: "player" }]);
    expect(screen.queryByText("자리 비움")).toBeNull();
  });
});
