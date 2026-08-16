import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 홈 '오늘' 커맨드 센터 — 화면이 서버가 준 숫자를 그대로 말하는가.
 *
 * 특히 두 가지를 고정한다:
 *   1) **빈 상태를 구분한다.** '고른 칸에만 없다'(검색 결과 없음)와 '내 티켓이 아예 없다'
 *      (데이터 없음)는 서로 다른 그림·다른 문장·다른 복구 행동을 준다. 예전 앱에는 이 구분이
 *      아예 없어서, 필터를 걸어 0건이 된 사용자가 데이터가 사라졌다고 생각했다.
 *   2) **장애 격리.** 티켓 소스가 죽어도 알림·최근 변경은 그대로 보인다(서버 계약과 같은 약속).
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

function ticket(tid, over = {}) {
  return {
    id: "p" + tid, tid, title: "티켓 " + tid, status: "진행", due: "2026-08-03",
    est_wd: 1, priority: null, difficulty: null, project: "",
    assignee_names: [], assignee_user_ids: [], project_names: [], ...over,
  };
}

const TODAY_OK = {
  ok: true,
  today: "2026-08-03",
  tickets: {
    configured: true, ok: true, mapped: true,
    due_today: { count: 2, items: [ticket(1), ticket(2)] },
    overdue: { count: 1, items: [ticket(3, { title: "지연 티켓", due: "2026-07-30" })] },
    in_progress: { count: 4, items: [ticket(1), ticket(2), ticket(3), ticket(4)] },
    due_soon: { count: 0, items: [] },
    blocked: { count: 1, items: [ticket(5, { status: "이슈" })] },
    done_total: 3,
  },
  sprint: {
    window: { start: "2026-08-03", end_exclusive: "2026-08-10" },
    assigned: 5, done: 2, remaining: 3, cancelled: 0, overdue: 1,
    completion_rate: 40, est_wd_total: 6, est_wd_done: 2,
  },
  inbox: { notifications_unread: 7, chat_unread: 4 },
  recent: {
    documents: [{ id: "d1", title: "회의록 초안", document_type: "회의록", owner: "동료", last_edited: "2026-08-02T10:00:00Z" }],
    board: [{ id: "b1", title: "점심 공지", category: "자유", author_name: "동료", is_pinned: false, comment_count: 2, created_at: "2026-08-02T02:00:00Z" }],
  },
  sync: { status: "ok", last_run_at: null, last_success_at: "2026-08-03T00:57:00Z", ticket_count: 9, truncated: false, error: null },
};

const EMPTY_BUCKETS = {
  configured: true, ok: true, mapped: true,
  due_today: { count: 0, items: [] },
  overdue: { count: 0, items: [] },
  in_progress: { count: 0, items: [] },
  due_soon: { count: 0, items: [] },
  blocked: { count: 0, items: [] },
  done_total: 0,
};

function routeApi(overrides = {}) {
  const today = overrides.today || TODAY_OK;
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/home/today")) return Promise.resolve(today);
    if (path.startsWith("/api/assistant/")) return Promise.resolve(overrides.assistant || { kind: "briefing", tickets: today.tickets, sprint: today.sprint });
    return Promise.resolve({});
  });
}

function renderHome() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

