import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* 서비스 주소 카드 · 바꾸기 대화 상자 (계획 M4, D-574 · 서버 계약 D-573).
 *
 * 못박는 것:
 *   1) 대표 주소와 「지금 접속한 주소」를 나란히 보이고, 다르면 주의 톤으로 별칭인지 · 모르는 이름인지 말한다.
 *   2) DNS 는 이 서버의 해석기 기준이다. 공개 해석기의 답은 정보 문장일 뿐 확인 점(정상)이 되지 않는다.
 *   3) 「고급」은 처음에 닫혀 있고, 열면 원문 값(바인드 주소 · server_name · env)이 보인다.
 *   4) 새 주소는 https · 이름 · 경로와 포트 없음만 받는다. 함께 쓸 주소의 기본은 지금 대표 주소다.
 *   5) 지금 인증서에 새 이름이 없으면 「지금 인증서 유지」를 고를 수 없다.
 *   6) 미리 확인에 실패가 있으면 적용 단추가 꺼진다. 적용은 한 번 묻고, 개인키는 PEM 방식일 때만 실린다.
 *   7) 성공은 「새 주소에서 다시 로그인하세요.」와 새 주소 링크, 실패는 되돌렸다는 문장이다.
 *   8) DNS · 프록시 줄은 도우미가 읽어 준 실제 값을 보이고, 호스트 이름 설명이 접속 주소와 섞이지 않는다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { SystemOps, dnsRow, proxyRow } from "./SystemOps.jsx";
import { recentRows } from "./system/ServiceAddressCard.jsx";
import {
  accessState, applyParams, certCoverage, isDomainName, normalizeAliases, orderedChecks, parseAddress, publicDnsText,
} from "./system/serviceAddress.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const OLD = "old.example.internal";
const NEW = "new.example.com";

function system(patch = {}) {
  return {
    available: true, status: "ok", detail: "",
    info: {
      hostname: "srv1", timezone: "Asia/Seoul", ntp_synchronized: "yes",
      units: { "clovirassist-web.service": "active" },
      dns: { configured: true, servers: ["10.0.0.53", "10.0.0.54"], search: "corp.example", source: "console" },
      proxy: { configured: false, url: null, no_proxy: null, source: "unset" },
    },
    certificate: { known: true, days_remaining: 300, self_signed: true },
    actions: [{ name: "system.info" }, { name: "dns.set" }, { name: "proxy.set" }, { name: "domain.apply" }],
    request: { host: OLD, authority: OLD, scheme: "https", url: `https://${OLD}` },
    domain: { canonical: OLD, dns_name: OLD, aliases: [], bind_ip: "10.0.0.5", cert_path: `/etc/clovirassist/tls/${OLD}.crt`,
      app_base_url: `https://${OLD}`, upstream_proxies: [] },
    ...patch,
  };
}

const CURRENT = {
  canonical: OLD, app_base_url: `https://${OLD}`, dns_name: OLD, aliases: [], bind_ip: "10.0.0.5", upstream_proxies: [],
  cert: { path: `/etc/clovirassist/tls/${OLD}.crt`, readable: true, subject: `CN = ${OLD}`, issuer: `CN = ${OLD}`,
    not_after: "2027-10-15T00:00:00+00:00", self_signed: true, sans: [OLD], ips: ["10.0.0.5"] },
  server_names: [OLD],
};

