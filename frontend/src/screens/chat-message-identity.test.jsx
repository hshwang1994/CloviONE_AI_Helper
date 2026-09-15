import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 핸드오프 RULES §9(소유자 확정 채팅 규격)가 지시 17 의 「내 말에도 아바타와 이름」을 「내 말은 오른쪽 Primary 말풍선, 아바타 · 이름 없음」으로 바꿔, 내 말의 신원 단언을 「오른쪽 자리 + 말풍선 + 시각」으로 옮기고 이어지는 말 단언은 상대의 말로 잰다(시각 · 전체 날짜 · 구분선 계약은 그대로). */

/* 🔴 **모든 메시지가 누가 언제 썼는지 말한다** (지시 17 → 핸드오프 RULES §9).
 *
 * ## 이 파일이 왜 생겼나
 *
 * `ChatPane.jsx` 의 주석은 「자기가 쓴 메시지도 예외가 아니다: 누가 언제 썼는지는 언제나
 * 확인할 수 있어야 한다」라고 적고 있었다. 코드는 `{!mine ? <아바타와 이름> : null}` 이었다 —
 * **주석이 지키던 계약을 코드가 안 지켰다.** 내 말은 오른쪽 말풍선이었고 얼굴도 이름도
 * 없었으며, 시각은 `HH:MM` 뿐이라 어제 온 말과 오늘 온 말이 같아 보였다.
 *
 * 주석은 검사가 아니다. 여기서 그 계약을 시험으로 바꾼다.
 *
 * 지키는 것 넷:
 *   1. 내 말에도 아바타가 선다.
 *   2. 내 말에도 이름이 선다.
 *   3. 시간만 그리지 않는다 — 줄의 시각이 전체 날짜/시각을 `title` 로 들고 있고, 날이
 *      바뀌는 자리에는 구분선이 선다.
 *   4. 같은 사람의 이어지는 말은 머리를 반복하지 않지만, 그 줄도 자기 시각을 갖는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatPane } from "./ChatPane.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ME = "u1";
const PEER = "u2";

function msg(over = {}) {
  return {
    seq: 1, kind: "text", sender_user_id: ME, sender_name: "나",
    body: "안녕", created_at: "2026-08-03T01:02:03", mentions_me: false, images: [], ...over,
  };
}

function payload(messages) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "방", member_count: 2 },
    members: [
      { user_id: ME, name: "나", role: "owner", last_read_seq: 9, online: true },
      { user_id: PEER, name: "상대", role: "member", last_read_seq: 0, online: false },
    ],
    messages,
    seq: messages.length,
    you: { user_id: ME, role: "owner", last_read_seq: 9, is_member: true,
           can_disband: true, can_hide: false, can_manage: true },
  };
}

function mount(data) {
  apiMock.mockImplementation((url) => {
    if (String(url).startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(data);
    if (String(url).startsWith("/api/team-chat/directory")) return Promise.resolve({ users: [] });
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <ChatPane roomId="r1" interval={false} />
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>
  );
}

/** 그 본문이 들어 있는 줄. 줄은 `data-chat-row` 로 자기가 누구 말인지 말한다. */
async function rowOf(text) {
  const body = await screen.findByText(text);
  return body.closest("[data-chat-row]");
}

beforeEach(() => { apiMock.mockReset(); });

