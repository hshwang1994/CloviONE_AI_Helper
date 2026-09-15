import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 채팅방 — 목록과 대화는 두 판이다 (핸드오프 RULES §9 · README §C · 계획 E).
 *
 * 지키는 것 셋:
 *   1. 목록 판(296 · `CHAT.listWidth`)과 대화 판이 판 틈을 두고 나란히 선다(좁으면 한 판).
 *   2. 지금 보는 방의 목록 행은 함몰면 + 왼쪽 레일이다 — 사이드바 활성 항목과 같은 어휘다.
 *   3. 새 그룹 · 1:1 창의 실패는 창 안 메시지 박스다(토스트였다) — 창을 닫았다 열면 걷힌다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { ChatRooms } from "./ChatRooms.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { CHAT } from "../ui/chat.js";

const ROOMS = {
  team: null,
  global: null,
  items: [
    { id: "r1", kind: "group", title: "인프라 팀", member_count: 4, unread: 0, last_preview: "", last_at: null },
    { id: "r2", kind: "group", title: "기획 팀", member_count: 3, unread: 2, last_preview: "안녕", last_at: null },
  ],
  unread_total: 2,
};
const ROOM_META = {
  room: { id: "r1", kind: "group", is_global: false, title: "인프라 팀", member_count: 4 },
  members: [], messages: [], seq: 0, people: {},
  you: { user_id: "u1", role: "member", last_read_seq: 0, is_member: true, can_disband: false, can_hide: false },
};
const DIRECTORY = { users: [{ user_id: "u9", display_name: "김하나", department_name: "개발팀" }] };

