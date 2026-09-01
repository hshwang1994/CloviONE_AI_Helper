/* 조건이 바뀔 때 **화면이 지켜야 하는 네 가지** (S15 · C7 · R-87).
 *
 * 서버가 맞는 답을 줘도 화면이 이 넷을 못 지키면 사용자는 틀린 목록을 본다. 그리고 넷 다
 * 조용하다 — 오류가 안 나고, 화면은 정상으로 보인다.
 *
 *   1) **쪽 초기화** — 3쪽을 보다가 조건을 바꾸면 1쪽으로 돌아온다. 안 그러면 결과가
 *      한 쪽뿐인데 빈 화면이 뜨고, 사용자는 그것을 "조건에 맞는 게 없다"로 읽는다.
 *   2) **경합** — 조건을 빠르게 연달아 바꿨을 때 **먼저 보낸 요청의 늦은 응답**이 최신
 *      조건의 결과를 덮지 않는다.
 *   3) **캐시 키** — 다른 조건인데 같은 결과를 재사용하지 않는다. 조건 전체가 키에 들어
 *      있어야 한다.
 *   4) **뒤로/앞으로** — 화면이 말하는 조건과 실제 질의 조건이 같다.
 *
 * 대상은 `/my-tickets` 다. 이 화면 하나가 세 부품을 전부 지난다 —
 * `useQueryState`(주소가 진실) · `TicketFilterBar`(조건) · `useTicketList`(질의 키).
 * 같은 부품을 쓰는 화면이 여덟이라, 여기서 지켜지면 그 여덟에서 지켜진다.
 */
import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "me-1" } }) }));

import { MyTickets } from "./MyTickets.jsx";
import { ConfirmProvider, ToastProvider, statusText } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const META = { configured: true, ok: true, statuses: ["진행", "검증", "완료"],
               priorities: ["High", "Normal"], difficulties: ["상", "중"] };
const PROJECTS = { configured: true, ok: true, projects: [{ id: "p-1", name: "인프라" }] };
const ASSIGNEES = { assignees: [] };

/** 조건별로 **다른 행**을 돌려준다 — 그래야 「엉뚱한 결과를 그렸다」가 화면에서 보인다.
 *
 * 상태는 **여러 값**이다(`TicketFilterBar.MULTI_FIELDS`). `get()` 은 첫 값만 주므로 그걸로
 * 꼬리표를 만들면 「진행」과 「진행+완료」가 화면에서 같은 글자가 되고, 그러면 이 파일의
 * 네 계약이 전부 판정력을 잃는다. 조건 전체를 읽는다.
 */
function rowsFor(query) {
  const picked = query.getAll("status").filter(Boolean);
  const status = picked[0] || "";
  const page = query.get("page") || "1";
  const tag = `${picked.length ? picked.join("+") : "전체"}·${page}쪽`;
  return {
    configured: true, ok: true,
    items: [{ id: `t-${tag}`, tid: 1, title: `티켓 ${tag}`, status: status || "진행",
              priority: "High", project: "인프라", due: "2026-08-20", assignee_names: ["나"] }],
    total: 60, page: Number(page), page_size: 20,
  };
}

/* 목록 응답을 **손으로 풀어 주는** 모드. 경합을 재현하려면 응답 순서를 시험이 정해야 한다. */
let pending = null;
let listCalls = [];

beforeEach(() => {
  pending = null;
  listCalls = [];
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const p = String(path);
    if (p.startsWith("/api/tickets/meta")) return Promise.resolve(META);
    if (p.startsWith("/api/tickets/projects")) return Promise.resolve(PROJECTS);
    if (p.startsWith("/api/tickets/assignees")) return Promise.resolve(ASSIGNEES);
    if (p.startsWith("/api/tickets/mine")) {
      const query = new URLSearchParams(p.includes("?") ? p.slice(p.indexOf("?") + 1) : "");
      listCalls.push(query);
      if (pending) {
        return new Promise((resolve) => pending.push({ query, resolve }));
      }
      return Promise.resolve(rowsFor(query));
    }
    return Promise.resolve({});
  });
});

