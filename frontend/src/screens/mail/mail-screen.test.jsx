import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 메일 화면 — 「운영 › 메일」 한 화면, 탭 셋 (계획 M1 · M2 · M3, D-546 · D-548 · D-549 · D-554 · D-555).
 *
 * qa-contract-replaced-by: frontend/src/screens/mail-status.test.jsx
 *
 * 옛 시험은 「메일 발송」 화면의 상태 탭(문제 목록 · 속성 줄 · 발송 현황 카드 · 최근 실패 표 · 메일로 보내는 알림)을 쟀다. 그 화면은 설정 ·
 * 발송 기록 · 알림 메일 세 탭이 됐고, 같은 성질을 새 자리에서 잰다:
 *   1) 서버가 준 상태 낱말과 한 문장이 상태 면에 서고, 마지막 확인의 단계 줄이 보인다. 원문(상태 코드 · 실패 종류)은 기술 정보 안이다.
 *   2) 설정은 이 화면에서 쓴다 - 보안 연결을 바꾸면 기본 포트가 따라오고, 저장 본문에 비밀 칸 이름이 없으며 비밀번호는 같은 저장에 실린다.
 *      저장하면 서버가 연 연결 확인을 지켜본다.
 *   3) 저장하지 않은 수정 내용이 있으면 머리의 「연결 확인」 · 「시험 메일 보내기」가 꺼진다.
 *   4) 설정 권한이 없는 역할은 같은 배치의 읽기 전용 값과 한 줄 안내를 본다. 운영 권한이 없는 역할에게는 머리 동작이 없다.
 *   5) 시험 메일 창은 내 주소가 기본값이고, 설정 권한이 없으면 칸이 읽기 전용이다. 결과는 「접수」로 말하고 「도착」이라고 하지 않는다.
 *   6) 발송 기록 탭은 상태별 수를 한 줄로 보이고 목록을 서버에서 받는다. 알림 메일 탭의 스위치는 허용 목록 전체를 설정 API 로 저장한다.
 *   7) 메일 모양 미리 보기는 빈 sandbox 틀 안의 HTML 과 평문 보기를 바꾼다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
let authRole = "system_admin";
vi.mock("../../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: authRole, email: "me@goodmit.co.kr" } }),
}));

import { MailScreen } from "./MailScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const STAGES = [
  { key: "dns", label: "DNS 조회", state: "ok", detail: null },
  { key: "connect", label: "서버 연결", state: "ok", detail: null },
  { key: "tls", label: "보안 연결", state: "ok", detail: null },
  { key: "auth", label: "인증", state: "failed", detail: "메일 서버가 로그인을 거부했습니다." },
  { key: "sender", label: "보내는 사람", state: "not_reached", detail: null },
];
const SETTINGS = {
  settings: {
    enabled: true, host: "smtp.internal", port: 587, security: "starttls", from_address: "noreply@goodmit.co.kr",
    from_name: "ClovirAssist", username: "mailer", timeout_seconds: 20, tls_verify: true, ca_pem: "",
  },
  password: { stored: true, updated_at: "2026-10-01T00:00:00" },
  presets: { ports: { starttls: 587, ssl: 465, none: 25 } },
  limits: {},
};

const PROGRESS = {
  steps: [
    { key: "enable", label: "메일 발송 켜기", state: "done", hint: null, anchor: "section:enable" },
    { key: "method", label: "보내는 방법 고르기", state: "done", hint: null, anchor: "section:method" },
    { key: "inputs", label: "보내는 사람과 방식별 정보 입력", state: "done", hint: null, anchor: "section:inputs" },
    { key: "applied", label: "저장과 적용", state: "done", hint: null, anchor: "section:relay" },
    { key: "verified", label: "연결 확인", state: "done", hint: null, anchor: "action:verify" },
    { key: "test_sent", label: "시험 메일", state: "current", hint: "시험 메일을 보내세요.", anchor: "action:test" },
    { key: "inbox_confirmed", label: "받은 편지함 확인", state: "todo", hint: null, anchor: "action:inbox" },
  ],
  next: { key: "test_sent", label: "시험 메일", state: "current", hint: "시험 메일을 보내세요.", anchor: "action:test" },
  done_count: 5, total: 7, complete: false,
};

