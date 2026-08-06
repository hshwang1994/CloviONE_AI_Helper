/* 티켓 목록의 **공용 필터 줄**과 **주소가 든 화면 상태** (사용자 지적 #3).
 *
 * 사용자가 말한 증상: "필터를 걸고 티켓 상세를 보고 돌아오면 필터가 풀린다". 문서 화면도
 * 같다고 했다. 원인은 필터가 `React.useState` 에만 있었다는 것이고, 고친 방향은 주소다.
 *
 * 여기서 보는 것은 넷이다.
 *   1) 조건을 고르면 **주소가 바뀌고 서버 질의에도 그대로** 나간다(화면에서 거르지 않는다 —
 *      서버가 20건씩 자르므로 화면에서 거르면 그 한 페이지 안에서만 걸러진다).
 *   2) 상세로 갔다가 뒤로 오면 그 조건이 **그대로**다. 그리고 상세로 갈 때 실어 준
 *      `location.state.from`(사이드바 선택 유지)이 살아 있다.
 *   3) 검색 글자를 쳐도 **목록이 다시 그려지지 않는다**. 세는 방법은 관리자 화면 검사와
 *      같다: 행 렌더가 실제로 몇 번 불렸는지(`priorityKo` 호출 수).
 *   4) 빈 목록이 "필터 때문"인지 "정말 없음"인지 화면이 **다르게 말한다**.
 *
 * 오탐 방지: 아무것도 안 고른 화면의 주소에는 쿼리가 없어야 하고, 필터를 지우면 다시
 * 비어야 한다. 이게 없으면 "주소가 바뀐다" 검사는 아무 값이나 실려도 통과한다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useLocation, useNavigate, useParams } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "me-1" } }) }));

/* 행 렌더 횟수를 세는 자리. `ticketColumns` 는 우선순위 칸마다 `priorityKo` 를 부르므로,
 * 이 호출 수가 곧 '지금 표에 그려진 행 수'다. 화면 밖에서 세는 것이 핵심이다 — 컴포넌트에
 * 메모를 붙였는지가 아니라 **사용자가 겪는 층(입력 지연)** 을 본다. */
let rowRenders = 0;
vi.mock("../lib/priority.js", async (importOriginal) => {
  const real = await importOriginal();
  return {
    ...real,
    priorityKo: (v) => { rowRenders += 1; return real.priorityKo(v); },
  };
});

import { MyTickets } from "./MyTickets.jsx";
import { TeamTickets } from "./TeamTickets.jsx";
import { SPRINT_FIELDS, matchesTicketFilters } from "./TicketFilterBar.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const META = { configured: true, ok: true, statuses: ["진행", "검증", "완료"], priorities: ["High", "Normal"], difficulties: ["상", "중"] };
const PROJECTS = { configured: true, ok: true, projects: [{ id: "p-1", name: "인프라" }] };
const ASSIGNEES = { assignees: [{ user_id: "u-1", display_name: "김하나" }, { user_id: "u-2", display_name: "박세찬" }] };

function ticket(n, over) {
  return {
    id: `t-${n}`, tid: n, title: `티켓 ${n}`, status: "진행", priority: "High",
    project: "인프라", due: "2026-08-20", assignee_names: ["나"], ...over,
  };
}

/** 마지막으로 나간 목록 요청의 쿼리스트링. */
function lastListQuery(prefix) {
  const calls = apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith(prefix));
  const last = calls[calls.length - 1];
  return new URLSearchParams(last && last.includes("?") ? last.slice(last.indexOf("?") + 1) : "");
}

let listPayload = null;

beforeEach(() => {
  rowRenders = 0;
  listPayload = { configured: true, ok: true, mapped: true, items: [ticket(1), ticket(2)], total: 2, page: 1, page_size: 20 };
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p.startsWith("/api/tickets/meta")) return Promise.resolve(META);
    if (p.startsWith("/api/tickets/projects")) return Promise.resolve(PROJECTS);
    if (p.startsWith("/api/tickets/assignees")) return Promise.resolve(ASSIGNEES);
    if (p.startsWith("/api/tickets/mine") || p.startsWith("/api/tickets/team") || p.startsWith("/api/tickets/unassigned")) {
      return Promise.resolve(listPayload);
    }
    return Promise.resolve({});
  });
});