function cardPreview(patch = {}) {
  return {
    available: true, status: "ok", ok: true, detail: "서비스 주소를 확인했습니다.",
    preview: {
      target: { host: OLD, aliases: [], names: [OLD], changes: false },
      current: CURRENT,
      checks: [
        { key: "dns", label: "DNS", state: "ok", message: "이 서버가 쓰는 DNS 가 이 서버 주소로 풉니다.", technical: `${OLD}=10.0.0.5` },
        { key: "https", label: "HTTPS", state: "ok", message: "지금 인증서가 이 이름을 모두 담고 있습니다.", technical: null },
        { key: "web", label: "웹 서버", state: "ok", message: "웹 서버가 이 이름들로 들어오는 요청을 받습니다.", technical: OLD },
        { key: "app", label: "서비스 설정", state: "ok", message: "알림 메일과 링크가 씁니다.", technical: "APP_BASE_URL=x" },
      ],
      dns: { system: [{ name: OLD, answers: ["10.0.0.5"], error: null, state: "ok" }],
        compare: [{ name: OLD, answers: ["203.0.113.10"], error: null, resolver: "8.8.8.8" }] },
      impact: [], can_apply: true,
    },
    recent_applies: [],
    ...patch,
  };
}

function reviewPreview(webState = "warn") {
  return cardPreview({
    preview: {
      ...cardPreview().preview,
      target: { host: NEW, aliases: [OLD], names: [NEW, OLD], changes: true },
      checks: [
        { key: "dns", label: "DNS", state: "warn", message: "다른 주소(203.0.113.10)로 풉니다." },
        { key: "https", label: "HTTPS", state: "warn", message: `지금 인증서에 ${NEW}가 없습니다.` },
        { key: "web", label: "웹 서버", state: webState, message: webState === "fail" ? "다른 웹 서버 설정이 이 이름을 이미 씁니다." : "적용하면 더합니다." },
        { key: "app", label: "서비스 설정", state: "warn", message: "적용하면 바뀝니다." },
      ],
      impact: ["새 주소로 처음 들어올 때 한 번 다시 로그인해야 합니다. 로그인은 주소마다 따로 유지됩니다."],
      can_apply: webState !== "fail",
    },
  });
}

let state;
let card;
let review;
let applied;
function route() {
  apiMock.mockImplementation((path, opts) => {
    const p = String(path);
    const method = (opts && opts.method) || "GET";
    if (p === "/api/admin/system" && method === "GET") return Promise.resolve(state);
    if (p === "/api/admin/system/domain") return Promise.resolve(card);
    if (p.startsWith("/api/admin/system/domain?")) return Promise.resolve(review);
    if (p === "/api/admin/system/domain.apply" && method === "POST") return Promise.resolve(applied);
    return Promise.resolve({});
  });
}

beforeEach(() => {
  apiMock.mockReset();
  state = system();
  card = cardPreview();
  review = reviewPreview();
  applied = {
    available: true, status: "ok", ok: true, changed: true, rolled_back: false, detail: `대표 주소를 ${NEW}로 바꿨습니다.`,
    data: {
      host: NEW, aliases: [OLD], url: `https://${NEW}`, warnings: [],
      web_restart: { scheduled: true, delay_seconds: 3, unit: "clovirassist-web-restart" },
      steps: [
        { name: "validate", label: "입력 확인", ok: true, detail: "확인했습니다." },
        { name: "cert", label: "인증서", ok: true, detail: "자체 서명 인증서를 새로 만들었습니다." },
        { name: "check", label: "자체 확인", ok: true, detail: "로그인 화면까지 확인했습니다." },
      ],
    },
  };
  route();
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true })));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <SystemOps embedded />
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function rowOf(root, label) {
  return within(root).getByText(label).closest(".k-settingrow");
}

