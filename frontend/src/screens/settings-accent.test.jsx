import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* '화면 강조색' 선택기 — PA-RC-0022로 관리자 전용 「설정」 화면에서 떼어 냈다. S19 가 그
 * 자리를 「내 프로필」 안으로 합쳤다(설정 하나짜리 `/my-display` 가 사이드바 항목도 없이
 * 따로 서 있었다). AccentPicker.jsx 자신은 옮기지 않았고 동작도 안 바꿨다 — 렌더하는
 * 자리만 바뀐다. 지키는 요구는 그대로다 — 시스템 정책 표에 못 닿는 역할도 개인 취향인
 * 강조색은 바꿀 수 있어야 한다(acceptance_criteria 5, "모든 역할이 자기 개인 설정에
 * 접근할 수 있다").
 *
 * 계약이 두 가지다:
 *   1) 강조색은 **개인 설정**이다 — 테마(밝게/어둡게)와 같이 localStorage에만 저장되고 서버로
 *      나가지 않는다. 서버 설정으로 만들면 한 사람의 취향이 전원 화면을 바꿔 버린다.
 *   2) 선택 표시를 색만으로 하지 않는다(WCAG 1.4.1) — aria-pressed와 한국어 이름이 함께 있어야
 *      색각 이상 사용자와 스크린리더가 무엇이 선택됐는지 알 수 있다. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { AccentPicker } from "./settings/AccentPicker.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { ACCENT_PRESETS, DEFAULT_ACCENT } from "../ui/theme.js";

beforeEach(() => {
  window.localStorage.clear();
  apiMock.mockReset();
  apiMock.mockResolvedValue({});
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <MemoryRouter>
          <AccentPicker />
        </MemoryRouter>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const group = () => screen.getByRole("group", { name: "화면 강조색" });

describe("화면 강조색 선택기 (내 프로필, PA-RC-0022)", () => {
  it("역할과 무관하게 이 자리에 닿는다 — 서버 role 조회 없이 렌더된다", () => {
    renderScreen();
    expect(group()).toBeInTheDocument();
    // 서버로는 아무 요청도 나가지 않는다 — 브라우저 로컬 값만으로 완결된다.
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("프리셋을 전부 보여주고 현재 색만 눌린 상태로 표시한다", async () => {
    renderScreen();
    const buttons = within(group()).getAllByRole("button");
    expect(buttons).toHaveLength(ACCENT_PRESETS.length);
    // 색 이름이 글자로도 있어야 한다(색만으로 구분하지 않는다).
    expect(within(group()).getByText("브랜드 인디고")).toBeInTheDocument();
    expect(within(group()).getByText("보라")).toBeInTheDocument();
    const pressed = buttons.filter((b) => b.getAttribute("aria-pressed") === "true");
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toHaveTextContent("브랜드 인디고"); // 저장된 값이 없으면 기본 색
    expect(DEFAULT_ACCENT).toBe(ACCENT_PRESETS[0]);
  });

  it("다른 색을 고르면 선택 표시가 옮겨가고 이 브라우저에만 저장된다(서버 저장 없음)", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(within(group()).getByRole("button", { name: /보라/ }));

    const buttons = within(group()).getAllByRole("button");
    const pressed = buttons.filter((b) => b.getAttribute("aria-pressed") === "true");
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toHaveTextContent("보라");
    expect(window.localStorage.getItem("clovirassist_accent")).toBe("#6B5BC7");
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("이전에 고른 색이 있으면 그 색이 선택된 채로 열린다", async () => {
    window.localStorage.setItem("clovirassist_accent", "#327C98");
    renderScreen();
    const pressed = within(group()).getAllByRole("button").filter((b) => b.getAttribute("aria-pressed") === "true");
    expect(pressed).toHaveLength(1);
    expect(pressed[0]).toHaveTextContent("청록");
  });
});
