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
 * qa-contract-change: 설정 탭이 다섯 구획(상태 요약 · 기본 설정 · 전달 방법 설정 · 연결과 발송 확인 · 문제 해결과 고급)이 되면서 머리의 확인 단추 둘이 ④ 줄로, 진행 띠가 상태 요약 안의 일곱 단계 목록으로 옮겼다(D-574). 같은 성질을 새 자리에서 잰다.
 *
 * 옛 시험은 「메일 발송」 화면의 상태 탭(문제 목록 · 속성 줄 · 발송 현황 카드 · 최근 실패 표 · 메일로 보내는 알림)을 쟀다. 그 화면은 설정 ·
 * 발송 기록 · 알림 메일 세 탭이 됐고, 같은 성질을 새 자리에서 잰다:
 *   1) 서버가 준 상태 낱말과 한 문장이 상태 면에 서고, 마지막 확인의 단계 줄이 보인다. 원문(상태 코드 · 실패 종류)은 기술 정보 안이다.
 *   2) 설정은 이 화면에서 쓴다 - 보안 연결을 바꾸면 기본 포트가 따라오고, 저장 본문에 비밀 칸 이름이 없으며 비밀번호는 같은 저장에 실린다.
 *      저장하면 서버가 연 연결 확인을 지켜본다.
 *   3) 저장하지 않은 수정 내용이 있으면 ④ 「연결과 발송 확인」의 「연결 확인」 · 「시험 메일 보내기」가 꺼지고 까닭이 그 구획에 선다.
 *      화면 머리에는 두 단추가 없다.
 *   4) 설정 권한이 없는 역할은 같은 다섯 구획의 읽기 전용 값과 한 줄 안내를 본다. 운영 권한이 없는 역할에게는 확인 단추가 없다.
 *   5) 시험 메일 창은 내 주소가 기본값이고, 설정 권한이 없으면 칸이 읽기 전용이다. 결과는 「접수」로 말하고 「도착」이라고 하지 않는다.
 *   6) 발송 기록 탭은 상태별 수를 한 줄로 보이고 목록을 서버에서 받는다. 알림 메일 탭의 스위치는 허용 목록 전체를 설정 API 로 저장한다.
 *   7) 메일 미리 보기는 빈 sandbox 틀 안의 HTML 과 평문 보기를 바꾼다. 알림 메일 종류는 범주마다 묶여 두 단까지 흐른다(D-592).
 *   8) 여섯 구획(D-574 · D-592): h2 여섯이 순서대로 서고, 고른 방법의 칸만 서며, 「지금 할 일」과 일곱 단계는 발송 상태 판 안이다.
 *      상태 줄 넷(메일 발송 가능 · SMTP 수락 · DNS 인증 · 받은 편지함 확인)은 서로 다른 사실을 따로 말한다. 보내는 주소 · 메일 서버
 *      이름(HELO) · 웹 서비스 주소는 다른 줄이다. 「요청 내용과 기술 상세」는 처음에 닫혀 있고 열면 고급 칸과 받은 편지함 아이콘 안내가 선다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 * qa-contract-change: 설정 탭이 여섯 구획(발송 상태 · 발신 정보 · 전달 방식과 서버 이름 · 연결과 시험 발송 · DNS 인증 진단 · 요청 내용과 기술 상세)이 됐다(D-592). 상태 면의 사실 띠는 상태 줄 넷(메일 발송 가능 · SMTP 수락 · DNS 인증 · 받은 편지함 확인)이 됐고, 정상일 때 연결 확인 단계 줄은 기술 정보 안이다. 같은 성질을 새 자리에서 잰다.
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

/* ④ 「연결과 시험 발송」 구획(머리 제목에서 거슬러 올라간 section). */
function checksSection() {
  return screen.getByRole("heading", { name: "연결과 시험 발송" }).closest("section");
}

