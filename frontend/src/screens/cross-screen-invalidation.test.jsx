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
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
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

  /* 작업 큐(/jobs)의 실패 건수는 대시보드 상단 경보/지표 타일("실패 작업"/"미해결 실패
   * 작업")과 **같은 사실**(jobs.failed_open, app/health/service.py)을 보여준다. 재시도로
   * 그 작업이 failed 상태를 벗어나면 서버 값은 즉시 바뀌지만, 대시보드는 자기 cacheRoot만
   * 무효화하는 여느 화면과 달리 별도 queryKey(["dashboard"])를 30초 폴링으로만 본다 —
   * CROSS_SCREEN_KEYS(X10)에 매핑이 없으면 재시도 직후에도 대시보드가 최대 30초 동안
   * 옛 실패 건수를 보여준다(알림 화면이 예전에 벨을 못 갱신했던 것과 같은 부류의 결함). */
  it("작업 큐의 재시도 작업이 대시보드 캐시까지 무효화한다", async () => {
    const jobsConfig = {
      key: "jobs",
      title: "작업 큐",
      endpoint: "/api/admin/jobs",
      paginated: true,
      columns: [{ key: "id", label: "ID" }],
      detailFields: [],
      actions: [
        { label: "재시도", when: (r) => r.status === "failed",
          path: (r) => "/api/admin/jobs/" + r.id + "/retry" },
      ],
    };
    apiMock.mockResolvedValue({ items: [{ id: "job-1", status: "failed" }], page: 1, page_size: 20, total: 1 });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 대시보드가 이미 값을 들고 있는 상태를 만든다 — 그래야 '무효화됐다'가 뜻을 가진다.
    qc.setQueryData(["dashboard"], { jobs_24h: { failed_open: 3 } });
    expect(qc.getQueryState(["dashboard"]).isInvalidated).toBe(false);

    render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <MemoryRouter><DataScreen config={jobsConfig} /></MemoryRouter>
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      </QueryClientProvider>,
    );
    await screen.findByText("job-1");
    apiMock.mockResolvedValueOnce({ ok: true });

    fireEvent.click(screen.getByText("job-1"));
    fireEvent.click(await screen.findByRole("button", { name: "재시도" }));

    await waitFor(() => {
      expect(qc.getQueryState(["dashboard"]).isInvalidated, "대시보드").toBe(true);
    }, { timeout: 3000 });
  });

  /* 공지 배너(app/Banners.jsx)는 AppShell에 한 번만 마운트되어 내비게이션 중에도
   * 언마운트되지 않는다 — 다른 화면처럼 벗어났다 돌아오는 것만으로는 재조회가 일어나지
   * 않는다. 공지 관리 화면(registry/platform.js의 announcements)의 '사용 안 함'
   * 확인 문구는 "모든 화면에서 즉시 사라집니다"라고 말한다 — CROSS_SCREEN_KEYS에 매핑이
   * 없으면 그 약속과 달리 배너는 자기 폴링(5분)이 돌 때까지 옛 상태를 그대로 보여준다. */
  it("공지 화면의 '사용 안 함' 작업이 배너 캐시까지 무효화한다", async () => {
    const announcementsConfig = {
      key: "announcements",
      title: "공지 배너",
      endpoint: "/api/admin/announcements",
      paginated: true,
      columns: [{ key: "title", label: "제목" }],
      detailFields: [],
      actions: [
        { label: "사용 안 함", when: (r) => r.active,
          method: "PATCH", path: (r) => "/api/admin/announcements/" + r.id, body: { active: false } },
      ],
    };
    apiMock.mockResolvedValue({ items: [{ id: "a-1", title: "정기 점검", active: true }], page: 1, page_size: 20, total: 1 });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 배너가 이미 값을 들고 있는 상태를 만든다 — 그래야 '무효화됐다'가 뜻을 가진다.
    qc.setQueryData(["announcements-active"], { items: [{ id: "a-1", title: "정기 점검" }] });
    expect(qc.getQueryState(["announcements-active"]).isInvalidated).toBe(false);

    render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <MemoryRouter><DataScreen config={announcementsConfig} /></MemoryRouter>
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      </QueryClientProvider>,
    );
    await screen.findByText("정기 점검");
    apiMock.mockResolvedValueOnce({ ok: true });

    fireEvent.click(screen.getByText("정기 점검"));
    fireEvent.click(await screen.findByRole("button", { name: "사용 안 함" }));

    await waitFor(() => {
      expect(qc.getQueryState(["announcements-active"]).isInvalidated, "배너").toBe(true);
    }, { timeout: 3000 });
  });

  /* WF44 배경 조사(L축) — 티켓 담당자 배정 드롭다운(ticket-options.js::useAssigneeOptions,
   * `["tickets","assignees"]`)은 이름과 함께 부서·직책·조직을 그대로 싣는다(사용자 지시
   * 2026-08-04, app/tickets/service.py::list_assignees). 부서 이름을 바꿔도 CROSS_SCREEN_KEYS
   * 에 매핑이 없으면, 다른 탭에 열린 티켓 생성/수정 모달의 담당자 후보가 staleTime(60초) 동안
   * 옛 부서 이름을 계속 보여준다. */
  it("부서 이름 수정이 티켓 담당자 후보 캐시까지 무효화한다", async () => {
    const departmentsConfig = {
      key: "departments",
      title: "부서 관리",
      endpoint: "/api/admin/departments",
      paginated: false,
      columns: [{ key: "name", label: "부서 이름" }],
      detailFields: [],
      edit: { roles: ["admin", "system_admin"], fields: [{ name: "name", label: "부서 이름", type: "text", required: true }] },
    };
    apiMock.mockResolvedValue({ items: [{ id: "d-1", name: "인프라팀" }] });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 티켓 담당자 후보 캐시가 이미 값을 들고 있는 상태를 만든다.
    qc.setQueryData(["tickets", "assignees"], { assignees: [{ user_id: "u1", department: "인프라팀" }] });
    expect(qc.getQueryState(["tickets", "assignees"]).isInvalidated).toBe(false);

    render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <MemoryRouter><DataScreen config={departmentsConfig} /></MemoryRouter>
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      </QueryClientProvider>,
    );
    await screen.findByText("인프라팀");
    apiMock.mockResolvedValueOnce({ item: { id: "d-1", name: "플랫폼팀" } });

    fireEvent.click(screen.getByText("인프라팀"));
    fireEvent.click(await screen.findByRole("button", { name: "수정" }));
    const dialog = await screen.findByRole("dialog");
    // 값을 실제로 바꿔야 한다 — DataScreen의 PATCH 경로는 diffFields로 바뀐 필드만 보내고,
    // 아무것도 안 바뀌었으면 api()조차 부르지 않고 "변경된 내용이 없습니다"로 조용히
    // 끝난다(CONC-01).
    fireEvent.change(within(dialog).getByLabelText(/^부서 이름/), { target: { value: "플랫폼팀" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "저장" }));

    await waitFor(() => {
      expect(qc.getQueryState(["tickets", "assignees"]).isInvalidated, "티켓 담당자 후보").toBe(true);
    }, { timeout: 3000 });
  });
});
