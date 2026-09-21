import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 채팅방 참여자 명단 — 방 머리의 요약 글자나 얼굴 스택을 누르면 누가 들어와 있는지 보인다 (사용자 지시 2026-09-21 항목 3).
 *
 * 예전에는 전체 명단이 방장 전용 「관리」 창에만 있어서 일반 참여자 · 1:1 · 내 팀 방에서는 누가 있는지 볼 길이 없었다.
 * 여기서 못박는 것:
 *   1. 요약 글자는 명단을 여는 **단추 하나**다. 얼굴 스택은 목록 뜻을 지킨 채 눌러도 같은 팝오버를 연다(탭 순서에는 없다).
 *   2. 줄 = 사진 + 이름 + 직급 + 둘째 줄 부서 경로 + 방장 · (나) · 보관됨 + 접속 상태 글자. 관리 창과 같은 줄 한 벌이다.
 *   3. 순서는 보는 중 → 방해금지 → 자리 비움, 그 안에서 이름순이다. 동명이인은 경로 줄이 가른다.
 *   4. 여덟 명을 넘으면 좁히기 칸이 서고, 공백 · 대소문자를 접어 대조한다. 줄에 보이는 부서 경로(윗칸 포함)로도 찾는다.
 *      조직이 둘 이상 섞인 방에서는 줄이 조직 + 끝 칸 부서로 선다.
 *   5. Esc 로 닫으면 초점이 요약 단추로 돌아온다. 얼굴을 눌러 열었어도 같다.
 *   6. 방장이 아니어도 열린다. 전체 채팅에는 명단이 없어서 여는 자리도 없다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { RoomDetailPanel } from "./ChatRoom.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ME = "u1";
const DEV = [{ id: "d1", name: "플랫폼본부" }, { id: "d2", name: "플랫폼 개발팀" }];
const DESIGN = [{ id: "d1", name: "플랫폼본부" }, { id: "d3", name: "디자인팀" }];
const OPS = [{ id: "d4", name: "ClovirONE 운영" }];

/** 참여자 한 명 — `members[]`(참여 사실)와 `people{}`(신원) 두 조각을 서버와 같은 모양으로 만든다. */
function who(user_id, name, { path = [], title = "", org = "", role = "member", online = false, presence, archived = false } = {}) {
  const dept = path.length ? path[path.length - 1].name : "";
  return {
    member: {
      user_id, name, dept, title, org, archived, role, last_read_seq: 0, online,
      presence: presence || (online ? "online" : "offline"),
    },
    person: {
      user_id, display_name: name, dept, title, org, dept_path: path, archived,
      avatar_url: null, avatar_default_key: null,
    },
  };
}

function payload(list, { room = {}, you = {} } = {}) {
  return {
    room: { id: "r1", kind: "group", is_global: false, title: "우리방", member_count: list.length, ...room },
    members: list.map((x) => x.member),
    people: Object.fromEntries(list.map((x) => [x.person.user_id, x.person])),
    messages: [],
    seq: 0,
    you: { user_id: ME, role: "member", last_read_seq: 0, is_member: true,
           can_disband: false, can_hide: false, can_manage: false, ...you },
  };
}

/* 일반 참여자(나) 시점의 그룹 방. 보는 중 셋(방해금지 한 명 포함), 자리 비움 둘. 조직은 하나다. */
const ORG = "굿모닝아이텍";
const ROOM = [
  who(ME, "나정민", { path: DEV, title: "책임", org: ORG, online: true }),
  who("u2", "강민수", { path: DESIGN, title: "팀장", org: ORG, role: "owner" }),
  who("u3", "김하나", { path: OPS, title: "매니저", org: ORG, online: true, presence: "dnd" }),
  who("u4", "박보관", { path: DEV, title: "선임", org: ORG, archived: true }),
  who("u5", "가나다", { org: ORG, online: true }),
];

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
        <MemoryRouter initialEntries={["/chat-rooms/r1"]}>
          <Routes>
            <Route path="/chat-rooms/:id" element={<RoomDetailPanel id="r1" />} />
            <Route path="/chat-rooms" element={<div>채팅방 목록</div>} />
          </Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const summaryButton = () => screen.findByRole("button", { name: /^참여자 \d+명, 보는 중 \d+명$/ });
const rowsOf = (dialog) => within(within(dialog).getByRole("list", { name: "참여자 명단" })).getAllByRole("listitem");
const rowOf = (dialog, name) => rowsOf(dialog).find((li) => within(li).queryByText(name));

