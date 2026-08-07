import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 티켓을 고치면 **그 티켓을 보여 주는 모든 화면**이 같이 바뀐다 (E6).
 *
 * 예전에는 `TicketEditModal` 이 저장 뒤 `["tickets"]` 하나만 무효화했다. 그런데 홈('오늘')은
 * `["home","today"]` 로, 스프린트 회의는 `["sprint", …]` 로 같은 티켓을 그린다 — 두 화면 모두
 * 편집 버튼을 달고 있으면서 저장 뒤에는 **옛 값을 그대로** 보여 줬다. 사용자는 "저장했습니다"
 * 토스트를 보고도 값이 안 바뀌니 저장이 안 된 줄 알고 같은 편집을 되풀이했다.
 *
 * 그래서 여기서는 값이 **실제로 달라지는 표본**을 쓴다: 서버가 두 번째 호출부터 새 제목을
 * 준다. 무효화가 빠지면 화면에는 옛 제목이 남는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u-1" } }),
}));

import { Home } from "./Home.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const OLD_TITLE = "옛 제목";
const NEW_TITLE = "새 제목";

function ticket(title) {
  return {
    id: "p1", tid: 1, title, status: "진행", due: "2026-08-03",
    est_wd: 1, act_wd: null, priority: null, difficulty: null, category: "",
    start: "", project_ids: [], project_names: [],
    assignee_names: [], assignee_user_ids: [],
  };
}

function today(title) {
  return {
    ok: true,
    today: "2026-08-03",
    tickets: {
      configured: true, ok: true, mapped: true,
      due_today: { count: 1, items: [ticket(title)] },
      overdue: { count: 0, items: [] },
      in_progress: { count: 0, items: [] },
      due_soon: { count: 0, items: [] },
      blocked: { count: 0, items: [] },
      done_total: 0,
    },
    sprint: null,
    inbox: { notifications_unread: 0, chat_unread: null },
    recent: { documents: [], board: [] },
    sync: { status: "ok", last_run_at: null, last_success_at: "2026-08-03T00:57:00Z", ticket_count: 1, truncated: false, error: null },
  };
}

/* 서버는 저장 전에는 옛 제목을, 저장 뒤에는 새 제목을 준다. 화면이 다시 물어봤는지가
 * 눈에 보이는 값으로 드러난다(호출 횟수만 세면 '물어봤지만 안 그렸다'를 놓친다). */
function routeApi() {
  let saved = false;
  apiMock.mockImplementation((path, options) => {
    if (path.startsWith("/api/home/today")) return Promise.resolve(today(saved ? NEW_TITLE : OLD_TITLE));
    if (path === "/api/tickets/p1" && options && options.method === "PATCH") {
      saved = true;
      return Promise.resolve({ ok: true, ticket: ticket(NEW_TITLE) });
    }
    if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    if (path.startsWith("/api/tickets/meta")) return Promise.resolve({ statuses: ["진행", "완료"], priorities: [], difficulties: [] });
    if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
    if (path.startsWith("/api/board/mine")) return Promise.resolve({ summary: {}, items: [] });
    if (path.startsWith("/api/assistant/")) return Promise.reject(new Error("off"));
    if (path.startsWith("/api/team-chat/")) return Promise.reject(new Error("off"));
    return Promise.resolve({});
  });
}

function renderHome(qc) {
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Home />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

async function editTitleTo(user, next) {
  await user.click(await screen.findByRole("button", { name: "편집: " + OLD_TITLE }));
  // 표 머리글에도 '제목'이 있다 — 편집 모달의 입력은 id 로 집는다(MyTickets.jsx te-title).
  await waitFor(() => expect(document.getElementById("te-title")).toBeTruthy());
  const title = document.getElementById("te-title");
  await user.clear(title);
  await user.type(title, next);
  await user.click(screen.getByRole("button", { name: "저장" }));
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("티켓 편집 뒤 화면 갱신", () => {
  it("홈에서 제목을 고치면 홈 목록의 값이 바로 바뀐다", async () => {
    routeApi();
    const user = userEvent.setup();
    renderHome(new QueryClient({ defaultOptions: { queries: { retry: false } } }));
    expect(await screen.findByText(OLD_TITLE)).toBeInTheDocument();

    await editTitleTo(user, NEW_TITLE);

    expect(await screen.findByText(NEW_TITLE)).toBeInTheDocument();
    expect(screen.queryByText(OLD_TITLE)).toBeNull();
  });

  it("지금 안 보고 있는 스프린트 회의 화면의 캐시도 함께 낡은 것으로 표시된다", async () => {
    routeApi();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // 스프린트 회의는 다른 키를 쓴다 — 사용자가 홈에서 고치고 스프린트 탭으로 넘어가면
    // 그 화면은 캐시에 남은 옛 값을 그대로 그린다(무효화가 이 키까지 닿지 않으면).
    const SPRINT_KEY = ["sprint", "2026-08-03", "2026-08-10"];
    qc.setQueryData(SPRINT_KEY, { ok: true, people: [] });
    const user = userEvent.setup();
    renderHome(qc);
    await screen.findByText(OLD_TITLE);

    await editTitleTo(user, NEW_TITLE);

    await waitFor(() => expect(qc.getQueryState(SPRINT_KEY).isInvalidated).toBe(true));
  });

  it("지금 안 보고 있는 개발자 월간 리포트 화면의 캐시도 함께 낡은 것으로 표시된다", async () => {
    // 월간 리포트(DevReport.jsx)는 담당자별 완료/진행/검증/계획 건수, 지연, 완료 업무량을
    // 마감일이 그 달인 티켓에서 센다 — 편집 모달이 바꾸는 상태·담당자·마감·WD가 전부 그 숫자에
    // 들어간다. 그런데 ticket-views.js의 TICKET_VIEW_KEYS에는 "dev-report"가 없어서, 사용자가
    // 리포트를 한 번 열어 본 뒤(캐시가 생긴 뒤) 홈에서 티켓을 고치고 리포트 탭으로 돌아가면
    // 그 화면은 옛 집계를 그대로 보여준다 — '새로고침' 버튼을 눌러야만 값이 맞아진다.
    routeApi();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const DEV_REPORT_KEY = ["dev-report", "2026-08"];
    qc.setQueryData(DEV_REPORT_KEY, { ok: true, configured: true, developers: [] });
    const user = userEvent.setup();
    renderHome(qc);
    await screen.findByText(OLD_TITLE);

    await editTitleTo(user, NEW_TITLE);

    await waitFor(() => expect(qc.getQueryState(DEV_REPORT_KEY).isInvalidated).toBe(true));
  });
});
