import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 작성 도움 항목이 통째로 단추이던 손 카드에서 판 하나 안의 목록 줄 + 줄마다 작은 「넣기」 단추(30)로 바뀌어(핸드오프 계획 C · O-4), 「선택」 표시와 넣은 뒤 상태를 단추 안이 아니라 항목 줄에서 잰다. */

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
  /* 라우터 안에서 그린다 — 실제 앱이 그렇고(`app/UserRoutes.jsx`), 만든 뒤 그 티켓으로
     이동하는 것이 이 화면의 마지막 단계다(`navigate('/tickets/:id')`). 라우터 없이 그리면
     그 단계 자체를 시험이 못 본다. */
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={createClovirTheme()}>
        <MemoryRouter initialEntries={["/new-ticket"]}>
          <NewTicket />
        </MemoryRouter>
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

/* 항목 줄 — 절 이름 · 무엇을 적나 · 예시가 읽을 것이고, 누를 것은 줄 오른쪽 「넣기」 하나다. */
const itemOf = (btn) => btn.closest("[data-writing-aid-item]");

describe("REAUDIT C19 — 「넷이 핵심, 둘은 더」가 화면에 보인다", () => {
  it("🔴 여섯 항목이 넷(핵심)과 둘(더 적으면 좋은 항목)로 갈린다", async () => {
    renderNewTicket();
    await screen.findByText("작성 도움");
    // 실측에서 "넷이 아니라 여섯"으로 읽힌 자리 — 그룹 표제가 실제로 있어야 한다.
    expect(screen.getByText("더 적으면 좋은 항목")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-writing-aid-item]")).toHaveLength(6);
    // 선택 둘(예외 처리·확인 방법)의 항목 줄에는 "선택" 표가 붙는다.
    const exceptionBtn = screen.getByRole("button", { name: /^설명에 '예외 처리'/ });
    expect(within(itemOf(exceptionBtn)).getByText("선택")).toBeInTheDocument();
    const verifyBtn = screen.getByRole("button", { name: /^설명에 '확인 방법'/ });
    expect(within(itemOf(verifyBtn)).getByText("선택")).toBeInTheDocument();
    // 핵심 넷에는 "선택" 표가 없다.
    const coreBtn = screen.getByRole("button", { name: /^설명에 '배경과 문제'/ });
    expect(within(itemOf(coreBtn)).queryByText("선택")).toBeNull();
  });

  it("항목 하나에 단추는 「넣기」 하나이고 작은 단추(30)다 — 항목 전체가 단추가 아니다", async () => {
    renderNewTicket();
    await screen.findByText("작성 도움");
    const items = [...document.querySelectorAll("[data-writing-aid-item]")];
    for (const item of items) {
      const buttons = within(item).getAllByRole("button");
      expect(buttons).toHaveLength(1);
      expect(buttons[0]).toHaveTextContent(/^넣기$/);
      expect(buttons[0].className).toMatch(/MuiButton-sizeSmall/);
      expect(item.tagName).toBe("LI");
    }
  });

  it("넣은 절은 단추가 꺼지고 「✓」가 선다 — 접근 이름은 예전 그대로이고 「넣었음」 낱말은 없다", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await screen.findByText("작성 도움");
    await user.click(screen.getByRole("button", { name: "설명에 '배경과 문제' 절 넣기" }));
    const done = await screen.findByRole("button", { name: "배경과 문제: 이미 넣었습니다" });
    expect(done).toBeDisabled();
    expect(done).toHaveTextContent(/^✓$/);
    expect(screen.queryByText(/넣었음/)).toBeNull();
    // 다른 절은 그대로 넣을 수 있다.
    expect(screen.getByRole("button", { name: "설명에 '완료 기준' 절 넣기" })).not.toBeDisabled();
  });
});
