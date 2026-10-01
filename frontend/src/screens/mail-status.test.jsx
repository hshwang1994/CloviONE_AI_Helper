import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* qa-contract-change: 메일 화면의 상태 탭 끝에 「메일로 보내는 알림」 구획이 섰다(계획 3.4, D-514) — 허용 목록 스위치와 오래된 메일 기준을 저장하는 단언과, 쓰기 역할이 아니면 바꿀 수 없다는 반례를 더했다.
 */
/* qa-contract-change: 메일 화면이 탭 그릇(상태 · 발송 기록)이 됐고 설정 완성 문장이 건강 상태(미설정 · 확인 전 · 정상 · 발송 실패, 계획 3.3 · D-512)로 바뀌었다 — 「설정이 완성돼 있습니다」를 기다리던 단언을 건강 문장으로, 「다시 보내지 않습니다」 각주를 「저절로 다시 보내지 않고 연결 확인 뒤 보낼 수 있다」로 옮기고, 연결 확인 · 쌓인 메일 보내기 단언을 더했다.
 */
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
 *
 * qa-contract-change: 발송 현황 판독 줄(MetricStrip)이 상태 요약 카드(StatusSummaryCard)로 바뀌었다(계획 B-6, 표 7) — 각주 자리를 판독 칸에서 카드의 정의 목록으로 옮긴다.
 * 0건 상태는 한 칩으로 접히므로 이름을 정규식으로 찾고, 각주가 발송 현황 카드 안에 있다는 단언을 더한다.
 *
 * qa-contract-change: 설정 문제가 남아 있으면 「시험 메일 보내기」는 이유와 함께 꺼진다(D-501) — 그 상태의 시험 발송은 서버가 「발송 못 함」 한 줄로
 * 끝내므로 성공할 수 없는 일이었다. 그래서 실제 POST 를 재는 시험은 설정이 완성된 상태(`CONFIGURED`)에서 같은 단언을 하고, 꺼짐 · 이유 연결 ·
 * 「메일 설정 열기」 · 빈 속성 줄 숨김 · 0통 상태의 문장을 재는 시험을 더한다.
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
  health: { state: "unconfigured", label: "미설정", message: "메일 발송이 꺼져 있습니다." },
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

