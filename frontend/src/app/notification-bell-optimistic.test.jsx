import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 벨 배지의 **낙관 갱신** — 서버가 답하기 전에 숫자가 먼저 움직여야 한다.
 *
 * ## 무엇이 문제였나
 *
 * 읽음 처리의 낙관 갱신이 배지 캐시에는 **한 번도 닿지 않았다.** 0060 이 안 읽음 캐시를
 * audience 별로 갈랐는데(`["noti","unread",audience]`), 낙관 갱신은 갈라지기 전의 접두어
 * (`["noti","unread"]`)를 계속 썼다. `get/setQueryData` 는 정확히 일치하는 키만 찾으므로
 * 읽기는 언제나 `undefined` 였고 쓰기는 아무 캐시에도 안 닿았다 — 조용히 아무 일도 안 하는
 * 코드였다. 같은 결함을 목록 캐시(`NOTI_LIST`)에서는 이미 찾아 고쳐 놓고, 그 바로 아래
 * 배지 쪽만 남아 있었다.
 *
 * 눈에 보이는 증상: 항목을 눌러 팝오버가 닫히며 이동하는 흐름에서, 벨의 빨간 숫자가 서버
 * 무효화가 끝날 때까지 옛 값에 얼어붙는다. 방금 읽은 것이 안 읽음으로 계속 세어진다.
 *
 * 이 파일은 캐시를 직접 들여다본다 — 화면 숫자만 보면 팝오버가 열려 있는 동안에는 목록
 * 응답의 `unread` 로 가려져 통과해 버리는(가짜 초록) 자리라서다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { NotificationBell } from "./NotificationBell.jsx";
import { notiUnreadKey } from "./notification-keys.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function noti(i) {
  return {
    id: "n" + i, type: "ticket_assigned", title: "티켓 배정 " + i, audience: "user",
    body: null, read_at: null,
    related_object_type: null, related_object_id: null, related_route: null,
    created_at: "2026-08-07T01:00:00",
  };
}

/** 읽음 처리 응답을 **붙잡아 둔 채** 벨을 띄운다 — 낙관 갱신만 관찰하기 위해서다. */
function mount({ unread = 3 } = {}) {
  const items = Array.from({ length: unread }, (_, i) => noti(i + 1));
  const held = [];
  const seen = [];
  apiMock.mockImplementation((url) => {
    seen.push(url);
    if (url.startsWith("/api/notifications/unread-count")) {
      return Promise.resolve({ unread, badge: unread });
    }
    if (url.startsWith("/api/notifications?")) {
      return Promise.resolve({ items, total: unread, unread, page: 1, page_size: 8 });
    }
    return new Promise((resolve) => held.push(resolve));  // 읽음 처리 — 답하지 않는다.
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={["/me"]}>
          <NotificationBell isUser />
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>
  );
  return { qc, held, seen };
}

/** 헤더의 '모두 읽음' → 확인 모달의 '모두 읽음'. 두 버튼의 라벨이 같지만, 모달이 열리면
 *  MUI 가 나머지 화면을 `aria-hidden` 으로 덮으므로 역할 조회에는 언제나 하나만 잡힌다. */
async function confirmMarkAll(user) {
  await user.click(screen.getByRole("button", { name: "모두 읽음" }));
  const inDialog = await screen.findByRole("button", { name: "모두 읽음" });
  await user.click(inDialog);
}

async function openBell(user) {
  await waitFor(() => expect(apiMock).toHaveBeenCalled());
  const bell = await screen.findByRole("button", { name: /알림/ });
  await waitFor(() => expect(bell).toHaveAccessibleName(/알림 3건/));
  await user.click(bell);
  return bell;
}

beforeEach(() => { apiMock.mockReset(); });

describe("알림 벨 — 읽음 처리는 서버를 기다리지 않고 배지를 움직인다", () => {
  it("항목 하나를 읽으면 배지 캐시가 곧바로 하나 줄어든다", async () => {
    const user = userEvent.setup();
    const { qc } = mount();
    await openBell(user);

    const readButtons = await screen.findAllByRole("button", { name: "읽음 표시" });
    await user.click(readButtons[0]);

    const cached = qc.getQueryData(notiUnreadKey("user"));
    expect(cached).toBeTruthy();
    expect(cached.unread).toBe(2);
    // badge 는 방해금지·뮤트를 반영한 '지금 눈길을 끌 숫자'다 — 한쪽만 움직이면 그 둘이 어긋난다.
    expect(cached.badge).toBe(2);
  });

  it("'모두 읽음'을 누르면 배지 캐시가 곧바로 0 이 된다", async () => {
    const user = userEvent.setup();
    const { qc } = mount();
    await openBell(user);

    await confirmMarkAll(user);

    await waitFor(() => {
      const cached = qc.getQueryData(notiUnreadKey("user"));
      expect(cached.unread).toBe(0);
      expect(cached.badge).toBe(0);
    });
  });

  it("'모두 읽음'은 자기 콘솔의 audience 만 서버에 지시한다", async () => {
    const user = userEvent.setup();
    const { seen } = mount();
    await openBell(user);

    await confirmMarkAll(user);

    await waitFor(() => {
      const call = seen.find((u) => u.includes("/read-all"));
      expect(call).toBeTruthy();
      // audience 가 빠지면 서버가 관리 알림까지 읽음 처리한다(app/notifications/router.py).
      expect(call).toContain("audience=user");
    });
  });
});

/* r23 화면 대장 EX-UI6 — 숫자 배지는 종 단추 가운데를 덮는다(34px 단추, 20px 배지를 글리프 쪽으로 당겼다). 배지가 누름을 받으면
   숫자를 누른 사람의 클릭이 단추에 닿지 않아 알림 창이 안 열렸다. 배지는 표시일 뿐이라 누름을 흘려보내야 한다. */
describe("알림 벨 — 숫자 배지는 누름을 막지 않는다", () => {
  it("배지는 pointer-events 를 받지 않는다", async () => {
    mount();
    const bell = await screen.findByRole("button", { name: /알림 3건/ });
    const badge = bell.parentElement.querySelector(".MuiBadge-badge");
    expect(badge).not.toBeNull();
    expect(badge).toHaveTextContent("3");
    expect(getComputedStyle(badge).pointerEvents).toBe("none");
  });
});
