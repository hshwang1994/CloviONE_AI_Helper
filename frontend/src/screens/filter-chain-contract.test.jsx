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
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "me-1" } }) }));

import { MyTickets } from "./MyTickets.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const META = { configured: true, ok: true, statuses: ["진행", "검증", "완료"],
               priorities: ["High", "Normal"], difficulties: ["상", "중"] };
const PROJECTS = { configured: true, ok: true, projects: [{ id: "p-1", name: "인프라" }] };
const ASSIGNEES = { assignees: [] };

/** 조건별로 **다른 행**을 돌려준다 — 그래야 「엉뚱한 결과를 그렸다」가 화면에서 보인다. */
function rowsFor(query) {
  const status = query.get("status") || "";
  const page = query.get("page") || "1";
  const tag = `${status || "전체"}·${page}쪽`;
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

const addrParam = (key) => {
  const s = screen.getByTestId("addr").textContent;
  return new URLSearchParams(s.includes("?") ? s.slice(s.indexOf("?") + 1) : "").get(key);
};

async function pickStatus(user, label) {
  await user.click(screen.getByRole("combobox", { name: "상태" }));
  await user.click(await screen.findByRole("option", { name: label }));
}

describe("조건이 바뀔 때 화면이 지키는 것", () => {
  it("쪽 초기화 — 3쪽에서 조건을 바꾸면 1쪽으로 돌아온다", async () => {
    const user = userEvent.setup();
    renderMine(["/my-tickets?page=3"]);
    await screen.findByText("티켓 전체·3쪽");
    expect(addrParam("page")).toBe("3");

    await pickStatus(user, "진행");

    await waitFor(() => expect(addrParam("status")).toBe("진행"));
    // 주소에서 page 가 빠졌다 = 기본값(1쪽)이다.
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

    await pickStatus(user, "완료");
    expect(await screen.findByText("티켓 완료·1쪽")).toBeInTheDocument();
    // 앞 조건의 행이 남아 있으면 키에 조건이 안 들어간 것이다.
    expect(screen.queryByText("티켓 진행·1쪽")).toBeNull();

    // 되돌아가도 그 조건의 결과다(다른 조건의 캐시를 물어 오지 않는다).
    await pickStatus(user, "진행");
    expect(await screen.findByText("티켓 진행·1쪽")).toBeInTheDocument();
    expect(screen.queryByText("티켓 완료·1쪽")).toBeNull();
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

    await pickStatus(user, "완료");
    await waitFor(() => expect(pending.length).toBe(1));
    const fast = pending.shift();                 // 「완료」 요청

    // 🔴 나중 조건이 먼저 도착하고, 먼저 보낸 조건이 **나중에** 도착한다.
    fast.resolve(rowsFor(fast.query));
    expect(await screen.findByText("티켓 완료·1쪽")).toBeInTheDocument();
    slow.resolve(rowsFor(slow.query));

    // 늦게 도착한 옛 조건의 결과가 화면을 덮으면 안 된다.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByText("티켓 완료·1쪽")).toBeInTheDocument();
    expect(screen.queryByText("티켓 진행·1쪽")).toBeNull();
    expect(addrParam("status")).toBe("완료");
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
