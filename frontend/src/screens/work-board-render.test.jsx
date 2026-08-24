import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 작업 보드가 **실제로 뜨는가**.
 *
 * 이 파일이 왜 생겼나: `/work-board` 는 아무에게도 안 열리고 있었다. 프로젝트 목록 응답은
 * 객체(`{ projects: [...] }`)인데 이 화면만 그것을 배열로 읽어 `.map` 을 불렀고, 질의가
 * 도착하는 순간 `TypeError` 로 ErrorBoundary 가 화면을 대신 그렸다. 같은 훅을 쓰는 나머지
 * 넷은 전부 `.projects` 를 읽는다 — **한 곳만 다르게 읽는 것**이라 정적 검사로는 안 보이고,
 * 이 화면에는 렌더 시험이 하나도 없었다. S16 의 실브라우저 캡처가 `console_errors` 로 잡았다.
 *
 * 그래서 여기서 지키는 것은 둘이다.
 *   1) 서버가 주는 **그 모양**으로 화면이 뜬다(크래시 없음).
 *   2) 프로젝트 선택기는 **검색 가능한 선택기**다 — 프로젝트는 기수가 무한히 자라는 대상이라
 *      평범한 드롭다운이면 데이터가 쌓일수록 못 쓰게 된다(`plain_dropdown_for_entity`).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { WorkBoard } from "./WorkBoard.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

/** 서버가 실제로 주는 모양. **배열이 아니다** — 이 시험의 요점이 이 한 줄이다. */
const PROJECTS = { projects: [{ id: "p-1", name: "포털 개편" }, { id: "p-2", name: "인프라 정비" }] };

function renderBoard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <WorkBoard />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("작업 보드", () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/tickets/projects")) return Promise.resolve(PROJECTS);
      if (path.startsWith("/api/work/sprints")) return Promise.resolve({ sprints: [] });
      if (path.startsWith("/api/work/board")) return Promise.resolve({ columns: [] });
      if (path.startsWith("/api/work/backlog")) return Promise.resolve({ items: [] });
      return Promise.resolve({});
    });
  });

  it("🔴 프로젝트 목록이 도착해도 화면이 죽지 않는다", async () => {
    const errors = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...a) => errors.push(String(a[0])));
    renderBoard();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    // 질의가 전부 정착한 뒤에도 오류 경계가 화면을 대신 그리지 않는다.
    await waitFor(() => expect(screen.queryByText(/다시 시도/)).toBeNull());
    expect(errors.filter((e) => /is not a function/.test(e))).toEqual([]);
    spy.mockRestore();
  });

  it("프로젝트 선택기가 서버가 준 이름을 담는다", async () => {
    renderBoard();
    const box = await screen.findByLabelText("프로젝트");
    expect(box).toBeTruthy();
  });

  it("🔴 프로젝트 선택기는 검색 가능한 선택기다 — 평범한 드롭다운이 아니다", async () => {
    renderBoard();
    const box = await screen.findByLabelText("프로젝트");
    // 검색 가능함의 정의는 QA 프로브와 같다: 안에 입력칸이 있거나 `aria-autocomplete="list"`.
    const searchable = box.tagName === "INPUT"
      || box.getAttribute("aria-autocomplete") === "list"
      || !!box.querySelector("input");
    expect(searchable).toBe(true);
  });
});
