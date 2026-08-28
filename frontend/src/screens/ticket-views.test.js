import { describe, it, expect } from "vitest";

import { PERSON_FACE_KEYS, TICKET_VIEW_KEYS } from "./ticket-views.js";

describe("얼굴을 그리는 질의 키", () => {
  it("아바타를 바꾸면 상단바와 티켓·게시판·채팅을 같이 무효화한다", () => {
    expect(PERSON_FACE_KEYS).toEqual(expect.arrayContaining([
      ["me"], ["board"], ["conversations"], ["messages"], ["knowledge"],
      ["team-chat-rooms"], ["users"], ["ticket-comments"], ["doc-comments"],
    ]));
    expect(TICKET_VIEW_KEYS).toEqual(expect.arrayContaining([
      ["ticket"], ["tickets"], ["work-board"], ["work-backlog"], ["home"],
    ]));
  });
});
