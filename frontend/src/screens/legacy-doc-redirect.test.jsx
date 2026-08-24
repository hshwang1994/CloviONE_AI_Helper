import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";

/* 옛 문서 주소가 계속 열린다 (S14 · C2).
 *
 * 문서 화면 둘을 하나로 합치면서 `/team-docs/:pageId` 를 없애면, 알림 딥링크와 감사 로그와
 * 사람들이 걸어 둔 북마크가 한꺼번에 죽는다. 사용자에게 그것은 「문서가 사라졌다」로 보인다.
 *
 * 그래서 이 화면이 서버에 다리를 하나 물어보고 새 주소로 넘긴다. 여기서 고정하는 것 셋:
 *
 *   1. 옛 page id 로 찾은 문서의 **새 주소**로 간다.
 *   2. 뒤로가기가 이 중간 화면으로 돌아오지 않는다(`replace`).
 *   3. 못 찾으면 **왜 못 찾았는지 말한다** — 조용히 목록으로 보내면 사용자는 자기가 잘못
 *      눌렀다고 생각하고 같은 링크를 다시 누른다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { LegacyDocRedirect } from "./LegacyDocRedirect.jsx";
import { ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const OLD_PAGE_ID = "2f3a-old-page";

function Where() {
  const loc = useLocation();
  const nav = useNavigate();
  return (
    <>
      <div data-testid="where">{loc.pathname}</div>
      {/* MemoryRouter 는 브라우저 이력이 아니라 자기 이력을 쓴다 — 뒤로가기를 재려면
          그 이력 위에서 한 걸음 물러나야 한다. */}
      <button onClick={() => nav(-1)}>뒤로</button>
    </>
  );
}

function renderAt(entries = [`/team-docs/${OLD_PAGE_ID}`]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider>
        <MemoryRouter initialEntries={entries}>
          <Where />
          <Routes>
            <Route path="/team-docs/:pageId" element={<LegacyDocRedirect />} />
            <Route path="/knowledge" element={<div>문서 목록</div>} />
            <Route path="/knowledge/:id" element={<div>문서 상세</div>} />
          </Routes>
        </MemoryRouter>
      </ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("옛 문서 주소", () => {
  it("옛 page id 를 서버에 물어보고 그 문서의 새 주소로 넘긴다", async () => {
    apiMock.mockResolvedValue({ id: "doc-uuid-1", title: "우리팀 설계서" });
    renderAt();

    expect(await screen.findByText("문서 상세")).toBeTruthy();
    expect(screen.getByTestId("where").textContent).toBe("/knowledge/doc-uuid-1");
    expect(apiMock.mock.calls[0][0]).toBe(
      "/api/knowledge/documents/by-legacy/" + encodeURIComponent(OLD_PAGE_ID));
  });

  it("뒤로가기가 이 중간 화면으로 돌아오지 않는다", async () => {
    apiMock.mockResolvedValue({ id: "doc-uuid-1", title: "우리팀 설계서" });
    renderAt(["/knowledge", `/team-docs/${OLD_PAGE_ID}`]);
    await screen.findByText("문서 상세");

    screen.getByRole("button", { name: "뒤로" }).click();
    // `replace` 라 옛 주소가 이력에서 지워졌다 — 한 걸음 뒤는 그 앞 화면이다.
    await screen.findByText("문서 목록");
    expect(screen.getByTestId("where").textContent).toBe("/knowledge");
  });

  it("못 찾으면 왜 못 찾았는지 말하고 목록으로 갈 길을 준다", async () => {
    const err = new Error("요청한 항목을 찾을 수 없습니다.");
    err.status = 404;
    apiMock.mockRejectedValue(err);
    renderAt();

    expect(await screen.findByText("옛 주소가 가리키는 문서를 찾지 못했습니다.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "문서 목록 열기" }).getAttribute("href"))
      .toBe("#/knowledge");
    // 조용히 넘어가지 않는다 — 주소는 그대로 있어야 사용자가 무엇을 눌렀는지 안다.
    expect(screen.getByTestId("where").textContent).toBe(`/team-docs/${OLD_PAGE_ID}`);
  });
});
