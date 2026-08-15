import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* 회귀: SystemOps.jsx가 useToast()를 잘못된 모양으로 불렀다.
 *
 * kit.jsx의 useToast()는 ToastCtx.Provider가 value로 넘기는 push 함수 하나를 그대로 준다
 * (`const ToastCtx = React.createContext(() => {}); ... <ToastCtx.Provider value={push}>`),
 * 즉 `toast(message, kind)` 두 인자 호출이 유일한 계약이다 — 이 앱의 다른 모든 화면
 * (Users.jsx, Offboarding.jsx, ops/Maintenance.jsx 등)이 전부 이 모양으로 호출한다.
 *
 * SystemOps.jsx만 `toast.error(...)`/`toast[result.ok ? "success" : "error"](...)`처럼
 * toast를 {success, error} 메서드를 가진 객체인 것처럼 호출했다 — push는 일반 함수라
 * `.success`/`.error` 속성이 없으므로 `undefined(...)`를 호출하는 셈이 되어 mutation의
 * onSuccess/onError 콜백이 매번 TypeError로 죽는다. 그 결과 토스트가 전혀 뜨지 않고,
 * 서비스 재시작·타임존 변경 등 이 화면의 모든 쓰기 동작이 결과를 사용자에게 알리지 못한다.
 *
 * 이 테스트는 수정 전엔 토스트 문구를 못 찾아 FAIL, 수정 후엔 PASS 해야 한다.
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
  // GET(초기 조회)과 POST(mutation) 모두 같은 목(mock)을 쓴다 — 실제 mutation 응답의
  // 세부 필드(ok 등)와 무관하게, "토스트가 뜨는가" 자체가 이 테스트의 관심사다.
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

describe("시스템 설정 — 작업 결과 토스트", () => {
  it("서비스 재시작 결과를 토스트로 보여준다", async () => {
    const user = userEvent.setup();
    renderScreen();

    const restartBtn = await screen.findByRole("button", { name: "재시작" });
    await user.click(restartBtn);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "확인" }));

    // STATE에는 result.ok가 없으므로 onSuccess는 "error" 분기(outcomeText가 반환하는
    // "적용하지 못했습니다. 잠시 후 다시 시도해 주세요.")를 토스트로 띄워야 한다. toast.error(...)가
    // 실제로는 undefined 호출이라 죽는 버그가 있으면 이 문구는 결코 화면에 나타나지 않는다.
    expect(await screen.findByText("적용하지 못했습니다. 잠시 후 다시 시도해 주세요.")).toBeInTheDocument();
  });
});