function status(patch = {}) {
  return {
    progress: PROGRESS,
    latest_test: null,
    inbox: null,
    health: {
      state: "ok", label: "정상", kind: "ok", message: "메일 발송을 사용할 수 있습니다.", checked_at: "2026-10-01T05:05:00",
      stages: STAGES.map((s) => ({ ...s, state: s.state === "failed" || s.state === "not_reached" ? "ok" : s.state, detail: null })),
    },
    problems: [],
    summary: { ...SETTINGS.settings, mode: "external", password: SETTINGS.password },
    counts: { queued: 1, retrying: 0, sent: 7, failed: 2, unconfigured: 0, cancelled: 1, superseded: 0 },
    recent_failures: [],
    backlog: { count: 0, window_days: 7 },
    base_url: { value: "https://clovirassist.gooddi.lab", problem: null },
    relay: null,
    capabilities: { can_configure: true, can_operate: true },
    notification_mail: {
      allowed: ["ticket_assigned"], max_age_days: 7,
      catalog: [{ key: "ticket_assigned", label: "티켓 배정", help: "누군가 나를 담당자로 지정했을 때" },
        { key: "ticket_resolved", label: "요청한 티켓 결과", help: "끝났을 때" }],
    },
    ...patch,
  };
}

let current = status();
function route(extra = () => null) {
  apiMock.mockImplementation((path, opts) => {
    const p = String(path);
    const method = (opts && opts.method) || "GET";
    const hit = extra(p, method, opts);
    if (hit) return hit;
    if (p.startsWith("/api/admin/mail/status")) return Promise.resolve(current);
    if (p === "/api/admin/mail/settings" && method === "GET") return Promise.resolve(SETTINGS);
    if (p.startsWith("/api/admin/mail/templates/") && p.endsWith("/preview")) {
      return Promise.resolve({ subject: "[ClovirAssist] ABC-12 담당자로 지정", text: "평문 본문입니다.", html: "<!DOCTYPE html><p>본문</p>" });
    }
    if (p.startsWith("/api/admin/mail/templates")) {
      return Promise.resolve({ items: [{ key: "ticket_assigned", label: "티켓 배정" }, { key: "invite", label: "초대" }] });
    }
    if (p.startsWith("/api/admin/mail/deliveries")) return Promise.resolve({ items: [], total: 0, page: 1, page_size: 50 });
    if (p.startsWith("/api/me/views")) return Promise.resolve({ items: [] });
    return Promise.resolve({});
  });
}

beforeEach(() => {
  authRole = "system_admin";
  current = status();
  apiMock.mockReset();
  route();
});

function renderScreen(path = "/mail") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <MailScreen />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const calls = (method, prefix) => apiMock.mock.calls.filter(([p, o]) => String(p).startsWith(prefix)
  && ((o && o.method) || "GET") === method);

describe("메일 화면 — 상태 면", () => {
  it("서버의 상태 낱말 · 한 문장 · 최근 확인 · 단계 줄을 보이고, 원문은 기술 정보 안이다", async () => {
    renderScreen();
    const card = await screen.findByTestId("mail-state");
    expect(within(card).getByTestId("mail-state-label")).toHaveTextContent("정상");
    expect(within(card).getByText("메일 발송을 사용할 수 있습니다.")).toBeInTheDocument();
    expect(within(card).getByText(/최근 확인/)).toBeInTheDocument();
    const stages = within(card).getByTestId("mail-stages");
    expect(within(stages).getByText("DNS 조회")).toBeInTheDocument();
    expect(within(stages).getByText("인증")).toBeInTheDocument();
    // 상태 코드는 기술 정보 접기 안에만 있다.
    const tech = card.querySelector("details");
    expect(tech).not.toBeNull();
    expect(within(tech).getByText("ok")).toBeInTheDocument();
  });

  it("발송 실패면 실패한 단계의 까닭 한 문장이 메시지 상자로 선다", async () => {
    current = status({ health: { state: "failing", label: "발송 실패", kind: "danger", message: "메일 발송이 실패하고 있습니다.",
      stages: STAGES, failure_kind: "auth", stage: "auth" } });
    renderScreen();
    const card = await screen.findByTestId("mail-state");
    expect(within(card).getByText("메일 서버가 로그인을 거부했습니다.")).toBeInTheDocument();
    const failed = card.querySelector("[data-stage='auth']");
    expect(failed.getAttribute("data-stage-state")).toBe("failed");
  });
});

