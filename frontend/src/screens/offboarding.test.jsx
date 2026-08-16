import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 오프보딩 화면 (PLAN Phase 6).
 *
 * 여기서 못박는 것은 "화면이 그려진다"가 아니라 **되돌릴 수 있고 거짓말하지 않는다**이다:
 *   1) 실행 전에 보유 티켓을 **먼저 보여 준다**(조용한 일괄 실행 금지).
 *   2) 실행 요청에는 **사용자가 화면에서 확인한 목록 그대로** 실린다(서버가 알아서 고르지 않는다).
 *   3) 12건 중 3건이 실패하면 **성공 토스트로 덮지 않고** 그 숫자를 말한다.
 *   4) 되돌리기 버튼이 이력 상세 안에 실제로 있다 — 되돌릴 방법이 화면에 없으면 아무도 실행을 못 누른다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { Offboarding } from "./Offboarding.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const LEAVER = {
  id: "u-leaver", email: "leaver@goodmit.co.kr", display_name: "퇴사자", role: "user",
  active: true, archived_at: null, department: "개발팀", department_id: "d-1",
  title: "팀원", notion_mapping_status: "verified", locked: false,
  must_change_password: false, last_login_at: null, created_at: "2026-07-01T00:00:00",
};

const PREVIEW = {
  user: { ...LEAVER },
  onboarding: [
    { key: "department", label: "부서 배정", ok: true, value: "개발팀" },
    { key: "notion", label: "Notion 사용자 연결", ok: true, value: "verified" },
  ],
  notion_mapped: true,
  tickets: [
    { id: "page-1", tid: 101, title: "혼자 담당 A", status: "진행", due: "2026-09-01", assignee_names: ["퇴사자"] },
    { id: "page-2", tid: 102, title: "공동 담당", status: "진행", due: "2026-09-02", assignee_names: ["퇴사자", "동료"] },
  ],
  ticket_count: 2,
  tickets_error: null,
  successor_candidates: [
    { user_id: "u-succ", display_name: "후임", email: "succ@goodmit.co.kr", department: "개발팀" },
  ],
  max_tickets_per_run: 100,
  open_run: null,
};

const RUN_ROW = {
  id: "run-1", user_id: "u-leaver", user_name: "퇴사자", actor_user_id: "actor-1",
  actor_name: "관리자", successor_user_id: "u-succ", successor_name: "후임",
  status: "partial", deactivated: true, archived: false, note: null,
  ticket_total: 2, ticket_moved: 1, ticket_failed: 1, undone_at: null,
  undone_by_user_id: null, undo_error: null, created_at: "2026-08-03T01:00:00",
};

let runs = [];
let lastRunBody = null;

beforeEach(() => {
  runs = [];
  lastRunBody = null;
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (path.startsWith("/api/admin/users?")) {
      return Promise.resolve({ items: [LEAVER], total: 1, page_size: 20 });
    }
    if (path.startsWith("/api/admin/offboarding/preview/")) return Promise.resolve(PREVIEW);
    if (path.startsWith("/api/admin/offboarding/run/") && method === "POST") {
      lastRunBody = opts.body;
      runs = [RUN_ROW];
      return Promise.resolve({
        run: RUN_ROW,
        moves: [
          { id: "m1", ticket_page_id: "page-1", tid: 101, title: "혼자 담당 A", status: "moved", error: null },
          { id: "m2", ticket_page_id: "page-2", tid: 102, title: "공동 담당", status: "failed", error: "Notion 오류" },
        ],
      });
    }
    if (path.startsWith("/api/admin/offboarding?")) {
      return Promise.resolve({ items: runs, total: runs.length, page: 1, page_size: 20 });
    }
    if (path === "/api/admin/offboarding/run-1") {
      return Promise.resolve({ run: { ...RUN_ROW, moves: [] } });
    }
    return Promise.resolve({});
  });
});

function renderScreen(qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Offboarding />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

async function pickLeaverAndRun(user) {
  await user.click(await screen.findByRole("button", { name: /상세 보기/ }));
  // 미리보기 — 실행 전에 보유 티켓이 화면에 있어야 한다.
  expect(await screen.findByText("혼자 담당 A")).toBeInTheDocument();
  expect(screen.getByText(/보유 티켓 2건/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "오프보딩 실행" }));
  // 확인 대화상자에서 무엇이 바뀌는지 먼저 말한다.
  const confirmDialog = await screen.findByRole("dialog");
  expect(within(confirmDialog).getByText(/티켓 2건을/)).toBeInTheDocument();
  await user.click(within(confirmDialog).getByRole("button", { name: "실행" }));
}