function AddressProbe() {
  const loc = useLocation();
  const nav = useNavigate();
  return (
    <div>
      <div data-testid="addr">{loc.pathname + loc.search}</div>
      {/* 바깥에서 주소만 바꾸는 이동 — 뒤로가기·앞으로가기가 하는 일과 같다. */}
      <button type="button" data-testid="goto-done"
        onClick={() => nav("/my-tickets?status=%EC%99%84%EB%A3%8C")}>주소만 바꾸기</button>
    </div>
  );
}

function renderMine(entries = ["/my-tickets"]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter initialEntries={entries}>
          <AddressProbe />
          <Routes><Route path="/my-tickets" element={<MyTickets />} /></Routes>
        </MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
  return view;
}

const addrQuery = () => {
  const s = screen.getByTestId("addr").textContent;
  return new URLSearchParams(s.includes("?") ? s.slice(s.indexOf("?") + 1) : "");
};
const addrParam = (key) => addrQuery().get(key);
/** 여러 값을 갖는 조건(상태·우선순위·프로젝트 등)은 **전부** 봐야 한다. */
const addrParamAll = (key) => addrQuery().getAll(key);

/* 상태 조건 하나를 **토글**한다 (P-47).
 *
 * 상태는 다중 선택이다. MUI 의 `Select multiple` 은 항목을 눌러도 **메뉴를 안 닫는다** —
 * 그것이 다중 선택의 정답이다(연달아 여러 개를 고른다). 그런데 메뉴가 떠 있는 동안 MUI 는
 * 나머지 화면 전체에 `aria-hidden` 을 건다. 그래서 고르고 나서 안 닫으면 그 뒤의
 * `getByRole` 이 **하나도 안 걸린다** — 예전 도우미는 단일 선택 시절 그대로라 여기서
 * 「combobox 상태 없음」으로 죽었고, 그것을 화면 결함으로 오해할 만한 모양이었다.
 * 제품은 맞다. 사용자가 하는 것과 같이 **닫고** 다음으로 간다.
 */
/* 🔴 인자는 **저장 키**다. 화면에 보이는 이름은 그것과 다를 수 있다 — 「진행」은 「진행 중」으로
   그려진다(`app/work/workflow.py` 가 키와 라벨을 나눠 갖고 있고 화면이 그 라벨을 쓴다).
   그래서 고를 때는 라벨로 찾고, 서버로 나가는 값은 키로 단언한다. */
async function pickStatus(user, key) {
  await user.click(screen.getByRole("combobox", { name: "상태" }));
  const listbox = await screen.findByRole("listbox");
  await user.click(within(listbox).getByRole("option", { name: statusText(key) }));
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
}

