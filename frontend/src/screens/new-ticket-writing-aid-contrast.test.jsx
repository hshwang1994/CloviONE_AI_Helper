import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";
import "@testing-library/jest-dom/vitest";

/* '작성 도움' 레일의 절 삽입 버튼이 흰 Card 위에서 안 보이던 회귀 (사용자 지적:
 * "새티켓 만들때 작성 도움 부분에 버튼이 명확하지가 않다. 버튼이 흰배경이라서").
 *
 * 원인: WritingAid(MyTickets.jsx)의 버튼이 bgcolor:"transparent" + border:0 라, 흰 Card
 * 배경 위에서 경계가 전혀 없었다. BodyEditor 툴바 버튼이 이미 쓰는 표면 톤
 * (background.surface2 + divider 테두리)으로 맞춘다. */

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

function apiOk() {
  apiMock.mockImplementation((path) => {
    if (path === "/api/tickets/projects") return Promise.resolve({ projects: [] });
    if (path === "/api/tickets/meta") return Promise.resolve({ statuses: ["계획"], priorities: [], difficulties: [] });
    if (path === "/api/tickets/assignees") return Promise.resolve({ assignees: [] });
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
  apiOk();
});

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

describe("작성 도움 버튼은 카드 배경과 구별되는 표면을 쓴다", () => {
  it("절 삽입 버튼의 배경이 투명이 아니다(카드와 같은 흰색으로 묻히지 않는다)", async () => {
    const { container } = renderNewTicket();
    await screen.findByText("작성 도움");
    const btn = container.querySelector('button[aria-label^="설명에"]');
    expect(btn, "작성 도움 절 삽입 버튼을 찾지 못했다").toBeTruthy();
    const bg = getComputedStyle(btn).backgroundColor;
    expect(bg).not.toBe("transparent");
    expect(bg).not.toBe("rgba(0, 0, 0, 0)");
    expect(getComputedStyle(btn).borderWidth).not.toBe("0px");
  });
});