describe("오프보딩 화면", () => {
  /* WF1 R4 — 제목·내비가 "온보딩, 오프보딩"이라 신규 입사자 온보딩을 이 화면에서 할 수 있는
   * 것처럼 약속했지만, 실제로는 퇴사자 재배정 마법사뿐이다(신규 계정 생성은 /users). */
  it("제목이 하지 않는 일(온보딩)을 더 이상 약속하지 않는다", async () => {
    renderScreen();
    expect(await screen.findByRole("heading", { level: 1, name: "오프보딩" })).toBeInTheDocument();
    expect(screen.queryByText(/온보딩/)).not.toBeInTheDocument();
  });

  it("실행 요청에는 화면에서 확인한 티켓 목록이 그대로 실린다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await pickLeaverAndRun(user);

    await waitFor(() => expect(lastRunBody).not.toBeNull());
    // 서버가 알아서 전부 옮기지 않는다 — 화면이 보낸 목록만 대상이다.
    expect(lastRunBody.ticket_page_ids).toEqual(["page-1", "page-2"]);
    expect(lastRunBody.deactivate).toBe(true);
  });

  it("실행하면 다른 화면의 티켓 캐시도 함께 낡은 것으로 표시된다(담당자 재배정 반영)", async () => {
    // 오프보딩 실행은 티켓의 담당자를 바꾼다(퇴사자 → 후임, 또는 미할당). 그런데 이 화면의
    // onDone은 offboarding-runs/preview/users만 무효화하고 ticket-views.js의 공용
    // invalidateTicketViews를 부르지 않는다 — 그래서 실행 전에 팀 티켓·내 티켓·스프린트·홈이
    // 이미 그 티켓을 캐시해 두고 있었다면, 실행 뒤에도 그 화면들은 옛 담당자를 그대로
    // 보여준다(새로고침해야만 맞아진다).
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const TEAM_KEY = ["tickets", "/api/tickets/team", ""];
    qc.setQueryData(TEAM_KEY, { items: [{ id: "page-1", assignee_names: ["퇴사자"] }], total: 1 });
    const user = userEvent.setup();
    renderScreen(qc);
    await pickLeaverAndRun(user);

    await waitFor(() => expect(lastRunBody).not.toBeNull());
    await waitFor(() => expect(qc.getQueryState(TEAM_KEY).isInvalidated).toBe(true));
  });

  it("부분 실패를 성공 토스트로 덮지 않는다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await pickLeaverAndRun(user);

    // 12건 중 3건 실패를 '완료'라고 말하면 그 3건은 영영 아무도 안 본다.
    expect(await screen.findByText(/1건은 실패했습니다/)).toBeInTheDocument();
    expect(await screen.findByText("Notion 오류")).toBeInTheDocument();
  });

  it("체크를 풀면 그 티켓은 요청에서 빠진다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole("button", { name: /상세 보기/ }));
    await screen.findByText("혼자 담당 A");

    /* 예전에는 "이 항목 선택" 이 모든 행에 똑같이 붙어서, 검사도 **몇 번째 상자인지**로만
       고를 수 있었다(접근성 감사 1). 그건 스크린리더 사용자가 처한 상황 그대로다.
       지금은 행마다 제목이 이름에 들어가므로, 끄려는 그 티켓을 이름으로 고른다. */
    await user.click(screen.getByRole("checkbox", { name: "혼자 담당 A 선택" }));
    await waitFor(() => expect(screen.getByText(/선택 1건/)).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "오프보딩 실행" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "실행" }));
    await waitFor(() => expect(lastRunBody).not.toBeNull());
    expect(lastRunBody.ticket_page_ids).toEqual(["page-2"]);
  });

  it("미리보기가 배경에서 다시 조회돼도(예: 재연결) 이미 체크를 푼 티켓 선택은 그대로 유지된다", async () => {
    // OffboardPlan의 '전부 선택' 초기화 이펙트가 previewQ.data 객체 참조 하나에만 매여 있으면,
    // 티켓 집합 자체는 그대로인데 다른 값(예: Notion에서 마감일이 바뀜)만 달라진 새 응답이 와도
    // 매번 재실행돼 사람이 방금 뺀 체크를 조용히 되살린다 — 실행하면 그 티켓까지 함께 옮겨진다.
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    let previewCalls = 0;
    apiMock.mockImplementation((path, opts) => {
      const method = (opts && opts.method) || "GET";
      if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items: [LEAVER], total: 1, page_size: 20 });
      if (path.startsWith("/api/admin/offboarding/preview/")) {
        previewCalls += 1;
        const due2 = previewCalls > 1 ? "2026-09-03" : "2026-09-02";
        return Promise.resolve({
          ...PREVIEW,
          tickets: PREVIEW.tickets.map((t) => (t.id === "page-2" ? { ...t, due: due2 } : { ...t })),
        });
      }
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderScreen(qc);
    await user.click(await screen.findByRole("button", { name: /상세 보기/ }));
    await screen.findByText("혼자 담당 A");

    await user.click(screen.getByRole("checkbox", { name: "혼자 담당 A 선택" }));
    await waitFor(() => expect(screen.getByText(/선택 1건/)).toBeInTheDocument());

    await qc.refetchQueries({ queryKey: ["offboarding-preview", "u-leaver"] });
    await waitFor(() => expect(screen.getByText("2026-09-03")).toBeInTheDocument());

    // 티켓 집합은 그대로인데 미리보기 객체만 새로 왔다고 해서 방금 사람이 뺀 티켓이
    // 조용히 다시 선택되면 안 된다.
    expect(screen.getByText(/선택 1건/)).toBeInTheDocument();
  });

  it("이력 상세에 되돌리기 버튼이 있다", async () => {
    runs = [RUN_ROW];
    const user = userEvent.setup();
    renderScreen();
    // 이력 표의 첫 열(실행 시각)은 render(날짜 포맷)가 있지만 rowName으로 "대상 · 시각"을
    // 명시했다(SEM-01) — 대상 고르기 표('상세 보기: 퇴사자')와 정규식으로 구별해 고른다.
    const openRun = await screen.findByRole("button", { name: /상세 보기: 퇴사자/ });
    await user.click(openRun);
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByRole("button", { name: "되돌리기" })).toBeInTheDocument();
  });

  it("이력 상세에 감사 로그로 가는 링크가 offboarding_run/그 실행 id로 걸려 있다(MEGA CYCLE G) — 되돌린 뒤에도 남는다", async () => {
    const UNDONE_RUN = { ...RUN_ROW, id: "run-1", undone_at: "2026-08-04T00:00:00" };
    runs = [UNDONE_RUN];
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items: [LEAVER], total: 1, page_size: 20 });
      if (path.startsWith("/api/admin/offboarding?")) {
        return Promise.resolve({ items: runs, total: runs.length, page: 1, page_size: 20 });
      }
      if (path === "/api/admin/offboarding/run-1") return Promise.resolve({ run: { ...UNDONE_RUN, moves: [] } });
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderScreen();
    const openRun = await screen.findByRole("button", { name: /상세 보기: 퇴사자/ });
    await user.click(openRun);
    const drawer = await screen.findByRole("dialog");
    const link = within(drawer).getByRole("link", { name: "감사 로그에서 보기" });
    expect(link).toHaveAttribute("href", "#/audit?object_type=offboarding_run&object_id=run-1");
    // 이미 되돌린 실행에는 '되돌리기' 버튼은 없어야 하지만 감사 로그 링크는 계속 유효하다.
    expect(within(drawer).queryByRole("button", { name: "되돌리기" })).not.toBeInTheDocument();
  });

  it("대상·실행자 이름을 못 받으면 UUID 대신 '알 수 없음'을 보여준다", async () => {
    // 서버가 이름을 못 주는 경우(탈퇴·조인 실패 등) — 목록/상세 모두 raw UUID가 새어 나가면
    // 안 된다(E-4). user_name/actor_name이 비어 있고 id만 있는 실행 이력.
    const NO_NAME_RUN = {
      ...RUN_ROW, id: "run-2", user_name: null, actor_name: null,
      user_id: "11111111-1111-1111-1111-111111111111",
      actor_user_id: "22222222-2222-2222-2222-222222222222",
    };
    runs = [NO_NAME_RUN];
    apiMock.mockImplementation((path, opts) => {
      const method = (opts && opts.method) || "GET";
      if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items: [LEAVER], total: 1, page_size: 20 });
      if (path.startsWith("/api/admin/offboarding?")) {
        return Promise.resolve({ items: runs, total: runs.length, page: 1, page_size: 20 });
      }
      if (path === "/api/admin/offboarding/run-2") return Promise.resolve({ run: { ...NO_NAME_RUN, moves: [] } });
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderScreen();

    // user_name이 null이라 rowName(SEM-01)도 같은 "알 수 없음" 폴백으로 떨어진다 — raw UUID는
    // 여기서도(버튼 접근 이름에서도) 새면 안 된다.
    const openRun = await screen.findByRole("button", { name: /상세 보기: 알 수 없음/ });
    await user.click(openRun);
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).queryByText(/1{8}-1{4}-1{4}-1{4}-1{12}/)).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/2{8}-2{4}-2{4}-2{4}-2{12}/)).not.toBeInTheDocument();
    expect(within(drawer).getAllByText("알 수 없음").length).toBeGreaterThan(0);
  });

  it("UB-40: 대상 고르기 목록이 page_size(20명)를 넘으면 잘렸음을 알린다", async () => {
    // 이 화면은 "그 사람을 찾아 실행"이 목적인데, 대상 목록이 page_size=20으로 고정돼
    // 조용히 잘렸었다 — 총건수도 잘림 경고도 없어 찾는 사람이 21번째 이후에 있으면
    // 검색창을 쓰라는 단서조차 없었다. Search.jsx의 truncation 안내와 같은 관용.
    const page1 = Array.from({ length: 20 }, (_, i) => ({ ...LEAVER, id: `u-${i}`, email: `u${i}@goodmit.co.kr`, display_name: `사용자${i}` }));
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items: page1, total: 25, page_size: 20 });
      return Promise.resolve({});
    });
    renderScreen();

    await screen.findByText("사용자0");
    expect(screen.getByText(/25명 중 20명을 보여 줍니다/)).toBeInTheDocument();
  });

  it("대상 고르기 목록이 잘리지 않았으면 안내를 보여주지 않는다", async () => {
    renderScreen();  // 기본 mock: items:[LEAVER], total:1 — 잘리지 않음.
    await screen.findByText(LEAVER.display_name);
    expect(screen.queryByText(/명을 보여 줍니다/)).not.toBeInTheDocument();
  });

  // PA-RC-0022 acceptance_criteria 9: Notion 미연결 행이 왜 막히는지 목록 수준에서 알 수
  // 있어야 한다 — 미리 보기까지 가지 않아도.
  it("Notion 미연결 후보는 목록에서부터 왜 막히는지 보인다(미리 보기 API의 help 문구를 그대로 재사용)", async () => {
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/admin/users?")) {
        return Promise.resolve({
          items: [{ ...LEAVER, notion_mapping_status: "unmapped" }], total: 1, page_size: 20,
        });
      }
      return Promise.resolve({});
    });
    renderScreen();
    await screen.findByText(LEAVER.display_name);
    // app/offboarding/service.py::_onboarding_checklist의 notion help와 글자 그대로 같아야 한다.
    expect(screen.getByText(
      "연결이 없으면 이 사람이 담당한 티켓을 조회할 수 없어 재배정도 할 수 없습니다.",
    )).toBeInTheDocument();
  });

  it("Notion 연결이 확인된 후보는 이 안내가 없다", async () => {
    renderScreen();  // 기본 mock: notion_mapping_status: "verified".
    await screen.findByText(LEAVER.display_name);
    expect(screen.queryByText(/담당한 티켓을 조회할 수 없어/)).not.toBeInTheDocument();
  });

  it("실행 이력이 20건을 넘으면 총 건수를 말하고 다음 페이지로 넘어갈 수 있다", async () => {
    // 25건 중 첫 페이지(20건)만 오면, 나머지 5건은 화면에 '없다'가 아니라 '더 있다'로
    // 보여야 한다 — 감사 이력이 조용히 잘리면 5건은 아무도 다시 못 찾는다.
    const page1 = Array.from({ length: 20 }, (_, i) => ({
      ...RUN_ROW, id: `run-p1-${i}`, user_name: `퇴사자${i}`,
    }));
    const page2 = Array.from({ length: 5 }, (_, i) => ({
      ...RUN_ROW, id: `run-p2-${i}`, user_name: `퇴사자2-${i}`,
    }));
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/admin/offboarding?")) {
        const url = new URL(path, "http://localhost");
        const page = Number(url.searchParams.get("page") || "1");
        const items = page === 2 ? page2 : page1;
        return Promise.resolve({ items, total: 25, page, page_size: 20 });
      }
      if (path.startsWith("/api/admin/users?")) return Promise.resolve({ items: [LEAVER], total: 1, page_size: 20 });
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderScreen();

    await screen.findByText("퇴사자0");
    expect(screen.getByText(/총 25건/)).toBeInTheDocument();
    expect(screen.queryByText("퇴사자2-0")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "다음" }));
    await screen.findByText("퇴사자2-0");
    expect(screen.queryByText("퇴사자0")).not.toBeInTheDocument();
  });
});
