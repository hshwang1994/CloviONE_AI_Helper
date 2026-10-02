import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* 내 프로필 · 메일 알림 카드 (계획 M4, D-550).
 *
 * 지키는 것:
 *   1) 받는 주소의 상태 낱말은 셋이다 — 계정 이메일 · 확인 중 · 확인됨.
 *   2) 「다른 주소로 받기」 → 주소 입력 → 「확인 코드 보내기」 → 코드 입력 → 「확인」. 코드를 다시 받으려면 서버가 정한 시각까지 기다린다.
 *   3) 받을 알림은 한 줄에 하나씩 스위치이고 누르는 즉시 저장된다(받을 유형 전체가 한 번에 간다).
 *   4) 메일 발송이 지연되면 한 문장만 말하고, 관리자가 메일 발송을 쓰지 않으면 스위치가 꺼지고 까닭을 한 줄로 말한다.
 *   5) 카드 글에 메일 서버의 기술 낱말(SMTP · 포트 · TLS · Postfix · DKIM)이 없다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { MailNotificationCard, PREFS_KEY } from "./MailNotificationCard.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const ACCOUNT = "me@goodmit.co.kr";
function mailBlock(patch = {}) {
  return {
    enabled: true,
    types: ["ticket_assigned"],
    catalog: [
      { key: "ticket_assigned", label: "티켓 배정", help: "누군가 나를 담당자로 지정했을 때" },
      { key: "ticket_resolved", label: "요청한 티켓 결과", help: "끝났을 때" },
    ],
    address: { account_email: ACCOUNT, effective: ACCOUNT, custom: null, pending: null, allowed_domains: [] },
    delivery: { state: "ok", message: null },
    ...patch,
  };
}

function Harness({ initial, save = () => {} }) {
  const qc = React.useMemo(() => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(PREFS_KEY, { mail: initial });
    return client;
  }, [initial]);
  const [mail, setMail] = React.useState(initial);
  React.useEffect(() => qc.getQueryCache().subscribe(() => {
    const data = qc.getQueryData(PREFS_KEY);
    if (data && data.mail) setMail(data.mail);
  }), [qc]);
  return (
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MailNotificationCard mail={mail} save={save} />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => { apiMock.mockReset(); });

describe("메일 알림 카드", () => {
  it("계정 이메일 · 확인 중 · 확인됨 세 상태를 말한다", () => {
    const { unmount } = render(<Harness initial={mailBlock()} />);
    expect(screen.getByTestId("mail-address-state")).toHaveTextContent("계정 이메일");
    unmount();
    const pending = { email: "other@goodmit.co.kr", sent_at: new Date().toISOString(), expires_at: null,
      resend_after: new Date(Date.now() + 30_000).toISOString() };
    const r2 = render(<Harness initial={mailBlock({ address: { ...mailBlock().address, pending } })} />);
    expect(screen.getByTestId("mail-address-state")).toHaveTextContent("확인 중");
    expect(screen.getByRole("button", { name: /코드 다시 받기\(\d+초 뒤\)/ })).toBeDisabled();
    r2.unmount();
    const custom = { email: "other@goodmit.co.kr", verified_at: "2026-10-01T00:00:00", active: true, inactive_reason: null };
    render(<Harness initial={mailBlock({ address: { ...mailBlock().address, custom, effective: custom.email } })} />);
    expect(screen.getByTestId("mail-address-state")).toHaveTextContent("확인됨");
    expect(screen.getByTestId("mail-address-value")).toHaveTextContent("other@goodmit.co.kr");
  });

  it("다른 주소로 받기 → 코드 보내기 → 코드 확인", async () => {
    const user = userEvent.setup();
    const pending = { email: "other@goodmit.co.kr", sent_at: new Date().toISOString(), expires_at: null,
      resend_after: new Date(Date.now() - 1000).toISOString() };
    const custom = { email: "other@goodmit.co.kr", verified_at: "2026-10-01T00:00:00", active: true, inactive_reason: null };
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/me/notify-email" && opts.method === "POST") {
        return Promise.resolve({ mail: mailBlock({ address: { ...mailBlock().address, pending } }) });
      }
      if (path === "/api/me/notify-email/verify") {
        return Promise.resolve({ mail: mailBlock({ address: { ...mailBlock().address, custom, effective: custom.email } }) });
      }
      return Promise.resolve({});
    });
    render(<Harness initial={mailBlock()} />);
    await user.click(screen.getByRole("button", { name: "다른 주소로 받기" }));
    await user.type(screen.getByLabelText("알림 받을 이메일"), "other@goodmit.co.kr");
    await user.click(screen.getByRole("button", { name: "확인 코드 보내기" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/me/notify-email", { method: "POST", body: { email: "other@goodmit.co.kr" } }));
    const codeBox = await screen.findByLabelText("확인 코드");
    expect(screen.getByRole("button", { name: "확인" })).toBeDisabled();
    await user.type(codeBox, "123456");
    await user.click(screen.getByRole("button", { name: "확인" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/me/notify-email/verify", { method: "POST", body: { code: "123456" } }));
    expect(await screen.findByText("알림 받을 주소를 확인했습니다.")).toBeInTheDocument();
    expect(screen.getByTestId("mail-address-state")).toHaveTextContent("확인됨");
  });

  it("받을 알림 스위치는 받을 유형 전체를 한 번에 저장한다", async () => {
    const user = userEvent.setup();
    const save = vi.fn();
    render(<Harness initial={mailBlock()} save={save} />);
    await user.click(screen.getByRole("switch", { name: "요청한 티켓 결과 메일로 받기" }));
    expect(save).toHaveBeenCalledWith({ mail_types: ["ticket_assigned", "ticket_resolved"] });
  });

  it("지연이면 한 문장만, 꺼진 설치면 스위치가 꺼지고 까닭을 말한다", () => {
    const { unmount } = render(<Harness initial={mailBlock({ delivery: { state: "delayed", message: "현재 메일 알림 발송이 지연되고 있습니다." } })} />);
    expect(screen.getByText("현재 메일 알림 발송이 지연되고 있습니다.")).toBeInTheDocument();
    unmount();
    render(<Harness initial={mailBlock({ enabled: false, delivery: { state: "off", message: "관리자가 메일 발송을 켜면 메일 알림을 받을 수 있습니다." } })} />);
    expect(screen.getByRole("switch", { name: "메일 알림 받기" })).toBeDisabled();
    expect(screen.getByText("관리자가 메일 발송을 켜면 메일 알림을 받을 수 있습니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다른 주소로 받기" })).toBeDisabled();
  });

  it("카드 글에 메일 서버의 기술 낱말이 없다", () => {
    render(<Harness initial={mailBlock()} />);
    const text = screen.getByTestId("mail-notification-card").textContent;
    for (const word of ["SMTP", "포트", "TLS", "Postfix", "DKIM", "OpenDKIM"]) {
      expect(text.includes(word), word).toBe(false);
    }
    expect(within(screen.getByTestId("mail-notification-card")).getByRole("heading", { name: "메일 알림" })).toBeInTheDocument();
  });
});
