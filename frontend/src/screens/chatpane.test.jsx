import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* ChatPane 계약 테스트 — 이모지 삽입, Ctrl+V 이미지, 인라인 렌더, 읽음 커서.
 *
 * 지키려는 것 넷:
 *  1. 이모지 피커는 **초안에 글자를 넣는다** — 메시지를 곧장 보내지 않는다(오발신 방지).
 *  2. Ctrl+V 이미지는 FormData 로 팀 채팅 전용 업로드 경로에 간다. 텍스트 붙여넣기는
 *     가로채지 않는다(평범한 Ctrl+V가 죽으면 채팅이 못 쓰게 된다).
 *  3. 말풍선의 이미지 주소는 **게시판 첨부 주소가 아니다** — 게시판 경로는 방 멤버십을
 *     모르므로 1:1 DM 사진이 전사 공개된다.
 *  4. 읽을 게 남아 있을 때만 읽음 POST 가 나간다. 전체 채팅 방(is_member=false)도 포함하되,
 *     새로 읽을 게 없으면 폴링이 돌아도 쓰기가 나가지 않아야 한다(가장 뜨거운 경로).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatPane } from "./ChatPane.jsx";

const IMG_URL = "/api/team-chat/messages/m1/images/i1";

function messagesPayload(overrides = {}) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "방", member_count: 2 },
    members: [],
    messages: [],
    seq: 0,
    you: { user_id: "u1", role: "member", last_read_seq: 0, is_member: true, can_disband: false, can_hide: false },
    ...overrides,
  };
}

