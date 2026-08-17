import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* AI 도우미 패널 — 계획서 Phase 5 의 "숫자 먼저, 문장은 나중"을 화면에서 고정한다.
 *
 *   * 기본 상태에서는 문장을 요청하지 않는다(?narrate 를 붙이지 않는다).
 *   * 러너가 죽거나 기능이 꺼져 있어도 **숫자는 그대로 남고** 왜 문장이 없는지만 덧붙는다.
 *   * 트리아지는 제안만 한다 — 배정 버튼이 없고, '제안'이라고 화면이 직접 말한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { AssistantPanel } from "./AssistantPanel.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const BRIEFING = {
  kind: "briefing",
  tickets: {
    configured: true, ok: true, mapped: true,
    due_today: { count: 2, items: [] },
    overdue: { count: 1, items: [] },
    in_progress: { count: 5, items: [] },
    blocked: { count: 0, items: [] },
  },
  sprint: { assigned: 5, done: 2, completion_rate: 40 },
};

const STANDUP = {
  kind: "standup",
  today: "2026-08-03",
  author: { user_id: "u-1", display_name: "나" },
  recently_done: { count: 1, items: [{ id: "p1", tid: 1, title: "끝낸 일", status: "완료", due: "2026-08-04" }] },
  today_plan: { count: 2, items: [
    { id: "p2", tid: 2, title: "오늘 처리할 티켓", status: "진행", due: "2026-08-03" },
    { id: "p3", tid: 3, title: "지연된 일", status: "진행", due: "2026-07-30" },
  ] },
  blocked: { count: 0, items: [] },
};

const TRIAGE = {
  kind: "triage", today: "2026-08-03", auto_assign: false, configured: true, ok: true,
  total: 2,
  items: [
    { id: "p9", tid: 9, title: "지연 미할당", status: "진행", due: "2026-07-20", priority: "낮음", overdue: true, priority_rank: 3 },
    { id: "p8", tid: 8, title: "긴급 미할당", status: "진행", due: "2026-08-20", priority: "긴급", overdue: false, priority_rank: 0 },
  ],
  candidates: [
    { user_id: "u-2", display_name: "동료", active_tickets: 2 },
    { user_id: "u-1", display_name: "나", active_tickets: 3 },
  ],
};