describe("모든 메시지가 신원을 갖는다", () => {
  it("🔴 내가 쓴 말은 오른쪽 Primary 말풍선이고 얼굴 · 이름을 되풀이하지 않는다 — 자리가 「나」를 말하고 시각은 남는다", async () => {
    mount(payload([msg({ seq: 1, body: "내가 쓴 말" })]));
    const row = await rowOf("내가 쓴 말");
    expect(row).toHaveAttribute("data-chat-row", "mine");
    // 오른쪽 자리 — 줄이 말풍선 묶음을 끝(오른쪽)으로 민다.
    expect(getComputedStyle(row).justifyItems).toBe("end");
    expect(row.querySelector('[data-chat-bubble="mine"]')).toBeTruthy();
    // 얼굴 · 이름은 상대의 말에만 선다(핸드오프 RULES §9 「나: 아바타 없음」).
    expect(row.querySelector(".k-avatar")).toBeNull();
    expect(within(row).queryByText("나")).toBeNull();
    // 언제 썼는지는 여전히 말한다.
    expect(row.querySelector("time")).toBeTruthy();
  });

  it("남이 쓴 말은 왼쪽 함몰면 말풍선에 얼굴 · 이름이 선다", async () => {
    mount(payload([msg({ seq: 1, sender_user_id: PEER, sender_name: "상대", body: "남이 쓴 말" })]));
    const row = await rowOf("남이 쓴 말");
    expect(row).toHaveAttribute("data-chat-row", "theirs");
    expect(within(row).getByText("상대")).toBeInTheDocument();
    // 아바타는 공용 부품이다 — 사진이 없으면 기본 그림이 선다(지시 6).
    expect(row.querySelector(".k-avatar")).toBeTruthy();
    expect(row.querySelector('[data-chat-bubble="theirs"]')).toBeTruthy();
  });

  it("🔴 시간만 보여 주지 않는다 — 줄의 시각이 전체 날짜를 들고 있다", async () => {
    mount(payload([msg({ seq: 1, body: "언제 썼나" })]));
    const row = await rowOf("언제 썼나");
    const time = row.querySelector("time");
    expect(time).toBeTruthy();
    // `dateTime` 은 기계가 읽는 값, `title` 은 사람이 읽는 값이다. 둘 다 날짜를 포함한다.
    expect(time.getAttribute("datetime")).toBe("2026-08-03T01:02:03");
    expect(time.getAttribute("title")).toMatch(/2026/);
  });
});

describe("날짜 구분선", () => {
  it("🔴 날이 바뀌면 구분선이 선다", async () => {
    mount(payload([
      msg({ seq: 1, body: "어제 말", created_at: "2026-08-03T01:00:00" }),
      msg({ seq: 2, body: "오늘 말", created_at: "2026-08-04T01:00:00" }),
    ]));
    await screen.findByText("어제 말");
    const seps = document.querySelectorAll("[data-day-separator]");
    expect(Array.from(seps).map((n) => n.getAttribute("data-day-separator")))
      .toEqual(["2026-08-03", "2026-08-04"]);
  });

  it("같은 날이면 구분선은 하나다", async () => {
    mount(payload([
      msg({ seq: 1, body: "첫 말", created_at: "2026-08-03T01:00:00" }),
      msg({ seq: 2, body: "둘째 말", created_at: "2026-08-03T09:00:00" }),
    ]));
    await screen.findByText("둘째 말");
    expect(document.querySelectorAll("[data-day-separator]")).toHaveLength(1);
  });
});

describe("연속 발언", () => {
  it("이어지는 말은 이름 · 얼굴을 반복하지 않는다", async () => {
    mount(payload([
      msg({ seq: 1, sender_user_id: PEER, sender_name: "상대", body: "첫 말", created_at: "2026-08-03T01:00:00" }),
      msg({ seq: 2, sender_user_id: PEER, sender_name: "상대", body: "이어지는 말", created_at: "2026-08-03T01:01:00" }),
    ]));
    await screen.findByText("이어지는 말");
    // 이름은 묶음의 첫 줄에만 — 다섯 줄을 연달아 쓴 사람의 이름이 다섯 번 서면
    // 대화가 아니라 명단으로 보인다.
    expect(screen.getAllByText("상대")).toHaveLength(1);
    expect((await rowOf("이어지는 말")).querySelector(".k-avatar")).toBeNull();
  });

  it("🔴 그래도 이어지는 줄이 자기 시각을 갖는다 — 언제 썼는지는 항상 확인 가능하다", async () => {
    mount(payload([
      msg({ seq: 1, body: "첫 말", created_at: "2026-08-03T01:00:00" }),
      msg({ seq: 2, body: "이어지는 말", created_at: "2026-08-03T01:01:00" }),
    ]));
    const row = await rowOf("이어지는 말");
    const gutter = row.querySelector("[data-row-time]");
    expect(gutter).toBeTruthy();
    expect(gutter.textContent.trim()).not.toBe("");
    expect(gutter.getAttribute("title")).toMatch(/2026/);
  });
});