/* 설정이 완성되고 연결이 확인된 설치 — 문제 목록이 비어 있고 시험 발송이 성공할 수 있다. */
const CONFIGURED = {
  ...NOT_CONFIGURED,
  health: { state: "ok", label: "정상", message: "메일 서버에 정상으로 연결했습니다.", checked_at: "2026-09-30T01:00:00" },
  mail: {
    configured: true,
    problems: [],
    server: { enabled: true, host: "smtp.internal", port: 587, security: "starttls", from_address: "portal@goodmit.co.kr", from_name: "", username: "" },
    password_secret: null,
  },
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
            <MemoryRouter initialEntries={["/mail"]}>
              <MailStatus />
            </MemoryRouter>
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
    // 0건인 상태는 「발송 실패, 발송 대기 0건」처럼 한 칩으로 접힌다 — 이름이 그 칩에 남는다.
    expect(within(metrics).getAllByText(/발송 실패/).length).toBeGreaterThan(0);
    expect(within(metrics).getAllByText(/발송 못 함/).length).toBeGreaterThan(0);
    expect(screen.getByText("비밀번호 재설정 안내")).toBeInTheDocument();
  });

  // MAIL-03: "발송 못 함" 건수는 설정을 나중에 고쳐도 저절로 재발송되지 않는다 — 화면이 그
  // 사실을 알려야 관리자가 "고치면 빠지겠지"로 오해하지 않는다. 별도 상자가 아니라 그 숫자의
  // 각주로 둔다(지시 35: 같은 강도의 경고 상자를 늘리지 않는다).
  it("발송 못 함 건수가 있으면 재발송 안 된다는 각주가 그 숫자에 붙는다", async () => {
    renderScreen();
    const note = await screen.findByText(/설정을 고쳐도 저절로 다시 보내지 않습니다/);
    // 정의 목록의 한 항목 — 이름(dt)과 각주(dd)가 한 짝이다.
    const cell = note.closest("[data-summary-notes] > *");
    expect(cell, "각주가 어느 숫자를 한정하는지 알 수 없는 자리에 있다").toBeTruthy();
    expect(within(cell).getByText("발송 못 함")).toBeInTheDocument();
    expect(screen.getByLabelText("발송 현황").contains(note), "각주가 발송 현황 카드 밖에 떨어져 있다").toBe(true);
  });

  it("발송 못 함 건수가 0이면 재발송 각주가 안 뜬다", async () => {
    withStatus({ counts: { ...NOT_CONFIGURED.counts, unconfigured: 0 } });
    renderScreen();
    await screen.findByText(/메일 서버 주소가 비어 있습니다/);
    expect(
      screen.queryByText(/설정을 고쳐도 저절로 다시 보내지 않습니다/),
    ).not.toBeInTheDocument();
  });

  it("🔴 '시험 메일 보내기'가 확인 후 실제로 POST /api/admin/mail/test를 부른다", async () => {
    const user = userEvent.setup();
    withStatus(CONFIGURED);
    renderScreen();
    await screen.findByText(/메일 서버에 정상으로 연결했습니다/);

    apiMock.mockImplementation((path, opt) => {
      if (String(path).startsWith("/api/admin/mail/status")) return Promise.resolve(CONFIGURED);
      if (String(path) === "/api/admin/mail/test" && opt && opt.method === "POST") {
        return Promise.resolve({
          delivery: { id: "d-2", status: "sent" },
          mail: CONFIGURED.mail,
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

  /* 계획 3.3 — 서버는 시험 메일을 큐에 넣고(`queued`) 돌아온다. 예전 화면은 그 응답을 실패로 읽어 성공한 시험
     메일도 「보내지 못했습니다」였다. 이제 한 통의 상세를 끝날 때까지 읽는다. */
  function sendTestWith(detailReply) {
    apiMock.mockImplementation((path, opt) => {
      if (String(path).startsWith("/api/admin/mail/status")) return Promise.resolve(CONFIGURED);
      if (String(path) === "/api/admin/mail/test" && opt && opt.method === "POST") {
        return Promise.resolve({ delivery: { id: "d-3", status: "queued" }, mail: CONFIGURED.mail });
      }
      if (String(path) === "/api/admin/mail/deliveries/d-3") return Promise.resolve({ delivery: detailReply });
      return Promise.resolve({});
    });
  }

  it("🔴 대기 중으로 돌아온 시험 메일을 실패로 읽지 않고, 보내진 뒤에 성공을 말한다", async () => {
    const user = userEvent.setup();
    withStatus(CONFIGURED);
    renderScreen();
    await screen.findByText(/메일 서버에 정상으로 연결했습니다/);
    sendTestWith({ id: "d-3", status: "sent", error_summary: null });

    await user.click(screen.getByRole("button", { name: "시험 메일 보내기" }));
    await user.click(await screen.findByRole("button", { name: "시험 발송" }));

    await screen.findByText(/시험 메일을 보냈습니다/);
    expect(screen.queryByText(/시험 메일을 보내지 못했습니다/)).toBeNull();
    expect(apiMock.mock.calls.some(([p]) => p === "/api/admin/mail/deliveries/d-3")).toBe(true);
  });

  it("보내지 못했으면 서버가 고른 까닭 한 문장을 함께 말한다", async () => {
    const user = userEvent.setup();
    withStatus(CONFIGURED);
    renderScreen();
    await screen.findByText(/메일 서버에 정상으로 연결했습니다/);
    sendTestWith({ id: "d-3", status: "failed", error_summary: "메일 서버가 로그인을 거부했습니다. 사용자 이름과 비밀번호를 확인하세요." });

    await user.click(screen.getByRole("button", { name: "시험 메일 보내기" }));
    await user.click(await screen.findByRole("button", { name: "시험 발송" }));

    expect(await screen.findByText(/시험 메일을 보내지 못했습니다\. 메일 서버가 로그인을 거부했습니다/)).toBeInTheDocument();
    expect(screen.queryByText(/시험 메일을 보냈습니다/)).toBeNull();
  });

  it("다시 보내는 중인 메일이 발송 현황에 따로 선다", async () => {
    withStatus({ counts: { queued: 0, retrying: 2, sent: 3, failed: 1, unconfigured: 0 } });
    renderScreen();
    const metrics = await screen.findByLabelText("발송 현황");
    expect(within(metrics).getAllByText(/다시 보내는 중/).length).toBeGreaterThan(0);
  });

  it("쓰기 권한이 없는 역할(operator)에게는 시험 발송 버튼이 안 보인다", async () => {
    authRole = "operator";
    renderScreen();
    await screen.findByText(/메일 서버 주소가 비어 있습니다/);
    expect(screen.queryByRole("button", { name: "시험 메일 보내기" })).toBeNull();
    // 설정을 고칠 수 없는 역할에게는 설정을 여는 단추도 없다(서버가 설정 쓰기를 같은 역할로 막는다).
    expect(screen.queryByRole("link", { name: "메일 설정 열기" })).toBeNull();
  });

  /* ── D-501: 성공할 수 없는 주 동작을 세우지 않는다 ─────────────────────────────── */

  it("설정 문제가 남아 있으면 시험 메일은 꺼져 있고, 꺼진 이유(문제 목록)를 가리킨다", async () => {
    renderScreen();
    await screen.findByText(/메일 서버 주소가 비어 있습니다/);
    const send = screen.getByRole("button", { name: "시험 메일 보내기" });
    expect(send).toBeDisabled();
    const reasonId = send.getAttribute("aria-describedby");
    expect(reasonId, "꺼진 단추가 이유를 가리키지 않는다").toBeTruthy();
    const reason = document.getElementById(reasonId);
    expect(reason).toHaveTextContent(/메일 서버 주소가 비어 있습니다/);
    expect(reason).toHaveTextContent(/시험 메일도 보낼 수 없습니다/);
  });

  it("반례: 설정이 완성돼 있으면 시험 메일이 켜져 있고 이유 연결도 없다", async () => {
    withStatus(CONFIGURED);
    renderScreen();
    await screen.findByText(/메일 서버에 정상으로 연결했습니다/);
    const send = screen.getByRole("button", { name: "시험 메일 보내기" });
    expect(send).toBeEnabled();
    expect(send).not.toHaveAttribute("aria-describedby");
  });

  it("문제 목록 상자가 「메일 설정 열기」로 설정 표의 메일 한 줄을 연다", async () => {
    renderScreen();
    await screen.findByText(/메일 서버 주소가 비어 있습니다/);
    const open = screen.getByRole("link", { name: "메일 설정 열기" });
    expect(open.getAttribute("href")).toBe("#/settings?setting=smtp");
    expect(open.closest(".k-callout"), "고칠 곳으로 가는 단추가 문제 목록 상자 밖에 있다").toBeTruthy();
  });

  it("설정이 하나도 없으면 「설정 안 됨」 여섯 칸의 속성 줄을 세우지 않는다", async () => {
    renderScreen();
    await screen.findByText(/메일 서버 주소가 비어 있습니다/);
    expect(screen.queryByLabelText("메일 서버 설정")).toBeNull();
    expect(screen.queryByText("설정 안 됨")).toBeNull();
  });

  it("한 통도 쌓인 적이 없으면 발송 현황 카드가 서지 않고, 빈 상태가 아직 안 보냈다고 말한다", async () => {
    withStatus({ counts: { queued: 0, sent: 0, failed: 0, unconfigured: 0 }, recent_failures: [] });
    renderScreen();
    expect(await screen.findByText("아직 보낸 메일이 없습니다")).toBeInTheDocument();
    expect(screen.queryByLabelText("발송 현황")).toBeNull();
    // 「실패가 없다」는 좋은 소식 문장은 보낸 것이 있을 때만이다.
    expect(screen.queryByText("최근 실패한 메일이 없습니다")).toBeNull();
  });

  it("반례: 보낸 메일이 있고 실패가 없으면 실패 없음이 좋은 소식으로 선다", async () => {
    withStatus({ counts: { queued: 0, sent: 4, failed: 0, unconfigured: 0 }, recent_failures: [] });
    renderScreen();
    expect(await screen.findByText("최근 실패한 메일이 없습니다")).toBeInTheDocument();
    expect(screen.getByLabelText("발송 현황")).toBeInTheDocument();
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
        server: { ...NOT_CONFIGURED.mail.server, username: "mailer" },
      },
    });
    renderScreen();
    const meta = await screen.findByLabelText("메일 서버 설정");
    expect(within(meta).getByText("등록 안 됨")).toBeInTheDocument();
    expect(within(meta).queryByText(/smtp.password|smtp_password/)).toBeNull();
  });
});

/* 계획 3.3 · D-512 — 건강 상태, 연결 확인, 설정 전에 쌓인 메일, 발송 기록 탭. */
describe("메일 건강 상태와 연결 확인", () => {
  function withHealth(health, extra = {}) {
    const body = { ...CONFIGURED, health, ...extra };
    apiMock.mockImplementation((path, opt) => {
      const p = String(path);
      if (p.startsWith("/api/admin/mail/status")) return Promise.resolve(body);
      if (p === "/api/admin/mail/verify" && opt && opt.method === "POST") return Promise.resolve({ job_id: "j-1", status: "queued" });
      if (p === "/api/admin/mail/verify/j-1") return Promise.resolve(extra.verifyReply || { job_id: "j-1", pending: false, result: { ok: true, message: "확인" } });
      if (p === "/api/admin/mail/resend-unconfigured") return Promise.resolve({ queued: 2 });
      if (p.startsWith("/api/admin/mail/deliveries")) return Promise.resolve({ items: [], total: 0, page: 1, page_size: 50 });
      return Promise.resolve({});
    });
  }

  it("값이 채워졌어도 확인 전이면 「지금 나간다」고 하지 않는다", async () => {
    withHealth({ state: "unverified", label: "확인 전" });
    renderScreen();
    expect(await screen.findByText(/아직 발송을 확인하지 않았습니다/)).toBeInTheDocument();
    expect(screen.queryByText(/지금 메일이 나갑니다/)).toBeNull();
  });

  it("발송 실패면 까닭과 설정으로 가는 단추가 선다", async () => {
    withHealth({ state: "failing", label: "발송 실패", message: "메일 서버가 로그인을 거부했습니다." });
    renderScreen();
    expect(await screen.findByText(/메일 발송이 실패하고 있습니다/)).toBeInTheDocument();
    expect(screen.getByText(/메일 서버가 로그인을 거부했습니다/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "메일 설정 열기" }).getAttribute("href")).toBe("#/settings?setting=smtp");
  });

  it("연결 확인은 잡을 넣고 결과를 읽어 성공을 말한다 — 메일은 보내지 않는다", async () => {
    const user = userEvent.setup();
    withHealth({ state: "unverified", label: "확인 전" });
    renderScreen();
    await user.click(await screen.findByRole("button", { name: "연결 확인" }));
    expect(await screen.findByText("메일 서버 연결을 확인했습니다.")).toBeInTheDocument();
    const paths = apiMock.mock.calls.map(([p]) => String(p));
    expect(paths).toContain("/api/admin/mail/verify/j-1");
    expect(paths).not.toContain("/api/admin/mail/test");
  });

  it("연결 확인이 실패하면 서버가 고른 까닭을 말한다", async () => {
    const user = userEvent.setup();
    withHealth({ state: "unverified", label: "확인 전" }, {
      verifyReply: { job_id: "j-1", pending: false, result: { ok: false, message: "메일 서버에 연결하지 못했습니다." } },
    });
    renderScreen();
    await user.click(await screen.findByRole("button", { name: "연결 확인" }));
    expect(await screen.findByText(/연결 확인에 실패했습니다\. 메일 서버에 연결하지 못했습니다\./)).toBeInTheDocument();
  });

  it("설정 전에 쌓인 메일은 연결이 정상일 때만 묻고, 누르면 보낸다", async () => {
    const user = userEvent.setup();
    withHealth(CONFIGURED.health, { pending_unconfigured_count: 2 });
    renderScreen();
    expect(await screen.findByText(/설정 전에 쌓인 메일 2건이 있습니다/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(apiMock.mock.calls.some(([p, o]) =>
      String(p) === "/api/admin/mail/resend-unconfigured" && o && o.method === "POST")).toBe(true));
  });

  it("반례: 확인 전이면 쌓인 메일을 보내자고 묻지 않는다", async () => {
    withHealth({ state: "unverified", label: "확인 전" }, { pending_unconfigured_count: 2 });
    renderScreen();
    await screen.findByText(/아직 발송을 확인하지 않았습니다/);
    expect(screen.queryByText(/설정 전에 쌓인 메일/)).toBeNull();
  });

  it("발송 기록 탭은 모든 발송 목록을 서버에서 받는다", async () => {
    const user = userEvent.setup();
    withHealth(CONFIGURED.health);
    renderScreen();
    await user.click(await screen.findByRole("tab", { name: "발송 기록" }));
    await waitFor(() => expect(apiMock.mock.calls.some(([p]) =>
      String(p).startsWith("/api/admin/mail/deliveries?"))).toBe(true));
  });

  it("메일로 보내는 알림: 스위치 하나가 허용 목록 전체를 설정 API 로 저장한다", async () => {
    const user = userEvent.setup();
    withHealth(CONFIGURED.health, {
      notification_mail: {
        allowed: ["ticket_assigned", "ticket_status_changed"],
        catalog: [
          { key: "ticket_assigned", label: "티켓 배정", help: "누군가 나를 티켓 담당자로 지정했을 때" },
          { key: "ticket_status_changed", label: "티켓 상태 변경", help: "지켜보거나 맡은 티켓의 상태가 바뀌었을 때" },
          { key: "ticket_resolved", label: "요청한 티켓 결과", help: "요청한 티켓이 끝났을 때" },
        ],
        max_age_days: 7,
      },
    });
    renderScreen();
    await user.click(await screen.findByRole("switch", { name: "요청한 티켓 결과 메일 허용" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/settings/mail_notification_types", {
      method: "PUT", body: { value: ["ticket_assigned", "ticket_status_changed", "ticket_resolved"] },
    }));
    await user.click(screen.getByRole("tab", { name: "3일" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/settings/mail_notification_max_age_days", {
      method: "PUT", body: { value: 3 },
    }));
  });

  /* D-525 — 저장 중에 허용 스위치를 끄지 않는다. 비활성은 실제 조건(쓰기 권한 없음) 하나뿐이다. */
  it("저장이 도는 동안에도 허용 스위치는 켜져 있고 누른 순간 바뀐다", async () => {
    const user = userEvent.setup();
    withHealth(CONFIGURED.health, {
      notification_mail: {
        allowed: ["ticket_assigned"],
        catalog: [
          { key: "ticket_assigned", label: "티켓 배정", help: "누군가 나를 티켓 담당자로 지정했을 때" },
          { key: "ticket_resolved", label: "요청한 티켓 결과", help: "요청한 티켓이 끝났을 때" },
        ],
        max_age_days: 7,
      },
    });
    const base = apiMock.getMockImplementation();
    let release = () => {};
    apiMock.mockImplementation((path, opt) => {
      if (String(path).startsWith("/api/admin/settings/") && opt && opt.method === "PUT") {
        return new Promise((resolve) => { release = () => resolve({}); });
      }
      return base(path, opt);
    });
    renderScreen();
    const resolved = await screen.findByRole("switch", { name: "요청한 티켓 결과 메일 허용" });
    const assigned = screen.getByRole("switch", { name: "티켓 배정 메일 허용" });
    expect(resolved).not.toBeChecked();
    await user.click(resolved);
    expect(resolved).toBeChecked();
    expect(resolved).toBeEnabled();
    expect(assigned).toBeEnabled();
    await act(async () => { release(); });
  });

  it("반례: 쓰기 역할이 아니면 허용 목록을 바꿀 수 없다", async () => {
    authRole = "auditor";
    withHealth(CONFIGURED.health, {
      notification_mail: {
        allowed: ["ticket_assigned"],
        catalog: [{ key: "ticket_assigned", label: "티켓 배정", help: "누군가 나를 티켓 담당자로 지정했을 때" }],
        max_age_days: 7,
      },
    });
    renderScreen();
    expect(await screen.findByRole("switch", { name: "티켓 배정 메일 허용" })).toBeDisabled();
    expect(screen.queryByRole("tab", { name: "3일" })).toBeNull();
    expect(screen.getByText("7일")).toBeInTheDocument();
  });
});