describe("서비스 주소 — 순수 함수", () => {
  it("새 주소는 https 이름만 받고 경로 · 포트 · IP · http 를 거절한다", () => {
    expect(parseAddress(`https://${NEW}`)).toEqual({ host: NEW });
    expect(parseAddress(`${NEW.toUpperCase()}/`)).toEqual({ host: NEW });
    expect(parseAddress(`http://${NEW}`).error).toBe("https 주소만 쓸 수 있습니다.");
    expect(parseAddress(`https://${NEW}/login`).error).toBe("경로 없이 주소만 넣으세요.");
    expect(parseAddress(`https://${NEW}:8443`).error).toBe("포트 없이 주소만 넣으세요.");
    expect(parseAddress("https://10.0.0.5").error).toBe("IP 주소가 아니라 이름을 넣으세요.");
    expect(parseAddress("localhost").error).toMatch(/올바른 도메인 이름이 아닙니다/);
    expect(parseAddress("").error).toBe("새 주소를 넣으세요.");
    expect(isDomainName("bad_name.example.com")).toBe(false);
  });

  it("지금 접속한 주소를 대표 · 별칭 · 모르는 이름으로 가른다", () => {
    const domain = { canonical: NEW, aliases: [OLD] };
    expect(accessState({ host: NEW }, domain).kind).toBe("canonical");
    expect(accessState({ host: OLD }, domain).message).toBe("대표 주소와 다릅니다. 이 주소는 함께 쓰는 주소(별칭)입니다.");
    expect(accessState({ host: "10.0.0.5" }, domain).message).toBe("대표 주소와 다릅니다. 이 서버가 모르는 이름입니다.");
  });

  it("인증서가 이름을 담는지, 함께 쓸 주소의 정리, 확인 넷의 순서", () => {
    expect(certCoverage({ readable: true, sans: [OLD] }, [NEW, OLD])).toEqual({ known: true, missing: [NEW] });
    expect(certCoverage({ readable: false }, [NEW]).known).toBe(false);
    expect(normalizeAliases([OLD, OLD.toUpperCase(), NEW, ""], NEW)).toEqual([OLD]);
    expect(orderedChecks([{ key: "app", state: "ok" }]).map((c) => [c.key, c.state])).toEqual(
      [["dns", "unknown"], ["https", "unknown"], ["web", "unknown"], ["app", "ok"]]);
    expect(publicDnsText({ compare: [{ resolver: "8.8.8.8", answers: ["203.0.113.10"] }] })).toBe("공개 DNS 8.8.8.8의 답은 203.0.113.10입니다.");
    expect(publicDnsText({ compare: [] })).toBeNull();
  });

  it("적용 본문은 PEM 방식일 때만 개인키를 싣는다", () => {
    expect(applyParams({ host: NEW, aliases: [OLD], strategy: "self_signed", certificate: "C", privateKey: "K", restartWeb: true }))
      .toEqual({ host: NEW, aliases: [OLD], cert: { strategy: "self_signed" }, restart_web: true });
    expect(applyParams({ host: NEW, aliases: [], strategy: "provided", certificate: "C", privateKey: "K", restartWeb: false }).cert)
      .toEqual({ strategy: "provided", certificate: "C", private_key: "K" });
  });

  it("최근 오류는 마지막 성공보다 뒤에 난 실패만이다", () => {
    const ok = { at: "2026-10-15T01:00:00", ok: true };
    const bad = { at: "2026-10-15T02:00:00", ok: false };
    expect(recentRows([bad, ok])).toEqual({ success: ok, failure: bad });
    expect(recentRows([{ ...ok, at: "2026-10-15T03:00:00" }, bad]).failure).toBeNull();
  });
});