describe("메일 화면 — 설정 탭", () => {
  it("보안 연결을 바꾸면 기본 포트가 따라오고, 저장 본문에 비밀 칸 이름이 없으며 비밀번호가 같은 저장에 실린다", async () => {
    const user = userEvent.setup();
    route((p, method, opts) => (p === "/api/admin/mail/settings" && method === "PUT"
      ? Promise.resolve({ ...SETTINGS, settings: { ...SETTINGS.settings, ...opts.body }, health: current.health, verify: { job_id: "job-1", timeout_seconds: 30 } })
      : null));
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    await user.click(screen.getByRole("combobox", { name: "보안 연결" }));
    await user.click(await screen.findByRole("option", { name: "SSL" }));
    expect(screen.getByLabelText("포트")).toHaveValue(465);
    await user.type(screen.getByLabelText("비밀번호"), "new-secret");
    await user.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(calls("PUT", "/api/admin/mail/settings")).toHaveLength(1));
    const body = calls("PUT", "/api/admin/mail/settings")[0][1].body;
    expect(body.security).toBe("ssl");
    expect(body.port).toBe(465);
    expect(body.password).toBe("new-secret");
    expect(Object.keys(body)).not.toContain("password_ref");
    // 저장하면 서버가 연 연결 확인을 지켜본다.
    await waitFor(() => expect(calls("GET", "/api/admin/mail/verify/job-1").length).toBeGreaterThan(0));
  });

  it("저장하지 않은 수정 내용이 있으면 머리 동작이 꺼지고 까닭이 이어진다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    const check = screen.getByRole("button", { name: "연결 확인" });
    expect(check).toBeEnabled();
    await user.clear(screen.getByLabelText(/서버 주소/));
    await user.type(screen.getByLabelText(/서버 주소/), "smtp.changed");
    expect(screen.getByRole("button", { name: "연결 확인" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "시험 메일 보내기" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "연결 확인" }).getAttribute("aria-describedby")).toBe("mail-dirty-hint");
    expect(screen.getByText("저장하지 않은 수정 내용이 있습니다.")).toBeInTheDocument();
  });

  it("인증서 확인을 끄면 저장 전에 확인을 받는다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    await user.click(screen.getByRole("checkbox", { name: "서버 인증서 확인" }));
    await user.click(screen.getByRole("button", { name: "저장" }));
    const dialog = await screen.findByRole("dialog", { name: /인증서 확인 끄기/ });
    expect(dialog).toHaveTextContent("가로챌 수 있게 됩니다");
    await user.click(within(dialog).getByRole("button", { name: "취소" }));
    expect(calls("PUT", "/api/admin/mail/settings")).toHaveLength(0);
  });

  it("설정 권한이 없으면 읽기 전용 값과 한 줄 안내를 본다", async () => {
    authRole = "admin";
    current = status({ capabilities: { can_configure: false, can_operate: true } });
    renderScreen();
    const view = await screen.findByTestId("mail-settings-readonly");
    expect(within(view).getByText("메일 서버 설정은 시스템 관리자만 바꿀 수 있습니다.")).toBeInTheDocument();
    expect(within(view).getByText("smtp.internal")).toBeInTheDocument();
    expect(screen.queryByTestId("mail-settings-form")).toBeNull();
    expect(calls("GET", "/api/admin/mail/settings")).toHaveLength(0);
  });

  it("운영 권한이 없으면 머리 동작이 없다", async () => {
    authRole = "auditor";
    current = status({ capabilities: { can_configure: false, can_operate: false } });
    renderScreen();
    await screen.findByTestId("mail-settings-readonly");
    expect(screen.queryByRole("button", { name: "연결 확인" })).toBeNull();
    expect(screen.queryByRole("button", { name: "시험 메일 보내기" })).toBeNull();
  });
});

