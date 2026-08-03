import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 설정 화면의 '화면 강조색' 선택기.
 *
 * 계약이 두 가지다:
 *   1) 강조색은 **개인 설정**이다 — 테마(밝게/어둡게)와 같이 localStorage에만 저장되고 서버로
 *      나가지 않는다. 서버 설정으로 만들면 한 사람의 취향이 전원 화면을 바꿔 버린다. 이 테스트는
 *      색을 바꾼 뒤 /api/admin/settings 로 쓰기 요청이 한 건도 나가지 않았음을 확인한다.
 *   2) 선택 표시를 색만으로 하지 않는다(WCAG 1.4.1) — aria-pressed와 한국어 이름이 함께 있어야
 *      색각 이상 사용자와 스크린리더가 무엇이 선택됐는지 알 수 있다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin" } }),
}));

import { Settings } from "./Settings.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { ACCENT_PRESETS, DEFAULT_ACCENT } from "../ui/theme.js";

const PAYLOAD = {
  settings: {
    conversation_retention_days: { value: 90, type: "int", description: "대화 보존", restart_required: false, is_default: true },
  },
};

beforeEach(() => {
  window.localStorage.clear();
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) return Promise.resolve(PAYLOAD);
    return Promise.resolve({});
  });
});

function renderSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <MemoryRouter>
          <Settings />
        </MemoryRouter>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const group = () => screen.getByRole("group", { name: "화면 강조색" });

describe("화면 강조색 선택기", () => {
  it("프리셋을 전부 보여주고 현재 색만 눌린 상태로 표시한다", async () => {
    renderSettings();
    const buttons = within(group()).getAllByRole("button");
    expect(buttons).toHaveLength(ACCENT_PRESETS.length);
    // 색 이름이 글자로도 있어야 한다(색만으로 구분하지 않는다).
    expect(within(group()).getByText("기본 파랑")).toBeInTheDocument();
    expect(within(group()).getByText("보라")).toBeInTheDocument();
    const pressed = buttons.filter((b) => b.getAttribute("aria-pressed") === "true");
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toHaveTextContent("기본 파랑"); // 저장된 값이 없으면 기본 색
    expect(DEFAULT_ACCENT).toBe(ACCENT_PRESETS[0]);
  });

  it("다른 색을 고르면 선택 표시가 옮겨가고 이 브라우저에만 저장된다(서버 저장 없음)", async () => {
    const user = userEvent.setup();
    renderSettings();
    await user.click(within(group()).getByRole("button", { name: /보라/ }));

    const buttons = within(group()).getAllByRole("button");
    const pressed = buttons.filter((b) => b.getAttribute("aria-pressed") === "true");
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toHaveTextContent("보라");
    expect(window.localStorage.getItem("clovirone_accent")).toBe("#6B5BC7");

    // 서버로는 아무것도 쓰지 않는다 — GET 조회만 있었어야 한다.
    const writes = apiMock.mock.calls.filter(([, opts]) => opts && opts.method && opts.method !== "GET");
    expect(writes).toEqual([]);
  });

  it("이전에 고른 색이 있으면 그 색이 선택된 채로 열린다", async () => {
    window.localStorage.setItem("clovirone_accent", "#327C98");
    renderSettings();
    const pressed = within(group()).getAllByRole("button").filter((b) => b.getAttribute("aria-pressed") === "true");
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toHaveTextContent("청록");
  });
});
