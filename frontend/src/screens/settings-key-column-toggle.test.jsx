import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* PA-RC-0022 acceptance_criteria 6: 백엔드 키는 기본 숨김 + 열 토글로 접근한다(완전히
 * 없애지는 않는다 — 운영 디버깅 가치가 있다, constraints가 명시). target_design: 「기본값」
 * 배지 10개를 없애고 「수정됨」만 남긴다 — 안 바뀐 항목은 배지가 아예 없다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin" } }) }));

import { Settings } from "./Settings.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const PAYLOAD = {
  settings: {
    conversation_retention_days: {
      value: 90, type: "int", description: "대화 보존 기간", restart_required: false, is_default: true,
    },
    session_policy: {
      value: { idle_hours: 3 }, type: "object", description: "세션 정책", restart_required: false, is_default: false,
    },
  },
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) return Promise.resolve(PAYLOAD);
    return Promise.resolve({});
  });
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Settings embedded />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("설정 표 — 백엔드 키 열 토글 + 상태 배지 (PA-RC-0022)", () => {
  it("기본은 키 열이 숨겨져 있다", async () => {
    renderScreen();
    await screen.findByText("대화 보존 기간");
    expect(screen.queryByRole("columnheader", { name: "키" })).not.toBeInTheDocument();
    expect(screen.queryByText("conversation_retention_days")).not.toBeInTheDocument();
  });

  it("'기술 정보(설정 키) 보기'를 켜면 키 열과 실제 원시 키가 보인다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("대화 보존 기간");
    await user.click(screen.getByRole("checkbox", { name: "기술 정보(설정 키) 보기" }));
    expect(screen.getByRole("columnheader", { name: "키" })).toBeInTheDocument();
    expect(screen.getByText("conversation_retention_days")).toBeInTheDocument();
  });

  it("기본값 그대로인 항목은 상태 배지가 아예 없고, 수정된 항목만 '수정됨' 배지가 있다", async () => {
    renderScreen();
    await screen.findByText("대화 보존 기간");
    expect(screen.queryByText("기본값")).not.toBeInTheDocument();
    expect(screen.getByText("수정됨")).toBeInTheDocument();
  });

  it("항목명 열 라벨이 '항목명', 값 열 라벨이 '현재 값'이다", async () => {
    renderScreen();
    await screen.findByText("대화 보존 기간");
    expect(screen.getByRole("columnheader", { name: "항목명" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "현재 값" })).toBeInTheDocument();
  });
});