/* 주소를 검사에서 읽기 위한 표시줄. 화면이 주소에 무엇을 실었는지 보는 유일한 방법이다. */
function AddressProbe() {
  const loc = useLocation();
  return <div data-testid="addr">{loc.pathname + loc.search}</div>;
}

function TicketDetailProbe() {
  const { id } = useParams();
  const loc = useLocation();
  const nav = useNavigate();
  return (
    <div>
      <div>티켓 상세: {id}</div>
      <div data-testid="from">{(loc.state && loc.state.from) || "없음"}</div>
      <button type="button" onClick={() => nav(-1)}>돌아가기</button>
    </div>
  );
}

function renderScreen(Screen, path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <AddressProbe />
              <Routes>
                <Route path={path.split("?")[0]} element={<Screen />} />
                <Route path="/tickets/:id" element={<TicketDetailProbe />} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const addr = () => screen.getByTestId("addr").textContent;
/** 주소에 실린 값 하나. 문자열로 비교하지 않는다 — 같은 값이 인코딩된 채로도, 안 된 채로도
 *  주소에 있을 수 있어서(직접 친 링크 vs 화면이 쓴 값) 문자열 비교는 무엇도 증명하지 않는다. */
function addrParam(key) {
  const s = addr();
  return new URLSearchParams(s.includes("?") ? s.slice(s.indexOf("?") + 1) : "").get(key);
}

async function pickOption(user, comboName, optionName) {
  await user.click(screen.getByRole("combobox", { name: comboName }));
  await user.click(await screen.findByRole("option", { name: optionName }));
}

describe("내 티켓 — 조건이 주소에 남는다", () => {
  it("아무것도 안 고르면 주소에 쿼리가 없고, 서버에도 조건을 안 보낸다", async () => {
    renderScreen(MyTickets, "/my-tickets");
    expect(await screen.findByText("티켓 1")).toBeInTheDocument();
    expect(addr()).toBe("/my-tickets");
    expect(lastListQuery("/api/tickets/mine").toString()).toBe("");
  });

  it("상태를 고르면 주소에 실리고 같은 값이 서버 질의로 나간다", async () => {
    const user = userEvent.setup();
    renderScreen(MyTickets, "/my-tickets");
    await screen.findByText("티켓 1");

    await pickOption(user, "상태", "검증");

    await waitFor(() => expect(addrParam("status")).toBe("검증"));
    await waitFor(() => expect(lastListQuery("/api/tickets/mine").get("status")).toBe("검증"));
  });

  it("필터를 지우면 주소가 다시 비워진다", async () => {
    const user = userEvent.setup();
    renderScreen(MyTickets, "/my-tickets?status=검증");
    await screen.findByText("티켓 1");
    expect(addr()).toContain("status=");

    await user.click(await screen.findByRole("button", { name: "필터 지우기" }));

    await waitFor(() => expect(addr()).toBe("/my-tickets"));
  });

  it("주소에 실린 조건으로 시작한다 (새로고침, 링크 공유)", async () => {
    renderScreen(MyTickets, "/my-tickets?status=검증&page=2");
    await screen.findByText("티켓 1");
    const sent = lastListQuery("/api/tickets/mine");
    expect(sent.get("status")).toBe("검증");
    expect(sent.get("page")).toBe("2");
  });

  it("페이지를 넘겨도 걸어 둔 조건은 그대로 간다", async () => {
    const user = userEvent.setup();
    listPayload = { ...listPayload, total: 45 };
    renderScreen(MyTickets, "/my-tickets?status=검증");
    await screen.findByText("티켓 1");

    await user.click(await screen.findByRole("button", { name: "다음" }));

    await waitFor(() => {
      const sent = lastListQuery("/api/tickets/mine");
      expect(sent.get("page")).toBe("2");
      expect(sent.get("status")).toBe("검증");
    });
  });

  it("조건을 바꾸면 페이지는 처음으로 돌아간다", async () => {
    const user = userEvent.setup();
    listPayload = { ...listPayload, total: 45, page: 3 };
    renderScreen(MyTickets, "/my-tickets?page=3");
    await screen.findByText("티켓 1");

    await pickOption(user, "상태", "검증");

    await waitFor(() => expect(lastListQuery("/api/tickets/mine").has("page")).toBe(false));
  });
});

describe("내 티켓 — 상세로 갔다 돌아오기", () => {
  it("뒤로 오면 필터가 그대로이고, 상세에는 어디서 왔는지가 실려 간다", async () => {
    const user = userEvent.setup();
    renderScreen(MyTickets, "/my-tickets?status=검증");
    await screen.findByText("티켓 1");

    await user.click(screen.getByRole("button", { name: "티켓 1" }));
    expect(await screen.findByText("티켓 상세: t-1")).toBeInTheDocument();
    // 사이드바 선택 유지의 근거. 이게 없으면 미할당에서 연 티켓도 '내 티켓'이 켜진다.
    expect(screen.getByTestId("from").textContent).toBe("/my-tickets");

    await user.click(screen.getByRole("button", { name: "돌아가기" }));

    expect(await screen.findByText("티켓 1")).toBeInTheDocument();
    expect(addrParam("status")).toBe("검증");
    await waitFor(() => expect(lastListQuery("/api/tickets/mine").get("status")).toBe("검증"));
  });
});

describe("내 티켓 — 검색 입력", () => {
  it("글자를 쳐도 목록이 다시 그려지지 않는다 (디바운스가 끝나기 전까지)", async () => {
    renderScreen(MyTickets, "/my-tickets");
    await screen.findByText("티켓 1");

    const before = rowRenders;
    expect(before).toBeGreaterThan(0); // 행이 실제로 그려졌다는 것부터 확인한다
    const input = screen.getByRole("searchbox", { name: "검색어" });
    for (const ch of ["배", "포", "자", "동", "화"]) {
      fireEvent.change(input, { target: { value: input.value + ch } });
    }

    expect(rowRenders).toBe(before);
    expect(input.value).toBe("배포자동화");   // 타이핑 자체는 즉시 보인다
  });

  it("잠시 뒤 검색어가 주소와 서버 질의로 확정된다", async () => {
    renderScreen(MyTickets, "/my-tickets");
    await screen.findByText("티켓 1");

    fireEvent.change(screen.getByRole("searchbox", { name: "검색어" }), { target: { value: "배포" } });

    await waitFor(() => expect(lastListQuery("/api/tickets/mine").get("q")).toBe("배포"), { timeout: 2000 });
    expect(addrParam("q")).toBe("배포");
  });
});

describe("빈 목록의 두 가지 뜻", () => {
  it("필터가 걸려 있으면 지우기 버튼이 있는 '조건에 맞는 티켓이 없습니다'", async () => {
    listPayload = { configured: true, ok: true, mapped: true, items: [], total: 0, page: 1, page_size: 20 };
    renderScreen(MyTickets, "/my-tickets?status=검증");
    expect(await screen.findByText("조건에 맞는 티켓이 없습니다")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "필터 지우기" }).length).toBeGreaterThan(0);
  });

  it("필터가 없으면 '정말 없다'고 말한다 (필터를 지우라고 하지 않는다)", async () => {
    listPayload = { configured: true, ok: true, mapped: true, items: [], total: 0, page: 1, page_size: 20 };
    renderScreen(MyTickets, "/my-tickets");
    expect(await screen.findByText("담당한 티켓이 없습니다")).toBeInTheDocument();
    expect(screen.queryByText("조건에 맞는 티켓이 없습니다")).toBeNull();
    expect(screen.queryByRole("button", { name: "필터 지우기" })).toBeNull();
  });

  it("연동이 없으면 필터 줄 자체를 그리지 않는다", async () => {
    listPayload = { configured: false, ok: false, tickets: [] };
    renderScreen(MyTickets, "/my-tickets");
    expect(await screen.findByText("Notion 연동이 아직 설정되지 않았습니다")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "상태" })).toBeNull();
    expect(screen.queryByRole("searchbox", { name: "검색어" })).toBeNull();
  });
});