describe("메일 화면 — 시험 메일", () => {
  it("내 주소가 기본값이고, 결과는 「접수」로 말한다", async () => {
    const user = userEvent.setup();
    const sent = { id: "d-9", status: "sent", to_email: "ops@example.org" };
    route((p, method, opts) => {
      if (p === "/api/admin/mail/test" && method === "POST") {
        return Promise.resolve({ delivery: { id: "d-9", status: "queued" }, sentence: "메일 서버가 시험 메일을 접수했습니다. 받은 편지함에서 확인하세요.", body: opts.body });
      }
      if (p === "/api/admin/mail/deliveries/d-9") return Promise.resolve({ delivery: sent });
      return null;
    });
    renderScreen();
    await user.click(await screen.findByRole("button", { name: "시험 메일 보내기" }));
    const dialog = await screen.findByRole("dialog", { name: "시험 메일 보내기" });
    const field = within(dialog).getByLabelText("받는 주소");
    expect(field).toHaveValue("me@goodmit.co.kr");
    await user.clear(field);
    await user.type(field, "ops@example.org");
    await user.click(within(dialog).getByRole("button", { name: "보내기" }));
    await waitFor(() => expect(calls("POST", "/api/admin/mail/test")[0][1].body).toEqual({ to: "ops@example.org" }));
    const toast = await screen.findByText("메일 서버가 시험 메일을 접수했습니다. 받은 편지함에서 확인하세요.");
    expect(toast.textContent).not.toMatch(/도착|받았습니다/);
  });

  it("설정 권한이 없으면 받는 주소 칸이 읽기 전용이고 까닭을 말한다", async () => {
    const user = userEvent.setup();
    authRole = "admin";
    current = status({ capabilities: { can_configure: false, can_operate: true } });
    renderScreen();
    await user.click(await screen.findByRole("button", { name: "시험 메일 보내기" }));
    const dialog = await screen.findByRole("dialog", { name: "시험 메일 보내기" });
    expect(within(dialog).getByLabelText("받는 주소")).toHaveAttribute("readonly");
    expect(within(dialog).getByText("다른 주소로 보내려면 시스템 관리자 권한이 필요합니다.")).toBeInTheDocument();
  });

  it("발송이 꺼진 설치에서는 두 머리 동작이 꺼져 있다", async () => {
    current = status({ health: { state: "disabled", label: "사용 안 함", kind: "neutral", message: "메일 발송을 사용하지 않습니다.", stages: [] } });
    renderScreen();
    expect(await screen.findByRole("button", { name: "연결 확인" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "시험 메일 보내기" })).toBeDisabled();
  });
});

describe("메일 화면 — 발송 기록 · 알림 메일", () => {
  it("발송 기록 탭은 상태별 수를 한 줄로 보이고 목록을 서버에서 받는다", async () => {
    renderScreen("/mail?tab=deliveries");
    const bar = await screen.findByRole("group", { name: "상태별 메일 수" });
    expect(within(bar).getByText("서버가 접수함")).toBeInTheDocument();
    expect(within(bar).getByText("7")).toBeInTheDocument();
    await waitFor(() => expect(calls("GET", "/api/admin/mail/deliveries").length).toBeGreaterThan(0));
  });

  it("알림 메일 스위치 하나가 허용 목록 전체를 설정 API 로 저장한다", async () => {
    const user = userEvent.setup();
    renderScreen("/mail?tab=notifications");
    await user.click(await screen.findByRole("switch", { name: "요청한 티켓 결과 메일 허용" }));
    await waitFor(() => expect(calls("PUT", "/api/admin/settings/mail_notification_types")).toHaveLength(1));
    expect(calls("PUT", "/api/admin/settings/mail_notification_types")[0][1].body).toEqual({ value: ["ticket_assigned", "ticket_resolved"] });
  });

  it("메일 모양은 빈 sandbox 틀의 HTML 이고 평문 보기로 바꿀 수 있다", async () => {
    const user = userEvent.setup();
    renderScreen("/mail?tab=notifications");
    const frame = await screen.findByTestId("mail-preview-frame");
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(frame.getAttribute("srcdoc")).toContain("<p>본문</p>");
    expect(screen.getByTestId("mail-preview-subject")).toHaveTextContent("[ClovirAssist] ABC-12 담당자로 지정");
    await user.click(screen.getByRole("tab", { name: "텍스트" }));
    expect(screen.getByTestId("mail-preview-text")).toHaveTextContent("평문 본문입니다.");
    expect(screen.queryByTestId("mail-preview-frame")).toBeNull();
  });
});