async function openFromSummary(user, n) {
  await user.click(await summaryButton());
  return screen.findByRole("dialog", { name: `참여자 ${n}명` });
}

beforeEach(() => { apiMock.mockReset(); });

describe("명단을 여는 자리 — 요약 단추 하나, 누르는 자리는 둘", () => {
  it("🔴 요약 글자가 명단 팝오버를 여는 단추다 — 보이는 글자가 이름이고 열림 상태를 말한다", async () => {
    const user = userEvent.setup();
    mount(payload(ROOM));
    const summary = await summaryButton();
    expect(summary.tagName).toBe("BUTTON");
    expect(summary).toHaveAccessibleName("참여자 5명, 보는 중 3명");
    expect(summary).toHaveAttribute("aria-haspopup", "dialog");
    expect(summary).toHaveAttribute("aria-expanded", "false");
    expect(summary).not.toHaveAttribute("aria-controls");
    expect(summary).toHaveAttribute("data-member-summary");

    await user.click(summary);
    const dialog = await screen.findByRole("dialog", { name: "참여자 5명" });
    expect(dialog).toHaveAttribute("data-member-roster");
    expect(within(dialog).getByText("참여자 5명")).toBeInTheDocument();
    expect(summary).toHaveAttribute("aria-expanded", "true");
    expect(summary).toHaveAttribute("aria-controls", dialog.id);
    expect(rowsOf(dialog)).toHaveLength(5);
  });

  it("🔴 얼굴 스택을 눌러도 같은 팝오버가 열린다 — 스택은 목록 뜻을 지키고 탭 순서에 서지 않는다", async () => {
    const user = userEvent.setup();
    const { container } = mount(payload(ROOM));
    await summaryButton();
    const faces = screen.getByRole("list", { name: "참여자" });
    expect(faces).not.toHaveAttribute("tabindex");
    expect(faces.closest("button")).toBeNull();
    expect(container.querySelector("[data-member-faces]").hasAttribute("tabindex")).toBe(false);
    // 명단을 여는 단추는 요약 하나뿐이다(같은 말을 두 번 읽지 않는다).
    expect(screen.getAllByRole("button", { name: /참여자/ })).toHaveLength(1);

    await user.click(within(faces).getAllByRole("listitem")[0]);
    const dialog = await screen.findByRole("dialog", { name: "참여자 5명" });
    expect(rowsOf(dialog)).toHaveLength(5);
  });

  it("🔴 방장이 아니어도(「관리」가 없어도) 명단을 연다", async () => {
    const user = userEvent.setup();
    mount(payload(ROOM, { you: { can_manage: false } }));
    await summaryButton();
    expect(screen.queryByRole("button", { name: "관리" })).toBeNull();
    const dialog = await openFromSummary(user, 5);
    expect(within(dialog).getByText("강민수")).toBeInTheDocument();
  });

  it("1:1 방과 내 팀 방도 명단을 연다", async () => {
    const user = userEvent.setup();
    const pair = [who(ME, "나정민", { path: DEV, online: true }), who("u2", "강민수", { path: DESIGN })];
    const { unmount } = mount(payload(pair, { room: { kind: "direct", title: "강민수" }, you: { can_hide: true } }));
    let dialog = await openFromSummary(user, 2);
    expect(within(dialog).getByText("강민수")).toBeInTheDocument();
    unmount();

    mount(payload(ROOM, { room: { title: "플랫폼 개발팀", department_id: "d2" } }));
    dialog = await openFromSummary(user, 5);
    expect(rowsOf(dialog)).toHaveLength(5);
  });

  it("🔴 전체 채팅은 서버에 명단이 없어서 여는 자리도 없다 — 없는 명단을 지어내지 않는다", async () => {
    const { container } = mount(payload([], {
      room: { is_global: true, title: "전체 채팅", member_count: 0 },
      you: { role: null, is_member: false },
    }));
    await screen.findByRole("heading", { name: "전체 채팅" });
    expect(screen.queryByRole("button", { name: /참여자/ })).toBeNull();
    expect(container.querySelector("[data-member-summary]")).toBeNull();
    expect(container.querySelector("[data-member-faces]")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("얼굴 스택 표본 선택자(`kit_measure.py` 의 머리 얼굴 26)가 실제 얼굴을 잡는다 — 예전 `[data-member-strip]` 은 표본 0 이었다", async () => {
    const many = Array.from({ length: 12 }, (_, i) => who(`m${i}`, `사람${i}`, { online: i % 3 === 0 }));
    const { container } = mount(payload(many));
    await summaryButton();
    expect(container.querySelectorAll('[data-member-faces] [role="listitem"] .k-avatar')).toHaveLength(8);
    expect(container.querySelectorAll("[data-member-strip]")).toHaveLength(0);
  });
});

describe("명단 줄 — 사진 · 이름 · 직급 · 부서 경로 · 방장 · (나) · 보관됨 · 접속 상태", () => {
  it("🔴 줄은 이름과 직급, 둘째 줄 부서 경로를 보여 준다", async () => {
    const user = userEvent.setup();
    mount(payload(ROOM));
    const dialog = await openFromSummary(user, 5);
    const mine = rowOf(dialog, "나정민");
    expect(mine).toHaveAttribute("data-member-row");
    expect(within(mine).getByText("책임")).toBeInTheDocument();
    expect(within(mine).getByText("플랫폼본부 › 플랫폼 개발팀")).toBeInTheDocument();
    expect(mine.querySelector(".k-avatar")).not.toBeNull();
    const owner = rowOf(dialog, "강민수");
    expect(within(owner).getByText("팀장")).toBeInTheDocument();
    expect(within(owner).getByText("플랫폼본부 › 디자인팀")).toBeInTheDocument();
    // 조직이 하나뿐이면 경로 앞에 조직을 붙이지 않는다 — 모든 줄에 같은 조직명이 서면 줄만 길어진다.
    expect(within(dialog).queryByText(new RegExp(ORG))).toBeNull();
  });

  it("🔴 보는 중 → 방해금지 → 자리 비움, 같은 상태 안에서는 이름순이다 — 접속 글자가 같은 사실을 말한다", async () => {
    const user = userEvent.setup();
    mount(payload(ROOM));
    const dialog = await openFromSummary(user, 5);
    const rows = rowsOf(dialog);
    const order = ["가나다", "나정민", "김하나", "강민수", "박보관"];
    const presence = ["이 대화 보는 중", "이 대화 보는 중", "방해금지", "자리 비움", "자리 비움"];
    order.forEach((name, i) => {
      expect(within(rows[i]).getByText(name), `${i}번째 줄`).toBeInTheDocument();
      expect(within(rows[i]).getByText(presence[i]), `${name} 의 접속 글자`).toBeInTheDocument();
    });
    // 얼굴 스택도 같은 순서와 같은 말이다 — 스택의 얼굴이 명단의 첫 줄들이다.
    const faces = within(screen.getByRole("list", { name: "참여자", hidden: true })).getAllByRole("listitem", { hidden: true });
    expect(faces.map((f) => f.getAttribute("aria-label"))).toEqual(order.map((name, i) => `${name}, ${presence[i]}`));
  });

  it("🔴 방장 배지 · (나) · (보관됨)이 제 줄에만 붙는다", async () => {
    const user = userEvent.setup();
    mount(payload(ROOM));
    const dialog = await openFromSummary(user, 5);
    const mine = rowOf(dialog, "나정민");
    expect(within(mine).getByText("(나)")).toBeInTheDocument();
    expect(getComputedStyle(within(mine).getByText("나정민")).fontWeight).toBe("700");
    expect(within(rowOf(dialog, "강민수")).getByText("방장")).toBeInTheDocument();
    expect(within(rowOf(dialog, "박보관")).getByText("(보관됨)")).toBeInTheDocument();
    expect(within(dialog).getAllByText("(나)")).toHaveLength(1);
    expect(within(dialog).getAllByText("방장")).toHaveLength(1);
    expect(within(dialog).getAllByText("(보관됨)")).toHaveLength(1);
  });

  it("🔴 동명이인은 부서 경로 줄이 가른다 — 얼굴 이름표도 소속을 붙인다", async () => {
    const user = userEvent.setup();
    mount(payload([
      who(ME, "나정민", { path: OPS, online: true }),
      who("u2", "김민수", { path: DEV, title: "책임", online: true }),
      who("u3", "김민수", { path: DESIGN, title: "책임" }),
    ]));
    const dialog = await openFromSummary(user, 3);
    const twins = rowsOf(dialog).filter((li) => within(li).queryByText("김민수"));
    expect(twins).toHaveLength(2);
    expect(within(twins[0]).getByText("플랫폼본부 › 플랫폼 개발팀")).toBeInTheDocument();
    expect(within(twins[1]).getByText("플랫폼본부 › 디자인팀")).toBeInTheDocument();
    const labels = within(screen.getByRole("list", { name: "참여자", hidden: true }))
      .getAllByRole("listitem", { hidden: true }).map((f) => f.getAttribute("aria-label"));
    expect(labels).toContain("김민수 (플랫폼 개발팀 책임), 이 대화 보는 중");
    expect(labels).toContain("김민수 (디자인팀 책임), 자리 비움");
  });

  it("🔴 조직이 둘 이상 섞인 방에서는 조직과 끝 칸 부서를 그린다 — 전체 경로를 세우면 좁은 줄에서 끝 칸이 먼저 잘린다", async () => {
    const user = userEvent.setup();
    mount(payload([
      who(ME, "나정민", { path: DEV, org: "굿모닝아이텍", online: true }),
      who("u2", "강민수", { path: DESIGN, org: "협력사" }),
    ]));
    const dialog = await openFromSummary(user, 2);
    expect(within(rowOf(dialog, "나정민")).getByText("굿모닝아이텍 › 플랫폼 개발팀")).toBeInTheDocument();
    expect(within(rowOf(dialog, "강민수")).getByText("협력사 › 디자인팀")).toBeInTheDocument();
    // 가운데 칸을 뺀 줄이라 전체 경로(조직 포함)는 풍선이 든다 — 줄이는 것은 정보를 없애는 것이 아니다.
    expect(within(dialog).getByLabelText("협력사 › 플랫폼본부 › 디자인팀")).toHaveTextContent("협력사 › 디자인팀");
  });

  it("관리 창도 같은 줄 한 벌을 쓴다 — 직급과 부서 경로가 두 자리에서 같다", async () => {
    const user = userEvent.setup();
    mount(payload(ROOM, { you: { role: "owner", can_manage: true } }));
    const dialog = await openFromSummary(user, 5);
    const inRoster = rowOf(dialog, "김하나");
    expect(within(inRoster).getByText("매니저")).toBeInTheDocument();
    expect(within(inRoster).getByText("ClovirONE 운영")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    await user.click(screen.getByRole("button", { name: "관리" }));
    const manage = await screen.findByRole("dialog", { name: "채팅방 관리" });
    const inManage = within(manage).getAllByRole("listitem").find((li) => within(li).queryByText("김하나"));
    expect(inManage).toHaveAttribute("data-member-row");
    expect(within(inManage).getByText("매니저")).toBeInTheDocument();
    expect(within(inManage).getByText("ClovirONE 운영")).toBeInTheDocument();
    expect(within(inManage).getByText("방해금지")).toBeInTheDocument();
    expect(within(inManage).getByRole("button", { name: "내보내기" })).toBeInTheDocument();
  });
});

describe("여러 명일 때 — 좁히기 칸", () => {
  const crowd = (n) => [
    who(ME, "나정민", { path: DEV, title: "책임", online: true }),
    who("u2", "김 하나", { path: DEV, title: "선임" }),
    who("u3", "이운영", { path: OPS, title: "매니저" }),
    ...Array.from({ length: n - 3 }, (_, i) => who(`x${i}`, `디자이너${i}`, { path: DESIGN, title: "주임" })),
  ];

  it("여덟 명까지는 좁히기 칸이 없다 — 다 보이는 명단에 칸을 세우면 소음이다", async () => {
    const user = userEvent.setup();
    mount(payload(crowd(8)));
    const dialog = await openFromSummary(user, 8);
    expect(within(dialog).queryByRole("searchbox")).toBeNull();
    expect(rowsOf(dialog)).toHaveLength(8);
  });

  it("🔴 여덟 명을 넘으면 목록 위에 좁히기 칸이 서고, 공백 · 대소문자를 접어 대조한다", async () => {
    const user = userEvent.setup();
    mount(payload(crowd(9)));
    const dialog = await openFromSummary(user, 9);
    const box = within(dialog).getByRole("searchbox", { name: "사람 좁히기" });
    expect(box).toHaveAttribute("placeholder", "이름, 부서로 좁히기");
    // 칸은 목록보다 앞에 선다.
    const list = within(dialog).getByRole("list", { name: "참여자 명단" });
    expect(box.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    await user.type(box, "플랫폼개발");
    expect(rowsOf(dialog).map((li) => li.querySelector("[title]").getAttribute("title"))).toEqual(["나정민 (나) 책임", "김 하나 선임"]);
    expect(within(dialog).getByText("2명 / 전체 9명")).toBeInTheDocument();

    await user.clear(box);
    await user.type(box, "김하나");
    expect(rowsOf(dialog)).toHaveLength(1);
    expect(within(rowsOf(dialog)[0]).getByText("김 하나")).toBeInTheDocument();

    await user.clear(box);
    await user.type(box, "CLOVIRONE");
    expect(rowsOf(dialog)).toHaveLength(1);
    expect(within(rowsOf(dialog)[0]).getByText("이운영")).toBeInTheDocument();
  });

  it("🔴 줄에 보이는 부서 경로로 찾는다 — 상위 부서 이름으로도 걸리고, 경로 두 칸을 이어 붙인 글자는 안 걸린다", async () => {
    const user = userEvent.setup();
    mount(payload(crowd(9)));
    const dialog = await openFromSummary(user, 9);
    const box = within(dialog).getByRole("searchbox", { name: "사람 좁히기" });
    // 「플랫폼본부」는 끝 칸 부서가 아니라 경로의 윗칸이다. 줄에 「플랫폼본부 › …」로 보이므로 찾을 수 있어야 한다.
    await user.type(box, "플랫폼본부");
    expect(rowsOf(dialog)).toHaveLength(8);
    expect(rowsOf(dialog).some((li) => within(li).queryByText("이운영"))).toBe(false);
    expect(within(dialog).getByText("8명 / 전체 9명")).toBeInTheDocument();

    await user.clear(box);
    await user.type(box, "본부플랫폼");
    expect(within(dialog).queryByRole("list", { name: "참여자 명단" })).toBeNull();
    expect(within(dialog).getByText("조건에 맞는 사람이 없습니다")).toBeInTheDocument();
  });

  it("🔴 조건 때문에 0명이면 「없다」가 아니라 「조건에 맞는 사람이 없다」고 말한다", async () => {
    const user = userEvent.setup();
    mount(payload(crowd(9)));
    const dialog = await openFromSummary(user, 9);
    await user.type(within(dialog).getByRole("searchbox", { name: "사람 좁히기" }), "없는사람");
    expect(within(dialog).queryByRole("list", { name: "참여자 명단" })).toBeNull();
    expect(within(dialog).getByText("조건에 맞는 사람이 없습니다")).toBeInTheDocument();
    expect(within(dialog).getByText("이름이나 부서 일부로 다시 찾아보세요.")).toBeInTheDocument();
  });

  it("명단 목록은 초점을 받는다 — 누를 것이 없는 줄이라 그러지 않으면 키보드로 넘친 줄까지 스크롤할 수 없다", async () => {
    const user = userEvent.setup();
    mount(payload(crowd(12)));
    const dialog = await openFromSummary(user, 12);
    expect(within(dialog).getByRole("list", { name: "참여자 명단" })).toHaveAttribute("tabindex", "0");
  });

  it("닫았다 다시 열면 좁히기 조건이 걷혀 전체 명단부터 보인다", async () => {
    const user = userEvent.setup();
    mount(payload(crowd(9)));
    let dialog = await openFromSummary(user, 9);
    await user.type(within(dialog).getByRole("searchbox", { name: "사람 좁히기" }), "이운영");
    expect(rowsOf(dialog)).toHaveLength(1);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    dialog = await openFromSummary(user, 9);
    expect(within(dialog).getByRole("searchbox", { name: "사람 좁히기" })).toHaveValue("");
    expect(rowsOf(dialog)).toHaveLength(9);
  });
});

describe("닫기와 초점", () => {
  it("🔴 Esc 로 닫히고 초점이 요약 단추로 돌아온다", async () => {
    const user = userEvent.setup();
    mount(payload(ROOM));
    const summary = await summaryButton();
    await user.click(summary);
    await screen.findByRole("dialog", { name: "참여자 5명" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(summary).toHaveAttribute("aria-expanded", "false");
    await waitFor(() => expect(summary).toHaveFocus());
  });

  it("🔴 얼굴 스택을 눌러 열었어도 닫히면 초점은 요약 단추로 돌아온다 — 스택은 초점을 받지 않는 자리다", async () => {
    const user = userEvent.setup();
    mount(payload(ROOM));
    const summary = await summaryButton();
    await user.click(within(screen.getByRole("list", { name: "참여자" })).getAllByRole("listitem")[2]);
    await screen.findByRole("dialog", { name: "참여자 5명" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(summary).toHaveFocus());
  });

  it("키보드로 요약 단추에 와서 Enter 를 누르면 열리고, Esc 로 닫으면 제자리다", async () => {
    const user = userEvent.setup();
    mount(payload(ROOM));
    const summary = await summaryButton();
    summary.focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("dialog", { name: "참여자 5명" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(summary).toHaveFocus());
  });
});