describe("팀 티켓 — 같은 부품, 담당자 조건까지", () => {
  it("담당자는 앱 user_id 로 나간다 (이름으로 화면에서 거르지 않는다)", async () => {
    const user = userEvent.setup();
    renderScreen(TeamTickets, "/team-tickets");
    await screen.findByText("티켓 1");

    await pickOption(user, "담당자", "김하나");

    await waitFor(() => expect(lastListQuery("/api/tickets/team").get("assignee_user_id")).toBe("u-1"));
    expect(addrParam("assignee_user_id")).toBe("u-1");
  });

  it("완료, 취소 포함을 켜면 목록 범위가 서버에서 넓어진다", async () => {
    const user = userEvent.setup();
    renderScreen(TeamTickets, "/team-tickets");
    await screen.findByText("티켓 1");
    expect(lastListQuery("/api/tickets/team").get("active")).toBe("true");

    await user.click(screen.getByRole("switch", { name: "완료, 취소 포함" }));

    await waitFor(() => expect(lastListQuery("/api/tickets/team").get("active")).toBe("false"));
    expect(addrParam("active")).toBe("0");
  });
});

/* 스프린트만 화면에서 거른다 — 그 화면의 응답에는 페이지가 없어서 전량이 오기 때문이다.
 * 여기서 지키는 것은 "거를 수 있는 조건만 내놓는다"다. 리포트 경로가 안 싣는 값을 조건으로
 * 내놓으면 고르는 순간 목록이 언제나 비고, 사용자는 그걸 '티켓이 없다'로 읽는다. */