describe("서비스 주소 카드", () => {
  it("대표 주소와 지금 접속한 주소를 보이고, 대표로 접속했으면 경고하지 않는다", async () => {
    renderScreen();
    const cardEl = await screen.findByTestId("service-address");
    expect(within(rowOf(cardEl, "대표 주소")).getByText(`https://${OLD}`)).toBeInTheDocument();
    expect(within(rowOf(cardEl, "지금 접속한 주소")).getByText("대표 주소로 접속했습니다.")).toBeInTheDocument();
    expect(within(cardEl).queryByTestId("service-address-access")).toBeNull();
    expect(within(cardEl).getByRole("heading", { name: "서비스 주소" })).toBeInTheDocument();
  });

  it("별칭으로 들어오면 주의 톤과 별칭 문장, 모르는 이름이면 그 문장이다", async () => {
    state = system({ request: { host: OLD, url: `https://${OLD}` }, domain: { ...system().domain, canonical: NEW, aliases: [OLD] } });
    const first = renderScreen();
    const access = await screen.findByTestId("service-address-access");
    expect(access).toHaveAttribute("data-dot-label", "warn");
    expect(screen.getByText("대표 주소와 다릅니다. 이 주소는 함께 쓰는 주소(별칭)입니다.")).toBeInTheDocument();
    first.unmount();
    state = system({ request: { host: "10.0.0.5", url: "https://10.0.0.5" } });
    renderScreen();
    expect(await screen.findByText("대표 주소와 다릅니다. 이 서버가 모르는 이름입니다.")).toBeInTheDocument();
  });

  it("DNS 는 이 서버 기준으로 판정하고 공개 답은 정보 문장일 뿐이다", async () => {
    renderScreen();
    const checks = await screen.findByTestId("service-address-checks");
    await waitFor(() => expect(checks.querySelector('[data-check="dns"]')).toHaveAttribute("data-check-state", "ok"));
    expect(within(checks).getAllByText(/정상$/)).toHaveLength(4);
    const row = rowOf(screen.getByTestId("service-address"), "상태");
    expect(within(row).getByText(/DNS는 사내 해석기\(이 서버가 쓰는 해석기\) 기준입니다\. 공개 DNS 8\.8\.8\.8의 답은 203\.0\.113\.10입니다\./))
      .toBeInTheDocument();
    expect(within(checks).queryByText(/공개/)).toBeNull();
  });

  it("「고급」은 처음에 닫혀 있고 열면 원문 값이 보인다", async () => {
    const user = userEvent.setup();
    renderScreen();
    const cardEl = await screen.findByTestId("service-address");
    const toggle = within(cardEl).getByRole("button", { name: "고급" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(cardEl).queryByText("바인드 주소")).toBeNull();
    await user.click(toggle);
    expect(within(cardEl).getByText("바인드 주소")).toBeInTheDocument();
    expect(within(cardEl).getByText("10.0.0.5")).toBeInTheDocument();
    expect(within(cardEl).getByText(`/etc/clovirassist/tls/${OLD}.crt`)).toBeInTheDocument();
  });

  it("최근 적용 · 최근 오류는 감사 기록에서 온다", async () => {
    card = cardPreview({ recent_applies: [
      { at: "2026-10-15T02:00:00", ok: false, detail: "새 주소로 접속하는 확인을 통과하지 못했습니다.", rolled_back: true, actor: "관리자" },
      { at: "2026-10-14T02:00:00", ok: true, detail: `대표 주소를 ${OLD}로 바꿨습니다.`, rolled_back: false, actor: "관리자" },
    ] });
    renderScreen();
    expect(await screen.findByText("새 주소로 접속하는 확인을 통과하지 못했습니다. 바꾸기 전 설정으로 되돌렸습니다.")).toBeInTheDocument();
    expect(screen.getByText(`대표 주소를 ${OLD}로 바꿨습니다. 관리자님이 적용했습니다.`)).toBeInTheDocument();
  });
});

async function openDialog(user) {
  renderScreen();
  const cardEl = await screen.findByTestId("service-address");
  await waitFor(() => expect(within(cardEl).getByRole("button", { name: "주소 바꾸기" })).toBeEnabled());
  await user.click(within(cardEl).getByRole("button", { name: "주소 바꾸기" }));
  return screen.findByRole("dialog", { name: "서비스 주소 바꾸기" });
}

describe("서비스 주소 바꾸기 대화 상자", () => {
  it("새 주소를 거르고, 함께 쓸 주소의 기본은 지금 대표 주소이며, 이름이 없는 인증서는 유지할 수 없다", async () => {
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    const field = within(dialog).getByLabelText(/새 주소/);
    await user.type(field, `http://${NEW}`);
    await user.tab();
    expect(within(dialog).getByText("https 주소만 쓸 수 있습니다.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "미리 확인" })).toBeDisabled();
    await user.clear(field);
    await user.type(field, `https://${NEW}`);
    expect(within(dialog).getByRole("checkbox", { name: `${OLD} 함께 쓰기` })).toBeChecked();
    expect(within(dialog).getByRole("radio", { name: /지금 인증서 유지/ })).toHaveAttribute("aria-disabled", "true");
    expect(within(dialog).getByRole("checkbox", { name: "웹 서버를 3초 뒤 다시 시작" })).toBeChecked();
    expect(within(dialog).getByText("약 3초 동안 접속이 끊깁니다.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "미리 확인" })).toBeEnabled();
  });

  it("미리 확인에 실패가 있으면 적용 단추가 꺼진다", async () => {
    const user = userEvent.setup();
    review = reviewPreview("fail");
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByLabelText(/새 주소/), NEW);
    await user.click(within(dialog).getByRole("button", { name: "미리 확인" }));
    const checks = await within(dialog).findByTestId("domain-checks");
    expect(checks.querySelector('[data-check="web"]')).toHaveAttribute("data-check-state", "fail");
    expect(within(dialog).getByText("실패한 확인이 있어 적용할 수 없습니다. 그 항목을 수정한 뒤 다시 확인하세요.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "적용" })).toBeDisabled();
    const sent = apiMock.mock.calls.map(([p]) => String(p)).find((p) => p.startsWith("/api/admin/system/domain?"));
    expect(sent).toBe(`/api/admin/system/domain?host=${NEW}&aliases=${OLD}`);
  });

  it("적용은 한 번 묻고, 성공하면 새 주소에서 다시 로그인하라고 말한다", async () => {
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByLabelText(/새 주소/), `https://${NEW}`);
    await user.click(within(dialog).getByRole("button", { name: "미리 확인" }));
    expect(await within(dialog).findByTestId("domain-impact")).toHaveTextContent("다시 로그인해야 합니다");
    expect(within(dialog).getByTestId("domain-impact")).toHaveTextContent("약 3초 동안 접속이 끊깁니다.");
    await user.click(within(dialog).getByRole("button", { name: "적용" }));
    const ask = await screen.findByRole("dialog", { name: "서비스 주소를 바꿀까요?" });
    await user.click(within(ask).getByRole("button", { name: "적용" }));
    await waitFor(() => expect(apiMock.mock.calls.some(([p, o]) => p === "/api/admin/system/domain.apply" && o.method === "POST")).toBe(true));
    const [, opts] = apiMock.mock.calls.find(([p]) => p === "/api/admin/system/domain.apply");
    expect(opts.body).toEqual({ params: { host: NEW, aliases: [OLD], cert: { strategy: "self_signed" }, restart_web: true } });
    expect(await within(dialog).findByText("새 주소에서 다시 로그인하세요.", { exact: false })).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: `https://${NEW}/login` })).toHaveAttribute("href", `https://${NEW}/login`);
    expect(within(dialog).getByTestId("domain-restart")).toHaveTextContent("웹 서버를 다시 시작하는 중입니다.");
    expect(within(dialog).getByTestId("domain-steps").querySelectorAll('[data-step-state="ok"]')).toHaveLength(3);
  });

  it("웹 서버 재시작은 예약한 시간 뒤 같은 주소의 /healthz 로 확인한다", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByLabelText(/새 주소/), NEW);
    await user.click(within(dialog).getByRole("button", { name: "미리 확인" }));
    await user.click(await within(dialog).findByRole("button", { name: "적용" }));
    await user.click(within(await screen.findByRole("dialog", { name: "서비스 주소를 바꿀까요?" })).getByRole("button", { name: "적용" }));
    await within(dialog).findByTestId("domain-restart");
    expect(fetch).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    await waitFor(() => expect(within(dialog).getByTestId("domain-restart")).toHaveAttribute("data-restart", "up"));
    expect(fetch).toHaveBeenCalledWith("/healthz", expect.objectContaining({ cache: "no-store" }));
  });

  it("실패하면 되돌렸다는 문장과 단계별 결과를 보인다", async () => {
    const user = userEvent.setup();
    applied = { available: true, status: "ok", ok: false, changed: false, rolled_back: true,
      detail: "새 주소로 접속하는 확인을 통과하지 못했습니다.",
      data: { steps: [
        { name: "check", label: "자체 확인", ok: false, detail: "확인을 통과하지 못했습니다.", technical: "https://x/healthz -> 502" },
        { name: "rollback", label: "되돌리기", ok: true, detail: "바꾸기 전 설정으로 되돌리고 웹 서버가 다시 읽게 했습니다." },
      ] } };
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByLabelText(/새 주소/), NEW);
    await user.click(within(dialog).getByRole("button", { name: "미리 확인" }));
    await user.click(await within(dialog).findByRole("button", { name: "적용" }));
    await user.click(within(await screen.findByRole("dialog", { name: "서비스 주소를 바꿀까요?" })).getByRole("button", { name: "적용" }));
    expect(await within(dialog).findByText("새 주소로 접속하는 확인을 통과하지 못했습니다. 바꾸기 전 설정으로 되돌렸습니다.")).toBeInTheDocument();
    expect(within(dialog).getByTestId("domain-steps").querySelector('[data-step="check"]')).toHaveAttribute("data-step-state", "failed");
    expect(within(dialog).queryByRole("link")).toBeNull();
  });
});

