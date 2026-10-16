import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { MembersList, MembersRows } from "./MembersList.jsx";
import { ChatPanel } from "./ChatPanel.jsx";

/* 참여자 줄은 한 줄이다 (D-594).
 *
 * 예전 줄은 두 줄(이름 / 소속)이라 61px 였고, 레일의 참여자 판(13rem)에 세 명 남짓만 보였다. 이제 얼굴 · 이름 · (나) · 부서 · 직책이 글
 * 상자 하나에 인라인으로 서고, 넘치면 그 상자가 말줄임표로 자른다 — 전체 글은 `title`("이름 (부서 직책)", `lib/people.js::personLabel`)이
 * 든다. 24자 이름도 줄을 늘리지 않는다. 채팅의 보낸 사람 이름도 한 줄로 자르고 `title` 에 전체 이름을 둔다.
 *
 * 실제 높이(32px · 보이는 줄 수)는 실브라우저 하네스(`games_e2e.py --rail`)가 잰다 — 여기서는 구조 계약이다. */

const ROOM = { host_user_id: "h1" };
const YOU = { user_id: "u9" };
const LONG = "크리스티아나 알레한드라 페르난데스 로드리게스";

function rows(members, props = {}) {
  return render(
    <MembersList members={members} room={ROOM} you={YOU} submissionActive={false} submittedSet={new Set()} {...props} />
  );
}

describe("참여자 줄 — 한 줄 (D-594)", () => {
  it("이름 · (나) · 부서 · 직책이 글 상자 하나에 서고, 그 상자가 말줄임표로 자르며 title 이 전체 글이다", () => {
    const { container } = rows([
      { user_id: "u9", name: "김하나", dept: "개발본부", title: "팀장", role: "player" },
      { user_id: "h1", name: LONG, dept: "플랫폼개발팀", title: "선임", role: "host" },
    ]);
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(2);
    items.forEach((li) => {
      const texts = li.querySelectorAll("[title]");
      expect(texts).toHaveLength(1); // 줄 하나에 글 상자 하나 — 두 줄(이름 / 소속) 구조가 아니다
      const box = texts[0];
      const st = getComputedStyle(box);
      expect(st.whiteSpace).toBe("nowrap");
      expect(st.textOverflow).toBe("ellipsis");
      expect(st.overflow).toBe("hidden");
      // 글 상자 안은 인라인 조각뿐이다(블록 · 플렉스 자식이 있으면 줄이 접힌다).
      Array.from(box.children).forEach((child) => expect(child.tagName).toBe("SPAN"));
    });
    const mine = items[0].querySelector("[title]");
    expect(mine).toHaveAttribute("title", "김하나 (개발본부 팀장)");
    expect(mine.textContent).toBe("김하나 (나)개발본부팀장");
    const host = items[1].querySelector("[title]");
    expect(host).toHaveAttribute("title", `${LONG} (플랫폼개발팀 선임)`);
    // 배지는 글 상자 밖, 줄 끝에 선다(자르는 글에 딸려 사라지지 않는다).
    expect(within(items[1]).getByText("방장").closest("[title]")).toBeNull();
  });

  it("소속이 없으면 title 은 이름뿐이다", () => {
    const { container } = rows([{ user_id: "u1", name: "이두리", role: "player" }]);
    expect(container.querySelector("li [title]")).toHaveAttribute("title", "이두리");
  });

  it("fill 이면 목록(스크롤 칸)이 판이 준 높이를 채우고, 아니면 내용만큼 선다 — 13rem 천장은 없다", () => {
    const members = [{ user_id: "u1", name: "이두리", role: "player" }];
    const { container, rerender } = render(
      <MembersRows members={members} room={ROOM} you={YOU} submissionActive={false} submittedSet={new Set()} fill />
    );
    let area = container.querySelector(".k-scrollarea");
    expect(getComputedStyle(area).flexGrow).toBe("1");
    expect(getComputedStyle(area).maxHeight).not.toBe("13rem");
    rerender(<MembersRows members={members} room={ROOM} you={YOU} submissionActive={false} submittedSet={new Set()} />);
    area = container.querySelector(".k-scrollarea");
    expect(getComputedStyle(area).flexGrow).not.toBe("1");
    expect(getComputedStyle(area).maxHeight).not.toBe("13rem");
  });
});

describe("채팅 보낸 사람 이름 — 한 줄 (D-594)", () => {
  it("다른 사람의 이름은 말줄임표로 자르고 title 에 전체 이름을 둔다", () => {
    const msgs = [{ seq: 1, kind: "chat", actor_user_id: "u2", created_at: "2026-10-16T01:00:00", payload: { name: LONG, text: "안녕하세요!" } }];
    render(
      <ChatPanel chatLogRef={{ current: null }} chatMsgs={msgs} you={{ user_id: "u1" }} people={{}} draft="" setDraft={() => {}}
        sendChat={() => {}} chatPending={false} chatFailure={null} />
    );
    const name = screen.getByTitle(LONG);
    expect(name).toHaveTextContent(LONG);
    const st = getComputedStyle(name);
    expect(st.whiteSpace).toBe("nowrap");
    expect(st.textOverflow).toBe("ellipsis");
  });
});
