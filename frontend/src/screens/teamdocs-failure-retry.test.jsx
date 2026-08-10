/* `/team-docs`가 500·abort에서 몇 초씩 "영원히 로딩 중"처럼 보이던 버그 (FAIL-03).
 *
 * react-query 기본값(retry:3, 지수 백오프)이면 실패가 isError로 뜨기까지 ~7초 걸린다 —
 * 이 화면의 목록/필터 쿼리만 retry를 명시적으로 안 껐다(다른 화면은 전부 껐다). 여기서는
 * 실패를 계속 흉내 내 api()가 몇 번 불리는지 세는 것으로 "재시도를 안 한다"를 직접 증명한다
 * (타이머를 흉내 내 실제로 몇 초씩 기다리지 않는다).
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/api.js", () => ({ api: vi.fn() }));
import { api } from "../lib/api.js";
import { TeamDocs } from "./TeamDocs.jsx";

function renderScreen() {
  // 실제 프런트가 쓰는 QueryClient 기본값(frontend/src/main.jsx)을 그대로 따른다 —
  // retry는 여기서 끄지 않는다. 이 테스트가 잡으려는 버그가 정확히 "TeamDocs 자신이
  // retry:false를 안 걸어서 react-query 기본 재시도(3회)를 그대로 물려받는 것"이므로,
  // 테스트 하네스가 대신 retry:false를 깔아 버리면 이 버그를 절대 못 잡는다.
  const qc = new QueryClient({
    defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30 * 1000 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><TeamDocs /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  api.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("/team-docs 목록 실패 시 재시도 없이 바로 오류 상태로 전환된다", () => {
  it("목록 쿼리가 재시도 없이 한 번만 불리고 오류 화면으로 전환된다", async () => {
    let listCalls = 0;
    api.mockImplementation((path) => {
      if (path.startsWith("/api/team-docs/filters")) {
        return Promise.resolve({ doc_types: [], work_fields: [], tech_tags: [], projects: [] });
      }
      listCalls += 1;
      return Promise.reject(Object.assign(new Error("서버에서 문제가 생겼습니다."), { status: 500 }));
    });

    renderScreen();

    // 오류 화면("불러오지 못했습니다")이 뜨는 것 자체가 isError로의 전환을 증명한다.
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByText("불러오지 못했습니다")).toBeTruthy();
    // 스켈레톤에 계속 머물지 않았다는 것도 함께 확인.
    expect(screen.queryByText("불러오는 중…")).toBeNull();

    // retry:false가 실제로 걸려 있으면 실패가 정착될 때까지도 목록 쿼리는 딱 1번만 불린다 —
    // 기본값(retry:3)이었다면 여기서 4(최초 1 + 재시도 3)에 도달했을 것이다.
    expect(listCalls).toBe(1);
  });
});
