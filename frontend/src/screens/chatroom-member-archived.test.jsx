import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 참여자 줄이 관리 창만의 것에서 누구나 여는 명단 팝오버와 관리 창이 함께 쓰는 한 벌(`MemberRow`)이 됐다(사용자 지시 2026-09-21 항목 3). 관리 창 단언은 그대로 두고, 명단 팝오버의 줄에도 같은 '(보관됨)' 표시가 붙는지와 살아 있는 사람에게는 안 붙는지를 더 잰다. */

/* 참여자 목록의 '보관됨' 표시 — 말풍선과 같은 사실을 말해야 한다 (N3, 교차 화면 감사).
 *
 * `GET /api/team-chat/rooms/{id}/messages` 는 **같은 응답 안에** 두 신원 표현을 함께 준다:
 *   `people`  — 말풍선이 쓴다. `app/core/people.identity()` 를 그대로 실어 `archived` 를 포함한다.
 *   `members` — 참여자 줄(명단 팝오버 · ManageRoomModal, 당시에는 MemberStrip)이 쓴다. `_member_view()` 가
 *               `person["archived"]` 를 계산해 놓고 응답 dict 에 담지 않아 **항상 빠졌다**.
 *
 * 그 결과 퇴사(보관)한 참여자가 같은 방에서: 말풍선에는 "(보관됨)"이 붙는데(chat-identity.test.jsx),
 * 참여자 목록(관리 대화상자)에는 아무 표시가 없어 "아직 있는 사람"처럼 보였다 — 답이 안 오는
 * 대화를 며칠 기다리게 하는 바로 그 침묵(N3, app/core/people.py 문서 참고).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { RoomDetailPanel } from "./ChatRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ME = "u1";
const PEER = "u2";

function meta(peerOverrides = {}) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "우리방", member_count: 2 },
    members: [
      { user_id: ME, name: "나", role: "owner", last_read_seq: 3, online: true, archived: false },
      { user_id: PEER, name: "동료", dept: "ClovirONE팀", role: "member", last_read_seq: 1, online: false, archived: false, ...peerOverrides },
    ],
    messages: [],
    seq: 0,
    people: {
      [ME]: { user_id: ME, display_name: "나", dept: "", title: "", org: "", archived: false },
      [PEER]: { user_id: PEER, display_name: "동료", dept: "ClovirONE팀", title: "", org: "", archived: !!peerOverrides.archived },
    },
    you: { user_id: ME, role: "owner", last_read_seq: 3, is_member: true,
           can_disband: true, can_hide: false, can_manage: true },
  };
}

function mount(payload) {
  apiMock.mockImplementation((url) => {
    if (String(url).startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(payload);
    if (String(url).startsWith("/api/team-chat/directory")) return Promise.resolve({ users: [] });
    return Promise.resolve({ ok: true });
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

describe("참여자 목록의 보관됨 표시", () => {
  beforeEach(() => apiMock.mockReset());

  it("보관된 참여자는 관리 대화상자의 참여자 줄에 '(보관됨)'이 붙는다", async () => {
    const user = userEvent.setup();
    mount(meta({ archived: true }));
    await user.click(await screen.findByRole("button", { name: "관리" }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByText("동료")).toBeInTheDocument());
    expect(within(dialog).getByText("(보관됨)")).toBeInTheDocument();
  });

  it("살아 있는 참여자에는 '(보관됨)'을 붙이지 않는다", async () => {
    const user = userEvent.setup();
    mount(meta({ archived: false }));
    await user.click(await screen.findByRole("button", { name: "관리" }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByText("동료")).toBeInTheDocument());
    expect(within(dialog).queryByText("(보관됨)")).toBeNull();
  });

  /* 명단 팝오버는 관리 창과 같은 줄(`MemberRow`)을 쓴다. 방장이 아닌 사람이 보는 명단에서 이 표시가 빠지면, 관리 창을
     못 여는 사람만 떠난 사람을 살아 있는 사람으로 읽는다. */
  it("명단 팝오버의 줄에도 '(보관됨)'이 붙는다 — 관리 창과 같은 줄이다", async () => {
    const user = userEvent.setup();
    mount(meta({ archived: true }));
    await user.click(await screen.findByRole("button", { name: "참여자 2명, 보는 중 1명" }));
    const dialog = await screen.findByRole("dialog", { name: "참여자 2명" });
    const row = within(dialog).getAllByRole("listitem").find((li) => within(li).queryByText("동료"));
    expect(row).toHaveAttribute("data-member-row");
    expect(within(row).getByText("(보관됨)")).toBeInTheDocument();
    // 부서 경로를 모르는 옛 신원이어도 소속 줄은 부서 이름 한 칸으로 선다(동명이인을 가르는 글자다).
    expect(within(row).getByText("ClovirONE팀")).toBeInTheDocument();
    expect(within(dialog).getAllByText("(보관됨)")).toHaveLength(1);
  });

  it("명단 팝오버에서도 살아 있는 참여자에는 '(보관됨)'을 붙이지 않는다", async () => {
    const user = userEvent.setup();
    mount(meta({ archived: false }));
    await user.click(await screen.findByRole("button", { name: "참여자 2명, 보는 중 1명" }));
    const dialog = await screen.findByRole("dialog", { name: "참여자 2명" });
    expect(within(dialog).getByText("동료")).toBeInTheDocument();
    expect(within(dialog).queryByText("(보관됨)")).toBeNull();
  });
});
