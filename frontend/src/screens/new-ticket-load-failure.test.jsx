import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";

/* 새 티켓 폼이 **후보를 못 받은 것**과 후보가 **없는 것**을 갈라 말하는가 (S21).
 *
 * 고치기 전에는 `/api/tickets/projects` 가 실패해도 `projects` 가 그냥 빈 배열이 되어,
 * 프로젝트 칸이 "선택할 수 있는 프로젝트가 없습니다" 라고만 말했다. 사용자는 자기 권한에
 * 프로젝트가 없다고 읽었고, 실제로는 서버를 못 부른 것인데 **다시 부를 자리도 없었다** —
 * 지시가 이 회차에 콕 집어 말한 「Error 가 숨겨짐」이다.
 *
 * 두 갈래를 같은 자리에서 센다: 실패면 오류 얼굴 + 다시 시도, 성공인데 비면 그대로 폼.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "me-1" } }),
}));

import { NewTicket } from "./MyTickets.jsx";
import { createClovirTheme } from "../ui/theme.js";

function renderNewTicket() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={createClovirTheme()}>
        <NewTicket />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("새 티켓 — 후보를 못 받은 것과 후보가 없는 것", () => {
  it("프로젝트 조회가 실패하면 오류 얼굴과 '다시 시도'를 준다(빈 목록처럼 말하지 않는다)", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/tickets/projects") {
        const err = new Error("서버에 연결하지 못했습니다.");
        err.kind = "network";
        return Promise.reject(err);
      }
      if (path === "/api/tickets/meta") {
        return Promise.resolve({ statuses: ["계획"], priorities: [], difficulties: [] });
      }
      return Promise.resolve({});
    });

    renderNewTicket();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument());
    // 폼 대신 오류 얼굴이다 — 제목 칸도, "없습니다" 안내도 없다.
    expect(screen.queryByLabelText(/제목/)).not.toBeInTheDocument();
    expect(screen.queryByText("선택할 수 있는 프로젝트가 없습니다")).not.toBeInTheDocument();
  });

  it("조회는 됐는데 고를 프로젝트가 없으면 폼을 그대로 두고 그 사실만 말한다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/tickets/projects") return Promise.resolve({ projects: [] });
      if (path === "/api/tickets/meta") {
        return Promise.resolve({ statuses: ["계획"], priorities: [], difficulties: [] });
      }
      return Promise.resolve({});
    });

    renderNewTicket();

    await waitFor(() =>
      expect(screen.getAllByText("선택할 수 있는 프로젝트가 없습니다").length)
        .toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
  });
});