function mount(payload) {
  apiMock.mockImplementation((url, opts) => {
    if (url.startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(payload);
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}><ChatPane roomId="r1" interval={false} /></QueryClientProvider>
  );
}

function postCalls(prefix) {
  return apiMock.mock.calls.filter(
    (c) => String(c[0]).startsWith(prefix) && c[1] && c[1].method === "POST"
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

// ── 1. 이모지 피커 ──────────────────────────────────────────────────────────

describe("이모지 피커", () => {
  it("버튼을 누르면 열리고, 고른 이모지는 초안에 들어간다(전송하지 않는다)", async () => {
    const user = userEvent.setup();
    mount(messagesPayload());
    await screen.findByLabelText("메시지 입력");

    await user.click(screen.getByLabelText("이모지 넣기"));
    const first = await screen.findByLabelText("이모지 👍");
    await user.click(first);

    const input = screen.getByLabelText("메시지 입력");
    await waitFor(() => expect(input).toHaveValue("👍"));
    // 이모지를 골랐다고 메시지가 나가면 안 된다.
    expect(postCalls("/api/team-chat/rooms/r1/messages")).toHaveLength(0);
  });

  it("이미 쓴 글 뒤에 이어 붙는다 — 문장 앞에 끼어들지 않는다", async () => {
    const user = userEvent.setup();
    mount(messagesPayload());
    const input = await screen.findByLabelText("메시지 입력");
    await user.type(input, "확인했습니다");

    await user.click(screen.getByLabelText("이모지 넣기"));
    await user.click(await screen.findByLabelText("이모지 ✅"));
    await waitFor(() => expect(input).toHaveValue("확인했습니다✅"));
  });
});

// ── 2. Ctrl+V 이미지 붙여넣기 ───────────────────────────────────────────────

function pasteEvent(items) {
  const ev = new Event("paste", { bubbles: true, cancelable: true });
  ev.clipboardData = { items };
  return ev;
}
// 진짜 File 이어야 한다 — FormData.append 는 Blob 이 아니면 던진다. 가짜 객체를 쓰면
// 업로드가 조용히 실패하고 테스트는 '아무 일도 안 일어남'을 통과로 읽는다.
function imageItem(type = "image/png", name = "shot.png", size = null) {
  const file = new File(["x"], name, { type });
  if (size != null) Object.defineProperty(file, "size", { value: size });
  return { kind: "file", type, getAsFile: () => file };
}

describe("이미지 붙여넣기", () => {
  it("이미지를 붙여넣으면 팀 채팅 전용 업로드 경로로 FormData 를 보낸다", async () => {
    mount(messagesPayload());
    const input = await screen.findByLabelText("메시지 입력");

    await act(async () => { input.dispatchEvent(pasteEvent([imageItem()])); });

    await waitFor(() => expect(postCalls("/api/team-chat/rooms/r1/images")).toHaveLength(1));
    const [, opts] = postCalls("/api/team-chat/rooms/r1/images")[0];
    expect(opts.body).toBeInstanceOf(FormData);
    // 게시판 업로드 경로를 절대 쓰지 않는다.
    expect(apiMock.mock.calls.some((c) => String(c[0]).includes("/api/board/"))).toBe(false);
  });

  it("텍스트 붙여넣기는 가로채지 않는다 — 업로드가 나가지 않는다", async () => {
    mount(messagesPayload());
    const input = await screen.findByLabelText("메시지 입력");

    await act(async () => {
      input.dispatchEvent(pasteEvent([{ kind: "string", type: "text/plain" }]));
    });

    expect(postCalls("/api/team-chat/rooms/r1/images")).toHaveLength(0);
  });

  it("상한(10MB)을 넘는 이미지는 올리기 전에 막고 사유를 보여 준다", async () => {
    mount(messagesPayload());
    const input = await screen.findByLabelText("메시지 입력");

    await act(async () => {
      input.dispatchEvent(pasteEvent([imageItem("image/png", "big.png", 11 * 1024 * 1024)]));
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(/10MB/);
    expect(postCalls("/api/team-chat/rooms/r1/images")).toHaveLength(0);
  });
});

// ── 3. 말풍선 인라인 이미지 ─────────────────────────────────────────────────

describe("이미지 말풍선", () => {
  it("이미지 메시지는 인라인 <img> 로 그리고, 주소는 게시판 첨부가 아니다", async () => {
    mount(messagesPayload({
      seq: 1,
      messages: [{
        seq: 1, kind: "image", sender_user_id: "u2", sender_name: "상대",
        body: "shot.png", created_at: "2026-08-03T01:02:03",
        images: [{ id: "i1", url: IMG_URL, filename: "shot.png", media_type: "image/png", size_bytes: 10 }],
      }],
    }));

    const img = await screen.findByRole("img", { name: "shot.png" });
    expect(img).toHaveAttribute("src", IMG_URL);
    expect(img.getAttribute("src")).not.toContain("/api/board/");
    // 파일명이 그림 옆에 텍스트로 또 나오지 않는다(첨부처럼 보이면 안 된다).
    expect(screen.queryByText("shot.png")).toBeNull();
  });

  it("텍스트 메시지는 그대로 글자로 그린다", async () => {
    mount(messagesPayload({
      seq: 1,
      messages: [{
        seq: 1, kind: "text", sender_user_id: "u2", sender_name: "상대",
        body: "안녕하세요", created_at: "2026-08-03T01:02:03", images: [],
      }],
    }));
    expect(await screen.findByText("안녕하세요")).toBeInTheDocument();
  });
});

// ── 4. 읽음 커서 ────────────────────────────────────────────────────────────

describe("읽음 처리", () => {
  it("전체 채팅 방(멤버십 없음)도 읽음을 기록한다 — 예전엔 안읽음이 영영 0이었다", async () => {
    mount(messagesPayload({
      room: { id: "r1", kind: "group", is_global: true, title: "전체 채팅", member_count: 0 },
      seq: 7,
      you: { user_id: "u1", role: null, last_read_seq: 0, is_member: false },
    }));

    await waitFor(() => expect(postCalls("/api/team-chat/rooms/r1/read")).toHaveLength(1));
    expect(postCalls("/api/team-chat/rooms/r1/read")[0][1].body).toEqual({ seq: 7 });
  });

  it("새로 읽을 게 없으면 읽음 POST 를 보내지 않는다 — 폴링이 쓰기를 만들면 안 된다", async () => {
    mount(messagesPayload({
      room: { id: "r1", kind: "group", is_global: true, title: "전체 채팅", member_count: 0 },
      seq: 7,
      you: { user_id: "u1", role: null, last_read_seq: 7, is_member: false },
    }));
    await screen.findByLabelText("메시지 입력");
    expect(postCalls("/api/team-chat/rooms/r1/read")).toHaveLength(0);
  });

  it("메시지가 하나도 없는 방(seq=0)에서는 읽음을 기록하지 않는다", async () => {
    mount(messagesPayload({ seq: 0 }));
    await screen.findByLabelText("메시지 입력");
    expect(postCalls("/api/team-chat/rooms/r1/read")).toHaveLength(0);
  });
});
