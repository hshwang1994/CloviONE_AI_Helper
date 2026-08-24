/* 목록 주소가 **이미 질의를 달고 있어도** 조건이 서버에 그대로 닿는다 (S15 · C7).
 *
 * 알림 화면은 대상(audience)을 주소에 박고 있다(`/api/notifications?audience=user`).
 * 예전 조립은 거기에 `?` 를 한 번 더 붙여서 이런 주소를 만들었다:
 *
 *     /api/notifications?audience=user?page=1&page_size=20
 *
 * 질의는 첫 `?` 뒤 전부이므로 서버가 읽은 값은 `audience="user?page=1"` 이었고 `page` 는
 * 아예 도착하지 않았다. 그리고 서버는 모르는 audience 를 «전체 보기» 로 떨어뜨린다 —
 * 즉 **사용자 알림 화면이 관리 알림까지 보여 주고, 「다음」을 눌러도 같은 20건이 온다.**
 * 둘 다 오류를 안 내므로 화면만 봐서는 정상이다.
 *
 * 그래서 여기서 보는 것은 「주소 문자열이 예쁜가」가 아니라 **서버가 실제로 받는 값**이다 —
 * 나간 주소를 `URLSearchParams` 로 파싱해 파라미터 단위로 확인한다.
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
import { withQuery } from "./datascreen-view.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const CONFIG = {
  key: "noti-probe",
  title: "알림",
  endpoint: "/api/notifications?audience=user",
  paginated: true,
  filters: [{ key: "unread_only", type: "select", label: "읽음 상태", options: [{ value: "true", label: "안 읽음만" }] }],
  columns: [{ key: "title", label: "제목" }],
  detailFields: [],
};

const ITEMS = Array.from({ length: 20 }, (_, i) => ({ id: `n${i}`, title: `알림 ${i}` }));

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter><DataScreen config={CONFIG} /></MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/** 목록을 부른 주소들만 뽑아 파라미터로 편다. */
function listCalls() {
  return apiMock.mock.calls
    .map(([path]) => String(path))
    .filter((p) => p.startsWith("/api/notifications"))
    .map((p) => new URLSearchParams(p.slice(p.indexOf("?") + 1)));
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ items: ITEMS, page: 1, page_size: 20, total: 60, unread: 3 });
});

describe("질의를 이미 달고 있는 목록 주소", () => {
  it("주소에 박힌 조건과 화면이 더한 조건이 **둘 다** 파라미터로 도착한다", async () => {
    renderScreen();
    await screen.findByText("알림 0");

    const params = listCalls();
    expect(params.length).toBeGreaterThan(0);
    const first = params[0];
    // 예전에는 이 값이 "user?page=1" 이었고, 서버는 그것을 모르는 값으로 보고 조건을 버렸다.
    expect(first.get("audience")).toBe("user");
    expect(first.get("page")).toBe("1");
  });

  it("「다음」을 누르면 page 가 실제로 2가 된다 — 같은 목록을 다시 받지 않는다", async () => {
    renderScreen();
    await screen.findByText("알림 0");
    apiMock.mockClear();

    // 화면 위아래 두 자리에 같은 페이저가 있다 — 위쪽 하나를 누른다.
    fireEvent.click(screen.getAllByRole("button", { name: "다음" })[0]);

    await waitFor(() => {
      const pages = listCalls().map((p) => p.get("page"));
      expect(pages).toContain("2");
    });
    // 그리고 쪽을 넘겨도 대상은 그대로다 — 넘기다가 남의 알림이 섞이면 안 된다.
    expect(listCalls().every((p) => p.get("audience") === "user")).toBe(true);
  });

  it("필터를 고르면 그 값도 자기 파라미터로 나간다", async () => {
    renderScreen();
    await screen.findByText("알림 0");
    apiMock.mockClear();

    fireEvent.mouseDown(screen.getByLabelText("읽음 상태"));
    fireEvent.click(await screen.findByRole("option", { name: "안 읽음만" }));

    await waitFor(() => {
      const hit = listCalls().find((p) => p.get("unread_only") === "true");
      expect(hit).toBeTruthy();
      expect(hit.get("audience")).toBe("user");
    });
  });
});

describe("붙이는 규칙 자체 (withQuery)", () => {
  it("맨 경로에는 `?`, 이미 질의가 있으면 `&` 로 잇는다", () => {
    expect(withQuery("/api/x", ["a=1", "b=2"])).toBe("/api/x?a=1&b=2");
    expect(withQuery("/api/x?k=v", ["a=1"])).toBe("/api/x?k=v&a=1");
  });

  it("붙일 것이 없으면 주소를 그대로 둔다", () => {
    expect(withQuery("/api/x?k=v", [])).toBe("/api/x?k=v");
    expect(withQuery("/api/x", [])).toBe("/api/x");
  });
});
