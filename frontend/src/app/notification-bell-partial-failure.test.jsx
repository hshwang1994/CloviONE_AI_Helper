/* 한 묶음의 실패가 **다른 묶음까지 지우지 않는다** (R8-06).
 *
 * 관리 역할 계정의 벨은 두 묶음을 함께 받는다(perm-09) — 지금 콘솔의 알림과 상대 콘솔의
 * 알림이다. 그런데 오류 판정이 둘을 `||` 로 묶고 있었다:
 *
 *     listError = open && (list.isError || (otherAudience && listOther.isError))
 *
 * 그래서 `?audience=user` 하나가 5xx 를 받으면, 멀쩡히 받아 화면에 있던 **관리 알림까지**
 * 통째로 「불러오지 못했습니다」 한 장으로 덮였고 머리의 숫자와 「모두 읽음」도 사라졌다.
 * 관리자는 지금 처리해야 할 승인 알림을 눈앞에 두고 오류 화면을 봤다.
 *
 * 여기서 못박는 것:
 *   1. 상대 묶음만 실패하면 **내 묶음은 그대로 보인다** — 그리고 실패했다는 사실은 목록 위
 *      한 줄이 말한다(조용히 빠지면 「없다」고 말하는 것이 된다).
 *   2. 그 줄의 「다시 불러오기」는 **실패한 질의 하나만** 다시 부른다.
 *   3. 반례 — 내 묶음이 실패하면 예전 그대로 오류 한 장을 그린다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

const ADMIN_ITEM = {
  id: "n-admin", type: "approval_requested", title: "승인 요청: 역할 변경", audience: "admin",
  body: null, read_at: null, related_object_type: null, related_object_id: null,
  related_route: null, created_at: "2026-08-24T01:00:00",
};

function serverError() {
  const e = new Error("일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.");
  e.status = 500;
  return e;
}

/** `failing` 에 적힌 audience 의 요청만 500 으로 답한다(나머지는 정상). */
function mount(failing) {
  const calls = [];
  apiMock.mockImplementation((url) => {
    calls.push(url);
    const audience = /audience=(\w+)/.exec(url)?.[1];
    if (failing.includes(audience)) return Promise.reject(serverError());
    const items = audience === "admin" ? [ADMIN_ITEM] : [];
    if (url.startsWith("/api/notifications/unread-count")) {
      return Promise.resolve({ unread: items.length, badge: items.length });
    }
    return Promise.resolve({ items, total: items.length, unread: items.length, page: 1, page_size: 8 });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/admin"]}>
              {/* 관리 콘솔에 서 있는 관리자 — 앞에 서는 묶음이 `admin` 이고 상대가 `user` 다. */}
              <NotificationBell isUser={false} consoleUser={false} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
  return { ...view, calls };
}

async function openBell(user) {
  await waitFor(() => expect(apiMock).toHaveBeenCalled());
  await user.click(screen.getByRole("button", { name: /알림/ }));
}

beforeEach(() => { apiMock.mockReset(); });

describe("알림 벨 — 실패는 그 묶음에만 머문다", () => {
  it("개인 알림만 실패해도 관리 알림은 그대로 보이고, 실패한 묶음은 한 줄로 말한다", async () => {
    const user = userEvent.setup();
    mount(["user"]);
    await openBell(user);

    // 멀쩡히 받아 온 관리 알림이 살아 있다 — 예전에는 이 자리가 오류 한 장이었다.
    expect(await screen.findByText("승인 요청: 역할 변경")).toBeInTheDocument();
    // 못 받아 온 묶음은 「없다」가 아니라 「못 불러왔다」로 말한다.
    expect(await screen.findByText("내 업무 알림을 불러오지 못했습니다.")).toBeInTheDocument();
    // 머리 숫자와 일괄 처리도 살아 있다(내 묶음은 정확히 알고 있다).
    expect(screen.getByText(/안 읽음 1/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "관리 알림 모두 읽음" })).toBeInTheDocument();
  });

  it("「다시 불러오기」는 실패한 묶음 하나만 다시 부른다", async () => {
    const user = userEvent.setup();
    const { calls } = mount(["user"]);
    await openBell(user);
    await screen.findByText("내 업무 알림을 불러오지 못했습니다.");

    const before = calls.length;
    await user.click(screen.getByRole("button", { name: "다시 불러오기" }));
    await waitFor(() => expect(calls.length).toBeGreaterThan(before));

    const retried = calls.slice(before);
    expect(retried.every((u) => u.includes("audience=user"))).toBe(true);
    expect(retried.some((u) => u.includes("audience=admin"))).toBe(false);
  });

  it("반례 — 내가 보고 있는 묶음이 실패하면 예전처럼 오류 한 장을 그린다", async () => {
    const user = userEvent.setup();
    mount(["admin"]);
    await openBell(user);

    expect(await screen.findByRole("button", { name: /다시 시도|재시도/ })).toBeInTheDocument();
    expect(screen.queryByText("승인 요청: 역할 변경")).toBeNull();
    // 몸통이 오류인데 머리가 「안 읽음 N」·「모두 읽음」을 자신 있게 말하지 않는다.
    expect(screen.queryByRole("button", { name: "관리 알림 모두 읽음" })).toBeNull();
  });

  it("반례 — 둘 다 정상이면 실패 줄이 없다", async () => {
    const user = userEvent.setup();
    mount([]);
    await openBell(user);

    expect(await screen.findByText("승인 요청: 역할 변경")).toBeInTheDocument();
    expect(screen.queryByText("내 업무 알림을 불러오지 못했습니다.")).toBeNull();
  });
});
