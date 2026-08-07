/* 목록에서 읽음 처리하면 **상단 벨도 같이** 갱신된다 (X10).
 *
 * 예전에는 알림 화면이 자기 키만 무효화했고, 벨은 접두어가 다른 키로 60초 폴링했다 —
 * '모두 읽음' 을 눌러도 **최대 1분 동안 벨이 옛 숫자**를 들고 있었다. 코드 주석이 이 결함을
 * 예고해 놓고 그대로 남아 있었다.
 *
 * ## 이 테스트가 키 이름을 단언하지 않는 이유 (PF9)
 *
 * 예전 판은 `invalidateQueries` 가 `["noti-unread"]` 로 불렸는지를 봤다. 그건 **구현을**
 * 본 것이라, 알림 캐시를 한 뿌리(`["noti"]`)로 합치자 통과하던 성질이 그대로인데도 빨개졌다.
 * 지금은 **벨의 캐시가 실제로 무효화됐는가**를 본다 — 키를 어떻게 짓든 사용자가 겪는
 * 사실은 그것 하나다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { NOTI_SCREEN, NOTI_UNREAD, notiListKey } from "../app/notification-keys.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const CONFIG = {
  key: "notifications",
  // 실제 설정(screens/registry/notifications.js)과 같은 캐시 뿌리를 쓴다 — 여기만 다르면
  // 통과해도 아무 것도 증명하지 못한다.
  cacheKey: NOTI_SCREEN,
  title: "알림",
  endpoint: "/api/notifications",
  paginated: true,
  columns: [{ key: "title", label: "제목" }],
  detailFields: [],
  headerActions: [
    { key: "read-all", label: "모두 읽음", path: () => "/api/notifications/read-all",
      method: "POST" },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: [{ id: "n1", title: "알림 하나" }], page: 1, page_size: 20, total: 1 });
});

function renderScreen(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><DataScreen config={CONFIG} /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("화면 밖 값 갱신", () => {
  it("알림 화면의 작업이 벨과 팝오버 목록의 캐시까지 무효화한다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 벨과 팝오버가 이미 값을 들고 있는 상태를 만든다 — 캐시가 없으면 '무효화됐다'가
    // 아무 뜻도 없어서, 무엇을 해도 통과하는 테스트가 된다.
    qc.setQueryData(NOTI_UNREAD, { unread: 3, badge: 3, by_type: {} });
    qc.setQueryData(notiListKey("unread"), { items: [] });
    expect(qc.getQueryState(NOTI_UNREAD).isInvalidated).toBe(false);

    renderScreen(qc);
    await screen.findByText("알림 하나");

    fireEvent.click(screen.getByRole("button", { name: "모두 읽음" }));

    await waitFor(() => {
      expect(qc.getQueryState(NOTI_UNREAD).isInvalidated, "벨 배지").toBe(true);
      expect(qc.getQueryState(notiListKey("unread")).isInvalidated, "팝오버 목록").toBe(true);
    }, { timeout: 3000 });
  });
});
