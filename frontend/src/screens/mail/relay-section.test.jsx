import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 메일 · 설정 탭의 「ClovirAssist 로컬 릴레이」 (계획 M7, D-551).
 *
 * 못박는 것:
 *   1) 보내는 방법 카드 둘이 다 고를 수 있고, 로컬 릴레이를 고르면 SMTP 서버 · 보안 구획 대신 로컬 릴레이 구획이 선다(점진 공개).
 *   2) 구성 요소 상태는 서버가 고른 낱말로 서고, 일반 화면에 구성 요소의 제품 이름이 없다(기술 정보 안에만).
 *   3) 「로컬 릴레이 활성화」는 저장한 설정으로만 한다 - 보내는 방법을 로컬 릴레이로 저장하기 전이나 저장하지 않은 수정 내용이 있으면 닫혀
 *      있고 까닭을 한 줄로 말한다. 거절되면 서버의 문장을 보인다.
 *   4) 「인터넷으로 직접 전달」을 고를 때만 서버 이름 · DKIM · 받는 도메인별 전달 서버가 보이고, 「상위 SMTP 이용」이면 상위 서버 칸이 보인다.
 *   5) 저장 본문에 로컬 릴레이 칸이 실리고 서버가 적는 칸(DKIM 공개키)은 실리지 않으며, 상위 SMTP 비밀번호는 같은 저장에 실린다.
 *   6) 준비 점검의 줄은 상태 · 지금 상태 · 할 일 · 고칠 곳을 말하고, 복사할 DNS 레코드는 펼쳐야 보인다.
 *   7) 상태 면은 「로컬 릴레이」 · 「바깥 전달」 두 줄을 더하고, 접수와 전달을 섞지 않는다.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", email: "me@goodmit.co.kr" } }),
}));

import { MailScreen } from "./MailScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../../ui/kit.jsx";
import { ThemeModeProvider } from "../../ui/ThemeModeProvider.jsx";

const RELAY_CONFIG = {
  delivery: "direct", smarthost: { host: "", port: 587, security: "starttls", username: "" }, helo_name: "mail.goodmit.co.kr",
  public_ip: "", ipv4_only: true, dkim_enabled: true, dkim_selector: "ca1", dkim_public: "QUJD",
  transport_overrides: [{ domain: "goodmit.co.kr", host: "goodmit-co-kr.mail.protection.outlook.com" }], compare_resolvers: [],
};

function settings(mode, relay = RELAY_CONFIG) {
  return {
    settings: {
      enabled: true, host: "", port: 587, security: "starttls", from_address: "noreply@goodmit.co.kr", from_name: "ClovirAssist",
      username: "", timeout_seconds: 20, tls_verify: true, ca_pem: "", mode, relay,
    },
    password: { stored: false }, relay_password: { stored: false }, presets: { ports: { starttls: 587, ssl: 465, none: 25 } }, limits: {},
  };
}

const RELAY_VIEW = {
  mode: "local_relay",
  component: {
    state: "ready", label: "구성 요소 준비됨", message: "이 서버에 설치돼 있고 꺼져 있습니다.", help: null, stale: false,
    technical: { packages: { postfix: "3.8.6", opendkim: "2.11" }, services: { postfix: "inactive" }, listeners: [] },
  },
  config: RELAY_CONFIG, password: { stored: false },
  dkim: { selector: "ca1", record_name: "ca1._domainkey.goodmit.co.kr", public: "QUJD", key_exists: true },
  readiness: {
    checked_at: "2026-10-02T01:00:00", delivery: "direct", state: "fail",
    checks: [
      { key: "relay_running", label: "로컬 릴레이 동작", state: "ok", message: "로컬 릴레이가 동작하고 있습니다." },
      { key: "ptr_fcrdns", label: "역방향 이름(PTR)", state: "fail", message: "공인 IP 의 역방향 이름(PTR)이 없습니다.",
        need: "역방향 이름을 등록해 달라고 요청하세요.", where: "회선이나 클라우드 업체" },
    ],
    records: [{ key: "spf", name: "goodmit.co.kr", type: "TXT", value: "v=spf1 ip4:221.147.80.10 ~all",
      note: "기존 SPF 에서 도메인이 아닌 항목(include:google-site-verification=QY1D)을 뺐습니다. 이 항목이 레코드 오류의 원인입니다." }],
    requests: [{ owner: "회선 또는 클라우드 업체", title: "PTR 등록 요청", why: "역방향 이름은 IP 를 준 쪽만 등록할 수 있습니다.",
      records: [{ key: "ptr", name: "221.147.80.10", type: "PTR", value: "mail.goodmit.co.kr" }],
      text: "공인 IP 221.147.80.10 의 역방향 이름(PTR 레코드)을 mail.goodmit.co.kr 로 등록해 주세요.\n" }],
  },
  outer: null,
};