/* 통계 카드 하나(라벨로 찾는다). StatCard 는 onClick 이 있으면 <button> 으로 그려진다. */
function statCard(label) {
  return screen.getAllByRole("button").find((el) => el.textContent.includes(label));
}
/* 카드가 보여주는 값(첫 줄의 큰 숫자). 같은 숫자가 화면 다른 곳에 있어도 이 카드 것만 본다. */
function cardValue(label) {
  const card = statCard(label);
  return card ? card.firstChild.textContent.trim() : null;
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("홈 '오늘' — 커맨드 센터", () => {
  it("한 번의 /api/home/today 로 티켓·알림·채팅·스프린트·최근 변경을 모두 그린다", async () => {
    routeApi();
    renderHome();

    expect(await screen.findByText("안 읽은 알림")).toBeInTheDocument();
    // 통계 카드 6장: 오늘 마감 / 지연 / 진행 중 / 7일 내 마감 / 안 읽은 알림 / 안 읽은 채팅
    for (const label of ["오늘 마감", "지연", "진행 중", "7일 내 마감", "안 읽은 알림", "안 읽은 채팅"]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    // 값은 카드 안에서 확인한다 — 같은 숫자가 화면 다른 곳(요약 문장 등)에도 나올 수 있다.
    expect(cardValue("안 읽은 알림")).toBe("7");
    expect(cardValue("안 읽은 채팅")).toBe("4");
    expect(cardValue("지연")).toBe("1");
    // 스프린트 내 몫 — 도넛을 못 보는 사람도 같은 수치를 글자로 읽는다.
    expect(screen.getByText(/내 티켓 5건 중 2건 완료/)).toBeInTheDocument();
    // 최근 문서 — 게시판 카드는 PA-RC-0018 direction 6으로 빠지고 사이드바 "자유게시판"으로
    // 돌아갔다(navConfig.js), 이 화면에는 더 이상 게시글 미리보기가 없다.
    expect(screen.getByText("회의록 초안")).toBeInTheDocument();
    // 홈은 요청을 한 번만 한다(티켓 목록을 따로 또 부르지 않는다).
    expect(apiMock.mock.calls.filter(([p]) => p.startsWith("/api/home/today"))).toHaveLength(1);
  });

  it("카드를 누르면 아래 목록이 그 칸으로 바뀐다(서버를 다시 부르지 않는다)", async () => {
    routeApi();
    renderHome();
    await screen.findByText("안 읽은 알림");
    const before = apiMock.mock.calls.length;

    await userEvent.click(statCard("지연"));
    expect(await screen.findByText("지연 (1건)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "지연 티켓" })).toBeInTheDocument();
    // 버킷은 이미 응답 안에 다 들어 있다 — 칸을 바꾼다고 네트워크가 다시 돌면 안 된다.
    expect(apiMock.mock.calls.length).toBe(before);
  });

  it("고른 칸만 비면 '검색 결과 없음'으로 안내한다(데이터 없음과 구분)", async () => {
    routeApi();
    renderHome();
    await screen.findByText("안 읽은 알림");

    await userEvent.click(statCard("7일 내 마감"));
    expect(await screen.findByText("7일 내 마감에 해당하는 티켓이 없습니다")).toBeInTheDocument();
    expect(screen.getByText("다른 칸을 눌러 보거나 전체 목록에서 확인하세요.")).toBeInTheDocument();
    // '담당한 티켓이 없습니다'(진짜 데이터 없음)와 절대 같은 문장을 쓰지 않는다.
    expect(screen.queryByText("담당한 티켓이 없습니다")).toBeNull();
  });

  it("내 티켓이 하나도 없으면 '데이터 없음'과 복구 행동을 준다", async () => {
    routeApi({ today: { ...TODAY_OK, tickets: EMPTY_BUCKETS } });
    renderHome();

    expect(await screen.findByText("담당한 티켓이 없습니다")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "미할당 티켓 보기" })).toBeInTheDocument();
    expect(screen.queryByText(/해당하는 티켓이 없습니다/)).toBeNull();
  });

  it("SEM-02: 최상위 구역이 h1 바로 아래 h2다(예전엔 h3로 건너뛰어 h2가 아예 없었다)", async () => {
    routeApi();
    renderHome();
    await screen.findByText("안 읽은 알림");

    expect(screen.getByRole("heading", { level: 1, name: "오늘" })).toBeInTheDocument();
    // AssistantPanel("AI 도우미")도 이 화면 안에서만 쓰여 같은 무게의 최상위 구역이다 —
    // h2여야 한다. TeamChatWidget("팀 채팅")·SideRail의 "게시판"은 PA-RC-0018 direction 6으로
    // 카드에서 빠지고 사이드바 "채팅방"/"자유게시판"으로 돌아갔다 — 더 이상 이 화면의 구역이
    // 아니다.
    const level2Names = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    for (const fixed of ["이번 주 내 진척", "최근 문서", "AI 도우미"]) {
      expect(level2Names).toContain(fixed);
    }
    // 티켓 칸 제목은 "진행 중 (4건)"처럼 고른 칸에 따라 바뀐다 — 값이 아니라 모양만 확인한다.
    expect(level2Names.some((t) => /\(\d+건\)$/.test(t))).toBe(true);
    expect(level2Names).toHaveLength(4);
    // AssistantPanel 내부 소제목(내 몫 등)이 h3로 낮아졌는지는 assistant-panel.test.jsx가
    // 그 화면 자신의 데이터 모양으로 직접 확인한다.
  });

  // VIS-35: 티켓 카드(행 수만큼 커짐)와 AssistantPanel을 같은 왼쪽 열에 쌓아 두면, 실데이터가
  // 있을수록 오른쪽 SideRail(고정 크기 카드 둘)과의 높이 차이가 벌어져 오른쪽 아래에 큰 흰
  // 여백이 남았다. AssistantPanel을 격자 밖 전체 폭으로 내려 그 조합 자체를 없앤다.
  it("AssistantPanel은 티켓/속성 2단 격자 밖, 전체 폭에 있다(격자 안에서 왼쪽 열과 쌓이지 않는다)", async () => {
    routeApi();
    renderHome();
    await screen.findByText("안 읽은 알림");

    const grid = screen.getByTestId("home-body-grid");
    const heading = screen.getByRole("heading", { level: 2, name: "AI 도우미" });
    expect(grid.contains(heading)).toBe(false);
    // 격자 다음에 이어지는 형제 구역이어야 한다(화면에서 그 아래로 온다).
    expect(grid.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("채팅이 꺼진 설치(chat_unread=null)에서는 그 자리를 '막힘' 카드가 채운다", async () => {
    routeApi({ today: { ...TODAY_OK, inbox: { notifications_unread: 0, chat_unread: null } } });
    renderHome();

    expect(await screen.findByText("막힘(이슈)")).toBeInTheDocument();
    expect(screen.queryByText("안 읽은 채팅")).toBeNull();
  });

  it("티켓 소스가 죽어도 알림·최근 변경은 그대로 보인다", async () => {
    routeApi({
      today: {
        ...TODAY_OK,
        tickets: { configured: true, ok: false, mapped: true, error: "Notion 조회에 실패했습니다." },
        sprint: null,
      },
    });
    renderHome();

    expect(await screen.findByText("Notion 조회에 실패했습니다.")).toBeInTheDocument();
    expect(cardValue("안 읽은 알림")).toBe("7");                      // 알림은 살아 있다
    expect(screen.getByText("회의록 초안")).toBeInTheDocument();      // 최근 문서도 살아 있다
    expect(screen.getByText(/이번 주 진척을 계산할 수 없습니다/)).toBeInTheDocument();
  });

  // VIS-34: 스프린트 카드(SprintProgress)와 AI 도우미의 '오늘 브리핑'(AssistantPanel의
  // Briefing)이 같은 실패를 각자 전체 문장으로 반복해 같은 화면에 같은 경고가 두 번
  // 떴다. AssistantPanel은 자기 쿼리가 따로 있어 findByText로 그 완료까지 기다려야
  // 실제로 렌더된 내용을 본다(Home 쿼리 완료만 기다리면 이 컴포넌트를 놓친다).
  it("티켓 소스가 죽으면 AI 도우미 브리핑은 스프린트 카드를 반복하지 않고 참조만 한다", async () => {
    routeApi({
      today: {
        ...TODAY_OK,
        tickets: { configured: true, ok: false, mapped: true, error: "Notion 조회에 실패했습니다." },
        sprint: null,
      },
    });
    renderHome();

    // SprintProgress(스프린트 카드)의 전체 문장은 그대로 남아 있다.
    expect(await screen.findByText(/이번 주 진척을 계산할 수 없습니다\. 관리자에게 문의하세요\./)).toBeInTheDocument();
    // Briefing은 그 문장을 반복하지 않고 짧게 참조한다 — AssistantPanel 자신의 쿼리가
    // 끝나야 나타나므로 findByText로 기다린다.
    expect(await screen.findByText(/위 스프린트 카드와 같은 이유로/)).toBeInTheDocument();
    // "티켓 소스를 읽지 못해"로 시작하는 전체 문장이 두 번 나오지는 않는다(딱 한 곳,
    // 스프린트 카드에만).
    expect(screen.getAllByText(/티켓 소스를 읽지 못해/)).toHaveLength(1);
  });

  it("미러 신선도를 화면에 드러낸다(잘린 동기화는 눈에 띄게)", async () => {
    routeApi({
      today: { ...TODAY_OK, sync: { ...TODAY_OK.sync, status: "error", truncated: true } },
    });
    renderHome();
    expect(await screen.findByText(/일부만 동기화됨/)).toBeInTheDocument();
  });

  it("불러오는 동안에는 스켈레톤을 보여준다", async () => {
    let resolve;
    apiMock.mockImplementation((path) =>
      path.startsWith("/api/home/today")
        ? new Promise((r) => { resolve = r; })
        : Promise.resolve({})
    );
    renderHome();
    expect(screen.getAllByText("불러오는 중…").length).toBeGreaterThan(0);
    resolve(TODAY_OK);
    await waitFor(() => expect(screen.getByText("안 읽은 알림")).toBeInTheDocument());
  });
});