describe("메일 화면 — 안내 흐름 (D-560)", () => {
  it("진행 띠가 일곱 단계와 다음 할 일을 보이고 「이동」이 머리 동작을 연다", async () => {
    const user = userEvent.setup();
    renderScreen();
    const strip = await screen.findByTestId("mail-progress");
    expect(within(strip).getAllByRole("listitem")).toHaveLength(7);
    expect(strip.querySelector('[data-step="test_sent"]')).toHaveAttribute("aria-current", "step");
    expect(strip.querySelectorAll('[data-step-state="done"]')).toHaveLength(5);
    expect(within(strip).getByText("시험 메일을 보내세요.")).toBeInTheDocument();
    await user.click(within(strip).getByRole("button", { name: "이동" }));
    expect(await screen.findByRole("dialog", { name: "시험 메일 보내기" })).toBeInTheDocument();
  });

  it("접수된 시험 메일은 받은 편지함 확인을 묻고 「받았습니다」가 기록 API 로 간다", async () => {
    const user = userEvent.setup();
    current = status({ latest_test: { id: "d1", status: "sent", sent_at: "2026-10-12T05:18:00", created_at: "2026-10-12T05:17:00" } });
    route((p, method) => {
      if (p === "/api/admin/mail/inbox-confirm" && method === "POST") {
        return Promise.resolve({ inbox: { delivery_id: "d1", received: true }, status: { ...current, inbox: { delivery_id: "d1", received: true } } });
      }
      return null;
    });
    renderScreen();
    const ask = await screen.findByTestId("mail-inbox-confirm");
    expect(ask).toHaveTextContent("받은 편지함(정크함 포함)에서 확인했습니까?");
    expect(ask.textContent).not.toMatch(/도착했습니다/);
    await user.click(within(ask).getByRole("button", { name: "받았습니다" }));
    await waitFor(() => expect(calls("POST", "/api/admin/mail/inbox-confirm")).toHaveLength(1));
    expect(calls("POST", "/api/admin/mail/inbox-confirm")[0][1].body).toEqual({ delivery_id: "d1", received: true });
    await waitFor(() => expect(screen.queryByTestId("mail-inbox-confirm")).toBeNull());
  });

  it("제공자 프리셋을 고르면 서버 값이 채워지고 도움말과 발급처 링크가 서며, 주소를 고치면 직접 입력으로 돌아간다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    expect(screen.getByRole("radio", { name: /직접 입력/ })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: /^Gmail/ }));
    expect(screen.getByLabelText(/서버 주소/)).toHaveValue("smtp.gmail.com");
    expect(screen.getByLabelText("포트")).toHaveValue(587);
    expect(screen.getByTestId("mail-preset-help")).toHaveTextContent("16자리 앱 비밀번호");
    expect(screen.getByRole("link", { name: "앱 비밀번호 발급 안내" })).toHaveAttribute("href", "https://myaccount.google.com/apppasswords");
    await user.click(screen.getByRole("radio", { name: /^Naver/ }));
    expect(screen.getByLabelText(/서버 주소/)).toHaveValue("smtp.naver.com");
    expect(screen.getByLabelText("포트")).toHaveValue(465);
    await user.type(screen.getByLabelText(/서버 주소/), "x");
    expect(screen.getByRole("radio", { name: /직접 입력/ })).toBeChecked();
    expect(screen.queryByTestId("mail-preset-help")).toBeNull();
  });

  it("발송 실패의 흔한 원인 한 문장이 까닭 아래에 선다", async () => {
    current = status({ health: { state: "failing", label: "발송 실패", kind: "danger", message: "메일 서버가 로그인을 거부했습니다.",
      checked_at: "2026-10-01T05:05:00", stages: STAGES, failure_kind: "auth", stage: "auth",
      hint: "비밀번호가 틀렸거나 앱 비밀번호가 필요합니다." } });
    renderScreen();
    expect(await screen.findByTestId("mail-failure-hint")).toHaveTextContent("앱 비밀번호가 필요합니다.");
  });

  it("보내는 방법은 로컬 릴레이가 먼저다", async () => {
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    const radios = within(screen.getByRole("radiogroup", { name: "보내는 방법" })).getAllByRole("radio");
    expect(radios[0]).toHaveAccessibleName(/로컬 릴레이/);
    expect(radios[0]).toHaveTextContent("메일 계정이 필요 없습니다.");
  });
});
