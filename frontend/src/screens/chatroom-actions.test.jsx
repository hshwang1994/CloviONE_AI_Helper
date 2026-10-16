import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 채팅방 헤더의 파괴적 동작 — 파하기(그룹·방장) / 숨기기(1:1) / 나가기.
 *
 * 이 화면이 틀리기 쉬운 지점은 **버튼을 누가 보느냐**가 아니라 **어디서 판단하느냐**다.
 * 방장인지·1:1인지·전체 채팅인지를 프런트가 다시 계산하면 서버 규칙과 어긋나는 순간
 * '보이는데 누르면 403/409'가 된다. 그래서 서버가 준 you.can_disband / you.can_hide 만 본다.
 *
 * 그리고 파하기와 숨기기는 다른 일이다: 그룹은 모두에게서 사라지고(soft delete), 1:1 은
 * 파할 수 없어(dm_key unique) 내 목록에서만 숨긴다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

// S1 로 목록·상세를 한 껍데기에 합치면서 방 본문이 RoomDetailPanel 이 됐다.
// 라우트 파라미터가 아니라 prop 으로 id 를 받는다 — 여기서 확인하는 동작
// (파하기·나가기·숨기기·관리 버튼의 노출 조건)은 그대로다.
import { RoomDetailPanel, leaveRoomConfirmMessage } from "./ChatRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function meta(you, room = {}) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "우리방", member_count: 3, ...room },
    members: [],
    messages: [],
    seq: 0,
    you: { user_id: "u1", role: "member", last_read_seq: 0, is_member: true,
           can_disband: false, can_hide: false, ...you },
  };
}

