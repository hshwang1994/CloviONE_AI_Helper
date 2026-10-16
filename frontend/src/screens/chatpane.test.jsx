/* qa-contract-change: 채팅방 대화 로그의 정렬이 아래 정렬(flex-end)에서 위 정렬(flex-start, 로그 상한 45rem 걷음)로 옮겼다 — 소유자 결정 「위 정렬 + 입력창 바닥」(UI 3차 조합 계약 C-6). 「full 로그는 flex-end」 단언을 「full 은 flex-start · 상한 없음 · 첫 진입과 새 메시지에 맨 아래로 굴림」으로 옮기고, compact 의 아래 정렬 · 입력 도킹 영역(위 실선 · 입력 영역 표식) · 공통 날짜 구분선 폭을 더 잰다.
 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* ChatPane 계약 테스트 — 이모지 삽입, Ctrl+V 이미지, 인라인 렌더, 읽음 커서, 입력 상자 규격 · 보내기 실패 상자.
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

// ── 0. 빈 방 안내 (VIS-90) ────────────────────────────────────────────────

describe("빈 방 안내", () => {
  it("메시지가 없으면 아이콘 있는 안내를 보여준다(예전엔 아이콘 없는 회색 한 줄이었다)", async () => {
    mount(messagesPayload({ messages: [] }));
    await screen.findByText("메시지가 없습니다.");
    expect(screen.getByText("💬")).toBeInTheDocument();
    expect(screen.getByText("첫 메시지를 보내 대화를 시작하세요.")).toBeInTheDocument();
  });
});

// ── 1. 이모지 피커 ──────────────────────────────────────────────────────────

describe("이모지 피커", () => {
  it("버튼을 누르면 열리고, 고른 이모지는 초안에 들어간다(전송하지 않는다)", async () => {
    const user = userEvent.setup();
    mount(messagesPayload());
    await screen.findByLabelText("메시지 입력");

    await user.click(screen.getByLabelText("이모지 넣기"));
    // VIS-86 — 개별 이모지 버튼의 aria-label은 이제 이모지 자체가 아니라 뜻을 말한다
    // (chat-compose.js::EMOJI_LABELS, "👍" → "엄지척").
    const first = await screen.findByLabelText("엄지척");
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
    // VIS-86 — "✅" → "완료 체크"(chat-compose.js::EMOJI_LABELS).
    await user.click(await screen.findByLabelText("완료 체크"));
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

// ── 5. 메시지 로그 정렬 ─────────────────────────────────────────────────────
// 소유자 결정(2026-09-15, UI 3차 조합 계약 C-6): 채팅방 대화는 **위에서부터** 쌓이고 입력창은 판 바닥이다. 짧은 방은
// 마지막 말과 입력창 사이가 빈다 — 그 빈자리는 결함이 아니라 결정이다. 긴 방은 로그가 넘쳐 스크롤되고, 첫 진입과
// 새 메시지에서 맨 아래(최신)로 굴리는 규칙은 그대로다. 아래 정렬(flex-end)은 제품 화면에 붙어 있지 않은 `compact`
// (홈 위젯)만 남는다. jsdom 은 레이아웃을 계산하지 않으므로 CSS 속성과 스크롤 규칙을 단정한다.
function logBoxOf(container) {
  const logBox = container.querySelector("[data-chat-log]");
  expect(logBox, "대화 로그 표식(data-chat-log)이 없다").toBeTruthy();
  expect(getComputedStyle(logBox).overflowY).toBe("auto");
  return logBox;
}

describe("메시지 로그 정렬", () => {
  it("채팅방 로그는 위에서부터 쌓이고(flex-start) 높이 상한이 없다 — 판의 남는 높이를 로그가 다 먹는다", async () => {
    const { container } = mount(messagesPayload({
      seq: 1,
      messages: [{
        seq: 1, kind: "text", sender_user_id: "u2", sender_name: "상대",
        body: "안녕하세요", created_at: "2026-08-03T01:02:03", images: [],
      }],
    }));
    await screen.findByText("안녕하세요");

    const logBox = logBoxOf(container);
    const cs = getComputedStyle(logBox);
    expect(cs.display).toBe("flex");
    expect(cs.flexDirection).toBe("column");
    expect(cs.justifyContent).toBe("flex-start");
    expect(cs.justifyContent).not.toBe("flex-end");
    // 예전 상한 45rem 은 넓은 화면에서 로그 아래에 빈 띠를 남기고 입력창을 판 가운데로 띄웠다.
    expect(cs.maxHeight === "" || cs.maxHeight === "none").toBe(true);
    expect(cs.flexGrow).toBe("1");
    expect(logBox.hasAttribute("data-chat-compact")).toBe(false);
  });

  it("첫 진입에서는 맨 아래(최신)로 굴린다 — 위 정렬이어도 긴 방은 마지막 말이 보인다", async () => {
    const heights = { scrollHeight: 2000, clientHeight: 400 };
    const spy = vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(function () {
      return this.hasAttribute && this.hasAttribute("data-chat-log") ? heights.scrollHeight : 0;
    });
    const spyC = vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(function () {
      return this.hasAttribute && this.hasAttribute("data-chat-log") ? heights.clientHeight : 0;
    });
    try {
      const { container } = mount(messagesPayload({
        seq: 2,
        messages: [1, 2].map((n) => ({
          seq: n, kind: "text", sender_user_id: "u2", sender_name: "상대",
          body: "말 " + n, created_at: "2026-08-03T01:02:0" + n, images: [],
        })),
      }));
      await screen.findByText("말 2");
      const logBox = logBoxOf(container);
      await waitFor(() => expect(logBox.scrollTop).toBe(2000));
    } finally {
      spy.mockRestore();
      spyC.mockRestore();
    }
  });

  // C15 — 빈 방 안내는 로그 상자의 하나뿐인 자식이라 아래로 붙이면 안내가 화면 맨 아래로 밀려나고 위가 통째로 빈다.
  it("메시지가 없을 때도 flex-end 를 쓰지 않는다 — 안내가 맨 아래로 밀려나 위가 비면 안 된다", async () => {
    const { container } = mount(messagesPayload({ messages: [] }));
    await screen.findByText("메시지가 없습니다.");
    expect(getComputedStyle(logBoxOf(container)).justifyContent).not.toBe("flex-end");
  });

  it("홈 위젯 크기(compact)는 대화가 있을 때만 아래에서부터 쌓는다 — 제품 화면 밖 갈래라 예전 규칙 그대로다", async () => {
    apiMock.mockImplementation((url) => {
      if (url.startsWith("/api/team-chat/rooms/r1/messages?")) {
        return Promise.resolve(messagesPayload({
          seq: 1,
          messages: [{ seq: 1, kind: "text", sender_user_id: "u2", sender_name: "상대", body: "위젯 말", created_at: "2026-08-03T01:02:03", images: [] }],
        }));
      }
      return Promise.resolve({ ok: true });
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    const { container } = render(<QueryClientProvider client={qc}><ChatPane roomId="r1" interval={false} compact /></QueryClientProvider>);
    await screen.findByText("위젯 말");
    const logBox = logBoxOf(container);
    expect(logBox.hasAttribute("data-chat-compact")).toBe(true);
    expect(getComputedStyle(logBox).justifyContent).toBe("flex-end");
  });
});

describe("입력 도킹 영역 · 날짜 구분선 (UI 3차 조합 계약 C-6)", () => {
  it("입력 상자는 스레드 아래 1px 실선(rule) 도킹 영역 안에 서고, 그 영역이 입력 영역 하나다", async () => {
    const { container } = mount(messagesPayload());
    const composer = await waitFor(() => {
      const el = container.querySelector("[data-chat-composer]");
      if (!el) throw new Error("입력 상자가 아직 없음");
      return el;
    });
    const dock = composer.closest("[data-chat-dock]");
    expect(dock, "입력 상자가 도킹 영역 밖이다").toBeTruthy();
    expect(getComputedStyle(dock).borderTopWidth).toBe("1px");
    expect(getComputedStyle(dock).borderTopStyle).toBe("solid");
    expect(dock.hasAttribute("data-form-scope")).toBe(true);
    expect(dock.contains(screen.getByRole("button", { name: "보내기" }))).toBe(true);
    // 로그와 도킹 영역은 형제다 — 로그 안에 입력이 들어가면 스크롤에 입력이 딸려 간다.
    expect(container.querySelector("[data-chat-log]").contains(dock)).toBe(false);
  });

  it("날짜 구분선은 채팅 공통 구분선이고 가운데 28rem 폭에 선다(스레드 전폭이 아니다)", async () => {
    const { container } = mount(messagesPayload({
      seq: 2,
      messages: [
        { seq: 1, kind: "text", sender_user_id: "u2", sender_name: "상대", body: "어제 말", created_at: "2026-08-02T01:02:03", images: [] },
        { seq: 2, kind: "text", sender_user_id: "u2", sender_name: "상대", body: "오늘 말", created_at: "2026-08-03T01:02:03", images: [] },
      ],
    }));
    await screen.findByText("오늘 말");
    const seps = [...container.querySelectorAll("[data-day-separator]")];
    expect(seps.length).toBe(2);
    for (const sep of seps) {
      expect(sep).toHaveAttribute("role", "separator");
      const cs = getComputedStyle(sep);
      expect(cs.maxWidth).toBe("28rem");
      expect(cs.alignSelf).toBe("center");
    }
    expect(seps[0].getAttribute("data-day-separator")).toBe("2026-08-02");
  });
});

// ── 입력 상자 (핸드오프 RULES §9 · ui/chat.js::CHAT) ──────────────────────────

describe("입력 상자", () => {
  it("입력은 모서리 10 의 상자 하나이고, 도구는 작은 단추(30), 보내기는 작은 채움 단추다", async () => {
    mount(messagesPayload());
    const box = await waitFor(() => {
      const el = document.querySelector("[data-chat-composer]");
      if (!el) throw new Error("입력 상자가 아직 없음");
      return el;
    });
    expect(getComputedStyle(box).borderRadius).toBe("10px");
    expect(screen.getByRole("button", { name: "이모지 넣기" }).className).toMatch(/MuiIconButton-sizeSmall/);
    const send = screen.getByRole("button", { name: "보내기" });
    expect(send.className).toMatch(/MuiButton-sizeSmall/);
    expect(send.className).toMatch(/MuiButton-contained/);
    // 빈 초안은 보낼 수 없다.
    expect(send).toBeDisabled();
    expect(box.contains(screen.getByRole("textbox", { name: "메시지 입력" }))).toBe(true);
  });

  it("보내기가 실패하면 입력 위 메시지 박스가 말하고 초안은 남으며, 다시 보내면 걷힌다(토스트였다)", async () => {
    const user = userEvent.setup();
    let fail = true;
    apiMock.mockImplementation((url, opts) => {
      if (url.startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(messagesPayload());
      if (url === "/api/team-chat/rooms/r1/messages" && opts && opts.method === "POST") {
        if (fail) return Promise.reject(new Error("이 방에는 지금 보낼 수 없습니다."));
        return new Promise(() => {});
      }
      return Promise.resolve({ ok: true });
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
    render(<QueryClientProvider client={qc}><ChatPane roomId="r1" interval={false} /></QueryClientProvider>);
    const input = await screen.findByRole("textbox", { name: "메시지 입력" });
    await user.type(input, "안녕하세요");
    await user.keyboard("{Enter}");
    const box = await screen.findByText("이 방에는 지금 보낼 수 없습니다.");
    // 상자는 입력 상자보다 앞(위)에 선다.
    expect(box.compareDocumentPosition(document.querySelector("[data-chat-composer]")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(input).toHaveValue("안녕하세요");
    fail = false;
    await user.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(screen.queryByText("이 방에는 지금 보낼 수 없습니다.")).toBeNull());
  });
});

// ── 7. 같은 말을 두 번 보내지 않는다 (P4 — Enter 연타 · 붙여넣기 연타) ─────────────────────

describe("중복 전송", () => {
  /* 보내기는 Enter 처리기가 직접 부른다. 그 처리기가 보는 `send.isPending` 은 지난 렌더의 값이라, 화면이 다시
     그려지기 전에 온 둘째 Enter 는 같은 말을 한 번 더 보냈다(요청마다 새 client_message_id 라 서버도 둘을 다른 말로
     받는다). 응답을 붙잡아 그 창을 열고, 같은 틱에 Enter 를 두 번 보낸다. */
  function mountHeld() {
    const held = { messages: [], images: [] };
    apiMock.mockImplementation((url, opts) => {
      if (url.startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(messagesPayload());
      if (url === "/api/team-chat/rooms/r1/messages" && opts && opts.method === "POST") {
        held.messages.push(opts.body);
        return new Promise(() => {});
      }
      if (url === "/api/team-chat/rooms/r1/images" && opts && opts.method === "POST") {
        held.images.push(opts.body);
        return new Promise(() => {});
      }
      return Promise.resolve({ ok: true });
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
    render(<QueryClientProvider client={qc}><ChatPane roomId="r1" interval={false} /></QueryClientProvider>);
    return held;
  }

  it("같은 틱에 Enter 가 두 번 와도 같은 글은 한 번만 나간다", async () => {
    const held = mountHeld();
    const input = await screen.findByRole("textbox", { name: "메시지 입력" });
    fireEvent.change(input, { target: { value: "회의 10분 뒤에 시작합니다" } });
    act(() => {
      fireEvent.keyDown(input, { key: "Enter" });
      fireEvent.keyDown(input, { key: "Enter" });
    });
    await waitFor(() => expect(held.messages).toHaveLength(1));
    await act(async () => {});
    expect(held.messages).toHaveLength(1);
    expect(held.messages[0].body).toBe("회의 10분 뒤에 시작합니다");
  });

  it("그림을 빠르게 두 번 붙여넣어도 올리는 요청은 한 번이다", async () => {
    const held = mountHeld();
    const input = await screen.findByRole("textbox", { name: "메시지 입력" });
    act(() => {
      input.dispatchEvent(pasteEvent([imageItem()]));
      input.dispatchEvent(pasteEvent([imageItem()]));
    });
    await waitFor(() => expect(held.images).toHaveLength(1));
    await act(async () => {});
    expect(held.images).toHaveLength(1);
  });
});
