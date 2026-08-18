import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* FN-01 + 지시 35 · 36 · 40: 메일 발송 화면.
 *
 * app/mail/router.py는 진단(GET /status)·시험 발송(POST /test)을 처음부터 완성해 뒀는데
 * 그걸 띄우는 화면이 없었다 — 실서버 확인 결과 SMTP 설정 오류가 한국어로 이미 나와 있었지만
 * 아무도 볼 방법이 없었고, 그동안 비밀번호 재설정 메일이 조용히 안 갔다. 여기서 지키는 것:
 *   1) 진단 문제 목록이 실제로 화면에 뜬다(숨기지 않는다).
 *   2) "시험 메일 보내기"가 확인 후 실제로 POST /api/admin/mail/test를 부른다.
 *   3) 쓰기 role이 아니면(operator/auditor) 시험 발송 버튼이 안 보인다 — 읽기는 되지만
 *      CONSOLE_WRITE_ROLES 밖의 역할로 쓰기를 시도할 길을 화면에서부터 안 열어 둔다.
 *   4) **내부 키·예외 원문·ISO 원문이 화면의 주된 내용이 되지 않는다**(지시 36) — 서버가 준
 *      이름을 쓰고 원문은 `기술 정보`로 접힌다. 지우지는 않는다.
 *   5) **같은 원인을 두 번 말하지 않는다**(지시 35 · 44) — 설정 문제로 못 보낸 행은 설정
 *      문제 문장을 다시 늘어놓지 않고 위를 가리킨다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

let authRole = "admin";
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: authRole, email: "me@goodmit.co.kr" } }),
}));

import { MailStatus } from "./MailStatus.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const NOT_CONFIGURED = {
  mail: {
    configured: false,
    problems: [
      "메일 발송이 꺼져 있습니다. 메일 설정에서 발송을 켜세요.",
      "메일 서버 주소가 비어 있습니다.",
      "보내는 사람 주소가 비어 있습니다.",
    ],
    server: { enabled: false, host: "", port: null, security: null, from_address: "", from_name: "", username: "" },
    password_secret: null,
  },
  counts: { queued: 0, sent: 3, failed: 1, unconfigured: 5 },
  recent_failures: [
    {
      id: "d-1", kind: "password_reset", kind_label: "비밀번호 재설정",
      to_email: "user@goodmit.co.kr",
      subject: "비밀번호 재설정 안내", status: "unconfigured", status_label: "발송 불가(설정 없음)",
      attempt_count: 1, error_summary: null, last_error: null,
      created_at: "2026-08-10T00:00:00", sent_at: null,
    },
  ],
};

function withStatus(patch) {
  const body = { ...NOT_CONFIGURED, ...patch };
  apiMock.mockImplementation((path) => {
    if (String(path).startsWith("/api/admin/mail/status")) return Promise.resolve(body);
    return Promise.resolve({});
  });
}