describe("OS와 서비스 — DNS · 프록시 · 호스트 이름 줄", () => {
  it("DNS · 프록시는 도우미가 읽어 준 실제 값이다", async () => {
    renderScreen();
    await screen.findByText("DNS 서버");
    const dns = screen.getByText("DNS 서버").closest(".k-settingrow");
    expect(within(dns).getByText("10.0.0.53, 10.0.0.54")).toBeInTheDocument();
    expect(within(dns).getByText(/검색 도메인은 corp\.example입니다\./)).toBeInTheDocument();
    const proxy = screen.getByText("아웃바운드 프록시").closest(".k-settingrow");
    expect(within(proxy).getByText("지정하지 않음")).toBeInTheDocument();
    expect(within(proxy).queryByText("서버에서만 확인할 수 있습니다")).toBeNull();
  });

  it("값 함수는 지정 · 미지정 · 못 읽음을 가른다", () => {
    expect(dnsRow({ source: "unreadable" }).value).toBe("확인하지 못했습니다");
    expect(dnsRow({ configured: false, servers: [], source: "unset" }).value).toBe("지정하지 않음");
    expect(proxyRow({ configured: true, url: "http://proxy:3128", no_proxy: "localhost", source: "console" }))
      .toEqual({ value: "http://proxy:3128", muted: false, note: "예외는 localhost입니다." });
  });

  it("호스트 이름은 접속 주소 · 인증서 · 메일 서버 이름과 별개라고 말한다", async () => {
    renderScreen();
    await screen.findByText("호스트 이름");
    const row = screen.getByText("호스트 이름").closest(".k-settingrow");
    expect(row).toHaveTextContent("접속 주소, 인증서, 메일 서버 이름(HELO)과는 별개이며");
    expect(row).not.toHaveTextContent("인증서와 메일 발신 주소가 이 이름을 씁니다");
  });

  it("도우미가 없으면 서비스 주소는 판이 아니라 설정 목록의 한 줄이다", async () => {
    state = { ...system(), available: false, status: "not_installed", detail: "시스템 설정 도우미가 설치되어 있지 않습니다.", info: {} };
    renderScreen();
    await screen.findByText("서비스 주소");
    expect(screen.queryByTestId("service-address")).toBeNull();
    expect(apiMock.mock.calls.some(([p]) => String(p).startsWith("/api/admin/system/domain"))).toBe(false);
  });
});
