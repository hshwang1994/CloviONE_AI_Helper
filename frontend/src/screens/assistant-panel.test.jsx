import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* AI 도우미 패널.
 *
 *   * 기본 상태에서는 문장을 요청하지 않는다(?narrate 를 붙이지 않는다).
 *   * 러너가 죽거나 기능이 꺼져 있어도 **사실은 그대로 남고** 왜 문장이 없는지만 덧붙는다.
 *   * 트리아지는 제안만 한다 — 배정 버튼이 없고, '제안'이라고 화면이 직접 말한다.
 *
 * 🔴 이 패널은 더 이상 **위 카드의 숫자를 그대로 다시 읽지 않는다.** 예전 첫 줄은
 * 「오늘 마감 2건, 지연 1건, 진행 중 5건, 막힘 0건」이었고 그 아래에 「위 숫자는 이 화면
 * 상단 카드와 같은 값입니다」라고 스스로 적고 있었다. 지금은 같은 사실에서 **무엇이 가장
 * 급한가**를 뽑아 한 문장으로 낸다 — 아래 `briefingFocus` 단위 시험이 그 규칙 자체를
 * 값으로 고정한다.
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

    // 지연 1건이 있으므로 그것이 오늘의 결론이다(개수 나열이 아니라 판단 한 줄).
    expect(await screen.findByText("마감이 지난 티켓 1건이 오늘 가장 급합니다.")).toBeInTheDocument();
    // 같은 화면 위 판독 줄이 이미 말하는 개수 나열을 여기서 되풀이하지 않는다.
    expect(screen.queryByText(/오늘 마감 2건, 지연 1건/)).toBeNull();
    expect(screen.queryByText(/위 숫자는 이 화면 상단 카드와 같은 값입니다/)).toBeNull();
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

    expect(await screen.findByText("담당 티켓을 읽지 못해 오늘 요약을 만들 수 없습니다.")).toBeInTheDocument();
    expect(screen.queryByText(/오늘 마감 0건/)).not.toBeInTheDocument();
    // 「지금 볼 것」도 0건을 지어내지 않고 왜 비었는지 말한다.
    expect(screen.getByText("티켓을 다시 읽을 수 있게 되면 여기에 급한 순서로 표시됩니다.")).toBeInTheDocument();
  });

  it("문장 생성이 꺼져 있으면 숫자는 그대로 두고 이유만 덧붙인다", async () => {
    routeApi();
    renderPanel();
    await screen.findByText("마감이 지난 티켓 1건이 오늘 가장 급합니다.");

    await userEvent.click(screen.getByRole("button", { name: "문장 요약 만들기" }));

    expect(await screen.findByText("요약 문장 생성이 꺼져 있습니다.")).toBeInTheDocument();
    // 사실은 한 글자도 사라지지 않는다 — 문장은 그 위에 얹히는 것이지 대신하는 것이 아니다.
    expect(screen.getByText("마감이 지난 티켓 1건이 오늘 가장 급합니다.")).toBeInTheDocument();
    expect(apiMock.mock.calls.some(([p]) => p.includes("narrate=true"))).toBe(true);
  });

  it("러너가 문장을 주면 요약으로 보여준다", async () => {
    routeApi({ narrative: { enabled: true, text: "오늘 마감 2건, 지연 1건입니다.", error: null } });
    renderPanel();
    await screen.findByText("마감이 지난 티켓 1건이 오늘 가장 급합니다.");

    await userEvent.click(screen.getByRole("button", { name: "문장 요약 만들기" }));
    expect(await screen.findByText("오늘 마감 2건, 지연 1건입니다.")).toBeInTheDocument();
    // 문장이 생기면 그것을 그대로 쓸 수 있는 행동이 함께 나온다.
    expect(screen.getByRole("button", { name: "문장 복사" })).toBeInTheDocument();
  });

  it("업무 공유 초안 탭은 최근 끝낸 일 / 오늘 할 일 / 막힌 일 세 단으로 나눈다", async () => {
    routeApi();
    renderPanel();
    await screen.findByText("마감이 지난 티켓 1건이 오늘 가장 급합니다.");

    await userEvent.click(screen.getByRole("tab", { name: "업무 공유 초안" }));

    expect(await screen.findByText("끝낸 일")).toBeInTheDocument();
    expect(screen.getByText("오늘 처리할 티켓")).toBeInTheDocument();
    expect(screen.getByText("지연된 일")).toBeInTheDocument();
    // 막힌 일이 0건이면 빈 칸이 아니라 '없다'고 말한다.
    expect(screen.getByText("상태가 이슈인 티켓이 없습니다.")).toBeInTheDocument();
  });

  it("트리아지는 '제안'이라고 말하고 배정 버튼을 두지 않는다", async () => {
    routeApi();
    renderPanel();
    await screen.findByText("마감이 지난 티켓 1건이 오늘 가장 급합니다.");

    await userEvent.click(screen.getByRole("tab", { name: "담당자 지정 필요" }));

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
    await screen.findByText("마감이 지난 티켓 1건이 오늘 가장 급합니다.");

    await userEvent.click(screen.getByRole("tab", { name: "담당자 지정 필요" }));
    expect(await screen.findByText("담당자를 지정할 티켓이 없습니다")).toBeInTheDocument();
  });

  it("SEM-02: 패널 제목은 h2, 안의 소제목(TicketLines)은 h3다", async () => {
    // 이 컴포넌트는 항상 Home.jsx(/me) 안에 박혀 있어 그 화면의 다른 최상위 구역과
    // 같은 무게(h2)를 받는다 — 그 아래 TicketLines 소제목은 h4에서 h3로 함께 낮췄다
    // (h2 → h4로 건너뛰지 않게).
    routeApi();
    renderPanel();
    await screen.findByText("마감이 지난 티켓 1건이 오늘 가장 급합니다.");
    expect(screen.getByRole("heading", { level: 2, name: "AI 도우미" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "업무 공유 초안" }));
    await screen.findByText("오늘 처리할 티켓");
    expect(screen.getByRole("heading", { level: 3, name: /최근 끝낸 일/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: /오늘 할 일/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: /막힌 일/ })).toBeInTheDocument();
  });
});