beforeEach(() => {
  authRole = "admin";
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (String(path).startsWith("/api/admin/mail/status")) return Promise.resolve(NOT_CONFIGURED);
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
            <MailStatus />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

describe("메일 발송 화면", () => {
  it("서버가 준 진단 문제를 그대로 보여준다", async () => {
    renderScreen();
    await screen.findByText(/메일 서버 주소가 비어 있습니다/);
    expect(screen.getByText(/메일 발송이 꺼져 있습니다/)).toBeInTheDocument();
    expect(screen.getByText(/보내는 사람 주소가 비어 있습니다/)).toBeInTheDocument();
  });

  it("발송 현황 숫자와 최근 실패 목록을 보여준다", async () => {
    renderScreen();
    await screen.findByText(/메일 서버 주소가 비어 있습니다/);
    const metrics = screen.getByLabelText("발송 현황");
    expect(within(metrics).getByText("발송 실패")).toBeInTheDocument();
    expect(within(metrics).getByText("발송 못 함")).toBeInTheDocument();
    expect(screen.getByText("비밀번호 재설정 안내")).toBeInTheDocument();
  });

  // MAIL-03: "발송 못 함" 건수는 설정을 나중에 고쳐도 저절로 재발송되지 않는다 — 화면이 그
  // 사실을 알려야 관리자가 "고치면 빠지겠지"로 오해하지 않는다. 별도 상자가 아니라 그 숫자의
  // 각주로 둔다(지시 35: 같은 강도의 경고 상자를 늘리지 않는다).
  it("발송 못 함 건수가 있으면 재발송 안 된다는 각주가 그 숫자에 붙는다", async () => {
    renderScreen();
    const note = await screen.findByText(/설정을 고쳐도 이 건들은 다시 보내지 않습니다/);
    const cell = note.closest(".k-readout");
    expect(cell, "각주가 어느 숫자를 한정하는지 알 수 없는 자리에 있다").toBeTruthy();
    expect(within(cell).getByText("발송 못 함")).toBeInTheDocument();
  });

  it("발송 못 함 건수가 0이면 재발송 각주가 안 뜬다", async () => {
    withStatus({ counts: { ...NOT_CONFIGURED.counts, unconfigured: 0 } });
    renderScreen();
    await screen.findByText(/메일 서버 주소가 비어 있습니다/);
    expect(
      screen.queryByText(/설정을 고쳐도 이 건들은 다시 보내지 않습니다/),
    ).not.toBeInTheDocument();
  });

  it("🔴 '시험 메일 보내기'가 확인 후 실제로 POST /api/admin/mail/test를 부른다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText(/메일 서버 주소가 비어 있습니다/);

    apiMock.mockImplementation((path, opt) => {
      if (String(path).startsWith("/api/admin/mail/status")) return Promise.resolve(NOT_CONFIGURED);
      if (String(path) === "/api/admin/mail/test" && opt && opt.method === "POST") {
        return Promise.resolve({
          delivery: { id: "d-2", status: "sent" },
          mail: NOT_CONFIGURED.mail,
        });
      }
      return Promise.resolve({});
    });

    await user.click(screen.getByRole("button", { name: "시험 메일 보내기" }));
    await user.click(await screen.findByRole("button", { name: "시험 발송" }));

    await waitFor(() => {
      const call = apiMock.mock.calls.find(
        ([p, opt]) => p === "/api/admin/mail/test" && opt && opt.method === "POST"
      );
      expect(call).toBeTruthy();
    });
    await screen.findByText(/시험 메일을 보냈습니다/);
  });

  it("쓰기 권한이 없는 역할(operator)에게는 시험 발송 버튼이 안 보인다", async () => {
    authRole = "operator";
    renderScreen();
    await screen.findByText(/메일 서버 주소가 비어 있습니다/);
    expect(screen.queryByRole("button", { name: "시험 메일 보내기" })).toBeNull();
  });

  /* ── 지시 36: 내부 구현이 화면의 주된 내용이 되지 않는다 ────────────────── */

  it("예외 원문은 요약 뒤 '기술 정보'로 접히고, 지워지지는 않는다", async () => {
    const RAW = "SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted')";
    withStatus({
      recent_failures: [{
        ...NOT_CONFIGURED.recent_failures[0],
        id: "d-7", status: "failed", status_label: "발송 실패",
        error_summary: "메일 서버가 로그인을 거부했습니다. 사용자 이름과 비밀번호를 확인하세요.",
        last_error: RAW,
      }],
    });
    renderScreen();
    await screen.findByText(/메일 서버가 로그인을 거부했습니다/);
    // 원문은 있다 — 다만 접힌 자리에 있다.
    const raw = screen.getByText(RAW);
    expect(raw.closest("details")).toBeTruthy();
    expect(screen.getByText("기술 정보")).toBeInTheDocument();
  });

  it("종류 열은 내부 키(backup_failed)가 아니라 서버가 준 이름을 쓴다", async () => {
    withStatus({
      recent_failures: [{
        ...NOT_CONFIGURED.recent_failures[0],
        id: "d-8", kind: "backup_failed", kind_label: "백업 실패 알림",
      }],
    });
    renderScreen();
    await screen.findByText("백업 실패 알림");
    expect(screen.queryByText("backup_failed")).toBeNull();
  });

  it("발생 시각은 ISO 원문이 아니라 압축 표기로 읽힌다", async () => {
    renderScreen();
    await screen.findByText("2026-08-10 09:00");
    expect(screen.queryByText(/2026-08-10T00:00:00/)).toBeNull();
  });

  it("보안 연결 값은 설정 어휘(starttls)가 아니라 이름으로 보인다", async () => {
    withStatus({
      mail: {
        ...NOT_CONFIGURED.mail,
        server: { ...NOT_CONFIGURED.mail.server, enabled: true, host: "smtp.internal", port: 587, security: "starttls" },
      },
    });
    renderScreen();
    const meta = await screen.findByLabelText("메일 서버 설정");
    expect(within(meta).getByText("STARTTLS")).toBeInTheDocument();
    expect(within(meta).queryByText("starttls")).toBeNull();
  });

  it("설정 문제로 못 보낸 행은 설정 문제 문장을 다시 늘어놓지 않는다", async () => {
    const JOINED = "메일 발송이 꺼져 있습니다. 메일 설정에서 발송을 켜세요. / 메일 서버 주소가 비어 있습니다.";
    withStatus({
      recent_failures: [{
        ...NOT_CONFIGURED.recent_failures[0],
        id: "d-9", status: "unconfigured", error_summary: JOINED, last_error: JOINED,
      }],
    });
    renderScreen();
    const row = (await screen.findByText(/발송 설정이 없어 보내지 못했습니다/)).closest("tr");
    expect(row, "원인 열이 표에 없다").toBeTruthy();
    /* 같은 문장이 상단 목록과 표에 나란히 펼쳐져 있으면 강조가 아니라 잡음이다(지시 35 · 44).
       그 시점의 설정 문제 자체는 지우지 않는다 — 지금 설정과 다를 수 있어 사실로서 값이
       있다. 다만 접힌 자리로 내려가 열어 볼 사람만 읽는다. */
    const dup = within(row).queryByText(JOINED);
    if (dup) expect(dup.closest("details"), "설정 문제 문장이 표에 그대로 펼쳐져 있다").toBeTruthy();
  });

  it("비밀번호는 파일 이름이 아니라 등록 여부만 말한다", async () => {
    withStatus({
      mail: {
        ...NOT_CONFIGURED.mail,
        password_secret: "missing",
        server: { ...NOT_CONFIGURED.mail.server, username: "mailer", password_ref: "smtp_password" },
      },
    });
    renderScreen();
    const meta = await screen.findByLabelText("메일 서버 설정");
    expect(within(meta).getByText("등록 안 됨")).toBeInTheDocument();
    expect(within(meta).queryByText(/smtp_password/)).toBeNull();
  });
});
