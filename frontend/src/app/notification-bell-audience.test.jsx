/* qa-contract-change: 소유자가 2026-09 에 「관리 콘솔의 종도 그 사람의 개인 알림(승인 결과·위임받음)을 라벨과 함께 보여 준다」로 정했다(perm-09) — 종이 한 묶음만 받는다는 옛 계약을 그렇게 바꾼다. 「모두 읽음」이 지금 보고 있는 묶음만 처리한다는 D-386 은 그대로 못박는다. */

/* 팀(사용자) 알림과 관리자 알림은 **서버가 갈라서** 준다 (0051 → 0060 → perm-09).
 *
 * 0051 의 원인 진단은 그대로다: `Notification` 에 "누구를 위한 것인가"(audience)가 없어,
 * 관리자이자 사용자인 사람의 벨에 자기 티켓 배정과 백업 실패가 구분 없이 섞였다.
 *
 * 0060 은 그 처방으로 **벨이 한 묶음만 받게** 했다. 그런데 그 축이 «역할» 이라, 관리 역할
 * 계정은 어느 콘솔에 서 있든 관리 알림만 받았다 — 실측: 승격을 요청한 관리자에게
 * `approval_decided` 가 29건 쌓였는데 종은 「승인 요청」만 보여 줬고, 같은 화면 사이드바의
 * 「알림」 배지는 34 였다. 한 화면이 두 숫자를 말했고, 개인 알림은 종에서 영영 안 보였다.
 *
 * 지금 계약은 셋이다:
 *   1. **앞에 서는 묶음은 지금 콘솔**이 정한다(`consoleUser`) — 역할이 아니다.
 *   2. **관리 역할 계정은 두 묶음을 다 받는다.** 어느 쪽인지는 묶음 머리가 밝힌다.
 *   3. **「모두 읽음」은 보고 있는 묶음만** 처리한다(D-386) — 화면에 뜬 적 없는 알림을
 *      지우지 않는다. 그래서 단추 문구가 범위를 말한다.
 *
 * 반례로 함께 못박는 것: role=user 의 벨은 상대 묶음을 **아예 묻지 않는다**(그 사람에게는
 * 관리 알림이 오지 않는다 — notify_admins 는 관리 역할에게만 보낸다).
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "admin", id: "u1" } }) }));

import { NotificationBell } from "./NotificationBell.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function noti(overrides = {}) {
  return {
    id: "n1", type: "ticket_assigned", title: "티켓 배정", audience: "user",
    body: null, read_at: null,
    related_object_type: null, related_object_id: null, related_route: null,
    created_at: "2026-08-07T01:00:00",
    ...overrides,
  };
}

/** 서버 대역 — **audience 파라미터를 실제로 보고** 그에 맞는 것만 돌려준다.
 *  화면에서 거르는 것이 아니라 서버가 거르는 것이 계약이므로, 대역도 그렇게 굴어야
 *  "화면이 몰래 필터링해서 통과하는" 가짜 초록을 만들지 않는다. */
