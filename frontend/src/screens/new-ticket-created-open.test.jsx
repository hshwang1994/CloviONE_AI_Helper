import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";

/* 만든 티켓을 **바로 연다** — 문서 만들기와 같은 마무리.
 *
 * 예전에는 목록으로 튕기고 응답의 `ticket` 을 버렸다. 그런데 그 목록이 방금 만든 티켓을
 * 보여 준다는 보장이 없다: 담당자를 안 붙였으면 「내 티켓」에 없고, 상태·기간 조건이 걸려
 * 있으면 거기에도 없다. 사용자에게는 「만들었는데 안 보인다」가 된다 — 그리고 그것은
 * 「만들기가 실패했다」와 화면에서 구별되지 않는다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "me-1" } }) }));
vi.mock("../ui/kit.jsx", async (orig) => {
  const real = await orig();
  return { ...real, useToast: () => () => {} };
});

import { NewTicket } from "./MyTickets.jsx";
import { createClovirTheme } from "../ui/theme.js";
import { fillDateField } from "../test-helpers/dateField.js";

const PROJECTS = { projects: [{ id: "p-1", name: "인프라", can_create_ticket: true }] };
const META = { statuses: ["계획", "진행"], priorities: [], difficulties: [] };

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    const url = String(path);
    if (url === "/api/tickets/projects") return Promise.resolve(PROJECTS);
    if (url === "/api/tickets/meta") return Promise.resolve(META);
    if (url.startsWith("/api/tickets/assignees")) {
      return Promise.resolve({ assignees: [{ user_id: "me-1", display_name: "나" }] });
    }
    if (url === "/api/tickets" && opts && opts.method === "POST") {
      return Promise.resolve({ configured: true, ok: true, ticket: { id: "t-99", key: "AAA-1" } });
    }
    return Promise.resolve({});
  });
});

function renderFlow() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={createClovirTheme()}>
        <MemoryRouter initialEntries={["/new-ticket"]}>
          <Routes>
            <Route path="/new-ticket" element={<NewTicket />} />
            <Route path="/tickets/:id" element={<div>티켓 상세 자리</div>} />
            <Route path="/my-tickets" element={<div>내 티켓 목록 자리</div>} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

/* 제목 칸은 id 로 짚는다 — 지연 로드한 편집기가 이미 떠 있으면 도구 줄의 「제목1」 · 「제목2」도 /제목/ 에 걸린다
   (같은 파일의 앞 시험이 편집기 조각을 받아 둔 뒤에 도는 시험에서 그렇다). */
async function findTitle() {
  return waitFor(() => {
    const el = document.getElementById("nt-title");
    expect(el).toBeTruthy();
    return el;
  });
}

async function fillForm(user) {
  await user.type(await findTitle(), "서버 등록 IP 중복 방지");
  await user.click(screen.getByRole("combobox", { name: /프로젝트/ }));
  await user.click(await screen.findByRole("option", { name: "인프라" }));
  await user.type(screen.getByLabelText(/예상 WD/), "2");
  await fillDateField(user, /마감일/, "2026-09-30");
}

async function fillAndSubmit(user) {
  await fillForm(user);
  /* 「티켓 추가」는 폼이 유효해지기 전까지 **비활성**이다(담당자 후보가 서버에서 오는 것을
     기다린다). 바로 누르면 부하가 걸린 실행에서 비활성 단추를 누르게 되고, 그때 나오는 것은
     이 시험이 재려는 결함이 아니라 「아직 못 누른다」다. 눌릴 때까지 기다렸다가 누른다. */
  const submit = screen.getByRole("button", { name: "티켓 추가" });
  await waitFor(() => expect(submit).not.toBeDisabled());
  await user.click(submit);
}

