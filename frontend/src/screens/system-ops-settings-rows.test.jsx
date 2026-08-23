import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* 지시 33 — OS와 서비스 화면은 "무엇을 바꿀 수 있는가"만 말하고 "무엇이 설정돼 있는가"는
 * 말하지 않았다. `변경` 카드 안에 기능명 버튼 여섯이 한 줄로 서 있었고, 지금 타임존은
 * 다른 카드에 있었으며, DNS 와 프록시의 현재 값은 어디에도 없었다.
 *
 * 여기서 고정하는 것은 넷이다.
 *   1) 항목마다 **이름 · 지금 값 · 바꾸는 동작**이 한 줄에 있다.
 *   2) 읽을 수 없는 값은 **모른다고 말한다** — 빈칸은 "설정 안 됨"으로 읽힌다.
 *   3) 헬퍼가 모르는 동작은 그리지 않는다(누를 수 있는데 404 나는 버튼을 만들지 않는다).
 *   4) 실행 중인 서비스의 재시작은 앞줄 버튼이 아니다(지시 43 — 서비스 영향 등급).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { SystemOps, certificateText } from "./SystemOps.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const STATE = {
  available: true,
  status: "ok",
  detail: "",
  info: {
    hostname: "srv1",
    timezone: "Asia/Seoul",
    ntp_synchronized: "yes",
    units: { "clovirassist-web.service": "active", "nginx.service": "failed" },
  },
  certificate: { known: true, days_remaining: 41, self_signed: false },
  actions: [
    { name: "system.info", mutating: false },
    { name: "timezone.set", mutating: true },
    { name: "hostname.set", mutating: true },
    { name: "cert.install", mutating: true },
    { name: "service.control", mutating: true },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(() => Promise.resolve(STATE));
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <SystemOps />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/** 그 항목 이름이 들어 있는 줄(설정 한 줄)을 찾는다. */
function rowOf(label) {
  return screen.getByText(label).closest(".k-settingrow");
}

describe("OS와 서비스 — 지금 값과 바꾸는 동작이 한 줄에 있다", () => {
  it("타임존은 현재 값과 수정 버튼이 같은 줄에 있다", async () => {
    renderScreen();
    await screen.findByText("타임존");
    const row = rowOf("타임존");
    expect(within(row).getByText("Asia/Seoul")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "수정" })).toBeInTheDocument();
  });

  it("읽을 수 없는 값은 빈칸이 아니라 '모른다'로 말한다", async () => {
    renderScreen();
    await screen.findByText("DNS 서버");
    const row = rowOf("DNS 서버");
    expect(within(row).getByText("서버에서만 확인할 수 있습니다")).toBeInTheDocument();
  });

  it("인증서는 만료까지 남은 날을 값으로 말한다", async () => {
    renderScreen();
    await screen.findByText("TLS 인증서");
    const row = rowOf("TLS 인증서");
    expect(within(row).getByText("만료까지 41일 남았습니다")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "교체" })).toBeInTheDocument();
  });

  it("헬퍼가 모르는 동작에는 버튼을 그리지 않는다", async () => {
    renderScreen();
    await screen.findByText("아웃바운드 프록시");
    // proxy.set 은 이 설치의 actions 목록에 없다 — 누르면 404 나는 버튼을 만들지 않는다.
    const row = rowOf("아웃바운드 프록시");
    expect(within(row).queryByRole("button")).toBeNull();
    // 반면 목록에 있는 hostname.set 은 버튼이 있다.
    expect(within(rowOf("호스트 이름")).getByRole("button", { name: "수정" })).toBeInTheDocument();
  });
});

describe("OS와 서비스 — 재시작의 무게 (지시 43)", () => {
  it("실행 중인 서비스의 재시작은 앞줄 버튼이 아니다", async () => {
    renderScreen();
    await screen.findByText("웹 서버");
    const row = rowOf("웹 서버");
    expect(within(row).queryByRole("button", { name: "재시작" })).toBeNull();
    expect(within(row).getByRole("button", { name: /더 보기$/ })).toBeInTheDocument();
  });

  it("멈춰 있는 서비스에서는 재시작이 그 줄에서 할 일이므로 앞으로 나온다", async () => {
    renderScreen();
    await screen.findByText("웹 프록시(nginx)");
    const row = rowOf("웹 프록시(nginx)");
    expect(within(row).getByRole("button", { name: "재시작" })).toBeInTheDocument();
  });

  it("넘침 메뉴의 재시작도 실제로 확인을 거쳐 실행된다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("웹 서버");
    await user.click(within(rowOf("웹 서버")).getByRole("button", { name: /더 보기$/ }));
    await user.click(await screen.findByRole("menuitem", { name: "재시작" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("웹 서버를 재시작할까요?")).toBeInTheDocument();
  });
});

describe("certificateText — 값을 모를 때 아는 척하지 않는다", () => {
  it("정보 자체가 없으면 확인하지 못했다고 말한다", () => {
    expect(certificateText(null)).toBe("확인하지 못했습니다");
    expect(certificateText({ known: false })).toBe("확인하지 못했습니다");
  });

  it("만료·자체서명을 각각 말한다", () => {
    expect(certificateText({ known: true, days_remaining: -1 })).toMatch(/이미 만료/);
    expect(certificateText({ known: true, days_remaining: 0 })).toMatch(/오늘 만료/);
    expect(certificateText({ known: true, days_remaining: 7, self_signed: true }))
      .toMatch(/자체 서명/);
  });
});