function mount(itemsByAudience, { isUser, consoleUser } = {}) {
  const seen = [];
  const writes = [];
  apiMock.mockImplementation((url, opts) => {
    if (opts && opts.method === "POST") { writes.push(url); return Promise.resolve({ read_count: 1 }); }
    seen.push(url);
    const audience = /audience=(\w+)/.exec(url)?.[1];
    const items = itemsByAudience[audience] || [];
    if (url.startsWith("/api/notifications/unread-count")) {
      return Promise.resolve({ unread: items.length, badge: items.length });
    }
    if (url.startsWith("/api/notifications?")) {
      return Promise.resolve({
        items, total: items.length, unread: items.length, page: 1, page_size: 8,
      });
    }
    return Promise.resolve({ ok: true });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/me"]}>
              <NotificationBell isUser={isUser} consoleUser={consoleUser} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
  return { ...view, seen, writes };
}

async function openBell(user) {
  await waitFor(() => expect(apiMock).toHaveBeenCalled());
  await user.click(screen.getByRole("button", { name: /알림/ }));
}

beforeEach(() => { apiMock.mockReset(); });

describe("알림 벨 — 관리 역할은 두 묶음을 함께 보고, 지금 콘솔의 것이 앞에 선다", () => {
  it("관리자 콘솔의 벨이 개인 알림도 보여 주고, 두 묶음에 이름표를 붙인다", async () => {
    const user = userEvent.setup();
    const { seen } = mount({
      user: [noti({ id: "n1", title: "승인 결과", type: "approval_decided", audience: "user" })],
      admin: [noti({ id: "n2", title: "백업 실패", type: "backup_failed", audience: "admin" })],
    }, { isUser: false, consoleUser: false });
    await openBell(user);

    // 관리 알림과 개인 알림이 **함께** 뜬다 — 예전에는 개인 알림이 종에서 영영 안 보였다.
    expect((await screen.findAllByText("백업 실패")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("승인 결과")).length).toBeGreaterThan(0);
    // 어느 쪽 알림인지 묶음 머리가 말한다.
    expect(screen.getByRole("separator", { name: "관리 알림" })).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: "내 업무 알림" })).toBeInTheDocument();
    // 두 audience 를 모두 물었다.
    expect(seen.some((u) => u.includes("audience=admin"))).toBe(true);
    expect(seen.some((u) => u.includes("audience=user"))).toBe(true);
    // 종의 이름은 툴팁 · 배지와 같은 수를 말한다 — 합계와 그 구성(r23 「후」 대장 EX-UI: 「읽지 않음 12」 뒤에 13건 구성이 붙었다).
    // 창이 열리면 나머지 화면은 aria-hidden 이라 역할 조회에서 빠진다 — 단추를 직접 짚는다.
    const bell = document.querySelector("[aria-controls=\"noti-pop\"]");
    expect(bell.getAttribute("aria-label")).toMatch(/^알림 2건\(.*1건.*1건\)$/);
    expect(bell.getAttribute("aria-label")).not.toMatch(/읽지 않음/);
  });

  it("사용자 콘솔에 선 관리 역할은 개인 알림이 **앞에** 선다(축은 역할이 아니라 콘솔이다)", async () => {
    const user = userEvent.setup();
    mount({
      user: [noti({ id: "n1", title: "승인 결과", type: "approval_decided", audience: "user" })],
      admin: [noti({ id: "n2", title: "백업 실패", type: "backup_failed", audience: "admin" })],
    }, { isUser: false, consoleUser: true });
    await openBell(user);

    await screen.findAllByText("승인 결과");
    const headers = screen.getAllByRole("separator").map((el) => el.getAttribute("aria-label"));
    expect(headers[0]).toBe("내 업무 알림");
    expect(headers[1]).toBe("관리 알림");
  });

  it("일반 사용자(role=user)의 벨은 관리 알림을 **아예 묻지 않는다**(반례)", async () => {
    const user = userEvent.setup();
    const { seen } = mount({
      user: [noti({ id: "n1", title: "티켓 배정", audience: "user" })],
      admin: [noti({ id: "n2", title: "백업 실패", type: "backup_failed", audience: "admin" })],
    }, { isUser: true, consoleUser: true });
    await openBell(user);

    expect((await screen.findAllByText("티켓 배정")).length).toBeGreaterThan(0);
    expect(screen.queryByText("백업 실패")).toBeNull();
    expect(seen.every((u) => u.includes("audience=user"))).toBe(true);
    // 한 묶음뿐이면 이름표는 소음이다 — 안 그린다.
    expect(screen.queryAllByRole("separator").length).toBe(0);
  });

  it("배지는 **보여 주는 것 전부**를 센다 — 종을 열면 그 숫자만큼의 항목이 실제로 있다", async () => {
    const user = userEvent.setup();
    mount({
      user: [noti({ id: "u1" }), noti({ id: "u2" }), noti({ id: "u3" })],
      admin: [noti({ id: "a1", type: "backup_failed", audience: "admin" })],
    }, { isUser: false, consoleUser: false });

    // 관리 1 + 개인 3 = 4. 예전에는 1 을 띄우고 개인 3건은 어디에도 안 세었다.
    expect(await screen.findByText("4")).toBeInTheDocument();
    await openBell(user);
    expect(screen.getByText(/안 읽음 4/)).toBeInTheDocument();
  });

  it("「모두 읽음」은 보고 있는 묶음만 처리하고, 단추와 확인 문구가 그 범위를 밝힌다(D-386)", async () => {
    const user = userEvent.setup();
    const { writes } = mount({
      user: [noti({ id: "u1" }), noti({ id: "u2" })],
      admin: [noti({ id: "a1", type: "backup_failed", audience: "admin" })],
    }, { isUser: false, consoleUser: false });
    await openBell(user);

    const button = await screen.findByRole("button", { name: "관리 알림 모두 읽음" });
    await user.click(button);
    const dialog = await screen.findByRole("dialog", { name: "확인" });
    expect(within(dialog).getByText(/관리 알림만 읽음 처리합니다/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "모두 읽음" }));

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0]).toBe("/api/notifications/read-all?audience=admin");
  });
});