/* 해석 규칙 자체를 값으로 고정한다.
 *
 * 렌더를 통해서만 재면 문구가 조금 바뀔 때마다 시험이 깨지고, 정작 **순서가 뒤바뀐 것**은
 * 안 잡힌다. 이 패널의 존재 이유가 「무엇이 가장 급한가」를 정하는 그 순서라 따로 잰다. */
import { attentionRows, briefingFocus, daysBetween, standupDraft, tabLinks } from "./AssistantPanel.jsx";

const T = (over) => ({ id: "p" + (over.tid || 1), tid: 1, title: "제목", status: "진행", due: null, ...over });

describe("briefingFocus — 오늘의 결론 한 줄", () => {
  it("버킷이 아예 없으면 0 을 지어내지 않고 모른다고 한다", () => {
    expect(briefingFocus({ configured: true, ok: true }).key).toBe("unknown");
    expect(briefingFocus(null).key).toBe("unknown");
  });

  it("지연이 막힘보다, 막힘이 오늘 마감보다 앞선다", () => {
    const full = {
      due_today: { count: 5 }, overdue: { count: 2 }, blocked: { count: 1 },
      due_soon: { count: 3 }, in_progress: { count: 9 },
    };
    expect(briefingFocus(full).key).toBe("overdue");
    expect(briefingFocus({ ...full, overdue: { count: 0 } }).key).toBe("blocked");
    expect(briefingFocus({ ...full, overdue: { count: 0 }, blocked: { count: 0 } }).key).toBe("due_today");
  });

  it("급한 것이 하나도 없으면 진행 중을 이어서 보라고 한다", () => {
    const calm = {
      due_today: { count: 0 }, overdue: { count: 0 }, blocked: { count: 0 },
      due_soon: { count: 0 }, in_progress: { count: 4 },
    };
    expect(briefingFocus(calm).key).toBe("in_progress");
    expect(briefingFocus({ ...calm, in_progress: { count: 0 } }).key).toBe("none");
  });
});

describe("attentionRows — 버킷을 가로질러 급한 셋", () => {
  it("같은 티켓을 두 번 넣지 않고 셋에서 멈춘다", () => {
    const dup = T({ tid: 7, id: "p7", due: "2026-07-30" });
    const rows = attentionRows({
      overdue: { items: [dup, T({ tid: 8, id: "p8", due: "2026-07-31" })] },
      blocked: { items: [dup] },
      due_today: { items: [T({ tid: 9, id: "p9", due: "2026-08-03" }), T({ tid: 10, id: "p10" })] },
    }, "2026-08-03");
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.item.id)).toEqual(["p7", "p8", "p9"]);
    // 지연 일수는 오늘과의 차이에서 나온다(문자열 날짜를 UTC 로 읽는다).
    expect(rows[0].reason).toBe("지연 4일");
    expect(rows[0].kind).toBe("danger");
  });

  it("마감일이 없는 지연 티켓도 사유를 잃지 않는다", () => {
    const rows = attentionRows({ overdue: { items: [T({ due: null })] } }, "2026-08-03");
    expect(rows[0].reason).toBe("지연");
  });
});

describe("daysBetween", () => {
  it("두 달력일 사이의 날짜 수를 센다", () => {
    expect(daysBetween("2026-07-30", "2026-08-03")).toBe(4);
    expect(daysBetween("2026-08-03", "2026-08-03")).toBe(0);
    expect(daysBetween(null, "2026-08-03")).toBeNull();
    expect(daysBetween("nope", "2026-08-03")).toBeNull();
  });
});

describe("standupDraft — 그대로 붙여 넣을 수 있는 초안", () => {
  it("세 단을 제목과 함께 담고, 빈 단은 '없음'이라고 적는다", () => {
    const text = standupDraft(STANDUP);
    expect(text).toContain("2026-08-03 업무 공유");
    expect(text).toContain("- 오늘 처리할 티켓 (마감 2026-08-03)");
    expect(text).toContain("막힌 일: 없음");
  });
});

describe("tabLinks — 갈 이유가 있을 때만 버튼을 낸다", () => {
  it("브리핑은 위 카드가 이미 같은 목적지를 주므로 비어 있다", () => {
    expect(tabLinks("briefing", {})).toEqual([]);
  });
  it("트리아지는 볼 것이 있을 때만 미할당 화면을 연다", () => {
    expect(tabLinks("triage", { total: 0 })).toEqual([]);
    expect(tabLinks("triage", { total: 3 })[0].href).toBe("#/unassigned");
  });
  it("이번 주 요약은 언제나 스프린트 회의로 이어진다", () => {
    expect(tabLinks("weekly", {})[0].href).toBe("#/sprint");
  });
});
