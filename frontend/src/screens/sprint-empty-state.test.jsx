import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

/* qa-contract-change: 회차가 팀의 것이 되어(D-482) 새 회차 폼에서 프로젝트 칸이 사라졌다 — 「프로젝트 칸이 보인다」 단정은 「어느 팀의 회차인지 한 줄이 말한다」로 바뀌었고, 단추 이름은 표준 동사표대로 「회차 추가」다. 팀 후보가 없는 경우의 빈 상태 단정이 새로 붙었다.
 *
 * 스프린트 회의 — 회차 0건일 때의 빈 상태 (A2 재검수).
 *
 * §8.3 은 이 빈 상태가 layout="page" 로 서고 「회차 추가」·「백로그 보기」 둘을 준다고
 * 못 박는다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { Sprint } from "./Sprint.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const TEAM = {
  selected: "d-a",
  options: [{ id: "d-a", name: "플랫폼개발팀", path: [{ id: "d-hq", name: "플랫폼본부" }, { id: "d-a", name: "플랫폼개발팀" }], manageable: true }],
  manageable: true,
};

function stub(path) {
  if (path.startsWith("/api/tickets/projects")) return Promise.resolve({ projects: [] });
  if (path.startsWith("/api/work/statuses")) return Promise.resolve({ statuses: [] });
  if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints: [], team: TEAM });
  return Promise.resolve({});
}

function renderSprint() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Sprint />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("스프린트 회의 — 회차 0건", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(stub);
  });

  it("안내 문장이 실제로 보이고, 추가/백로그 두 행동이 있다", async () => {
    renderSprint();
    await waitFor(() =>
      expect(screen.getByText("아직 만든 회차가 없습니다.")).toBeTruthy(),
    );
    expect(screen.getByText(/번다운과 건강, 담당자별 남은 일/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "회차 추가" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "백로그 보기" })).toBeTruthy();
  });

  it("회차 추가를 누르면 추가 대화상자가 열린다", async () => {
    renderSprint();
    const btn = await screen.findByRole("button", { name: "회차 추가" });
    btn.click();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
    expect(screen.getByRole("heading", { name: "새 회차" })).toBeTruthy();
  });

  it("🔴 폼에 프로젝트 칸이 없고, 어느 팀의 회차인지 한 줄이 말한다(D-482)", async () => {
    renderSprint();
    (await screen.findByRole("button", { name: "회차 추가" })).click();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByText("프로젝트")).toBeNull();
    expect(within(dialog).getByText("플랫폼본부 › 플랫폼개발팀의 회차를 추가합니다.")).toBeTruthy();
  });
});

describe("스프린트 회의 — 회차는 있는데 열린 것이 없다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/work/sprints")) {
        return Promise.resolve({
          sprints: [{
            id: "sp-9", name: "지난 회차", department_id: "d-a",
            starts_on: "2026-08-01", ends_on: "2026-08-07", state: "closed",
          }],
          team: TEAM,
        });
      }
      return stub(path);
    });
  });

  it("🔴 자동 선택 대신 「회차를 고르세요」 안내가 선다 — 백지가 아니다", async () => {
    renderSprint();
    await screen.findByText("회의할 회차를 고르세요.");
    expect(screen.getByRole("button", { name: "가장 최근 회차 열기" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "회차 추가" })).toBeTruthy();
  });
});

describe("스프린트 회의 — 볼 수 있는 팀이 없다", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/work/sprints")) {
        return Promise.resolve({ sprints: [], team: { selected: null, options: [], manageable: false } });
      }
      return stub(path);
    });
  });

  it("소속이 없는 사람에게는 팀이 없다고 말한다 — 빈 회차 안내가 아니다", async () => {
    renderSprint();
    await screen.findByText("회차를 볼 수 있는 팀이 없습니다.");
    expect(screen.queryByText("아직 만든 회차가 없습니다.")).toBeNull();
    expect(screen.queryByRole("button", { name: "회차 추가" })).toBeNull();
  });
});
