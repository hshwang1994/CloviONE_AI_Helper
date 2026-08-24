/**
 * VIS-88 — 저수준 `Modal`의 미저장 보호(`dirty` prop)는 opt-in인데, 실제 폼을 담은
 * 19개 호출부 중 `Games.jsx`(게임방 만들기) 한 곳에만 걸려 있었다. 나머지는 Esc·바깥
 * 클릭·X 한 번에 입력이 그냥 사라졌다.
 *
 * `modal-unsaved-guard.test.jsx`가 `Modal`의 `dirty` 메커니즘 자체(있으면 확인, 없으면
 * 그냥 닫힘)를 이미 못박아 뒀다 — 여기서는 그 메커니즘을 실제로 쓰기 시작한 7개 화면
 * 각각이 (a) 값을 채우면 `dirty`가 true가 되는지, (b) 하단 '취소/닫기' 버튼도(Modal이
 * 아니라 화면이 직접 그리는 footer라 Modal의 dirty 가드를 우회한다 — Games.jsx가 이미
 * 겪은 문제) 같은 확인을 받는지를 고정한다.
 *
 * 감사 결과 나머지 호출부(DataScreen 상세/안내, SubListDrawer, Offboarding 상세,
 * SchedulerCalendar 실행 상세, Users 상세/임시비밀번호, SettingVersions, Tour, ChatRooms의
 * 1:1 시작)는 읽기 전용이거나 즉시-실행 액션만 있어 잃을 입력이 없다 — 그대로 둔다.
 * SettingEditor는 이미 자기 자신의 requestClose로 Modal.onClose 자체를 감싸고 있어(FormModal과
 * 같은 패턴) 별도 수정이 필요 없었다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { TicketEditModal } from "../screens/MyTickets.jsx";
import { PostFormModal } from "../screens/Board.jsx";
import { GroupModal } from "../screens/ChatRooms.jsx";
import { ImportModal } from "../screens/UsersBulk.jsx";
import { ManageRoomModal } from "../screens/ChatRoomMembers.jsx";
import { SavedViews } from "./SavedViews.jsx";
import { ConfirmProvider, ToastProvider } from "./kit.jsx";

function Providers({ children }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <ConfirmProvider>
          <MemoryRouter>{children}</MemoryRouter>
        </ConfirmProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}

// 모달 헤더의 X 아이콘도 접근성 이름이 "닫기"다(ModalHeader, kit.jsx) — 하단 footer 버튼과
// 이름이 같아 role만으로는 구분이 안 된다. footer 버튼이 DOM에서 나중에 그려진다
// (modal-unsaved-guard.test.jsx와 같은 관례).
function footerCloseButton(name) {
  const all = screen.getAllByRole("button", { name });
  return all[all.length - 1];
}

const WARN = /저장되지 않았습니다/;

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({});
});

describe("MyTickets — 티켓 편집 모달(VIS-88 지목 사례)", () => {
  const ticket = {
    id: "t1", tid: 1, title: "옛 제목", status: "진행", due: "", start: "", category: "",
    priority: "", difficulty: "", est_wd: null, act_wd: null,
    project_ids: [], assignee_user_ids: [],
  };
  it("제목을 고치고 '취소'를 누르면 확인을 먼저 묻는다", async () => {
    const onClose = vi.fn();
    render(<Providers><TicketEditModal ticket={ticket} open onClose={onClose} /></Providers>);
    await waitFor(() => expect(document.getElementById("te-title")).toBeTruthy());
    const title = document.getElementById("te-title");
    await userEvent.clear(title);
    await userEvent.type(title, "새 제목");
    await userEvent.click(screen.getByRole("button", { name: "취소" }));
    await screen.findByText(WARN);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("아무것도 안 바꿨으면 '취소'가 바로 닫는다", async () => {
    const onClose = vi.fn();
    render(<Providers><TicketEditModal ticket={ticket} open onClose={onClose} /></Providers>);
    await waitFor(() => expect(document.getElementById("te-title")).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(onClose).toHaveBeenCalled();
    expect(screen.queryByText(WARN)).toBeNull();
  });
});

describe("Board — 새 게시글 모달", () => {
  it("제목을 쓰고 Esc를 누르면 확인을 먼저 묻는다", async () => {
    const onClose = vi.fn();
    render(<Providers><PostFormModal open onClose={onClose} categories={["자유"]} mode="create" kind="free" /></Providers>);
    await waitFor(() => expect(document.getElementById("board-title")).toBeTruthy());
    await userEvent.type(document.getElementById("board-title"), "새 글 제목");
    await userEvent.keyboard("{Escape}");
    await screen.findByText(WARN);
    expect(onClose).not.toHaveBeenCalled();
  });
});

// 옛 문서 화면의 「새 문서」 모달은 사라졌다 (S14 · C2). `/knowledge` 의 새 문서 모달은
// 공용 `FormModal` 이고, 그 부품의 더티 가드는 이 파일 위쪽에서 이미 고정한다.


describe("ChatRooms — 새 그룹 채팅방 모달", () => {
  it("방 이름을 쓰고 '취소'를 누르면 확인을 먼저 묻는다", async () => {
    apiMock.mockImplementation((path) =>
      path === "/api/team-chat/directory" ? Promise.resolve({ users: [] }) : Promise.resolve({}));
    const onClose = vi.fn();
    render(<Providers><GroupModal open onClose={onClose} /></Providers>);
    const nameInput = document.getElementById("tc-gtitle");
    await waitFor(() => expect(nameInput).toBeTruthy());
    await userEvent.type(nameInput, "프로젝트 A 팀");
    await userEvent.click(screen.getByRole("button", { name: "취소" }));
    await screen.findByText(WARN);
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("UsersBulk — CSV 가져오기 모달", () => {
  it("CSV를 붙여넣고 '취소'를 누르면 확인을 먼저 묻는다", async () => {
    const onClose = vi.fn();
    render(<Providers><ImportModal onClose={onClose} onImported={() => {}} /></Providers>);
    const textarea = await screen.findByRole("textbox");
    await userEvent.type(textarea, "email,display_name\na@example.com,A");
    await userEvent.click(screen.getByRole("button", { name: "취소" }));
    await screen.findByText(WARN);
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("SavedViews — 뷰 저장 모달", () => {
  it("이름을 쓰고 '취소'를 누르면 확인을 먼저 묻는다", async () => {
    apiMock.mockImplementation((path) =>
      String(path).startsWith("/api/me/views") ? Promise.resolve({ items: [] }) : Promise.resolve({}));
    render(<Providers><SavedViews screenKey="tickets" query="" onApply={() => {}} /></Providers>);
    await userEvent.click(await screen.findByRole("button", { name: /저장된 뷰/ }));
    await userEvent.click(await screen.findByText("지금 필터를 뷰로 저장…"));
    const nameInput = await screen.findByLabelText("뷰 이름");
    await userEvent.type(nameInput, "내 뷰");
    const dialog = await screen.findByRole("dialog", { name: "현재 필터를 뷰로 저장" });
    await userEvent.click(within(dialog).getByRole("button", { name: "취소" }));
    await screen.findByText(WARN);
  });
});

describe("ChatRoomMembers — 채팅방 관리 모달", () => {
  it("이름을 고치고 '닫기'를 누르면 확인을 먼저 묻는다", async () => {
    apiMock.mockImplementation((path) =>
      path === "/api/team-chat/directory" ? Promise.resolve({ users: [] }) : Promise.resolve({}));
    const onClose = vi.fn();
    render(
      <Providers>
        <ManageRoomModal open onClose={onClose} roomId="r1" title="원래 이름" members={[]} meId="u1" />
      </Providers>,
    );
    const nameInput = document.getElementById("tc-rename");
    await waitFor(() => expect(nameInput).toBeTruthy());
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "새 이름");
    await userEvent.click(footerCloseButton("닫기"));
    await screen.findByText(WARN);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("아무것도 안 고쳤으면 '닫기'가 바로 닫는다", async () => {
    apiMock.mockImplementation((path) =>
      path === "/api/team-chat/directory" ? Promise.resolve({ users: [] }) : Promise.resolve({}));
    const onClose = vi.fn();
    render(
      <Providers>
        <ManageRoomModal open onClose={onClose} roomId="r1" title="원래 이름" members={[]} meId="u1" />
      </Providers>,
    );
    await waitFor(() => expect(document.getElementById("tc-rename")).toBeTruthy());
    await userEvent.click(footerCloseButton("닫기"));
    expect(onClose).toHaveBeenCalled();
  });
});
