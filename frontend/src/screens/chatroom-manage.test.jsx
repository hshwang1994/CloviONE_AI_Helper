import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 그룹 관리 화면 — 이름 변경 · 초대 · 내보내기 · 방장 넘기기 (PLAN Phase 3 §F).
 *
 * 이 화면이 틀리기 쉬운 지점은 **어디서 판단하느냐**다. '그룹인가? 방장인가? 전체인가?'를
 * 프런트가 다시 계산하면 서버 규칙과 어긋나는 순간 '보이는데 누르면 403'이 된다.
 * 그래서 서버가 준 `you.can_manage` 하나만 본다.
 *
 * 그리고 **주인 없는 방을 만들 수 있는 버튼은 없어야 한다**: 내 줄에는 '내보내기'가 없다
 * (서버도 409로 막는다). 빠지는 길은 '방장 넘기기'와 '나가기'뿐이다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

// S1 로 목록·상세를 한 껍데기에 합치면서 방 본문이 RoomDetailPanel 이 됐다.
// 라우트 파라미터가 아니라 prop 으로 id 를 받는다 — 여기서 확인하는 동작
// (파하기·나가기·숨기기·관리 버튼의 노출 조건)은 그대로다.
import { RoomDetailPanel } from "./ChatRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ME = "u1";
const PEER = "u2";

function meta(over = {}, you = {}) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "우리방", member_count: 2 },
    members: [
      { user_id: ME, name: "나", role: "owner", last_read_seq: 3, online: true },
      { user_id: PEER, name: "동료", role: "member", last_read_seq: 1, online: false },
    ],
    messages: [],
    seq: 0,
    you: { user_id: ME, role: "owner", last_read_seq: 3, is_member: true,
           can_disband: true, can_hide: false, can_manage: true, ...you },
    ...over,
  };
}