describe("조건이 바뀔 때 화면이 지키는 것", () => {
  it("묶음 초기화 — 더 받아 둔 뒤 조건을 바꾸면 첫 묶음부터 다시 받는다", async () => {
    const user = userEvent.setup();
    renderMine();
    await screen.findByText("티켓 전체·1쪽");
    await user.click(await screen.findByRole("button", { name: "티켓 더 보기" }));
    await waitFor(() => {
      expect(listCalls[listCalls.length - 1].get("page")).toBe("2");
    });

    await pickStatus(user, "진행");

    await waitFor(() => expect(addrParam("status")).toBe("진행"));
    /* 쪽 번호는 주소에도 요청에도 없다 — 조건이 바뀌면 받아 둔 묶음을 통째로 버리고
       첫 묶음부터 다시 받는다. */
    expect(addrParam("page")).toBeNull();
    const last = listCalls[listCalls.length - 1];
    expect(last.get("status")).toBe("진행");
    expect(last.get("page")).toBeNull();
  });

  it("캐시 키 — 다른 조건인데 앞 조건의 결과를 재사용하지 않는다", async () => {
    const user = userEvent.setup();
    renderMine();
    await screen.findByText("티켓 전체·1쪽");

    await pickStatus(user, "진행");
    expect(await screen.findByText("티켓 진행·1쪽")).toBeInTheDocument();

    // 다중 선택이라 누를수록 **쌓인다**. 그래서 조건은 [진행, 완료] 가 된다.
    await pickStatus(user, "완료");
    expect(await screen.findByText("티켓 진행+완료·1쪽")).toBeInTheDocument();
    // 앞 조건의 행이 남아 있으면 키에 조건이 안 들어간 것이다.
    expect(screen.queryByText("티켓 진행·1쪽")).toBeNull();

    // 같은 항목을 다시 누르면 빠진다 — **앞서 본 적 있는 조건**으로 되돌아가는 이동이다.
    // 그때 다른 조건의 캐시를 물어 오면 안 된다.
    await pickStatus(user, "완료");
    expect(await screen.findByText("티켓 진행·1쪽")).toBeInTheDocument();
    expect(screen.queryByText("티켓 진행+완료·1쪽")).toBeNull();
  });

  it("경합 — 먼저 보낸 요청의 늦은 응답이 최신 조건을 덮지 않는다", async () => {
    const user = userEvent.setup();
    pending = [];
    renderMine();
    // 첫 로드부터 손으로 풀어 준다.
    await waitFor(() => expect(pending.length).toBe(1));
    pending.shift().resolve(rowsFor(new URLSearchParams()));
    await screen.findByText("티켓 전체·1쪽");

    await pickStatus(user, "진행");
    await waitFor(() => expect(pending.length).toBe(1));
    const slow = pending.shift();                 // 「진행」 요청 — 아직 안 풀었다

    await pickStatus(user, "완료");               // 조건이 [진행, 완료] 로 넓어진다
    await waitFor(() => expect(pending.length).toBe(1));
    const fast = pending.shift();                 // 「진행+완료」 요청

    // 🔴 나중 조건이 먼저 도착하고, 먼저 보낸 조건이 **나중에** 도착한다.
    fast.resolve(rowsFor(fast.query));
    expect(await screen.findByText("티켓 진행+완료·1쪽")).toBeInTheDocument();
    slow.resolve(rowsFor(slow.query));

    // 늦게 도착한 옛 조건의 결과가 화면을 덮으면 안 된다.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByText("티켓 진행+완료·1쪽")).toBeInTheDocument();
    expect(screen.queryByText("티켓 진행·1쪽")).toBeNull();
    expect(addrParamAll("status")).toEqual(["진행", "완료"]);
  });

  /* 뒤로가기·앞으로가기는 화면이 **바깥에서 주소가 바뀌는** 이동이다. 그때 조건 상자와
   * 목록이 따라오지 않으면, 화면이 말하는 조건과 실제 질의 조건이 어긋난다 — 사용자는
   * 걸려 있지도 않은 조건을 읽는다. 여기서는 그 이동을 라우터의 이동으로 재현한다
   * (뒤로가기가 하는 일이 정확히 이것이다: 주소만 바뀐다). */
  it("바깥에서 주소가 바뀌면 조건 상자와 목록이 함께 따라온다", async () => {
    const user = userEvent.setup();
    renderMine();
    await screen.findByText("티켓 전체·1쪽");

    await pickStatus(user, "진행");
    expect(await screen.findByText("티켓 진행·1쪽")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "상태" }).textContent).toContain("진행");

    // 주소만 바꾼다 — 화면을 다시 마운트하지 않는다(그러면 아무것도 증명 못 한다).
    await user.click(screen.getByTestId("goto-done"));

    expect(await screen.findByText("티켓 완료·1쪽")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "상태" }).textContent).toContain("완료");
    expect(addrParam("status")).toBe("완료");
    const last = listCalls[listCalls.length - 1];
    expect(last.get("status")).toBe("완료");
  });
});
