/* 검색창 타이핑이 **화면 전체를 다시 그리지 않는다** (PF4).
 *
 * `DataScreen` 은 관리자 40화면이 공유하는 1,000줄짜리 컴포넌트다. 타이핑 중인 값이 그
 * 컴포넌트에 살면 **글자 하나마다** 표 100행·필터 일곱 개·상세 드로어가 전부 다시 실행된다.
 *
 * 이 테스트는 "메모를 붙였다" 를 보지 않는다. **행 렌더 함수가 몇 번 불렸는지**를 센다 —
 * 그게 사용자가 겪는 층(입력 지연)에 실제로 대응하는 값이다.
 *
 * 검색어의 모양도 여기서 본다. 확정하는 값은 다듬은 검색어이고(`lib/search.js::normalizeQuery`), 화면이 스스로 거르는
 * 목록은 검색어와 행 값을 서버와 같은 규칙으로 접는다(`includesFolded`) — 공백 · 대소문자 · 전각 표기가 결과를 바꾸지 않는다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

let renderCount = 0;

const CONFIG = {
  key: "probe",
  title: "검사 화면",
  endpoint: "/api/admin/probe",
  searchable: true,
  searchPlaceholder: "이름 검색",
  paginated: true,
  columns: [
    { key: "name", label: "이름", render: (row) => { renderCount += 1; return row.name; } },
  ],
  detailFields: [],
};

const ITEMS = Array.from({ length: 20 }, (_, i) => ({ id: `r${i}`, name: `행 ${i}` }));

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

/** 목록 요청(`endpoint` 로 시작하는 호출)만 모은다 — 다른 부품의 요청이 섞여도 세는 값이 흔들리지 않는다. */
function listCalls(endpoint = CONFIG.endpoint) {
  return apiMock.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith(endpoint));
}

/** 마지막 목록 요청에 실린 검색어. 없으면 null. */
function sentQ() {
  const calls = listCalls();
  const last = calls[calls.length - 1] || "";
  return new URLSearchParams(last.includes("?") ? last.slice(last.indexOf("?") + 1) : "").get("q");
}

beforeEach(() => {
  renderCount = 0;
  // 화면은 검색어를 주소(해시)에 되쓰고 다음 화면이 그것을 읽는다 — 앞 시험의 검색어가 다음 시험의 시작 조건이 되지 않게 비운다.
  window.location.hash = "";
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: ITEMS, page: 1, page_size: 20, total: 20 });
});

describe("관리자 목록 검색", () => {
  it("글자를 쳐도 표가 다시 그려지지 않는다 (디바운스가 끝나기 전까지)", async () => {
    renderScreen();
    await screen.findByText("행 0");

    const before = renderCount;
    const input = screen.getByRole("searchbox", { name: "이름 검색" });
    for (const ch of ["가", "나", "다", "라", "마", "바", "사", "아"]) {
      fireEvent.change(input, { target: { value: input.value + ch } });
    }

    // 여덟 글자를 쳤는데 행 렌더가 한 번도 더 일어나면 안 된다.
    expect(renderCount).toBe(before);
  });

  it("입력한 값은 그대로 보이고, 잠시 뒤 서버 질의로 확정된다", async () => {
    renderScreen();
    await screen.findByText("행 0");
    apiMock.mockClear();

    const input = screen.getByRole("searchbox", { name: "이름 검색" });
    fireEvent.change(input, { target: { value: "회의" } });
    expect(input.value).toBe("회의");   // 타이핑은 즉시 보인다

    await waitFor(
      () => expect(apiMock.mock.calls.some(([path]) => String(path).includes("q=%ED%9A%8C%EC%9D%98")
                                                || String(path).includes("q=회의"))).toBe(true),
      { timeout: 2000 },
    );
  });

  /* 확정하는 값은 검색어의 표시 모양이다(`lib/search.js::normalizeQuery`) — 서버에는 다듬은 값이 가고 입력 상자에는
     친 글자가 그대로 남는다. 끝 공백 하나는 새 조건이 아니라서 요청도 다시 안 나간다. 입력을 다시 쓰면 치는 도중에
     끝 공백이 사라져 다음 낱말이 앞 낱말에 붙는다. */
  it("앞뒤 · 연속 공백은 서버 질의에서 한 칸으로 접히고, 입력 상자는 친 글자 그대로다", async () => {
    renderScreen();
    await screen.findByText("행 0");
    const input = screen.getByRole("searchbox", { name: "이름 검색" });
    fireEvent.change(input, { target: { value: "  회의   록 " } });
    await waitFor(() => expect(sentQ()).toBe("회의 록"), { timeout: 2000 });
    expect(input.value).toBe("  회의   록 ");
  });

  it("끝에 공백 하나를 더 쳐도 새 질의가 아니다 — 요청이 다시 안 나가고 입력도 안 바뀐다", async () => {
    renderScreen();
    await screen.findByText("행 0");
    const input = screen.getByRole("searchbox", { name: "이름 검색" });
    fireEvent.change(input, { target: { value: "회의" } });
    await waitFor(() => expect(sentQ()).toBe("회의"), { timeout: 2000 });
    const before = listCalls().length;

    fireEvent.change(input, { target: { value: "회의 " } });
    // 디바운스보다 넉넉히 기다린다 — 그 사이에 확정이 일어났다면 목록 요청이 하나 더 나갔을 것이다.
    await new Promise((r) => setTimeout(r, 800));
    expect(listCalls().length).toBe(before);
    expect(input.value).toBe("회의 ");

    // 공백 뒤에 낱말을 이어 치면 그때 새 질의다 — 끝 공백이 먹혔다면 「회의록」이 나갔을 것이다.
    fireEvent.change(input, { target: { value: "회의 록" } });
    await waitFor(() => expect(sentQ()).toBe("회의 록"), { timeout: 2000 });
  });
});