function mount(payload) {
  apiMock.mockImplementation((url) => {
    if (String(url).startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(payload);
    if (String(url).startsWith("/api/team-chat/directory")) {
      return Promise.resolve({ users: [{ user_id: "u9", display_name: "새사람", dept: "개발", title: "" }] });
    }
    return Promise.resolve({ ok: true, added: 1 });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/chat-rooms/r1"]}>
          <Routes>
            <Route path="/chat-rooms/:id" element={<RoomDetailPanel id="r1" />} />
            <Route path="/chat-rooms" element={<div>채팅방 목록</div>} />
          </Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>
  );
}

const posted = (path) => apiMock.mock.calls.filter((c) => c[0] === path && c[1] && c[1].method === "POST");

beforeEach(() => { apiMock.mockReset(); });

// ── 1. 버튼이 언제 보이나 ───────────────────────────────────────────────────

describe("관리 버튼", () => {
  it("can_manage 가 true 일 때만 보인다", async () => {
    mount(meta());
    expect(await screen.findByRole("button", { name: "관리" })).toBeInTheDocument();
  });

  it("일반 참여자·1:1·전체 채팅에는 없다", async () => {
    const { unmount } = mount(meta({}, { role: "member", can_manage: false, can_disband: false }));
    await screen.findByRole("heading", { name: /채팅|대화|방/ });
    expect(screen.queryByRole("button", { name: "관리" })).toBeNull();
    unmount();

    mount(meta(
      { room: { id: "r1", kind: "direct", is_global: false, title: "동료", member_count: 2 } },
      { can_manage: false, can_hide: true, can_disband: false },
    ));
    await screen.findByRole("heading", { name: /채팅|대화|방/ });
    expect(screen.queryByRole("button", { name: "관리" })).toBeNull();
  });
});

// ── 2. 관리 동작 ────────────────────────────────────────────────────────────

async function openManage(user) {
  await user.click(await screen.findByRole("button", { name: "관리" }));
  return screen.findByRole("dialog");
}

describe("관리 대화상자", () => {
  it("이름 입력 상한이 서버의 MAX_TITLE(200)과 같다 — 짧게 잘라 두면 서버가 받는 이름을 화면이 못 치게 막는다", async () => {
    const user = userEvent.setup();
    mount(meta());
    await openManage(user);
    expect(screen.getByDisplayValue("우리방")).toHaveAttribute("maxlength", "200");
  });

  it("이름을 바꾸면 rename 을 호출한다(같은 이름이면 저장이 잠겨 있다)", async () => {
    const user = userEvent.setup();
    mount(meta());
    await openManage(user);

    const save = screen.getByRole("button", { name: "저장" });
    expect(save).toBeDisabled();     // 이름이 그대로면 저장할 게 없다

    const input = screen.getByDisplayValue("우리방");
    await user.clear(input);
    await user.type(input, "새 이름");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(posted("/api/team-chat/rooms/r1/rename")).toHaveLength(1));
    expect(posted("/api/team-chat/rooms/r1/rename")[0][1].body).toEqual({ title: "새 이름" });
  });

  it("이미 참여 중인 사람은 초대 후보에 없다", async () => {
    const user = userEvent.setup();
    mount(meta());
    await openManage(user);
    expect(await screen.findByText(/새사람/)).toBeInTheDocument();
    expect(screen.queryByText(/^동료 ·/)).toBeNull();
  });

  it("고른 사람을 초대하면 members/add 에 그 id 들이 간다", async () => {
    const user = userEvent.setup();
    mount(meta());
    await openManage(user);
    await user.click(await screen.findByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "1명 초대" }));

    await waitFor(() => expect(posted("/api/team-chat/rooms/r1/members/add")).toHaveLength(1));
    expect(posted("/api/team-chat/rooms/r1/members/add")[0][1].body).toEqual({ user_ids: ["u9"] });
  });

  it("내보내기는 확인을 받은 뒤에만 나간다", async () => {
    const user = userEvent.setup();
    mount(meta());
    await openManage(user);
    await user.click(screen.getByRole("button", { name: "내보내기" }));
    // 확인 창의 확정 버튼(같은 이름이라 마지막 것을 고른다).
    const confirms = await screen.findAllByRole("button", { name: "내보내기" });
    await user.click(confirms[confirms.length - 1]);

    await waitFor(() => expect(posted("/api/team-chat/rooms/r1/members/remove")).toHaveLength(1));
    expect(posted("/api/team-chat/rooms/r1/members/remove")[0][1].body).toEqual({ user_id: PEER });
  });

  it("방장 넘기기는 확인을 받은 뒤에만 나간다", async () => {
    const user = userEvent.setup();
    mount(meta());
    await openManage(user);
    await user.click(screen.getByRole("button", { name: "방장 넘기기" }));
    await user.click(await screen.findByRole("button", { name: "넘기기" }));

    await waitFor(() => expect(posted("/api/team-chat/rooms/r1/owner")).toHaveLength(1));
    expect(posted("/api/team-chat/rooms/r1/owner")[0][1].body).toEqual({ user_id: PEER });
  });

  it("내 줄에는 관리 버튼이 없다 — 주인 없는 방을 만들 수 있는 버튼은 존재하지 않는다", async () => {
    const user = userEvent.setup();
    mount(meta());
    await openManage(user);
    // 참여자가 둘인데 관리 버튼 쌍은 상대 한 명분(각 1개)뿐이다.
    expect(screen.getAllByRole("button", { name: "내보내기" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "방장 넘기기" })).toHaveLength(1);
    expect(screen.getByText(/방장은 스스로 내보낼 수 없습니다/)).toBeInTheDocument();
  });
});

// ── 3. 접속 표시 ────────────────────────────────────────────────────────────

describe("참여자 줄", () => {
  it("몇 명이 지금 이 대화를 보고 있는지 글자로도 말한다(색만으로 전하지 않는다)", async () => {
    mount(meta());
    expect(await screen.findByText("참여자 2명, 보는 중 1명")).toBeInTheDocument();
  });

  it("사람이 많으면 이름을 잘라 '외 N명'으로 말한다 — 한 줄이 대화창을 밀어내면 안 된다", async () => {
    const many = Array.from({ length: 12 }, (_, i) => ({
      user_id: `m${i}`, name: `사람${i}`, role: i === 0 ? "owner" : "member",
      last_read_seq: 0, online: i % 4 === 0,
    }));
    mount(meta({ members: many }, { can_manage: false }));
    expect(await screen.findByText("참여자 12명, 보는 중 3명")).toBeInTheDocument();
    expect(screen.getByText("외 4명")).toBeInTheDocument();
  });

  it("전체 채팅은 참여자 행이 없어 아무것도 그리지 않는다", async () => {
    mount(meta(
      { room: { id: "r1", kind: "group", is_global: true, title: "전체 채팅", member_count: 0 }, members: [] },
      { role: null, is_member: false, can_manage: false, can_disband: false },
    ));
    await screen.findByRole("heading", { name: /채팅|대화|방/ });
    expect(screen.queryByText(/참여자 \d+명/)).toBeNull();
  });
});