let savedMode = "local_relay";
let relayView = RELAY_VIEW;
function status() {
  return {
    health: { state: "unverified", label: "확인 전", kind: "info", message: "연결을 아직 확인하지 않았습니다.", stages: [] },
    problems: [], summary: { ...settings(savedMode).settings, password: { stored: false } },
    counts: {}, recent_failures: [], backlog: { count: 0, window_days: 7 }, base_url: { value: "https://x", problem: null },
    relay: savedMode === "local_relay" ? {
      delivery: "direct", component: { state: "running", label: "동작 중", message: "", help: null, stale: false },
      outer: { status: "delivered", label: "수신측 메일 서버로 전달함", sentence: null, at: "2026-10-02T01:00:00" },
    } : null,
    capabilities: { can_configure: true, can_operate: true },
    notification_mail: { allowed: [], max_age_days: 7, catalog: [] },
  };
}

function route() {
  apiMock.mockImplementation((path, opts) => {
    const p = String(path);
    const method = (opts && opts.method) || "GET";
    if (p.startsWith("/api/admin/mail/status")) return Promise.resolve(status());
    if (p === "/api/admin/mail/settings" && method === "GET") return Promise.resolve(settings(savedMode));
    if (p === "/api/admin/mail/settings" && method === "PUT") {
      return Promise.resolve({ ...settings(opts.body.mode, opts.body.relay), verify: null, relay_apply: null });
    }
    if (p === "/api/admin/mail/relay" && method === "GET") return Promise.resolve(relayView);
    if (p === "/api/admin/mail/relay/apply") {
      return Promise.resolve({ result: { ok: false, message: "이 서버에는 기존 메일 발송 구성이 있습니다. ClovirAssist 로컬 릴레이가 자동으로 구성되지 않았습니다." }, relay: relayView, verify: null });
    }
    if (p.startsWith("/api/admin/mail/templates")) return Promise.resolve({ items: [] });
    if (p.startsWith("/api/admin/mail/deliveries")) return Promise.resolve({ items: [], total: 0, page: 1, page_size: 50 });
    return Promise.resolve({});
  });
}

