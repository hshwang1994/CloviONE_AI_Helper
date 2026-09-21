import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 신호를 **켤 수 있는가** (D-349).
 *
 * 🔴 이것이 비어 있었다. `이슈 있음` 과 `차단됨` 은 설계상 「사람이 켜는 플래그」인데
 * (`docs/ui-redesign/PLAN.md`), 서버가 그 세 칸을 받고(`TicketUpdate`) 목록·상세·작업 보드·
 * 회의·주간보고가 전부 그 값을 읽어 그리는 동안 **쓰는 화면이 하나도 없었다.** 그래서
 * 「이슈 있음」 필터를 걸면 언제나 이관 시점 데이터뿐이었고, 보드의 신호 타일은 0 이었다.
 *
 * 여기서 재는 것은 화면이 아니라 **요청 본문**이다. 체크박스가 그려지는지만 보면 그것이
 * 서버로 가는지는 모른다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u-1" } }),
}));

import { TicketEditModal } from "./MyTickets.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function ticket(extra) {
  return {
    id: "p1", tid: 1, key: "ABC-1", title: "티켓 하나", status: "진행",
    due: "2026-08-03", start: "", est_wd: 1, act_wd: null,
    priority: null, difficulty: null, category: "",
    project_ids: [], project_names: [],
    assignee_names: [], assignee_user_ids: [],
    issue: false, blocked: false, blocked_reason: null,
    ...extra,
  };
}

function routeApi() {
  const patches = [];
  apiMock.mockImplementation((path, options) => {
    if (path === "/api/tickets/p1" && options && options.method === "PATCH") {
      patches.push(options.body);
      return Promise.resolve({ ok: true, ticket: ticket() });
    }
    if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    if (path.startsWith("/api/tickets/meta")) {
      return Promise.resolve({ statuses: ["진행", "완료"], priorities: [], difficulties: [] });
    }
    if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
    return Promise.resolve({});
  });
  return patches;
}

function renderModal(t) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <TicketEditModal ticket={t} open onClose={() => {}} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

async function save(user) {
  await user.click(screen.getByRole("button", { name: "저장" }));
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("티켓 편집 — 신호", () => {
  it("「이슈 있음」을 켜면 issue_flag 가 서버로 간다", async () => {
    const patches = routeApi();
    const user = userEvent.setup();
    renderModal(ticket());
    await waitFor(() => expect(document.getElementById("te-issue")).toBeTruthy());

    await user.click(screen.getByRole("checkbox", { name: "이슈 있음" }));
    await save(user);

    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]).toEqual({ issue_flag: true });
  }, { timeout: 10000 });

  it("이미 켜져 있으면 끌 수 있다 — 켜기만 되는 스위치는 신호가 아니라 낙인이다", async () => {
    const patches = routeApi();
    const user = userEvent.setup();
    renderModal(ticket({ issue: true }));
    await waitFor(() => expect(document.getElementById("te-issue")).toBeTruthy());
    expect(screen.getByRole("checkbox", { name: "이슈 있음" })).toBeChecked();

    await user.click(screen.getByRole("checkbox", { name: "이슈 있음" }));
    await save(user);

    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]).toEqual({ issue_flag: false });
  }, { timeout: 10000 });

  it("차단 사유 칸은 차단을 켜야 선다 — 사유만 적은 저장은 서버가 버린다", async () => {
    routeApi();
    const user = userEvent.setup();
    renderModal(ticket());
    await waitFor(() => expect(document.getElementById("te-blocked")).toBeTruthy());
    expect(document.getElementById("te-blocked-reason")).toBeNull();

    await user.click(screen.getByRole("checkbox", { name: "차단됨" }));

    await waitFor(() => expect(document.getElementById("te-blocked-reason")).toBeTruthy());
  }, { timeout: 10000 });

  it("차단과 사유를 함께 저장하면 **깃발이 사유보다 먼저** 실린다", async () => {
    const patches = routeApi();
    const user = userEvent.setup();
    renderModal(ticket());
    await waitFor(() => expect(document.getElementById("te-blocked")).toBeTruthy());

    await user.click(screen.getByRole("checkbox", { name: "차단됨" }));
    await waitFor(() => expect(document.getElementById("te-blocked-reason")).toBeTruthy());
    await user.type(document.getElementById("te-blocked-reason"), "배포 승인 대기");
    await save(user);

    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]).toEqual({ blocked_flag: true, blocked_reason: "배포 승인 대기" });
    // 서버는 사유를 적용할 때 그 순간의 차단 여부를 본다. 순서가 뒤집히면 이유만 사라진다.
    expect(Object.keys(patches[0])).toEqual(["blocked_flag", "blocked_reason"]);
  }, { timeout: 10000 });

  it("차단을 풀 때는 사유를 안 보낸다 — 지우는 것은 서버가 한다", async () => {
    const patches = routeApi();
    const user = userEvent.setup();
    renderModal(ticket({ blocked: true, blocked_reason: "외부 응답 대기" }));
    await waitFor(() => expect(document.getElementById("te-blocked")).toBeTruthy());

    await user.click(screen.getByRole("checkbox", { name: "차단됨" }));
    await save(user);

    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]).toEqual({ blocked_flag: false });
  }, { timeout: 10000 });

  it("「지연」은 켜는 칸이 아니다 — 마감일에서 계산한다", async () => {
    routeApi();
    renderModal(ticket());
    await waitFor(() => expect(document.getElementById("te-issue")).toBeTruthy());

    expect(screen.queryByRole("checkbox", { name: "지연" })).toBeNull();
  }, { timeout: 10000 });
});

describe("티켓 편집 — 같은 저장을 두 번 보내지 않는다 (P4)", () => {
  it("제목 칸에서 Enter 를 두 번 쳐도 PATCH 는 한 번이다", async () => {
    /* Enter 는 발의 「저장」이 아니라 폼 안의 숨은 제출 단추를 누른다. 그 단추는 저장 중에도 꺼지지 않으므로
       예전에는 Enter 두 번이 같은 PATCH 두 번이었다. 응답을 붙잡아 두고 그 창 안에서 두 번 친다. */
    const patches = [];
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    apiMock.mockImplementation((path, options) => {
      if (path === "/api/tickets/p1" && options && options.method === "PATCH") {
        patches.push(options.body);
        return held;
      }
      if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
      if (path.startsWith("/api/tickets/meta")) {
        return Promise.resolve({ statuses: ["진행", "완료"], priorities: [], difficulties: [] });
      }
      if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderModal(ticket());
    await waitFor(() => expect(document.getElementById("te-title")).toBeTruthy());

    const title = document.getElementById("te-title");
    await user.clear(title);
    await user.type(title, "고친 제목");
    await user.keyboard("{Enter}{Enter}");

    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]).toEqual({ title: "고친 제목" });
    await act(async () => { release({ ok: true, ticket: ticket({ title: "고친 제목" }) }); });
    expect(patches).toHaveLength(1);
  }, { timeout: 10000 });
});