function mount(entry, extra = () => undefined) {
  apiMock.mockImplementation((url, opts) => {
    const special = extra(url, opts);
    if (special) return special;
    if (url === "/api/team-chat/rooms") return Promise.resolve(ROOMS);
    if (String(url).startsWith("/api/team-chat/rooms/r1/messages?")) return Promise.resolve(ROOM_META);
    if (url === "/api/team-chat/directory") return Promise.resolve(DIRECTORY);
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/chat-rooms" element={<ChatRooms />} />
            <Route path="/chat-rooms/:id" element={<ChatRooms />} />
          </Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/* emotion 이 <style> 에 낸 규칙 텍스트 — jsdom 은 미디어 질의를 평가하지 않으므로 넓은 화면 트랙은 규칙에서 읽는다. */
const emittedCss = () => [...document.querySelectorAll("style")].map((s) => s.textContent || "").join("\n");

beforeEach(() => { apiMock.mockReset(); });

describe("두 판", () => {
  it("목록 판과 대화 판이 나란히 서고, 넓은 화면의 트랙은 목록 296 / 나머지다", async () => {
    mount("/chat-rooms/r1");
    await screen.findByRole("heading", { name: "인프라 팀" });
    const layout = document.querySelector("[data-chat-layout]");
    expect(layout).toBeTruthy();
    const cards = [...layout.children].filter((el) => el.classList.contains("MuiCard-root"));
    expect(cards).toHaveLength(2);
    const listHeading = within(cards[0]).getByRole("heading", { name: "대화" });
    expect(listHeading).toBeInTheDocument();
    // 목록 판 머리는 판 제목 글자 갈래다(1.0625rem/700 — 대장 §0-13). 옛 `FONT_SIZE.sectionTitle`(1.1875rem)로 돌아가면 깨진다.
    expect(getComputedStyle(listHeading).fontSize).toBe("1.0625rem");
    expect(String(getComputedStyle(listHeading).fontWeight)).toBe("700");
    expect(within(cards[1]).getByRole("heading", { name: "인프라 팀" })).toBeInTheDocument();
    expect(emittedCss()).toContain(`grid-template-columns:${CHAT.listWidth} minmax(0, 1fr)`);
    expect(CHAT.listWidth).toBe("18.5rem");
  });

  it("지금 보는 방의 목록 행은 함몰면이고 다른 행은 면이 없다", async () => {
    mount("/chat-rooms/r1");
    await screen.findByRole("heading", { name: "인프라 팀" });
    const active = document.querySelector('button[aria-current="true"]');
    expect(active).toHaveTextContent("인프라 팀");
    const other = screen.getByRole("button", { name: /기획 팀/ });
    expect(getComputedStyle(active).backgroundColor).not.toBe(getComputedStyle(other).backgroundColor);
    expect(getComputedStyle(active).borderLeftStyle).toBe("solid");
  });
});

describe("목록 판 머리 · 페이지 머리 동작 · 목록 시각 (조합 계약 C-4 · C-6 · 채팅방 시안)", () => {
  it("「1:1」 · 「새 그룹」은 페이지 머리의 34 보조 단추이고, 목록 판 머리는 「대화」 + 건수다", async () => {
    mount("/chat-rooms/r1");
    await screen.findByRole("heading", { name: "인프라 팀" });
    const layout = document.querySelector("[data-chat-layout]");
    const listCard = [...layout.children].find((el) => el.classList.contains("MuiCard-root"));
    for (const name of ["1:1", "새 그룹"]) {
      const btn = screen.getByRole("button", { name });
      // 목록 판 밖(페이지 머리)이고 채움이 아니다 — 이 화면의 채움은 보내기 하나다.
      expect(listCard.contains(btn), `${name} 가 목록 판 안에 섰다`).toBe(false);
      expect(layout.contains(btn)).toBe(false);
      expect(btn.className).not.toMatch(/MuiButton-contained/);
      expect(btn.className).not.toMatch(/MuiButton-sizeSmall/);
    }
    // 머리 건수는 목록이 세우는 방 수다(내 팀 · 전체 없음 + 방 둘).
    const count = listCard.querySelector("[data-room-count]");
    expect(count).toHaveTextContent("2");
    // 판 높이는 화면 아래까지 서는 정본 값이다(높이 고정 판).
    expect(layout.getAttribute("data-page-fill")).toBe("");
    expect(emittedCss()).toContain("height:calc(100vh - 12rem)");
  });

  it("이레가 넘은 마지막 대화 시각은 「M월 D일」 짧은 형식이고 전체 시각은 이름표가 든다", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-15T03:00:00Z"));
    try {
      mount("/chat-rooms/r1", (url) => (url === "/api/team-chat/rooms"
        ? Promise.resolve({ ...ROOMS, items: [ROOMS.items[0], { ...ROOMS.items[1], last_at: "2026-08-24T03:00:00" }] })
        : undefined));
      const stamp = await screen.findByText("8월 24일");
      expect(stamp.tagName.toLowerCase()).toBe("time");
      expect(stamp.getAttribute("title")).toMatch(/2026/);
      expect(screen.queryByText(/2026\. 8\. 24\./)).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("창 안의 실패 (핸드오프 RULES §1 — 토스트였다)", () => {
  it("새 그룹 만들기가 실패하면 창 안 상자가 말하고, 창을 닫았다 열면 걷힌다", async () => {
    const user = userEvent.setup();
    mount("/chat-rooms/r1", (url, opts) => (
      url === "/api/team-chat/rooms" && opts && opts.method === "POST"
        ? Promise.reject(new Error("같은 이름의 방이 이미 있습니다."))
        : undefined
    ));
    await screen.findByRole("heading", { name: "인프라 팀" });
    await user.click(screen.getByRole("button", { name: "새 그룹" }));
    let dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/방 이름/), "인프라 팀");
    await user.click(within(dialog).getByRole("button", { name: "추가" }));
    expect(await within(dialog).findByText("같은 이름의 방이 이미 있습니다.")).toBeInTheDocument();

    // 이름을 쳐 둔 창이라 닫기 전에 버릴지 묻는다(VIS-88) — 버리고 닫는다.
    await user.click(within(dialog).getByRole("button", { name: "취소" }));
    await screen.findByText(/저장되지 않았습니다/);
    // 확인 창의 「닫기」가 DOM 에서 가장 나중이다(모달 머리의 닫기 아이콘과 이름이 같다).
    const closes = screen.getAllByRole("button", { name: "닫기" });
    await user.click(closes[closes.length - 1]);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await user.click(screen.getByRole("button", { name: "새 그룹" }));
    dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByText("같은 이름의 방이 이미 있습니다.")).toBeNull();
  });

  it("1:1 대화 시작이 실패하면 창 안 상자가 말한다", async () => {
    const user = userEvent.setup();
    mount("/chat-rooms/r1", (url, opts) => (
      url === "/api/team-chat/rooms/direct" && opts && opts.method === "POST"
        ? Promise.reject(new Error("이 사람과는 대화를 시작할 수 없습니다."))
        : undefined
    ));
    await screen.findByRole("heading", { name: "인프라 팀" });
    await user.click(screen.getByRole("button", { name: "1:1" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(await within(dialog).findByRole("button", { name: /김하나/ }));
    expect(await within(dialog).findByText("이 사람과는 대화를 시작할 수 없습니다.")).toBeInTheDocument();
  });
});