beforeEach(() => {
  savedMode = "local_relay";
  relayView = RELAY_VIEW;
  apiMock.mockReset();
  route();
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={["/mail"]}>
              <MailScreen />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/* 「기술 정보」 접기 안을 뺀 화면 글. */
function visibleText(root) {
  const clone = root.cloneNode(true);
  clone.querySelectorAll("details").forEach((d) => d.remove());
  return clone.textContent;
}

describe("로컬 릴레이 — 보내는 방법과 점진 공개", () => {
  it("외부 SMTP 로 저장된 설치에서 로컬 릴레이를 고르면 구획이 바뀌고, 활성화는 저장 전까지 닫혀 있다", async () => {
    savedMode = "external";
    renderScreen();
    const form = await screen.findByTestId("mail-settings-form");
    expect(within(form).getByRole("heading", { name: "SMTP 서버" })).toBeInTheDocument();
    const relayCard = within(form).getByRole("radio", { name: /ClovirAssist 로컬 릴레이/ });
    expect(relayCard).not.toHaveAttribute("aria-disabled", "true");
    await userEvent.click(relayCard);
    expect(await within(form).findByRole("heading", { name: "로컬 릴레이" })).toBeInTheDocument();
    expect(within(form).queryByRole("heading", { name: "SMTP 서버" })).toBeNull();
    expect(within(form).queryByRole("heading", { name: "보안" })).toBeNull();
    const start = await within(form).findByRole("button", { name: "로컬 릴레이 활성화" });
    expect(start).toBeDisabled();
    expect(within(form).getByText("보내는 방법을 로컬 릴레이로 저장한 뒤에 활성화할 수 있습니다.")).toBeInTheDocument();
  });

  it("구성 요소 상태는 서버의 낱말이고, 일반 화면에 구성 요소의 제품 이름이 없다", async () => {
    renderScreen();
    const component = await screen.findByTestId("relay-component");
    expect(within(component).getByText("구성 요소 준비됨")).toBeInTheDocument();
    const form = screen.getByTestId("mail-settings-form");
    expect(visibleText(form)).not.toMatch(/postfix|opendkim/i);
  });

  it("거절된 활성화는 서버의 문장을 보인다", async () => {
    renderScreen();
    const start = await screen.findByRole("button", { name: "로컬 릴레이 활성화" });
    expect(start).toBeEnabled();
    await userEvent.click(start);
    expect(await screen.findByText(/기존 메일 발송 구성이 있습니다/)).toBeInTheDocument();
    expect(apiMock.mock.calls.some(([p, o]) => p === "/api/admin/mail/relay/apply" && o.method === "POST")).toBe(true);
  });

  it("직접 전달이면 서버 이름 · DKIM 선택자 · 전달 서버가, 상위 SMTP 면 상위 서버 칸이 선다", async () => {
    renderScreen();
    const form = await screen.findByTestId("mail-settings-form");
    expect(await within(form).findByLabelText(/서버 이름\(HELO\)/)).toHaveValue("mail.goodmit.co.kr");
    expect(within(form).getByLabelText("선택자")).toHaveValue("ca1");
    expect(within(form).getByTestId("relay-overrides")).toBeInTheDocument();
    await userEvent.click(within(form).getByRole("radio", { name: /상위 SMTP 이용/ }));
    expect(await within(form).findByRole("heading", { name: "상위 SMTP 서버" })).toBeInTheDocument();
    expect(within(form).queryByLabelText(/서버 이름\(HELO\)/)).toBeNull();
    // 저장하지 않은 수정 내용이 생겼으니 활성화와 점검이 닫힌다.
    expect(within(form).getByRole("button", { name: "로컬 릴레이 활성화" })).toBeDisabled();
    expect(within(form).getByRole("button", { name: "점검 다시 하기" })).toBeDisabled();
  });

  it("저장 본문에 로컬 릴레이 칸이 실리고 DKIM 공개키는 실리지 않으며 상위 SMTP 비밀번호가 같은 저장에 실린다", async () => {
    renderScreen();
    const form = await screen.findByTestId("mail-settings-form");
    await userEvent.click(await within(form).findByRole("radio", { name: /상위 SMTP 이용/ }));
    await userEvent.type(within(form).getByLabelText(/서버 주소/), "smtp.office365.com");
    await userEvent.type(within(form).getByLabelText("계정"), "notify@goodmit.co.kr");
    await userEvent.type(within(form).getByLabelText("비밀번호"), "pw-SENTINEL");
    await userEvent.click(within(form).getByRole("button", { name: "저장" }));
    await waitFor(() => expect(apiMock.mock.calls.some(([p, o]) => p === "/api/admin/mail/settings" && o && o.method === "PUT")).toBe(true));
    const [, opts] = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/mail/settings" && o && o.method === "PUT");
    expect(opts.body.mode).toBe("local_relay");
    expect(opts.body.relay.delivery).toBe("smarthost");
    expect(opts.body.relay.smarthost).toEqual({ host: "smtp.office365.com", port: 587, security: "starttls", username: "notify@goodmit.co.kr" });
    expect(opts.body.relay).not.toHaveProperty("dkim_public");
    expect(opts.body.relay_password).toBe("pw-SENTINEL");
    expect(opts.body.password).toBeUndefined();
  });

  it("조건 상자가 고르기 전부터 서고, 요청문은 담당자별로 복사할 수 있다", async () => {
    const user = userEvent.setup();
    renderScreen();
    expect(await screen.findByTestId("relay-direct-conditions")).toHaveTextContent("담당자가 없다면 상위 SMTP 이용을 고르세요.");
    expect(await screen.findByTestId("relay-summary")).toHaveTextContent(
      "준비 2개 중 1개를 통과했습니다. 지금 막는 것은 역방향 이름(PTR)입니다. 담당은 회선 또는 클라우드 업체입니다.",
    );
    const requests = screen.getByTestId("relay-requests");
    expect(within(requests).getByText("PTR 등록 요청")).toBeInTheDocument();
    expect(requests).toHaveTextContent("mail.goodmit.co.kr 로 등록해 주세요.");
    const write = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText: write }, configurable: true });
    await user.click(within(requests).getByRole("button", { name: "회선 또는 클라우드 업체 요청문 복사" }));
    await waitFor(() => expect(write).toHaveBeenCalledWith(expect.stringContaining("역방향 이름(PTR 레코드)")));
  });

  it("준비 점검의 줄이 상태 · 할 일 · 고칠 곳을 말하고, 표와 레코드는 「진단」 안에서 펼쳐야 보인다", async () => {
    renderScreen();
    await screen.findByTestId("relay-summary");
    expect(screen.queryByTestId("relay-checks")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "진단 펼치기" }));
    const checks = await screen.findByTestId("relay-checks");
    const ptr = checks.querySelector('[data-check="ptr_fcrdns"]');
    expect(ptr).toHaveAttribute("data-check-state", "fail");
    expect(within(ptr).getByText("실패")).toBeInTheDocument();
    expect(within(ptr).getByText("역방향 이름을 등록해 달라고 요청하세요.")).toBeInTheDocument();
    expect(within(ptr).getByText("고칠 곳: 회선이나 클라우드 업체")).toBeInTheDocument();
    expect(screen.queryByTestId("relay-records")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "복사할 DNS 레코드 펼치기" }));
    const records = screen.getByTestId("relay-records");
    expect(within(records).getByText("v=spf1 ip4:221.147.80.10 ~all")).toBeInTheDocument();
    // 합친 제안에서 뺀 항목과 그 까닭이 레코드 아래 한 줄로 선다(P18 랩: 도메인이 아닌 include).
    expect(within(records).getByText(/도메인이 아닌 항목\(include:google-site-verification=QY1D\)을 뺐습니다\./)).toBeInTheDocument();
    expect(within(records).getByRole("button", { name: "goodmit.co.kr 값 복사" })).toBeInTheDocument();
  });

  it("상태 면은 로컬 릴레이 · 바깥 전달 두 줄을 더하고 「도착」이라고 말하지 않는다", async () => {
    renderScreen();
    const lines = await screen.findByTestId("relay-lines");
    expect(within(lines).getByText("동작 중")).toBeInTheDocument();
    expect(within(lines).getByTestId("relay-outer")).toHaveTextContent("수신측 메일 서버로 전달함");
    expect(screen.getByTestId("mail-state").textContent).not.toMatch(/도착|받았습니다/);
  });
});
