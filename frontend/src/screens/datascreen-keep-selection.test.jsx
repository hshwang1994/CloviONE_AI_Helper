import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* `keepSelection` 이 넣은 **방금 만든 행**은 지금 조건에 없어도 닫지 않는다 (ai-03).
 *
 * 상세 드로어는 「지금 조건의 결과에 없는 sel」을 닫는다. 그 규칙 자체는 옳다 — 다른
 * 관리자가 지운 행을 계속 붙들고 있으면 안 된다. 문제는 그 판정이 **방금 내가 만든 행**과
 * **남이 지운 행**을 구별하지 못했다는 것이다: 「봤던 행인가」 표식이 참/거짓 하나뿐이라,
 * 발행본을 보다가 「새 버전」을 누르면 앞 행에서 세워 둔 참이 그대로 남아 새 초안이 «사라진
 * 행» 으로 읽혔다. 기본 상태 필터가 '발행됨'인 화면에서 초안은 구조적으로 목록에 없으므로,
 * 초안→테스트→검토→발행 흐름이 첫 걸음에서 끊겼다(실브라우저 실측: 드로어가 닫히고 방금
 * 만든 v2 초안은 목록에도 드로어에도 없다).
 *
 * 반례를 함께 고정한다 — **내가 본 적 있는 행**이 목록에서 사라지면 드로어는 그대로 닫힌다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const PUBLISHED = { id: "p1", name: "티켓 요약", status: "published", version: 1 };
const NEW_DRAFT = { id: "p2", name: "티켓 요약 v2 초안", status: "draft", version: 2 };

const CONFIG = {
  key: "prompts", area: "AI", title: "프롬프트", endpoint: "/api/admin/prompts",
  columns: [{ key: "name", label: "이름", identifier: true }, { key: "status", label: "상태" }],
  filters: [{
    key: "status", label: "상태", type: "select", value: "published",
    options: [{ value: "draft", label: "초안" }, { value: "published", label: "발행됨" }],
  }],
  actions: [
    // 응답이 새 항목을 주면 드로어를 그 항목으로 갱신한다 — 곧바로 '수정'을 누를 수 있게.
    { label: "새 버전", keepSelection: true, path: (r) => "/api/admin/prompts/" + r.id + "/new-version" },
    // 같은 행을 그대로 돌려주는 액션. 그 사이 목록에서 사라지면(다른 관리자가 지웠다) 닫혀야 한다.
    { label: "다시 읽기", keepSelection: true, path: (r) => "/api/admin/prompts/" + r.id + "/reload" },
  ],
};

let listRows;

beforeEach(() => {
  apiMock.mockReset();
  listRows = [PUBLISHED];
  apiMock.mockImplementation((path, opts) => {
    const url = String(path);
    if (opts && opts.method === "POST" && url.endsWith("/new-version")) {
      return Promise.resolve({ item: NEW_DRAFT });
    }
    if (opts && opts.method === "POST" && url.endsWith("/reload")) {
      listRows = [];                       // 그 사이 다른 관리자가 지웠다
      return Promise.resolve({ item: PUBLISHED });
    }
    return Promise.resolve({ items: listRows, total: listRows.length });
  });
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <DataScreen config={CONFIG} />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("기본 필터가 걸린 화면의 keepSelection (ai-03)", () => {
  it("새 버전을 만들면 드로어가 그 초안으로 갱신되고 열려 있다 — 목록에 없어도 닫지 않는다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("티켓 요약");

    await user.click(screen.getByText("티켓 요약"));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "새 버전" }));

    // 방금 만든 초안이 드로어에 그대로 있다(목록은 여전히 발행본만 보여 준다).
    await waitFor(() => expect(within(screen.getByRole("dialog")).getAllByText("티켓 요약 v2 초안").length).toBeGreaterThan(0));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // 목록이 다시 도착한 뒤에도 닫히지 않는다 — 예전 결함이 나던 자리가 바로 그 refetch 다.
    await waitFor(() => expect(apiMock.mock.calls.filter((c) => String(c[0]).startsWith("/api/admin/prompts?")).length).toBeGreaterThan(1));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(screen.getByRole("dialog")).getAllByText("티켓 요약 v2 초안").length).toBeGreaterThan(0);
    // 목록은 그대로 발행본만 — 새 초안은 조건 밖이라 목록에 없다(그래서 예전에 닫혔다).
    expect(within(document.querySelector("table")).queryByText("티켓 요약 v2 초안")).toBeNull();
  });

  it("반례 — 목록에서 실제로 보던 행이 사라지면 드로어는 닫힌다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("티켓 요약");

    await user.click(screen.getByText("티켓 요약"));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "다시 읽기" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});
