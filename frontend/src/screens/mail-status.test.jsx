import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* FN-01: 메일 발송 상태 화면.
 *
 * app/mail/router.py는 진단(GET /status)·시험 발송(POST /test)을 처음부터 완성해 뒀는데
 * 그걸 띄우는 화면이 없었다 — 실서버 확인 결과 SMTP 설정 오류가 한국어로 이미 나와 있었지만
 * 아무도 볼 방법이 없었고, 그동안 비밀번호 재설정 메일이 조용히 안 갔다. 여기서 지키는 것:
 *   1) 진단 문제 목록이 실제로 화면에 뜬다(숨기지 않는다).
 *   2) "시험 메일 보내기"가 확인 후 실제로 POST /api/admin/mail/test를 부른다.
 *   3) 쓰기 role이 아니면(operator/auditor) 시험 발송 버튼이 안 보인다 — 읽기는 되지만
 *      CONSOLE_WRITE_ROLES 밖의 역할로 쓰기를 시도할 길을 화면에서부터 안 열어 둔다.
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
      "메일 발송이 꺼져 있습니다. 설정에서 smtp.enabled 를 켜세요.",
      "SMTP 서버 주소(host)가 비어 있습니다.",
      "보내는 사람 주소(from_address)가 비어 있습니다.",
    ],
    server: { enabled: false, host: "", port: null, security: null, from_address: "", from_name: "" },
    password_secret: null,
  },
  counts: { queued: 0, sent: 3, failed: 1, unconfigured: 5 },
  recent_failures: [
    {
      id: "d-1", kind: "password_reset", to_email: "user@goodmit.co.kr",
      subject: "비밀번호 재설정", status: "unconfigured", status_label: "설정 안 됨",
      attempt_count: 1, last_error: null, created_at: "2026-08-10T00:00:00", sent_at: null,
    },
  ],
};

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

describe("메일 발송 상태 화면", () => {
  it("서버가 준 진단 문제를 그대로 보여준다", async () => {
    renderScreen();
    await screen.findByText(/SMTP 서버 주소\(host\)가 비어 있습니다/);
    expect(screen.getByText(/메일 발송이 꺼져 있습니다/)).toBeInTheDocument();
    expect(screen.getByText(/보내는 사람 주소\(from_address\)가 비어 있습니다/)).toBeInTheDocument();
  });

  it("발송 현황 숫자와 최근 실패 목록을 보여준다", async () => {
    renderScreen();
    await screen.findByText(/SMTP 서버 주소/);
    expect(screen.getByText("실패 1건")).toBeInTheDocument();
    expect(screen.getByText("설정 안 됨(발송 못 함) 5건")).toBeInTheDocument();
    expect(screen.getByText("비밀번호 재설정")).toBeInTheDocument();
  });

  // MAIL-03: "설정 안 됨" 건수는 SMTP를 나중에 고쳐도 저절로 재발송되지 않는다 —
  // 화면이 그 사실을 명시적으로 알려야 관리자가 "고치면 빠지겠지"로 오해하지 않는다.
  it("설정 안 됨 건수가 있으면 재발송 안 된다는 안내가 뜬다", async () => {
    renderScreen();
    await screen.findByText(/SMTP 서버 주소/);
    expect(
      screen.getByText(/SMTP 설정을 고쳐도 자동으로 재발송되지 않습니다/),
    ).toBeInTheDocument();
  });

  it("설정 안 됨 건수가 0이면 재발송 안내가 안 뜬다", async () => {
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/admin/mail/status")) {
        return Promise.resolve({
          ...NOT_CONFIGURED,
          counts: { ...NOT_CONFIGURED.counts, unconfigured: 0 },
        });
      }
      return Promise.resolve({});
    });
    renderScreen();
    await screen.findByText(/SMTP 서버 주소/);
    expect(
      screen.queryByText(/SMTP 설정을 고쳐도 자동으로 재발송되지 않습니다/),
    ).not.toBeInTheDocument();
  });

  it("🔴 '시험 메일 보내기'가 확인 후 실제로 POST /api/admin/mail/test를 부른다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText(/SMTP 서버 주소/);

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
    await screen.findByText(/SMTP 서버 주소/);
    expect(screen.queryByRole("button", { name: "시험 메일 보내기" })).toBeNull();
  });

  // '오류' 열에 값 그대로 보여주는 render(r => r.last_error || "-")가 있으면 DataTable의
  // 기본 말줄임(title 힌트 포함)에서 빠진다 — 표 폭이 긴 오류 문장에 끌려가 옆 '발생' 열이
  // "2026-0..."로 잘렸다. render를 없애 기본 cellValue 경로(말줄임 + title)를 타게 했다.
  it("긴 오류 메시지는 title로 전체를 노출한다(말줄임 경로를 탄다)", async () => {
    const LONG_ERROR = "메일 발송이 꺼져 있습니다. 설정에서 smtp.enabled 를 켜세요. SMTP 서버 주소(host)가 비어 있습니다. 보내는 사람 주소(from_address)가 비어 있습니다.";
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/admin/mail/status")) {
        return Promise.resolve({
          ...NOT_CONFIGURED,
          recent_failures: [
            {
              id: "d-9", kind: "backup_failed", to_email: "admin@goodmit.co.kr",
              subject: "[Clovir] 백업 실패", status: "unconfigured", status_label: "발송 불가(설정 없음)",
              attempt_count: 0, last_error: LONG_ERROR, created_at: "2026-08-15T23:38:00", sent_at: null,
            },
          ],
        });
      }
      return Promise.resolve({});
    });
    renderScreen();
    const cell = await screen.findByText(LONG_ERROR);
    expect(cell.closest("td")).toHaveAttribute("title", LONG_ERROR);
  });
});