function routeApi(extra = {}) {
  apiMock.mockImplementation((path) => {
    if (path.startsWith("/api/assistant/standup")) return Promise.resolve({ ...STANDUP, ...(extra.standup || {}) });
    if (path.startsWith("/api/assistant/weekly-digest")) return Promise.resolve(extra.weekly || {});
    if (path.startsWith("/api/assistant/triage")) return Promise.resolve(extra.triage || TRIAGE);
    if (path.startsWith("/api/assistant/briefing")) {
      return Promise.resolve(path.includes("narrate=true")
        ? { ...BRIEFING, narrative: extra.narrative || { enabled: false, text: null, error: "요약 문장 생성이 꺼져 있습니다." } }
        : { ...BRIEFING, narrative: null });
    }
    return Promise.resolve({});
  });
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <AssistantPanel />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("AI 도우미 패널", () => {
  it("처음에는 숫자만 가져온다 — 문장(narrate)을 요청하지 않는다", async () => {
    routeApi();
    renderPanel();

    expect(await screen.findByText(/오늘 마감 2건, 지연 1건/)).toBeInTheDocument();
    expect(apiMock.mock.calls.every(([p]) => !p.includes("narrate"))).toBe(true);
  });

  // PA-RC-0027: mapped:false면 백엔드가 버킷 키를 아예 안 싣는다(app/home/service.py)
  // — n()이 그 부재를 그냥 0으로 접으면 "오늘 마감 0건..."이 "모른다"를 "없다"로 오독시킨다.
  it("매핑이 없으면 '오늘 마감 0건' 대신 판단 불가 문장을 낸다", async () => {
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/assistant/briefing")) {
        return Promise.resolve({
          kind: "briefing",
          tickets: { configured: true, ok: true, mapped: false },
          sprint: null,
          narrative: null,
        });
      }
      if (path.startsWith("/api/assistant/standup")) return Promise.resolve(STANDUP);
      if (path.startsWith("/api/assistant/triage")) return Promise.resolve(TRIAGE);
      return Promise.resolve({});
    });
    renderPanel();

    expect(await screen.findByText("담당 티켓을 판단할 수 없어 오늘 요약을 계산할 수 없습니다.")).toBeInTheDocument();
    expect(screen.queryByText(/오늘 마감 0건/)).not.toBeInTheDocument();
    // 두 번째 절("위 스프린트 카드와...")도 "0"을 지어낸 상단 줄을 다시 가리키지 않는다.
    expect(screen.queryByText(/위 숫자는 이 화면 상단 카드와 같은 값입니다/)).not.toBeInTheDocument();
  });

  it("문장 생성이 꺼져 있으면 숫자는 그대로 두고 이유만 덧붙인다", async () => {
    routeApi();
    renderPanel();
    await screen.findByText(/오늘 마감 2건, 지연 1건/);

    await userEvent.click(screen.getByRole("button", { name: "문장 요약 만들기" }));

    expect(await screen.findByText("요약 문장 생성이 꺼져 있습니다.")).toBeInTheDocument();
    // 숫자는 한 글자도 사라지지 않는다 — 이것이 계획서 Phase 5 의 요구사항이다.
    expect(screen.getByText(/오늘 마감 2건, 지연 1건/)).toBeInTheDocument();
    expect(apiMock.mock.calls.some(([p]) => p.includes("narrate=true"))).toBe(true);
  });

  it("러너가 문장을 주면 요약으로 보여준다", async () => {
    routeApi({ narrative: { enabled: true, text: "오늘 마감 2건, 지연 1건입니다.", error: null } });
    renderPanel();
    await screen.findByText(/오늘 마감 2건, 지연 1건/);

    await userEvent.click(screen.getByRole("button", { name: "문장 요약 만들기" }));
    expect(await screen.findByText("오늘 마감 2건, 지연 1건입니다.")).toBeInTheDocument();
  });

  it("스탠드업 탭은 최근 끝낸 일 / 오늘 할 일 / 막힌 것 세 단으로 나눈다", async () => {
    routeApi();
    renderPanel();
    await screen.findByText(/오늘 마감 2건/);

    await userEvent.click(screen.getByRole("tab", { name: "스탠드업 초안" }));

    expect(await screen.findByText("끝낸 일")).toBeInTheDocument();
    expect(screen.getByText("오늘 처리할 티켓")).toBeInTheDocument();
    expect(screen.getByText("지연된 일")).toBeInTheDocument();
    // 막힌 것이 0건이면 빈 칸이 아니라 '없다'고 말한다.
    expect(screen.getByText("상태가 ‘이슈’인 티켓이 없습니다.")).toBeInTheDocument();
  });

  it("트리아지는 '제안'이라고 말하고 배정 버튼을 두지 않는다", async () => {
    routeApi();
    renderPanel();
    await screen.findByText(/오늘 마감 2건/);

    await userEvent.click(screen.getByRole("tab", { name: "미할당 트리아지" }));

    expect(await screen.findByText(/이 화면은 아무것도 배정하지 않습니다/)).toBeInTheDocument();
    // 순서는 서버가 준 그대로(지연이 먼저).
    const links = screen.getAllByRole("link").map((a) => a.textContent);
    expect(links.indexOf("지연 미할당")).toBeLessThan(links.indexOf("긴급 미할당"));
    // 부하가 적은 후보가 근거(건수)와 함께 나온다.
    expect(screen.getByText("동료")).toBeInTheDocument();
    // 배정을 실행하는 컨트롤은 없다.
    expect(screen.queryByRole("button", { name: /배정/ })).toBeNull();
    // 트리아지 탭에는 문장 버튼 자체가 없다(제안이 결정처럼 읽히지 않게).
    expect(screen.queryByRole("button", { name: "문장 요약 만들기" })).toBeNull();
  });

  it("미할당이 하나도 없으면 '데이터 없음'을 분명히 말한다", async () => {
    routeApi({ triage: { ...TRIAGE, total: 0, items: [], candidates: [] } });
    renderPanel();
    await screen.findByText(/오늘 마감 2건/);

    await userEvent.click(screen.getByRole("tab", { name: "미할당 트리아지" }));
    expect(await screen.findByText("담당자 없는 티켓이 없습니다")).toBeInTheDocument();
  });

  it("SEM-02: 패널 제목은 h2, 안의 소제목(TicketLines)은 h3다", async () => {
    // 이 컴포넌트는 항상 Home.jsx(/me) 안에 박혀 있어 그 화면의 다른 최상위 구역과
    // 같은 무게(h2)를 받는다 — 그 아래 TicketLines 소제목은 h4에서 h3로 함께 낮췄다
    // (h2 → h4로 건너뛰지 않게).
    routeApi();
    renderPanel();
    await screen.findByText(/오늘 마감 2건/);
    expect(screen.getByRole("heading", { level: 2, name: "AI 도우미" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "스탠드업 초안" }));
    await screen.findByText("오늘 처리할 티켓");
    expect(screen.getByRole("heading", { level: 3, name: /최근 끝낸 일/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: /오늘 할 일/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: /막힌 것/ })).toBeInTheDocument();
  });
});