describe("스프린트 — 화면이 직접 거르는 조건", () => {
  const row = { title: "배포 자동화", status: "진행", priority: "High", difficulty: "상" };

  it("상태, 우선순위, 난이도, 검색어를 판단한다", () => {
    expect(matchesTicketFilters(row, { status: "진행" }, SPRINT_FIELDS)).toBe(true);
    expect(matchesTicketFilters(row, { status: "완료" }, SPRINT_FIELDS)).toBe(false);
    expect(matchesTicketFilters(row, { q: "배포" }, SPRINT_FIELDS)).toBe(true);
    expect(matchesTicketFilters(row, { q: "회의" }, SPRINT_FIELDS)).toBe(false);
    expect(matchesTicketFilters(row, {}, SPRINT_FIELDS)).toBe(true);
  });

  /* 프로젝트와 담당자는 티켓 하나가 **여럿**을 가질 수 있다. 스칼라로 비교하면 둘 이상 달린
     티켓이 조용히 떨어진다 — 판정은 서버와 같게 "하나라도 맞으면 통과"다. */
  it("프로젝트와 담당자는 배열 안에 있는지로 판단한다", () => {
    const multi = { ...row, project_ids: ["p-1", "p-2"], assignee_user_ids: ["u-1", "u-2"] };
    expect(matchesTicketFilters(multi, { project_id: "p-2" }, SPRINT_FIELDS)).toBe(true);
    expect(matchesTicketFilters(multi, { project_id: "p-9" }, SPRINT_FIELDS)).toBe(false);
    expect(matchesTicketFilters(multi, { assignee_user_id: "u-2" }, SPRINT_FIELDS)).toBe(true);
    expect(matchesTicketFilters(multi, { assignee_user_id: "u-9" }, SPRINT_FIELDS)).toBe(false);
    // 그 값을 아예 안 싣는 행(옛 리포트 경로)은 통과하지 못한다 — 그래서 화면이 그 응답
    // 모양에서는 두 조건을 **내놓지 않는다**(SPRINT_REPORT_FIELDS).
    expect(matchesTicketFilters(row, { project_id: "p-1" }, SPRINT_FIELDS)).toBe(false);
  });

  it("판단할 수 없는 조건은 조용히 넘기지 않고 소리를 낸다", () => {
    // 기한은 버킷('지연'·'이번 주')이라 '오늘'이 있어야 풀린다 — 화면은 그걸 모른다.
    expect(() => matchesTicketFilters(row, { due: "overdue" }, ["due"])).toThrow(/거를 수 없는/);
    expect(() => matchesTicketFilters(row, { category: "인프라" }, ["category"])).toThrow(/거를 수 없는/);
  });

  it("스프린트가 내놓는 조건은 전부 판단 가능한 것뿐이다", () => {
    for (const key of SPRINT_FIELDS) {
      expect(() => matchesTicketFilters(row, { [key]: "아무값" }, [key])).not.toThrow();
    }
  });
});
