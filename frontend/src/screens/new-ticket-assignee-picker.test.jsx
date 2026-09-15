import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { fillDateField } from "../test-helpers/dateField.js";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";

/* qa-contract-change: 새 티켓 칸 이름이 MUI 노치 라벨(「제목 *」)에서 칸 위 FieldLabel(「제목」 + 눈으로만 보이는 「필수」)로 옮겨(핸드오프 계획 C), 제목 칸을 찾는 라벨 글자 규칙을 그 모양으로 옮긴다. */

/* qa-contract-replaced-by: frontend/src/ui/body-editor-no-emoji.test.jsx
 * qa-contract-replaced-by: frontend/src/ui/body-editor-toolbar-contrast.test.jsx
 *
 * 그 둘은 티켓 설명이 **글자 칩 열한 개**(제목1·제목2·제목3·글머리·번호·체크·인용·코드·
 * 구분선·링크·이모지)짜리 마크다운 편집기이던 시절의 계약이었다. 이름으로 그 열한 개가
 * 있는지, 그 칩들이 흰 판 위에서 경계를 갖는지를 쟀다. 지금 티켓 설명은 문서와 **같은
 * 편집기**(TipTap 아이콘 툴바)를 쓰므로 그 열한 개가 존재하지 않는다 — 아래
 * 「설명은 문서와 같은 편집기다」가 그 자리를 대신해 아이콘 툴바와 접근 이름을 잰다.
 *
 * PA-RC-0035: 담당자 선택이 사람 수만큼 자라는 평면 체크박스 목록이었다(14명 기준 새 티켓
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

/* 0060: 담당자 후보는 **선택된 프로젝트**에 달렸다(§14) — 프로젝트를 고르기 전에는
   후보를 묻지도 않는다. 그래서 이 파일의 대역도 프로젝트를 하나 준다. */
const PROJECT = { id: "p-1", name: "알파", dept_id: null, dept_path: [], can_create_ticket: true };

function apiOk(candidates = MANY_CANDIDATES) {
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/tickets/projects") return Promise.resolve({ projects: [PROJECT] });
    if (path === "/api/tickets/meta") return Promise.resolve({ statuses: ["계획"], priorities: [], difficulties: [] });
    if (path.startsWith("/api/tickets/assignees")) return Promise.resolve({ assignees: candidates });
    if (path === "/api/tickets" && opts && opts.method === "POST") return Promise.resolve({ id: "t-9" });
    return Promise.resolve({});
  });
}

/** 프로젝트를 고른 상태로 만든다 — 담당자 칸은 그 뒤에야 나타난다. */
async function pickProject(user) {
  const select = await screen.findByLabelText(/프로젝트/);
  await user.click(select);
  await user.click(await screen.findByRole("option", { name: /알파/ }));
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

describe("새 티켓 — 담당자는 검색 가능한 자동완성이다 (PA-RC-0035)", () => {
  it("후보가 50명이어도 평소엔 옵션 목록이 화면에 없다 — 입력 한 줄만 있다(폼 길이가 인원 수와 무관)", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await pickProject(user);
    // '나'가 기본 선택되므로 그 칩이 뜨는 것으로 로드 완료를 기다린다.
    await screen.findByText("나");
    // 예전 체크박스 그리드였다면 50개 행이 전부 그려졌을 것이다 — 지금은 옵션 role 자체가
    // (열기 전엔) 문서에 없다.
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    expect(screen.getByRole("combobox", { name: /담당자/ })).toBeInTheDocument();
  });

  it("로드되면 '나'가 기본 담당자로 칩에 나타난다(기존 자동 선택 동작 보존)", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await pickProject(user);
    expect(await screen.findByText("나")).toBeInTheDocument();
  });

  it("프로젝트를 고르기 전에는 담당자 칸이 후보를 묻지 않는다 (0060 §14)", async () => {
    renderNewTicket();
    await screen.findByLabelText(/프로젝트/);
    // 전체 명부를 먼저 보여 줬다가 프로젝트를 고르는 순간 절반이 사라지면, 사용자는 방금
    // 고른 사람이 왜 없어졌는지 알 수 없다 — 그래서 아예 묻지 않는다.
    expect(apiMock.mock.calls.some(([p]) => String(p).startsWith("/api/tickets/assignees"))).toBe(false);
    expect(screen.getByText(/프로젝트를 먼저 고르세요/)).toBeInTheDocument();
  });

  it("이름으로 검색하면 일치하는 사람만 옵션에 뜬다", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await pickProject(user);
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
    await pickProject(user);
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
    await pickProject(user);
    await screen.findByText("나");

    const chip = screen.getByText("나").closest(".MuiChip-root");
    await user.click(within(chip).getByTestId("CancelIcon"));

    await waitFor(() => expect(screen.queryByText("나")).not.toBeInTheDocument());
  });

  it("키보드만으로 검색·선택·해제할 수 있다", async () => {
    const user = userEvent.setup();
    renderNewTicket();
    await pickProject(user);
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
    await pickProject(user);
    await screen.findByText("나");

    await user.type(screen.getByLabelText(/^제목( 필수)?$/), "담당자 배정 확인");
    /* 예상 WD 와 마감일도 필수다 (지시 10) — 이 시험이 재는 것은 담당자 축이지만,
       필수를 안 채우면 제출 자체가 막혀 아무것도 못 잰다. */
    await user.type(screen.getByLabelText(/예상 WD/), "1");
    await fillDateField(user, /마감일/, "2026-09-30");

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

describe("새 티켓 — 설명은 문서와 같은 편집기다", () => {
  it("편집기가 자기 이름을 들고, 서식 안내는 항상 보이는 캡션에 있다", async () => {
    renderNewTicket();
    /* `contenteditable` 은 `<label htmlFor>` 의 대상이 될 수 없다 — 편집기가 `aria-label`
       로 자기 이름을 든다. 이름으로 고를 수 있다는 것 자체가 스크린리더로 찾을 수 있다는 뜻이다. */
    expect(await screen.findByRole("textbox", { name: "설명" })).toBeInTheDocument();
    expect(screen.getByText(/문서와 같은 도구로 서식, 목록, 표, 링크, 이모지를 넣을 수 있습니다/)).toBeInTheDocument();
    /* 미리보기 판은 **새로 쓰는 자리에 없다** — 편집기가 이미 결과를 그대로 보여 준다(WYSIWYG).
       마크다운 편집기이던 시절에는 「무엇을 쳤나」와 「어떻게 보이나」가 달라서 필요했다. */
    expect(screen.queryByText("미리보기")).toBeNull();
  });

  it("서식 도구가 문서 편집기와 같은 묶음으로 선다", async () => {
    renderNewTicket();
    // 아이콘 툴바다 — 글자 칩 열한 개가 아니다. 묶음 이름은 `ui/BlockEditor.jsx::TOOL_GROUPS`.
    expect(await screen.findByRole("toolbar", { name: "설명 서식" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "굵게" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "표" })).toBeInTheDocument();
  });
});