describe("새 티켓 — 만든 뒤", () => {
  it("응답의 티켓 id 로 그 티켓 상세를 연다 — 목록으로 튕기지 않는다", async () => {
    const user = userEvent.setup();
    renderFlow();
    await fillAndSubmit(user);
    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith("/api/tickets", expect.objectContaining({ method: "POST" }));
    });
    expect(await screen.findByText("티켓 상세 자리")).toBeInTheDocument();
  /* 이 하나는 새 티켓 폼 전체를 그리고 두 번의 `userEvent` 타이핑을 지난다 — 단독 실행에서
     2.2초다. 기본 5초는 병렬 실행(`verify.py`)에서 실제로 넘겼다. 느린 시험이라 늘리는
     것이지 불안정한 시험을 덮는 것이 아니다. */
  }, 20000);
});

describe("새 티켓 — 같은 제출을 두 번 보내지 않는다 (P4)", () => {
  it("제목 칸의 Enter 연타와 같은 틱의 두 제출이 와도 티켓은 한 번만 만든다", async () => {
    /* 만들기 요청이 끝나기 전의 창을 연다 — 응답을 붙잡아 둔다. 예전에는 `submit()` 에 진행 중 가드가 없어서
       「티켓 추가」가 꺼지기 전에 도착한 둘째 제출이 같은 티켓을 한 번 더 만들었다. */
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    const base = apiMock.getMockImplementation();
    apiMock.mockImplementation((path, opts) => {
      if (String(path) === "/api/tickets" && opts && opts.method === "POST") return held;
      return base(path, opts);
    });
    const user = userEvent.setup();
    renderFlow();
    await fillForm(user);
    await waitFor(() => expect(screen.getByRole("button", { name: "티켓 추가" })).not.toBeDisabled());

    const title = await findTitle();
    const form = title.closest("form");
    act(() => {
      fireEvent.submit(form);
      fireEvent.submit(form);
    });
    await user.click(title);
    await user.keyboard("{Enter}{Enter}");

    const creates = () => apiMock.mock.calls.filter(
      ([p, o]) => String(p) === "/api/tickets" && o && o.method === "POST",
    );
    expect(creates()).toHaveLength(1);
    await act(async () => { release({ configured: true, ok: true, ticket: { id: "t-99" } }); });
    expect(await screen.findByText("티켓 상세 자리")).toBeInTheDocument();
    expect(creates()).toHaveLength(1);
  }, 20000);
});

describe("새 티켓 — 담당자 기본값", () => {
  it("프로젝트를 두 번째로 고를 때도 「나」가 다시 채워진다", async () => {
    /* 프로젝트를 바꾸면 담당자를 비운다(후보가 그 프로젝트 사람으로 바뀐다). 예전에는 「나」를
       채우는 이펙트가 컴포넌트 수명당 한 번만 돌아서, 두 번째 프로젝트에서는 담당자가 빈 채로
       남고 **미할당 티켓**이 만들어졌다 — 그 티켓은 「내 티켓」에 안 뜬다. */
    apiMock.mockImplementation((path, opts) => {
      const url = String(path);
      if (url === "/api/tickets/projects") {
        return Promise.resolve({ projects: [
          { id: "p-1", name: "인프라", can_create_ticket: true },
          { id: "p-2", name: "보안", can_create_ticket: true },
        ] });
      }
      if (url === "/api/tickets/meta") return Promise.resolve(META);
      if (url.startsWith("/api/tickets/assignees")) {
        return Promise.resolve({ assignees: [{ user_id: "me-1", display_name: "나" }] });
      }
      if (url === "/api/tickets" && opts && opts.method === "POST") {
        return Promise.resolve({ configured: true, ok: true, ticket: { id: "t-99" } });
      }
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderFlow();
    await user.click(await screen.findByRole("combobox", { name: /프로젝트/ }));
    await user.click(await screen.findByRole("option", { name: "인프라" }));
    /* 고른 담당자는 `Autocomplete` 의 칩으로 선다 — 「나」 칩이 있으면 채워진 것이다. */
    await waitFor(() => expect(screen.getAllByText("나").length).toBeGreaterThan(0));

    await user.click(screen.getByRole("combobox", { name: /프로젝트/ }));
    await user.click(await screen.findByRole("option", { name: "보안" }));
    await waitFor(() => expect(screen.getAllByText("나").length).toBeGreaterThan(0));
  });
});