const H2_ORDER = ["발송 상태", "발신 정보", "전달 방식과 서버 이름", "연결과 시험 발송", "DNS 인증 진단", "요청 내용과 기술 상세"];
const ADVANCED = "요청 내용과 기술 상세";
const sectionOf = (name) => screen.getByRole("heading", { level: 2, name }).closest("section");
/* 상태 줄 하나의 글(이름 칸 dt 를 뺀 값 칸 dd). */
const line = (card, key) => card.querySelector(`[data-status-line="${key}"]`);
const h2Names = () => screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);

describe("메일 화면 — 상태 면", () => {
  it("상태 줄 넷이 따로 서고, 정상일 때 연결 확인 단계와 원문은 기술 정보 안이다", async () => {
    renderScreen();
    const card = await screen.findByTestId("mail-state");
    expect(within(card).getByTestId("mail-state-label")).toHaveTextContent("정상");
    expect(within(card).getByText("메일 발송을 사용할 수 있습니다.")).toBeInTheDocument();
    expect(within(card).getByText(/최근 확인/)).toBeInTheDocument();
    const lines = within(card).getByTestId("mail-status-lines");
    expect([...lines.querySelectorAll("dt")].map((dt) => dt.textContent)).toEqual(["메일 발송 가능", "SMTP 수락", "DNS 인증", "받은 편지함 확인"]);
    expect(line(card, "smtp")).toHaveTextContent("시험 메일 없음");
    // 외부 SMTP 는 이 서버가 DNS 인증을 점검하지 않는다 - 통과로 쓰지 않는다.
    expect(line(card, "dns")).toHaveTextContent("점검 대상 아님");
    expect(line(card, "dns")).toHaveTextContent("외부 SMTP 서비스의 DNS 설정을 따릅니다.");
    expect(line(card, "inbox")).toHaveTextContent("기록 없음");
    // 정상일 때 단계 줄은 화면에 없고, 상태 코드 · 단계 결과는 기술 정보 접기 안에만 있다.
    expect(within(card).queryByTestId("mail-stages")).toBeNull();
    const tech = card.querySelector("details");
    expect(tech).not.toBeNull();
    expect(within(tech).getByText("ok")).toBeInTheDocument();
    expect(tech).toHaveTextContent("DNS 조회 정상");
  });

  it("SMTP 수락과 받은 편지함 확인은 다른 줄이다 - 접수만 된 시험 메일은 받은 편지함 줄이 「기록 없음」이다", async () => {
    current = status({ latest_test: { id: "d1", status: "sent", sent_at: "2026-10-12T05:18:00", created_at: "2026-10-12T05:17:00" } });
    const first = renderScreen();
    let card = await screen.findByTestId("mail-state");
    expect(line(card, "smtp")).toHaveTextContent("서버가 접수함");
    expect(line(card, "inbox")).toHaveTextContent("기록 없음");
    expect(card.textContent).not.toMatch(/도착|받았습니다/);
    first.unmount();
    current = status({ latest_test: { id: "d1", status: "sent", sent_at: "2026-10-12T05:18:00", created_at: "2026-10-12T05:17:00" },
      inbox: { delivery_id: "d1", received: false, at: "2026-10-12T05:30:00" } });
    renderScreen();
    card = await screen.findByTestId("mail-state");
    expect(line(card, "smtp")).toHaveTextContent("서버가 접수함");
    expect(line(card, "inbox")).toHaveTextContent("받은 편지함에 없음");
  });

  it("일곱 단계가 다 끝났으면 단계 목록 대신 한 문장만 선다", async () => {
    current = status({ progress: { ...PROGRESS, steps: PROGRESS.steps.map((st) => ({ ...st, state: "done", hint: null })), next: null, complete: true } });
    renderScreen();
    const card = await screen.findByTestId("mail-state");
    expect(within(card).getByTestId("mail-progress-complete")).toHaveTextContent("일곱 단계가 모두 끝났습니다.");
    expect(within(card).queryByTestId("mail-steps")).toBeNull();
    expect(card.querySelector(".k-mail-next")).toBeNull();
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

  it("저장에 실패하면 그 까닭이 따라오는 발(저장 단추 곁) 안에 선다 — 폼 끝에 서지 않는다(r23 설정 저장 왕복)", async () => {
    const user = userEvent.setup();
    route((p, method) => (p === "/api/admin/mail/settings" && method === "PUT"
      ? Promise.reject(Object.assign(new Error("보내는 주소 형식이 올바르지 않습니다."), { status: 422 }))
      : null));
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    const from = screen.getByLabelText(/보내는 주소/);
    await user.clear(from);
    await user.type(from, "qa@example.com");
    await user.click(screen.getByRole("button", { name: "저장" }));
    const failure = await screen.findByText(/보내는 주소 형식이 올바르지 않습니다/);
    const footer = failure.closest("[data-action-footer-sticky]");
    expect(footer, "실패 문장이 따라오는 발 밖에 섰다").not.toBeNull();
    expect(failure.closest("[role=alert]")).not.toBeNull();
    // 실패의 까닭과 함께 「저장하지 않은 수정 내용」도 선다 — 입력은 그대로 남아 있고 아직 저장되지 않았다.
    expect(within(footer).getByText("저장하지 않은 수정 내용이 있습니다.")).toBeInTheDocument();
    expect(from).toHaveValue("qa@example.com");
  });

  it("「보내는 이름」 도움말은 비울 때의 실제 결과를 말한다 — 제품 이름이 보내는 이름이 된다(D-572)", async () => {
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    expect(screen.getByText("비우면 제품 이름이 보내는 이름으로 보입니다.")).toBeInTheDocument();
    expect(screen.queryByText("비우면 주소만 보입니다.")).toBeNull();
  });

  it("저장하지 않은 수정 내용이 있으면 ④ 의 확인 단추가 꺼지고 까닭이 그 구획에 선다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    const checks = checksSection();
    const check = within(checks).getByRole("button", { name: "연결 확인" });
    expect(check).toBeEnabled();
    await user.clear(screen.getByLabelText(/서버 주소/));
    await user.type(screen.getByLabelText(/서버 주소/), "smtp.changed");
    expect(within(checks).getByRole("button", { name: "연결 확인" })).toBeDisabled();
    expect(within(checks).getByRole("button", { name: "시험 메일 보내기" })).toBeDisabled();
    expect(within(checks).getByRole("button", { name: "연결 확인" }).getAttribute("aria-describedby")).toBe("mail-dirty-hint");
    expect(within(checks).getByText("저장한 뒤에 확인할 수 있습니다.")).toHaveAttribute("id", "mail-dirty-hint");
    expect(screen.getByText("저장하지 않은 수정 내용이 있습니다.")).toBeInTheDocument();
  });

  it("두 확인 단추는 화면 머리가 아니라 ④ 「연결과 시험 발송」에 한 번씩만 선다", async () => {
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    expect(screen.getAllByRole("button", { name: "연결 확인" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "시험 메일 보내기" })).toHaveLength(1);
    const checks = checksSection();
    expect(within(checks).getByRole("button", { name: "연결 확인" })).toBeInTheDocument();
    expect(within(checks).getByRole("button", { name: "시험 메일 보내기" })).toBeInTheDocument();
    // 정상 상태에서 다음 할 일이 시험 메일이면 그 단추가 이 구획의 주 동작이다(구획당 주 단추 하나).
    expect(within(checks).getByRole("button", { name: "시험 메일 보내기" }).className).toMatch(/MuiButton-containedPrimary/);
    expect(within(checks).getByRole("button", { name: "연결 확인" }).className).not.toMatch(/MuiButton-contained/);
    expect(checks.querySelectorAll(".MuiButton-containedPrimary")).toHaveLength(1);
  });

  it("인증서 확인을 끄면 저장 전에 확인을 받는다", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    await user.click(screen.getByRole("checkbox", { name: "서버 인증서 확인" }));
    await user.click(screen.getByRole("button", { name: "저장" }));
    const dialog = await screen.findByRole("dialog", { name: /인증서 확인 비활성화/ });
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

  it("운영 권한이 없으면 확인 단추가 없다", async () => {
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

  it("메일 알림 종류는 서버가 준 범주마다 묶이고(제목 h3), 두 단까지만 흐른다(D-592)", async () => {
    current = status({ notification_mail: {
      allowed: ["ticket_assigned"], max_age_days: 7,
      catalog: [
        { key: "ticket_assigned", label: "티켓 배정", help: "누군가 나를 담당자로 지정했을 때", group: "티켓" },
        { key: "ticket_resolved", label: "요청한 티켓 결과", help: "끝났을 때", group: "티켓" },
        { key: "approval_decided", label: "승인 결과", help: "내가 올린 승인 요청이 처리됐을 때", group: "승인" },
      ],
    } });
    renderScreen("/mail?tab=notifications");
    const groups = await screen.findByTestId("mail-kind-groups");
    expect([...groups.querySelectorAll("[data-kind-group]")].map((g) => g.getAttribute("data-kind-group"))).toEqual(["티켓", "승인"]);
    expect(within(groups).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["티켓", "승인"]);
    const ticket = groups.querySelector('[data-kind-group="티켓"]');
    expect(within(ticket).getAllByRole("switch")).toHaveLength(2);
    expect(groups).toHaveStyle({ columnCount: "2" });
    expect(screen.getByRole("heading", { level: 2, name: "오래된 알림 발송 제한" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "발송 제한 기간" })).toHaveTextContent("7일");
    expect(screen.getByRole("heading", { level: 2, name: "메일 미리 보기" })).toBeInTheDocument();
  });

  it("메일 미리 보기는 빈 sandbox 틀의 HTML 이고 평문 보기로 바꿀 수 있다", async () => {
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
  it("발송 상태 판이 일곱 단계와 「지금 할 일」을 보이고, 「이동」은 ④ 의 그 줄 단추로 초점을 옮긴다", async () => {
    const user = userEvent.setup();
    renderScreen();
    const card = await screen.findByTestId("mail-state");
    const steps = within(card).getByTestId("mail-steps");
    expect(steps.tagName).toBe("OL");
    expect(steps.querySelectorAll("li[data-step-state]")).toHaveLength(7);
    expect(steps.querySelector('[data-step="test_sent"]')).toHaveAttribute("aria-current", "step");
    expect(steps.querySelectorAll('[data-step-state="done"]')).toHaveLength(5);
    expect(within(steps.querySelector('[data-step="enable"]')).getByText("끝남")).toBeInTheDocument();
    expect(within(steps.querySelector('[data-step="inbox_confirmed"]')).getByText("아직 안 함")).toBeInTheDocument();
    const next = card.querySelector(".k-mail-next");
    expect(next).not.toBeNull();
    expect(next).toHaveTextContent("지금 할 일");
    expect(within(next).getByText("시험 메일을 보내세요.")).toBeInTheDocument();
    // 「지금 할 일」 상자가 이미 말한 문장은 단계 목록이 다시 쓰지 않는다.
    expect(within(card).getAllByText("시험 메일을 보내세요.")).toHaveLength(1);
    await user.click(within(next).getByRole("button", { name: "이동" }));
    // 이동은 누르지 않는다 — 그 줄의 단추에 초점만 둔다(창이 열리지 않는다).
    expect(document.activeElement).toBe(within(checksSection()).getByRole("button", { name: "시험 메일 보내기" }));
    expect(screen.queryByRole("dialog", { name: "시험 메일 보내기" })).toBeNull();
  });

  it("막힌 단계는 그 문장을 이름 아래에 달고, 「지금 할 일」이 막힘이면 주의 톤이다", async () => {
    const blocked = { key: "inbox_confirmed", label: "받은 편지함 확인", state: "blocked",
      hint: "수신측이 거부했습니다. 진단의 요청문을 담당자에게 보낸 뒤 시험 메일을 다시 보내세요.", anchor: "action:inbox" };
    current = status({ progress: { ...PROGRESS, steps: [...PROGRESS.steps.slice(0, 6), blocked], next: PROGRESS.next } });
    renderScreen();
    const steps = await screen.findByTestId("mail-steps");
    const row = steps.querySelector('[data-step="inbox_confirmed"]');
    expect(row).toHaveAttribute("data-step-state", "blocked");
    expect(within(row).getByText("막힘")).toBeInTheDocument();
    expect(within(row).getByText(/수신측이 거부했습니다/)).toBeInTheDocument();
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
    // 받은 편지함 단추는 ④ 「연결과 시험 발송」의 셋째 줄이다.
    expect(checksSection().contains(ask)).toBe(true);
    expect(ask).toHaveAttribute("data-check-row", "inbox");
    expect(within(ask).getByRole("button", { name: "받은 편지함에 없음" })).toBeEnabled();
    await user.click(within(ask).getByRole("button", { name: "받은 편지함에서 확인함" }));
    await waitFor(() => expect(calls("POST", "/api/admin/mail/inbox-confirm")).toHaveLength(1));
    expect(calls("POST", "/api/admin/mail/inbox-confirm")[0][1].body).toEqual({ delivery_id: "d1", received: true });
    await waitFor(() => expect(screen.queryByTestId("mail-inbox-confirm")).toBeNull());
  });

  it("수신측이 거부한 시험 메일은 받은 편지함을 묻지 않고, 수신측까지 간 메일은 「전달했습니다」로 묻는다", async () => {
    current = status({ latest_test: { id: "d2", status: "sent", sent_at: "2026-10-12T13:24:00", created_at: "2026-10-12T13:24:00", remote_status: "bounced" } });
    const first = renderScreen();
    await screen.findByText("메일");
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("mail-inbox-confirm")).toBeNull();
    first.unmount();
    current = status({ latest_test: { id: "d3", status: "sent", sent_at: "2026-10-12T13:23:00", created_at: "2026-10-12T13:23:00", remote_status: "delivered" } });
    renderScreen();
    const ask = await screen.findByTestId("mail-inbox-confirm");
    expect(ask).toHaveTextContent("받는 쪽 메일 서버로 전달했습니다");
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
    const radios = within(screen.getByRole("radiogroup", { name: "발송 방식" })).getAllByRole("radio");
    expect(radios[0]).toHaveAccessibleName(/로컬 릴레이/);
    expect(radios[0]).toHaveTextContent("메일 계정이 필요 없습니다.");
  });
});

describe("메일 화면 — 여섯 구획 (D-574 · D-592)", () => {
  it("설정 탭은 h2 여섯이 순서대로 서고, 발송 상태만 독립된 판이다", async () => {
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    expect(h2Names()).toEqual(H2_ORDER);
    const card = screen.getByTestId("mail-state");
    expect(within(card).getByRole("heading", { level: 2, name: "발송 상태" })).toBeInTheDocument();
    const form = screen.getByTestId("mail-settings-form");
    for (const name of H2_ORDER.slice(1)) {
      expect(form.contains(screen.getByRole("heading", { level: 2, name }))).toBe(true);
    }
  });

  it("발신 정보는 보내는 주소와 웹 서비스 주소를 다른 줄로 말하고, 세 값이 따로라는 문장이 머리에 한 번 선다", async () => {
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    const basics = sectionOf("발신 정보");
    expect(basics).toHaveTextContent("보내는 주소, 메일 서버 이름(HELO), 웹 서비스 주소는 서로 따로 정합니다. 하나를 바꿔도 나머지는 바뀌지 않습니다.");
    expect(within(basics).getByLabelText(/보내는 주소/)).toHaveValue("noreply@goodmit.co.kr");
    const web = within(basics).getByText("웹 서비스 주소").closest(".k-settingrow");
    expect(web).toHaveTextContent("https://clovirassist.gooddi.lab");
    expect(web).toHaveTextContent("메일 속 링크가 여는 주소입니다.");
    // 메일 서버 이름(HELO)은 발신 정보가 아니라 전달 방식과 서버 이름의 줄이다 - 외부 SMTP 면 넘겨받는 서버에 대는 이름이다.
    expect(within(basics).queryByText("메일 서버 이름(HELO)")).toBeNull();
    const helo = within(sectionOf("전달 방식과 서버 이름")).getByText("메일 서버 이름(HELO)").closest(".k-settingrow");
    expect(helo).toHaveTextContent("이 서버의 기본 이름");
    expect(helo).toHaveTextContent("외부 SMTP 서버에 이 서버를 소개하는 이름입니다. 받는 쪽에는 외부 SMTP 서버의 이름이 보입니다.");
  });

  it("체크박스 줄과 확인 줄은 판 끝까지 늘지 않고 같은 묶음 폭(반 칸 입력과 같은 세로선)을 받는다(D-590)", async () => {
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    const groups = [
      screen.getByRole("checkbox", { name: "메일 발송 사용" }).closest(".k-settingrows"),
      screen.getByRole("checkbox", { name: "서버 인증서 확인" }).closest(".k-settingrows"),
      checksSection().querySelector(".k-settingrows"),
    ];
    // 폭 자체는 컨테이너 질의라 jsdom 이 계산하지 않는다 - 실제 세로선은 캡처(r23-mail-2)가 잰다. 여기서는 묶음이 같은 폭 계약을 받는지만 본다.
    for (const group of groups) expect(group).toHaveClass("k-settingrows--form");
  });

  it("전달 방식과 서버 이름에는 발송 방식과 고른 방법의 칸만 선다 - 외부 SMTP 면 로컬 릴레이 칸이 없다", async () => {
    renderScreen();
    const form = await screen.findByTestId("mail-settings-form");
    const method = within(form).getByRole("heading", { name: "전달 방식과 서버 이름" }).closest("section");
    expect(within(method).getByRole("radiogroup", { name: "발송 방식" })).toBeInTheDocument();
    expect(within(method).getByRole("radiogroup", { name: "메일 서비스" })).toBeInTheDocument();
    expect(within(method).getByLabelText(/서버 주소/)).toHaveValue("smtp.internal");
    expect(within(method).getByRole("checkbox", { name: "서버 인증서 확인" })).toBeInTheDocument();
    expect(within(method).queryByRole("radiogroup", { name: "전달 방식" })).toBeNull();
    expect(screen.queryByTestId("relay-component")).toBeNull();
  });

  it("외부 SMTP 의 DNS 인증 진단은 이 서버가 점검하지 않는다고 말하고 점검 단추가 없다", async () => {
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    const diagnosis = sectionOf("DNS 인증 진단");
    expect(diagnosis).toHaveTextContent("외부 SMTP를 쓰면 이 서버가 DNS 인증을 점검하지 않습니다.");
    expect(within(diagnosis).queryByRole("button", { name: "점검 다시 하기" })).toBeNull();
  });

  it("요청 내용과 기술 상세는 처음에 닫혀 있고, 열면 고급 칸과 받은 편지함 아이콘 안내가 선다", async () => {
    const user = userEvent.setup();
    current = status({ help: { inbox_icon: [
      { provider: "Microsoft 365", what: "보내는 주소의 공유 사서함에 사진을 넣습니다.", who: "받는 쪽 메일 관리자", external: true,
        note: "SPF 와 DKIM 이 통과해야 보입니다." },
      { provider: "Gmail", what: "BIMI 레코드와 인증된 로고가 필요합니다.", who: "도메인 DNS 담당자", external: true },
      { provider: "ClovirAssist", what: "메일 본문 머리에 제품 표식을 넣습니다.", who: "이 서버", external: false },
    ] } });
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    const toggle = screen.getByRole("button", { name: ADVANCED });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("응답 대기 시간(초)")).toBeNull();
    expect(screen.queryByTestId("mail-inbox-icon-help")).toBeNull();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("응답 대기 시간(초)")).toHaveValue(20);
    expect(screen.getByLabelText("사설 CA 인증서")).toBeInTheDocument();
    const help = screen.getByTestId("mail-inbox-icon-help");
    const rows = help.querySelectorAll("li[data-inbox-provider]");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("외부")).toBeInTheDocument();
    expect(within(rows[0]).getByText("하는 사람: 받는 쪽 메일 관리자")).toBeInTheDocument();
    expect(within(rows[0]).getByText("SPF 와 DKIM 이 통과해야 보입니다.")).toBeInTheDocument();
    expect(within(rows[2]).queryByText("외부")).toBeNull();
    // 고급 칸도 같은 저장에 실린다.
    await user.clear(screen.getByLabelText("응답 대기 시간(초)"));
    await user.type(screen.getByLabelText("응답 대기 시간(초)"), "45");
    expect(screen.getByText("저장하지 않은 수정 내용이 있습니다.")).toBeInTheDocument();
  });

  it("받은 편지함 아이콘 안내가 없는 서버면 그 자리를 그리지 않는다", async () => {
    const user = userEvent.setup();
    current = status({ help: { inbox_icon: [] } });
    renderScreen();
    await screen.findByTestId("mail-settings-form");
    await user.click(screen.getByRole("button", { name: ADVANCED }));
    expect(screen.getByLabelText("응답 대기 시간(초)")).toBeInTheDocument();
    expect(screen.queryByTestId("mail-inbox-icon-help")).toBeNull();
    expect(screen.queryByRole("heading", { name: "받은 편지함 아이콘" })).toBeNull();
  });

  it("읽기 전용 화면의 로컬 릴레이는 고른 전달 방식의 값만 보이고, 고급 값은 접기 안이다", async () => {
    const user = userEvent.setup();
    authRole = "admin";
    const relay = { delivery: "direct", helo_name: "mail.goodmit.co.kr", dkim_enabled: true, dkim_selector: "ca1",
      compare_resolvers: ["8.8.8.8"], transport_overrides: [{ domain: "goodmit.co.kr", host: "mx.goodmit.co.kr" }],
      smarthost: { host: "", port: 587, security: "starttls", username: "" } };
    current = status({ capabilities: { can_configure: false, can_operate: false },
      summary: { ...status().summary, mode: "local_relay", relay } });
    renderScreen();
    const view = await screen.findByTestId("mail-settings-readonly");
    expect(within(view).getByText("인터넷으로 직접 전달합니다.")).toBeInTheDocument();
    expect(within(view).getByText("mail.goodmit.co.kr")).toBeInTheDocument();
    expect(within(view).getByText("사용, 선택자 ca1")).toBeInTheDocument();
    expect(within(view).queryByText("상위 SMTP 서버")).toBeNull();
    expect(within(view).queryByText("8.8.8.8")).toBeNull();
    await user.click(within(view).getByRole("button", { name: ADVANCED }));
    expect(within(view).getByText("8.8.8.8")).toBeInTheDocument();
    expect(within(view).getByText("1개")).toBeInTheDocument();
    expect(within(checksSection()).queryByRole("button")).toBeNull();
  });

  it("읽기 전용 화면도 같은 여섯 구획이고, 운영 권한이 있으면 ④ 에 확인 단추가 선다", async () => {
    authRole = "admin";
    current = status({ capabilities: { can_configure: false, can_operate: true } });
    renderScreen();
    await screen.findByTestId("mail-settings-readonly");
    expect(h2Names()).toEqual(H2_ORDER);
    const checks = checksSection();
    expect(within(checks).getByRole("button", { name: "연결 확인" })).toBeEnabled();
    expect(within(checks).getByRole("button", { name: "시험 메일 보내기" })).toBeEnabled();
  });
});
