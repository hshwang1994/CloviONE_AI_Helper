import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { forgetPresets, presetRange } from "../ui/period.js";

/* 보기 기준과 「기간」 칸 (F4 · D-530).
 *
 * AI 사용 통계의 「묶음」은 조건이 아니라 표를 어떻게 묶어 볼지 고르는 축인데, 예전에는 필터로 다뤄 「묶음: 기능(기본값)」이 조건
 * 1개로 세어졌고 자료가 없는 화면이 「검색 결과가 없습니다」였다. 기간은 날짜 칸 둘이 아니라 칸 하나 · 칩 하나다. 합성 설정을
 * DataScreen 에 직접 꽂아 공용 셸의 분기를 잰다 — 같은 선언을 쓰는 화면 전부가 같은 계약을 받는다. */

const CONFIG = {
  key: "probe-usage", title: "사용 통계(검사)", endpoint: "/api/admin/probe/usage", smallSet: true,
  emptyTitle: "아직 기록이 없습니다",
  filters: [
    { key: "group_by", type: "select", role: "view", label: "보기 기준", value: "action",
      options: [{ value: "action", label: "기능" }, { value: "user", label: "사용자" }] },
    { key: "status", type: "select", label: "결과", options: [{ value: "ok", label: "성공" }, { value: "error", label: "실패" }] },
    { key: "from", endKey: "to", type: "period", label: "기간", presets: ["today", "7d", "30d"], emptyPreset: "30d" },
  ],
  columns: [{ key: "label", label: "묶음", type: "name" }],
  detailFields: [],
};

function renderScreen(config = CONFIG) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter><DataScreen config={config} /></MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const lastUrl = () => String(apiMock.mock.calls[apiMock.mock.calls.length - 1][0]);

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
});
afterEach(() => forgetPresets());

describe("보기 기준은 조건이 아니다", () => {
  it("기본 보기 기준만 걸린 0건은 「자료 없음」이다 — 조건 줄도 「검색 조건에 맞는 항목이 없습니다」도 없다", async () => {
    apiMock.mockResolvedValue({ items: [] });
    const { container } = renderScreen();
    expect(await screen.findByText("아직 기록이 없습니다")).toBeInTheDocument();
    expect(lastUrl()).toContain("group_by=action");
    expect(screen.queryByText("검색 조건에 맞는 항목이 없습니다.")).toBeNull();
    expect(container.querySelector("[data-condition-line]")).toBeNull();
    expect(screen.queryByRole("button", { name: "필터 초기화" })).toBeNull();
  });

  it("보기 기준 칸은 필터 줄 오른쪽 끝 묶음에 서고 「전체」가 없다", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "a", label: "채팅" }] });
    const user = userEvent.setup();
    const { container } = renderScreen();
    await screen.findByText("채팅");
    const view = screen.getByRole("combobox", { name: "보기 기준" });
    const row = container.querySelector("[data-filter-row]");
    // 오른쪽 끝 묶음(ToolbarEnd)은 줄의 마지막 자식이다 — 조건 칸들과 같은 흐름에 서지 않는다.
    expect(row.lastElementChild.contains(view)).toBe(true);
    await user.click(view);
    const options = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(options).toEqual(["기능", "사용자"]);
    await user.click(screen.getByRole("option", { name: "사용자" }));
    await waitFor(() => expect(lastUrl()).toContain("group_by=user"));
    // 보기 기준을 바꿔도 조건이 생기지 않는다 — 칩이 없다.
    expect(container.querySelector("[data-condition-chip]")).toBeNull();
  });

  it("필터 초기화는 조건만 지우고 보기 기준은 남긴다", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "a", label: "채팅" }] });
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("채팅");
    await user.click(screen.getByRole("combobox", { name: "보기 기준" }));
    await user.click(await screen.findByRole("option", { name: "사용자" }));
    await user.click(screen.getByRole("combobox", { name: "결과" }));
    await user.click(await screen.findByRole("option", { name: "성공" }));
    await waitFor(() => expect(lastUrl()).toContain("status=ok"));
    await user.click(screen.getByRole("button", { name: "필터 초기화" }));
    await waitFor(() => expect(lastUrl()).not.toContain("status="));
    expect(lastUrl()).toContain("group_by=user");
  });
});

describe("기간 칸 하나 · 칩 하나 · 키 둘", () => {
  it("빈 기간은 서버 기본값의 이름이다", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "a", label: "채팅" }] });
    const { container } = renderScreen();
    await screen.findByText("채팅");
    const cell = container.querySelector('[data-filter-kind="period"]');
    expect(cell.querySelector("[data-row-value]")).toHaveTextContent("최근 30일");
    expect(lastUrl()).not.toContain("from=");
    // 날짜 칸 둘(라벨 위 + 36)이 필터 줄에 서지 않는다.
    expect(container.querySelector('[data-filter-row] [data-filter-kind="date"]')).toBeNull();
  });

  it("프리셋을 고르면 두 키가 서버로 가고 칩은 하나이며, 칩을 지우면 두 키가 함께 빠진다", async () => {
    apiMock.mockResolvedValue({ items: [{ id: "a", label: "채팅" }] });
    const user = userEvent.setup();
    const { container } = renderScreen();
    await screen.findByText("채팅");
    await user.click(screen.getByRole("combobox", { name: "기간" }));
    await user.click(within(await screen.findByRole("dialog", { name: "기간 고르기" })).getByRole("menuitemradio", { name: "최근 7일" }));
    const want = presetRange("7d", { now: new Date() });
    await waitFor(() => expect(lastUrl()).toContain(`from=${want.from}`));
    expect(lastUrl()).toContain(`to=${want.to}`);
    const chips = container.querySelectorAll("[data-condition-chip]");
    expect(chips).toHaveLength(1);
    expect(chips[0]).toHaveTextContent("기간: 최근 7일");
    // 칩의 지우기 표지를 누르면 두 키가 함께 빠진다 — 반쪽 기간이 남지 않는다.
    await user.click(chips[0].querySelector(".MuiChip-deleteIcon"));
    await waitFor(() => expect(lastUrl()).not.toContain("from="));
    expect(lastUrl()).not.toContain("to=");
  });

  it("주소에 실린 키 쌍을 그대로 복원한다(저장된 뷰 · 공유 링크)", async () => {
    window.location.hash = "#/probe?from=2026-09-02&to=2026-09-03";
    apiMock.mockResolvedValue({ items: [{ id: "a", label: "채팅" }] });
    const { container } = renderScreen();
    await screen.findByText("채팅");
    expect(lastUrl()).toContain("from=2026-09-02");
    expect(lastUrl()).toContain("to=2026-09-03");
    expect(container.querySelector('[data-filter-kind="period"] [data-row-value]')).toHaveTextContent("9월 2일 ~ 9월 3일");
  });
});
