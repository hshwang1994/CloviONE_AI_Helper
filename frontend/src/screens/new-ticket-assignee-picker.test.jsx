import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@mui/material/styles";

/* PA-RC-0035: 담당자 선택이 사람 수만큼 자라는 평면 체크박스 목록이었다(14명 기준 새 티켓
 * 폼 세로의 상당 부분) — 검색 가능한 자동완성 입력 + 선택 칩(MUI Autocomplete)으로 바꿨다.
 * 후보가 많아져도 입력 자리는 한 줄로 고정된다는 것이 이 RC의 핵심 주장이라, 큰 후보
 * 집합(50명)으로 시험한다.
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

// 50명 — Handoff acceptance(1)의 재측정 기준("14명 -> 50명이 되어도 세로 길이가 유의하게
// 늘지 않는다")을 그대로 후보 수로 재현한다. me-1을 포함해 자동 선택("나") 동작도 함께 본다.
const MANY_CANDIDATES = [
  { user_id: "me-1", display_name: "나", dept: "개발팀", title: "팀원" },
  ...Array.from({ length: 49 }, (_, i) => ({
    user_id: `u-${i}`, display_name: `사람${String(i).padStart(2, "0")}`, dept: "개발팀", title: "팀원",
  })),
];

function apiOk(candidates = MANY_CANDIDATES) {
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/tickets/projects") return Promise.resolve({ projects: [] });
    if (path === "/api/tickets/meta") return Promise.resolve({ statuses: ["계획"], priorities: [], difficulties: [] });
    if (path === "/api/tickets/assignees") return Promise.resolve({ assignees: candidates });
    if (path === "/api/tickets" && opts && opts.method === "POST") return Promise.resolve({ id: "t-9" });
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

describe("새 티켓 — 담당자는 검색 가능한 자동완성이다 (PA-RC-0035)", () => {
  it("후보가 50명이어도 평소엔 옵션 목록이 화면에 없다 — 입력 한 줄만 있다(폼 길이가 인원 수와 무관)", async () => {
    renderNewTicket();
    // '나'가 기본 선택되므로 그 칩이 뜨는 것으로 로드 완료를 기다린다.
    await screen.findByText("나");
    // 예전 체크박스 그리드였다면 50개 행이 전부 그려졌을 것이다 — 지금은 옵션 role 자체가
    // (열기 전엔) 문서에 없다.
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    expect(screen.getByRole("combobox", { name: /담당자/ })).toBeInTheDocument();
  });

  it("로드되면 '나'가 기본 담당자로 칩에 나타난다(기존 자동 선택 동작 보존)", async () => {
    renderNewTicket();
    expect(await screen.findByText("나")).toBeInTheDocument();
  });

  it("이름으로 검색하면 일치하는 사람만 옵션에 뜬다", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await screen.findByText("나");

    const input = screen.getByRole("combobox", { name: /담당자/ });
    await user.click(input);
    await user.type(input, "사람07");

    const options = await screen.findAllByRole("option");
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent("사람07");
  });

  it("검색해서 고르면 칩이 추가되고, 여러 명 선택이 유지된다", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await screen.findByText("나");

    const input = screen.getByRole("combobox", { name: /담당자/ });
    await user.click(input);
    await user.type(input, "사람00");
    await user.click(await screen.findByRole("option", { name: /사람00/ }));

    // '나'(자동 선택) + '사람00'(방금 선택) 두 명이 칩으로 남는다.
    expect(await screen.findByText("사람00")).toBeInTheDocument();
    expect(screen.getByText("나")).toBeInTheDocument();
  });

  it("칩의 삭제 버튼으로 선택을 해제할 수 있다", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await screen.findByText("나");

    const chip = screen.getByText("나").closest(".MuiChip-root");
    await user.click(within(chip).getByTestId("CancelIcon"));

    await waitFor(() => expect(screen.queryByText("나")).not.toBeInTheDocument());
  });

  it("키보드만으로 검색·선택·해제할 수 있다", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await screen.findByText("나");

    // Tab으로 입력에 도달(키보드 흐름의 전제) — 제목 다음 필드들을 지나 담당자 입력까지.
    await user.click(document.body); // 포커스 초기화
    const input = screen.getByRole("combobox", { name: /담당자/ });
    input.focus();
    expect(input).toHaveFocus();

    await user.keyboard("사람01");
    await screen.findByRole("option", { name: /사람01/ });
    await user.keyboard("{ArrowDown}{Enter}");
    expect(await screen.findByText("사람01")).toBeInTheDocument();

    // 입력이 비어 있을 때 Backspace는 MUI Autocomplete의 표준 동작대로 마지막 칩을 지운다.
    await user.keyboard("{Backspace}");
    await waitFor(() => expect(screen.queryByText("사람01")).not.toBeInTheDocument());
  });

  it("선택한 담당자 id 배열이 그대로 요청 본문에 실린다(Notion 연동 계약 불변)", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await screen.findByText("나");

    await user.type(screen.getByLabelText(/제목/), "담당자 배정 확인");

    const input = screen.getByRole("combobox", { name: /담당자/ });
    await user.click(input);
    await user.type(input, "사람02");
    await user.click(await screen.findByRole("option", { name: /사람02/ }));
    await screen.findByText("사람02");
    // 선택 뒤에도 목록(multiple 모드는 기본적으로 안 닫는다)이 남아 다른 요소를 가릴 수
    // 있다 — Esc로 명시적으로 닫고 제출로 넘어간다.
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryAllByRole("option")).toHaveLength(0));

    await user.click(screen.getByRole("button", { name: "티켓 추가" }));

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith("/api/tickets", expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({ assignee_user_ids: expect.arrayContaining(["me-1", "u-2"]) }),
      }));
    });
  });
});

describe("새 티켓 — 설명 필드의 안내는 입력 중에도 남는다 (PA-RC-0035 acceptance 5,6)", () => {
  it("placeholder는 예시 한 줄이고, 서식/미리보기 안내는 항상 보이는 캡션에 있다", async () => {
    renderNewTicket();
    await screen.findByText("나");
    const editor = document.getElementById("nt-desc");
    expect(editor).toHaveAttribute("placeholder", expect.stringMatching(/^예:/));
    expect(screen.getByText(/위 도구로 제목, 글머리, 번호, 구분선, 이모지를 넣을 수 있고/)).toBeInTheDocument();
  });

  it("설명을 입력해도 안내 캡션이 사라지지 않는다(placeholder와 달리)", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await screen.findByText("나");
    const editor = document.getElementById("nt-desc");
    await user.type(editor, "실제 내용을 입력합니다");
    expect(screen.getByText(/위 도구로 제목, 글머리, 번호, 구분선, 이모지를 넣을 수 있고/)).toBeInTheDocument();
  });
});