function mount(payload) {
  apiMock.mockImplementation((url) => {
    if (url.startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(payload);
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/chat-rooms/r1"]}>
              <Routes>
                <Route path="/chat-rooms/:id" element={<RoomDetailPanel id="r1" />} />
                {/* 동작 후 목록으로 되돌아간다 — 라우트가 없으면 경고만 남고 이동이 검증되지 않는다. */}
                <Route path="/chat-rooms" element={<div>채팅방 목록</div>} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const posted = (path) => apiMock.mock.calls.filter((c) => c[0] === path && c[1] && c[1].method === "POST");

beforeEach(() => { apiMock.mockReset(); });

describe("방 파하기 버튼", () => {
  it("서버가 can_disband 를 주면 보이고, 확인 후 disband 를 호출한다", async () => {
    const user = userEvent.setup();
    mount(meta({ role: "owner", can_disband: true }));

    const btn = await screen.findByRole("button", { name: "채팅방 삭제" });
    await user.click(btn);
    // 되돌릴 수 없는 동작이라 확인을 받는다.
    await user.click(await screen.findByRole("button", { name: "삭제" }));

    await waitFor(() => expect(posted("/api/team-chat/rooms/r1/disband")).toHaveLength(1));
  });

  it("can_disband 가 false 면 버튼 자체가 없다(1:1·전체·비방장)", async () => {
    mount(meta({ role: "member", can_disband: false }));
    await screen.findByRole("heading", { name: /채팅|대화|방/ });
    expect(screen.queryByRole("button", { name: "채팅방 삭제" })).toBeNull();
  });

  it("확인 창에서 취소하면 아무 요청도 나가지 않는다", async () => {
    const user = userEvent.setup();
    mount(meta({ role: "owner", can_disband: true }));
    await user.click(await screen.findByRole("button", { name: "채팅방 삭제" }));
    await user.click(await screen.findByRole("button", { name: "취소" }));
    expect(posted("/api/team-chat/rooms/r1/disband")).toHaveLength(0);
  });
});

describe("1:1 숨기기 버튼", () => {
  it("1:1 방에서는 '파하기'가 아니라 '숨기기'가 나온다", async () => {
    const user = userEvent.setup();
    mount(meta({ can_hide: true, can_disband: false },
               { kind: "direct", title: "상대이름", member_count: 2 }));

    expect(await screen.findByRole("button", { name: "숨기기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "채팅방 삭제" })).toBeNull();
    // 1:1 은 '나가기'도 없다(그룹 전용).
    expect(screen.queryByRole("button", { name: "나가기" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "숨기기" }));
    // 확인 모달의 확정 버튼(헤더 버튼과 같은 이름이라 마지막 것을 고른다).
    const confirms = await screen.findAllByRole("button", { name: "숨기기" });
    await user.click(confirms[confirms.length - 1]);
    await waitFor(() => expect(posted("/api/team-chat/rooms/r1/hide")).toHaveLength(1));
    // 숨기고 나면 목록으로 돌아간다.
    expect(await screen.findByText("채팅방 목록")).toBeInTheDocument();
  });
});

describe("나가기 확인 문구 — 방장이면 결과가 다르다(step 9 #5)", () => {
  /* 예전엔 누가 나가든 "계속할까요?" 한 문장이었다 - 방장이 나가고 남은 사람이 없으면
     방이 사라지는데(파하기와 같은 결과), 바로 옆 파하기 버튼만 "되돌릴 수 없습니다"를
     경고해 결과가 같은 두 버튼이 다른 무게로 보였다. */
  it("방장이 아니면 그냥 나간다는 안내다", () => {
    expect(leaveRoomConfirmMessage({ role: "member" }, { member_count: 3 }))
      .toBe("이 채팅방을 나갑니다. 계속할까요?");
  });

  it("방장이고 남은 사람이 없으면 방이 사라진다고 말한다(파하기와 같은 결과)", () => {
    const msg = leaveRoomConfirmMessage({ role: "owner" }, { member_count: 1 });
    expect(msg).toMatch(/사라|되돌릴 수 없/);
  });

  it("방장이고 남은 사람이 있으면 방장 권한이 자동으로 넘어간다고 말한다", () => {
    const msg = leaveRoomConfirmMessage({ role: "owner" }, { member_count: 3 });
    expect(msg).toMatch(/방장.*넘어|넘어.*방장/);
    expect(msg).not.toMatch(/사라/);
  });

  it("실제 화면에서 방장으로 나가기를 누르면 방장 전용 문구가 뜬다", async () => {
    const user = userEvent.setup();
    mount(meta({ role: "owner", can_disband: true }, { member_count: 3 }));
    await user.click(await screen.findByRole("button", { name: "나가기" }));
    expect(await screen.findByText(/방장 권한은 가장 먼저 들어온/)).toBeInTheDocument();
  });
});

describe("전체 채팅 방", () => {
  it("파하기·나가기·숨기기가 모두 없다 — 서버가 409 로 막는 동작을 화면에 보이지 않는다", async () => {
    mount(meta({ role: null, is_member: false, can_disband: false, can_hide: false },
               { is_global: true, title: "전체 채팅", member_count: 0 }));
    await screen.findByRole("heading", { name: /채팅|대화|방/ });
    expect(screen.queryByRole("button", { name: "채팅방 삭제" })).toBeNull();
    expect(screen.queryByRole("button", { name: "나가기" })).toBeNull();
    expect(screen.queryByRole("button", { name: "숨기기" })).toBeNull();
  });
});

describe("머리 동작의 실패는 머리 바로 아래 메시지 박스다 (핸드오프 RULES §1 — 토스트였다)", () => {
  it("파하기가 실패하면 상자가 말하고 방은 그대로 열려 있으며, 다시 누르면 걷힌다", async () => {
    const user = userEvent.setup();
    let fail = true;
    apiMock.mockImplementation((url, opts) => {
      if (url.startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(meta({ role: "owner", can_disband: true }));
      if (url === "/api/team-chat/rooms/r1/disband" && opts && opts.method === "POST") {
        if (fail) return Promise.reject(new Error("아직 파할 수 없는 방입니다."));
        return new Promise(() => {});
      }
      return Promise.resolve({ ok: true });
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <MemoryRouter initialEntries={["/chat-rooms/r1"]}>
            <Routes>
              <Route path="/chat-rooms/:id" element={<RoomDetailPanel id="r1" />} />
              <Route path="/chat-rooms" element={<div>채팅방 목록</div>} />
            </Routes>
          </MemoryRouter>
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      </QueryClientProvider>,
    );
    await user.click(await screen.findByRole("button", { name: "채팅방 삭제" }));
    await user.click(await screen.findByRole("button", { name: "삭제" }));
    const box = await screen.findByText("아직 파할 수 없는 방입니다.");
    const head = document.querySelector("[data-room-head]");
    expect(head.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(head.contains(box)).toBe(false);
    expect(screen.queryByText("채팅방 목록")).toBeNull();

    fail = false;
    await user.click(screen.getByRole("button", { name: "채팅방 삭제" }));
    await user.click(await screen.findByRole("button", { name: "삭제" }));
    await waitFor(() => expect(screen.queryByText("아직 파할 수 없는 방입니다.")).toBeNull());
  });
});
