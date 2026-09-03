import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 티켓을 **끝낸 순간** 축포가 터진다 (사용자 지적, 2026-09-03).
 *
 * 사용자: "티켓이 완료됐을때 폭죽이 터지기로했는데 수정을 눌러서 완료누르고 저장눌렀을때는
 * 폭죽이 안터짐."
 *
 * 그 말이 맞았다. `ui/celebrate.js` 가 붙어 있던 자리는 넷뿐이었고 — 놀이 승자 공개 ·
 * 승인함 비움 · 내 티켓 목록 비움 · 회차 닫기 — 전부 「할 게 **없어졌다**」였다.
 * 「이 티켓을 **끝냈다**」에는 아무도 연결하지 않았다.
 *
 * 🔴 이 파일은 **문자열 grep 이 아니라 실제 폼**을 쓴다. 저장 버튼을 눌러 PATCH 가 나가고,
 * 그 성공 뒤에 축포가 실제로 불리는지 본다 — 배선이 끊기면 여기서 빨간불이 난다.
 * (이 저장소는 "테스트가 헛것이었다" 를 여러 번 겪었다.)
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u-1" } }),
}));

const confettiSpy = vi.fn();
vi.mock("canvas-confetti", () => ({ default: (...a) => confettiSpy(...a) }));

import { TicketEditModal } from "./MyTickets.jsx";
import { resetBurstCooldown } from "../ui/celebrate.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/** 서버의 상태 어휘 그대로. **갈래가 대문자**다(`app/work/workflow.py::CAT_DONE`) —
 *  이 값이 어긋나면 화면은 정상으로 보이고 축포만 조용히 안 터진다. */
const WORK_STATUSES = {
  statuses: [
    { key: "계획", label: "계획", category: "OPEN", terminal: false },
    { key: "진행", label: "진행 중", category: "IN_PROGRESS", terminal: false },
    { key: "완료", label: "완료", category: "DONE", terminal: true },
    { key: "취소", label: "취소", category: "CANCELED", terminal: true },
  ],
};

function ticket(extra) {
  return {
    id: "p1", tid: 1, key: "ABC-1", title: "티켓 하나", status: "진행",
    due: "", start: "", est_wd: null, act_wd: null,
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
      return Promise.resolve({ ok: true, ticket: ticket(options.body) });
    }
    if (path.startsWith("/api/work/statuses")) return Promise.resolve(WORK_STATUSES);
    if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    if (path.startsWith("/api/tickets/meta")) {
      return Promise.resolve({ statuses: ["계획", "진행", "완료", "취소"], priorities: [], difficulties: [] });
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

/** 진행상태 드롭다운에서 한 값을 고른다. 화면이 실제로 하는 손짓 그대로다. */
async function pickStatus(user, label) {
  await user.click(screen.getByRole("combobox", { name: /진행상태/ }));
  await user.click(await screen.findByRole("option", { name: label }));
}

beforeEach(() => {
  apiMock.mockReset();
  confettiSpy.mockClear();
  resetBurstCooldown();
});

/* 축포 한 벌은 가운데 → 좌 → 우로 140·260ms 뒤에 두 발이 더 예약된다. 여기서 걷지 않으면
   그 타이머가 **다음 시험** 도중에 발사돼, 쏘지 않아야 하는 자리에서 쏜 것으로 잡힌다.
   실제로 이 파일이 그렇게 한 번 빨개졌다(로그인 시험 파일도 같은 자리에서 겪었다). */
afterEach(async () => {
  if (confettiSpy.mock.calls.length) {
    await new Promise((r) => setTimeout(r, 350));
  }
});

describe("수정 폼에서 완료로 저장하면 축포가 터진다", () => {
  it("🔴 진행 → 완료 로 바꿔 저장하면 터진다 — 사용자가 짚은 바로 그 경로다", async () => {
    const patches = routeApi();
    const user = userEvent.setup();
    renderModal(ticket());
    await waitFor(() => expect(document.getElementById("te-status")).toBeTruthy());

    await pickStatus(user, "완료");
    await user.click(screen.getByRole("button", { name: "저장" }));

    // 서버로 상태가 실제로 갔고,
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0].status).toBe("완료");
    // 그 성공 뒤에 축포가 터진다.
    await waitFor(() => expect(confettiSpy).toHaveBeenCalled());
  }, { timeout: 15000 });

  it("취소로 바꿔 저장하면 안 터진다 — 접은 일은 끝낸 일이 아니다", async () => {
    const patches = routeApi();
    const user = userEvent.setup();
    renderModal(ticket());
    await waitFor(() => expect(document.getElementById("te-status")).toBeTruthy());

    await pickStatus(user, "취소");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0].status).toBe("취소");
    expect(confettiSpy).not.toHaveBeenCalled();
  }, { timeout: 15000 });

  it("이미 완료인 티켓의 제목만 고쳐 저장하면 안 터진다 — 옮긴 것이 아니다", async () => {
    const patches = routeApi();
    const user = userEvent.setup();
    renderModal(ticket({ status: "완료" }));
    await waitFor(() => expect(document.getElementById("te-title")).toBeTruthy());

    await user.type(screen.getByLabelText(/제목/), " 보강");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(patches).toHaveLength(1));
    // 상태 칸 자체가 안 실린다(`buildChanges` 는 바뀐 값만 담는다).
    expect(patches[0].status).toBeUndefined();
    expect(confettiSpy).not.toHaveBeenCalled();
  }, { timeout: 15000 });

  it("저장이 실패하면 안 터진다 — 서버가 받아 준 뒤에만 축하한다", async () => {
    apiMock.mockImplementation((path, options) => {
      if (path === "/api/tickets/p1" && options && options.method === "PATCH") {
        return Promise.reject(new Error("저장하지 못했습니다."));
      }
      if (path.startsWith("/api/work/statuses")) return Promise.resolve(WORK_STATUSES);
      if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
      if (path.startsWith("/api/tickets/meta")) {
        return Promise.resolve({ statuses: ["진행", "완료"], priorities: [], difficulties: [] });
      }
      if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderModal(ticket());
    await waitFor(() => expect(document.getElementById("te-status")).toBeTruthy());

    await pickStatus(user, "완료");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await screen.findByText(/저장하지 못했습니다/);
    expect(confettiSpy).not.toHaveBeenCalled();
  }, { timeout: 15000 });
});