/* 화면이 스스로 거르는 목록(서버 검색 없음 · 전량 수신)도 서버 검색과 같은 접기로 본다(`lib/search.js::includesFolded`).
 * 검색어와 행 값을 같은 규칙으로 접으므로 공백 · 대소문자 · 전각 표기가 결과를 바꾸지 않는다. */
const LOCAL = {
  key: "probe-local",
  title: "검사 화면",
  endpoint: "/api/admin/probe-local",
  searchPlaceholder: "이름 검색",
  paginated: false,
  searchFields: ["name", "code"],
  columns: [{ key: "name", label: "이름" }, { key: "code", label: "코드" }],
  detailFields: [],
};
const LOCAL_ITEMS = [
  { id: "a", name: "현황 제외 보고", code: "RPT-1" },
  { id: "b", name: "ClovirONE 전환", code: "CLV-2" },
  { id: "c", name: "회의록 정리", code: "MTG-3" },
];
const NAMES = LOCAL_ITEMS.map((r) => r.name);
const shownNames = () => NAMES.filter((name) => screen.queryAllByText(name).length > 0);

describe("화면이 거르는 목록의 검색", () => {
  it("공백 · 대소문자 · 전각 표기가 달라도 같은 행이 남는다 — 행 값 쪽 공백도 접는다", async () => {
    apiMock.mockResolvedValue({ items: LOCAL_ITEMS });
    renderScreen(LOCAL);
    await screen.findByText("현황 제외 보고");
    const input = screen.getByRole("searchbox", { name: "이름 검색" });

    for (const [typed, want] of [
      ["현황제외", ["현황 제외 보고"]],
      ["  현황   제외 ", ["현황 제외 보고"]],
      ["clovirone", ["ClovirONE 전환"]],
      ["CLOVIRONE", ["ClovirONE 전환"]],
      ["ＣｌｏｖｉｒＯＮＥ", ["ClovirONE 전환"]],
      ["mtg-3", ["회의록 정리"]],
    ]) {
      fireEvent.change(input, { target: { value: typed } });
      await waitFor(() => expect(shownNames(), typed).toEqual(want), { timeout: 2000 });
    }
  });

  it("필드를 이어 붙여 찾지 않는다 — 이름 끝과 코드를 붙인 글자는 안 걸린다", async () => {
    apiMock.mockResolvedValue({ items: LOCAL_ITEMS });
    renderScreen(LOCAL);
    await screen.findByText("현황 제외 보고");
    fireEvent.change(screen.getByRole("searchbox", { name: "이름 검색" }), { target: { value: "보고rpt" } });
    await waitFor(() => expect(shownNames()).toEqual([]), { timeout: 2000 });
  });
});
