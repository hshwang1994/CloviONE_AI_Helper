import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";

/* 회차 문맥에서 만드는 티켓의 프로젝트 후보는 **그 팀의 것만**이다 (D-482).
 *
 * 회차에 담을 수 있는 자격은 「티켓의 팀(프로젝트의 부서) == 회차의 팀」정확 일치다. 작업
 * 보드의 「티켓 추가」는 주소에 `team` 을 싣고, 이 폼은 그 팀의 프로젝트만 후보로 둔다 —
 * 다른 팀·조직 공통 프로젝트를 골라 서버의 422 를 보는 것은 안내가 아니다. 팀 문맥이
 * 없으면(일반 「새 티켓」) 예전처럼 전부다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "me-1" } }) }));
vi.mock("../ui/kit.jsx", async (orig) => {
  const real = await orig();
  return { ...real, useToast: () => () => {} };
});

import { NewTicket } from "./MyTickets.jsx";
import { createClovirTheme } from "../ui/theme.js";
import { eligibleProjects } from "./ticket-options.js";

const PROJECTS = {
  projects: [
    { id: "p-a", name: "A팀 프로젝트", dept_id: "d-a", can_create_ticket: true },
    { id: "p-a1", name: "A-1파트 프로젝트", dept_id: "d-a1", can_create_ticket: true },
    { id: "p-org", name: "조직 공통 프로젝트", dept_id: null, can_create_ticket: true },
  ],
};
const META = { statuses: ["계획", "진행"], priorities: [], difficulties: [] };

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    const url = String(path);
    if (url === "/api/tickets/projects") return Promise.resolve(PROJECTS);
    if (url === "/api/tickets/meta") return Promise.resolve(META);
    if (url.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: [] });
    return Promise.resolve({});
  });
  window.location.hash = "";
});

function renderForm(hash) {
  window.location.hash = hash;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={createClovirTheme()}>
        <MemoryRouter initialEntries={["/new-ticket"]}>
          <Routes>
            <Route path="/new-ticket" element={<NewTicket />} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("eligibleProjects", () => {
  it("팀이 정확히 같은 프로젝트만 남긴다 — 하위 팀·조직 공통은 없다", () => {
    expect(eligibleProjects(PROJECTS.projects, "d-a").map((p) => p.id)).toEqual(["p-a"]);
    expect(eligibleProjects(PROJECTS.projects, "d-a1").map((p) => p.id)).toEqual(["p-a1"]);
    // 팀 문맥이 없으면 전부다.
    expect(eligibleProjects(PROJECTS.projects, "").length).toBe(3);
  });
});

describe("새 티켓 — 팀 문맥의 프로젝트 후보", () => {
  it("🔴 `team` 을 실어 오면 그 팀의 프로젝트만 후보이고 한 줄로 이유를 말한다", async () => {
    renderForm("#/new-ticket?team=d-a&sprint=sp-1");
    const box = await screen.findByRole("combobox", { name: /프로젝트/ });
    await userEvent.click(box);
    const options = within(await screen.findByRole("listbox")).getAllByRole("option").map((o) => o.textContent);
    expect(options.some((o) => o.includes("A팀 프로젝트"))).toBe(true);
    expect(options.some((o) => o.includes("A-1파트 프로젝트"))).toBe(false);
    expect(options.some((o) => o.includes("조직 공통 프로젝트"))).toBe(false);
    expect(screen.getByText("이 팀의 회차에 담을 수 있는 프로젝트만 보입니다.")).toBeTruthy();
  });

  it("팀 문맥이 없으면 예전처럼 전부 후보다", async () => {
    renderForm("#/new-ticket");
    const box = await screen.findByRole("combobox", { name: /프로젝트/ });
    await userEvent.click(box);
    const options = within(await screen.findByRole("listbox")).getAllByRole("option").map((o) => o.textContent);
    expect(options.some((o) => o.includes("조직 공통 프로젝트"))).toBe(true);
    expect(screen.queryByText(/이 팀의 회차에 담을 수 있는/)).toBeNull();
  });
});
