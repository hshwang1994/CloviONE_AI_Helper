/* 검색 실패를 "결과 없음" 이라고 말하지 않는다 (E9).
 *
 * 예전에는 500 이든 네트워크 끊김이든 전부 "검색 결과 없음" 이었다 — 사용자는 찾는 것이
 * 정말 없다고 믿고 포기한다. 화면이 거짓말하는 부류이고, 이 저장소가 곳곳에서 잡아낸 그것이다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const searchMock = vi.fn();
/* `searchApi` 는 `lib/search.js` 에 있다 — 거기를 모킹해야 한다. 나머지 순수 함수
   (isSearchable/normalizeQuery/routeOf/…)는 실제 구현을 그대로 쓴다. */
vi.mock("../lib/search.js", async (orig) => ({
  ...(await orig()),
  searchApi: (...a) => searchMock(...a),
}));
vi.mock("./auth.jsx", () => ({ useAuth: () => ({ data: { role: "user", id: "u1" } }) }));

import { CommandPalette } from "./CommandPalette.jsx";

function renderPalette() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, throwOnError: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><CommandPalette open onClose={() => {}} /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => searchMock.mockReset());

describe("검색 팔레트", () => {
  it("서버가 실패하면 '결과 없음' 이 아니라 실패라고 말한다", async () => {
    // 빈 질의(마운트 직후)는 정상 응답으로 둔다 — 그때 거부하면 렌더 도중 unhandled 가 되어
    // 테스트가 그 오류로 죽는다(무엇을 재는지 흐려진다).
    searchMock.mockImplementation((q) =>
      q ? Promise.reject(Object.assign(new Error("요청 실패 (500)"), { status: 500 }))
        : Promise.resolve({ groups: [] }));
    renderPalette();

    const input = screen.getByRole("textbox") || screen.getByRole("searchbox");
    fireEvent.change(input, { target: { value: "회의록" } });

    await waitFor(
      () => expect(screen.getByText(/검색하지 못했습니다/)).toBeTruthy(),
      { timeout: 3000 },
    );
    expect(screen.queryByText("검색 결과 없음")).toBeNull();
  });

  it("정말 없을 때는 그대로 '결과 없음' 이다 — 실패로 뭉개지도 않는다", async () => {
    searchMock.mockResolvedValue({ groups: [] });
    renderPalette();

    const input = screen.getByRole("textbox") || screen.getByRole("searchbox");
    fireEvent.change(input, { target: { value: "없는것" } });

    await waitFor(
      () => expect(screen.getByText("검색 결과 없음")).toBeTruthy(),
      { timeout: 3000 },
    );
  });
});
