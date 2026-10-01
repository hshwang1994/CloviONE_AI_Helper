import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 프롬프트 화면 — 기능마다 한 줄, 행을 열면 그 기능의 서랍 (계획 A4, D-541).
 *
 * qa-contract-replaced-by: frontend/src/screens/prompt-usage-deeplink-status-filter.test.jsx
 *
 * 옛 시험은 「사용 통계의 딥링크가 그 지시문을 열고 목록을 상태로 좁히지 않는다」를 쟀다. 사용 통계 탭은 이 목록이 됐고(D-541), 딥링크는
 * 그대로 산다: `?id=` 가 기능 키 · `builtin:<기능>` · 그 기능의 버전 id 어느 것이든 서버가 기능으로 풀어 그 서랍을 연다. 목록은 조건이
 * 없다(기능 다섯 줄). 새로 지키는 것:
 *   1) 행에는 기능 · 지금 쓰는 지시문 · 기능 상태 · 초안 · 최근 30일 요청 · 실패율 · 마지막 사용이 선다. 0 회의 까닭은 기능 상태 칸이 말한다.
 *   2) 서랍은 지금 지시문 · 초안 · 고정 틀(역할 · 출력 형식 · 안전 규칙)을 읽기로 보이고, 「수정」은 그 기능의 초안을 PATCH 로 고친다.
 *   3) 초안이 있으면 「초안 발행」이 서랍의 동작이다(확인을 받는 동작이라 「작업 더 보기」에 선다).
 *   4) 기능 다섯 줄이 한 화면에 다 서므로 검색 칸이 없다(`searchable: false`).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "actor-1", admin_scope: "global" } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { REGISTRY } from "./registry.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const ROW = {
  id: "draft", slot: "draft", label: "문서 초안", description: "작업 공간에서 문서 초안을 쓸 때 씁니다.",
  feature_state: "off", feature_state_label: "꺼짐", feature_note: "AI 사용이 꺼져 있어 이 기능이 답을 만들지 않습니다.",
  current: { source: "builtin", label: "기본 제공", instruction: "아래 사내 문서 발췌만 근거로 초안을 써 주세요." },
  draft: { id: "p-9", version: 3, label: "v3 초안", content: "고친 초안 지시문입니다." },
  content: "고친 초안 지시문입니다.",
  frame: { role: "당신은 초안을 쓰는 도우미입니다.", format_line: "제목 없이 본문만 씁니다.", grounding: "발췌만 근거로 씁니다." },
  calls_30d: 0, errors_30d: 0, failure_rate: null, last_used_at: null,
};

function route() {
  apiMock.mockImplementation((path, opts) => {
    const p = String(path);
    const method = (opts && opts.method) || "GET";
    if (p.startsWith("/api/me/views")) return Promise.resolve({ items: [] });
    if (p === "/api/admin/prompts/features" && method === "GET") return Promise.resolve({ items: [ROW], total: 1, days: 30 });
    if (p.startsWith("/api/admin/prompts/features/") && method === "GET") return Promise.resolve({ item: ROW });
    if (p === "/api/admin/prompts/features/draft" && method === "PATCH") {
      return Promise.resolve({ item: { ...ROW, draft: { ...ROW.draft, content: opts.body.content }, content: opts.body.content } });
    }
    return Promise.resolve({});
  });
}

function renderPrompts() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={REGISTRY.prompts} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => { apiMock.mockReset(); route(); });
afterEach(() => { window.location.hash = ""; });

describe("프롬프트 화면 — 기능마다 한 줄", () => {
  it("행이 지금 지시문 · 기능 상태 · 초안을 말하고 목록은 조건 없이 읽는다", async () => {
    window.location.hash = "#/prompts";
    renderPrompts();
    expect(await screen.findByText("문서 초안")).toBeInTheDocument();
    expect(screen.getByText("기본 제공")).toBeInTheDocument();
    expect(screen.getByText("꺼짐")).toBeInTheDocument();
    expect(screen.getByText("v3 초안")).toBeInTheDocument();
    const lists = apiMock.mock.calls.map((c) => String(c[0])).filter((p) => p.startsWith("/api/admin/prompts/features"));
    expect(lists.every((p) => !p.includes("status="))).toBe(true);
    // 기능 다섯 줄이 한 화면에 다 선다 — 찾을 것이 없는 검색 칸은 서지 않는다.
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  it("옛 딥링크(?id=builtin:…)는 그 기능의 서랍을 연다", async () => {
    window.location.hash = "#/prompts?id=" + encodeURIComponent("builtin:draft");
    renderPrompts();
    await waitFor(() => expect(apiMock.mock.calls.some(([p]) => p === "/api/admin/prompts/features/builtin%3Adraft"
      || p === "/api/admin/prompts/features/builtin:draft")).toBe(true));
    expect(await screen.findByText("고친 초안 지시문입니다.")).toBeInTheDocument();
    expect(screen.getByText("당신은 초안을 쓰는 도우미입니다.")).toBeInTheDocument();
    expect(screen.getByText("AI 사용이 꺼져 있어 이 기능이 답을 만들지 않습니다.")).toBeInTheDocument();
  });

  it("수정은 그 기능의 초안을 PATCH 로 고친다", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/prompts?id=draft";
    renderPrompts();
    await screen.findByText("고친 초안 지시문입니다.");
    // 「초안 발행」은 확인을 받는 동작이라 셸 규칙대로 「작업 더 보기」 메뉴에 선다(DataScreen 의 액션 위계).
    await user.click(screen.getByRole("button", { name: "프롬프트 작업 더 보기" }));
    expect(await screen.findByRole("menuitem", { name: "초안 발행" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "수정" }));
    const box = await screen.findByLabelText(/지시문/);
    await user.clear(box);
    await user.type(box, "새 지시문입니다.");
    const dialog = screen.getAllByRole("dialog").at(-1);
    await user.click(within(dialog).getByRole("button", { name: /저장/ }));
    await waitFor(() => {
      const sent = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/prompts/features/draft" && o && o.method === "PATCH");
      expect(sent && sent[1].body).toEqual({ content: "새 지시문입니다." });
    });
  });
});
