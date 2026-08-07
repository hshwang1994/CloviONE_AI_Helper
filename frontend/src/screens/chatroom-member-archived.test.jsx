import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 참여자 목록의 '보관됨' 표시 — 말풍선과 같은 사실을 말해야 한다 (N3, 교차 화면 감사).
 *
 * `GET /api/team-chat/rooms/{id}/messages` 는 **같은 응답 안에** 두 신원 표현을 함께 준다:
 *   `people`  — 말풍선이 쓴다. `app/core/people.identity()` 를 그대로 실어 `archived` 를 포함한다.
 *   `members` — 참여자 목록(MemberStrip · ManageRoomModal)이 쓴다. `_member_view()` 가
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
});
