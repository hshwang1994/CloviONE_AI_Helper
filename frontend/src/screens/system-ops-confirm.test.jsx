import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* 회귀: SystemOps.jsx가 useConfirm()을 잘못된 시그니처로 불렀다.
 *
 * kit.jsx의 useConfirm()은 (message: string, opts: {title, danger, confirmLabel}) 두 인자를
 * 받는다(ConfirmProvider가 message를 그대로 <Typography>에 그리고, opts.title만 대화상자
 * 제목으로 쓴다). SystemOps.jsx는 재시작·인증서 교체 두 확인 대화상자에서 confirm({title, body})
 * 처럼 객체 하나만 넘겼다 — 그러면:
 *   1) opts가 undefined가 되어 title이 항상 기본값 "확인"으로 뭉개지고,
 *   2) message 자리에 들어간 {title, body} 객체를 <Typography>가 그대로 그리려다
 *      "Objects are not valid as a React child"로 렌더가 죽는다.
 * 이 테스트는 수정 전엔 대화상자 제목이 "확인"으로 뭉개지거나 렌더가 던져 FAIL, 수정 후엔
 * 실제 동작을 설명하는 제목이 보여 PASS 해야 한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { SystemOps } from "./SystemOps.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const STATE = {
  available: true,
  info: { hostname: "srv1", timezone: "Asia/Seoul", ntp_synchronized: "yes", units: { "clovirone-web-assistant.service": "active" } },
  actions: [{ name: "cert.install", mutating: true }],
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

describe("시스템 설정 — 서비스 재시작 확인 대화상자", () => {
  it("일반적인 '확인' 대신 무엇을 재시작하는지 제목으로 말한다", async () => {
    const user = userEvent.setup();
    renderScreen();

    const restartBtn = await screen.findByRole("button", { name: "재시작" });
    await user.click(restartBtn);

    const dialog = await screen.findByRole("dialog");
    // 지적 대상: 수정 전에는 opts가 undefined라 title이 기본값 "확인"으로 뭉개진다.
    expect(within(dialog).getByText("웹 서버 를 재시작할까요?")).toBeInTheDocument();
    expect(within(dialog).getByText("재시작하는 동안 그 기능이 잠시 멈춥니다.")).toBeInTheDocument();
  });
});

describe("시스템 설정 — 인증서 교체 확인 대화상자", () => {
  it("같은 시그니처 문제가 인증서 교체 확인에도 있었다", async () => {
    const user = userEvent.setup();
    renderScreen();

    const certBtn = await screen.findByRole("button", { name: "TLS 인증서 교체" });
    await user.click(certBtn);
    const formDialog = await screen.findByRole("dialog");
    await user.type(within(formDialog).getByLabelText(/인증서 \(PEM\)/), "cert");
    await user.type(within(formDialog).getByLabelText(/개인키 \(PEM\)/), "key");
    await user.click(within(formDialog).getByRole("button", { name: "적용" }));

    const confirmDialog = await screen.findByRole("dialog", { name: /인증서를 교체할까요/ });
    expect(within(confirmDialog).getByText(/검사에 실패하면 원래 인증서로 되돌립니다/)).toBeInTheDocument();
  });
});
