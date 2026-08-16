import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* VIS-55 — '설명' 열의 첫 문장이 바로 왼쪽 '항목명' 열과 글자 그대로 같은 항목이 여럿이다
 * (예: "대화 보존 기간(일)" / "대화 보존 기간(일). 초과 시…") — 라벨을 표 한 줄 안에서
 * 두 번 반복해 가로 공간을 먹었다. 라벨과 겹치는 접두부만 벗겨내고 실제 추가 정보만 보여준다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin" } }) }));

import { Settings } from "./Settings.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const PAYLOAD = {
  settings: {
    // 실제 백엔드 문구(app/settings/registry.py) 그대로 — 라벨과 마침표로 겹친다.
    conversation_retention_days: {
      value: 90, type: "int",
      description: "대화 보존 기간(일). 초과 시 백그라운드 작업이 자동 삭제",
      restart_required: false, is_default: true,
    },
    // 콜론(:)으로 겹치는 계열(비밀번호/세션/잠금 정책류)도 같은 방식으로 벗겨져야 한다.
    password_policy: {
      value: { min_length: 8 }, type: "object",
      description: "비밀번호 정책: 최소 길이·복잡도 규칙을 정합니다",
      restart_required: false, is_default: true,
    },
    // 라벨과 안 겹치는 설명은 그대로 보여야 한다(잘못 벗겨내지 않는다). 실제 라벨은
    // "문서 자동화"(settingsRegistry.js)라 이 설명과 안 겹친다.
    document_automation_enabled: {
      value: true, type: "bool",
      description: "새 티켓이 들어오면 관련 문서를 자동으로 만듭니다",
      restart_required: false, is_default: true,
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

describe("설정 표 — '설명' 열이 '항목명'과 겹치는 접두부를 반복하지 않는다 (VIS-55)", () => {
  it("마침표로 겹치는 설명은 라벨 부분을 벗겨내고 나머지만 보여준다", async () => {
    renderScreen();
    await screen.findByText("대화 보존 기간(일)");
    expect(screen.getByText("초과 시 백그라운드 작업이 자동 삭제")).toBeInTheDocument();
    expect(screen.queryByText("대화 보존 기간(일). 초과 시 백그라운드 작업이 자동 삭제")).not.toBeInTheDocument();
  });

  it("콜론으로 겹치는 설명도 같은 방식으로 벗겨진다", async () => {
    renderScreen();
    await screen.findByText("비밀번호 정책");
    expect(screen.getByText("최소 길이·복잡도 규칙을 정합니다")).toBeInTheDocument();
  });

  it("라벨과 안 겹치는 설명은 원문 그대로 보여준다", async () => {
    renderScreen();
    await screen.findByText("문서 자동화");
    expect(screen.getByText("새 티켓이 들어오면 관련 문서를 자동으로 만듭니다")).toBeInTheDocument();
  });
});
