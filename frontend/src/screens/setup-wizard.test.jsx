import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 초기 설정 체크리스트 화면 (9-3 · D-520 · D-534).
 *
 * 이 화면이 지켜야 하는 것은 예쁘게 그리는 것이 아니라 **서버가 말한 사실을 바꾸지 않는 것**이다.
 *
 *   ① 서버가 준 **순서 그대로** 필수 · 선택 구획에 그린다. 상태로 다시 정렬하지 않는다.
 *   ② 상태를 **낱말로** 말한다(색과 아이콘만으로 말하지 않는다). 상태 낱말은 서버가 준다.
 *   ③ 지금 할 줄은 하나뿐이고 저절로 펼쳐지며, 요약 띠의 주 동작이 그 항목의 화면으로 간다.
 *   ④ 선택 값은 서버의 선택 API 하나로 바꾸고, 돌아온 체크리스트로 바로 다시 그린다(다른 선택을 덮지 않는다).
 *   ⑤ **없는 화면으로 보내지 않는다.** 링크는 실제로 라우팅되는 경로다.
 *
 * qa-contract-change: 초기 설정이 카드 격자에서 체크리스트가 됐다(D-534). 항목은 카드가 아니라 한 판 위의 줄이고, 번호(1/6)와
 * 「목록 접기」가 없어졌으며, 상태는 넷(됨 · 안 됨 · 확인 불가 · 사용하지 않음)에서 서버가 고르는 일곱(완료 · 해야 함 · 확인 필요 ·
 * 정하지 않음 · 문제 있음 · 사용하지 않음 · 앞 항목 대기)이 됐다. 진행 문장은 화면이 세지 않고 서버의 `headline` · `subline` 을 그린다
 * (그래서 `setupProgressText` 와 그 시험을 걷었다). 「사용하지 않음」은 범용 설정 API 로 객체 전체를 덮지 않고
 * `PUT /api/admin/setup/choices/{key}` 로 한 값만 보낸다. 지금 할 줄은 목록에서 할 일을 숨기지 않고 저절로 펼쳐진다 — 요약 띠의
 * 주 동작과 줄의 이동 단추가 같은 화면을 가리킨다(띠는 지름길, 줄은 모든 줄이 같은 모양). 끝난 줄은 단추를 세우지 않고 펼친 칸에
 * 이동 링크와 선택 되돌리기를 둔다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
let mockRole = "system_admin";
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: mockRole, id: "u-1" } }),
}));
const copyMock = vi.fn(() => Promise.resolve(true));
vi.mock("./ops/opsHelpers.js", async (importOriginal) => ({
  ...(await importOriginal()),
  copyText: (...args) => copyMock(...args),
}));

import { SetupWizard, SETUP_LINKS } from "./SetupWizard.jsx";
import { REGISTRY } from "./registry.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const CHECKLIST = "/api/admin/setup/checklist";
const STATUS_LABELS = {
  done: "완료", todo: "해야 함", check: "확인 필요", pending: "정하지 않음",
  problem: "문제 있음", skipped: "사용하지 않음", waiting: "앞 항목 대기",
};
const STATE_OF = { done: "done", skipped: "skipped", check: "unknown" };

function item(key, label, status, extra = {}) {
  return {
    key,
    label,
    why: `${label} 가 안 되면 화면이 빕니다.`,
    state: STATE_OF[status] || "todo",
    status,
    status_label: STATUS_LABELS[status],
    detail: `${label} 상태 설명`,
    action: ["todo", "pending", "problem", "waiting"].includes(status) ? `${label} 를 채우세요` : null,
    question: status === "check" ? `${label} 를 확인해 주세요` : null,
    required: true,
    requires: [],
    requires_why: "",
    blocked_by: null,
    blocked_by_label: null,
    notes: [],
    command: null,
    choices: [],
    checked_at: null,
    ...extra,
  };
}

// 서버(`build_setup_checklist`)가 주는 모양 그대로 — 지금 할 줄, 필수 진행, 요약 두 문장.
function payload(items, extra = {}) {
  const open = items.filter((i) => i.state !== "done" && i.state !== "skipped");
  const requiredRemaining = open.filter((i) => i.required).map((i) => i.key);
  const requiredTotal = items.filter((i) => i.required).length;
  const current = (open.find((i) => !i.blocked_by && i.required) || open.find((i) => !i.blocked_by) || {}).key || null;
  return {
    items: items.map((i) => ({ ...i, current: i.key === current })),
    next_key: current,
    current_key: current,
    required_total: requiredTotal,
    required_done: requiredTotal - requiredRemaining.length,
    required_remaining: requiredRemaining,
    complete: !requiredRemaining.length,
    headline: requiredRemaining.length ? `필수 설정 ${requiredRemaining.length}개가 남았습니다.` : "기본 설정이 끝났습니다.",
    subline: requiredRemaining.length ? `필수 ${requiredTotal}개 중 ${requiredTotal - requiredRemaining.length}개가 끝났습니다.` : "선택 기능도 모두 정했습니다.",
    ...extra,
  };
}

// 갓 설치한 세계: 관리자는 있고, 조직이 비었고, TLS 는 인증서 경로가 없으며, 메일은 아직 정하지 않았고, AI 는 조직을 기다린다.
function freshItems() {
  return [
    item("admin_account", "관리자 계정", "done", { href: "#/users", link_label: "사용자 화면 열기" }),
    item("mail", "메일 발송", "pending", {
      required: false, optional_choice: "mail", choice: "use", configured: false,
      href: "#/mail?tab=settings", link_label: "메일 설정 열기",
      choices: [{ key: "mail", value: "unused", label: "사용하지 않음" }],
    }),
    item("organization", "조직과 부서", "todo", { href: "#/departments", link_label: "부서 화면 열기", requires: ["admin_account"] }),
    item("llm", "AI", "waiting", {
      required: false, optional_choice: "llm", choice: "use",
      requires: ["organization"], requires_why: "조직 단위가 없으면 AI 가 살아 있어도 답이 비어 있습니다.",
      blocked_by: "organization", blocked_by_label: "조직과 부서",
      href: "#/ai-connection", link_label: "AI 연결 열기",
    }),
    item("integrations", "외부 연동", "done", { required: false, href: "#/diagnostics", link_label: "진단에서 연동 상태 보기" }),
    item("tls", "TLS 인증서", "todo", {
      detail: "인증서 파일을 찾지 못했습니다.", href: "#/diagnostics", link_label: "진단에서 인증서 확인",
      choices: [{ key: "tls", value: "proxy", label: "외부 프록시가 맡음" }],
    }),
  ];
}

function renderWizard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <SetupWizard />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

function serve(body) {
  apiMock.mockImplementation((path) => Promise.resolve(path === CHECKLIST ? body : {}));
}

const keysIn = (root) => Array.from(root.querySelectorAll("[data-setup-key]")).map((n) => n.getAttribute("data-setup-key"));

beforeEach(() => {
  mockRole = "system_admin";
  apiMock.mockReset();
  copyMock.mockClear();
  serve(payload(freshItems()));
});

// ── ① 순서와 구획 ────────────────────────────────────────────────────────────

describe("순서와 구획", () => {
  it("필수와 선택이 다른 구획에 서고, 구획 안에서는 서버가 준 순서 그대로다", async () => {
    renderWizard();
    await screen.findByTestId("setup-item-organization");
    const required = screen.getByRole("list", { name: "필수 항목" });
    const optional = screen.getByRole("list", { name: "선택 항목" });
    expect(keysIn(required)).toEqual(["admin_account", "organization", "tls"]);
    expect(keysIn(optional)).toEqual(["mail", "llm", "integrations"]);
    expect(screen.getByRole("heading", { level: 2, name: "필수" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "선택" })).toBeInTheDocument();
  });

  it("끝난 항목을 아래로 밀어내거나 빼지 않는다", async () => {
    renderWizard();
    const required = await screen.findByRole("list", { name: "필수 항목" });
    expect(keysIn(required)[0]).toBe("admin_account");
  });

  it("항목은 카드가 아니라 한 판 위의 줄이다 — 번호와 「목록 접기」가 없다", async () => {
    renderWizard();
    const org = await screen.findByTestId("setup-item-organization");
    expect(org.tagName).toBe("LI");
    expect(org.closest("[data-surface='plate']")).toBe(screen.getByTestId("setup-checklist"));
    expect(org.querySelector("[data-surface]")).toBeNull();
    expect(screen.queryByText(/\d\/\d/)).toBeNull();
    expect(screen.queryByRole("button", { name: /목록 접기|목록 펼치기/ })).toBeNull();
  });
});

// ── ② 상태 낱말 ──────────────────────────────────────────────────────────────

describe("상태", () => {
  it("상태를 아이콘 모양과 낱말로 말한다 — 낱말은 서버가 준 것이다", async () => {
    renderWizard();
    await screen.findByTestId("setup-item-organization");
    const expectRow = (key, status, label) => {
      const row = screen.getByTestId("setup-item-" + key);
      expect(row).toHaveAttribute("data-row-status", status);
      expect(row.querySelector(`[data-status-icon="${status}"]`)).not.toBeNull();
      expect(within(row).getByText(label, { selector: "[data-status-label]" })).toBeInTheDocument();
    };
    expectRow("admin_account", "done", "완료");
    expectRow("organization", "todo", "해야 함");
    expectRow("mail", "pending", "정하지 않음");
    expectRow("llm", "waiting", "앞 항목 대기");
    expectRow("tls", "todo", "해야 함");
  });

  it("일곱 상태의 아이콘 모양이 모두 다르다", async () => {
    const statuses = ["done", "todo", "check", "pending", "problem", "skipped", "waiting"];
    serve(payload(statuses.map((s, i) => item("k" + i, "항목 " + i, s))));
    renderWizard();
    await screen.findByTestId("setup-item-k0");
    const icons = statuses.map((s, i) => screen.getByTestId("setup-item-k" + i).querySelector("[data-status-icon] path").getAttribute("d"));
    expect(new Set(icons).size).toBe(statuses.length);
  });

  it("줄의 설명은 지금 상태 한 문장이다", async () => {
    renderWizard();
    const tls = await screen.findByTestId("setup-item-tls");
    expect(within(tls).getByText("인증서 파일을 찾지 못했습니다.")).toBeInTheDocument();
  });
});

// ── ③ 지금 할 줄과 요약 띠 ────────────────────────────────────────────────────

describe("지금 할 차례와 요약 띠", () => {
  it("지금 할 줄은 하나뿐이고 저절로 펼쳐져 할 일과 까닭을 말한다", async () => {
    renderWizard();
    const org = await screen.findByTestId("setup-item-organization");
    expect(screen.getAllByText("지금 할 차례")).toHaveLength(1);
    expect(org).toHaveAttribute("aria-current", "step");
    expect(within(org).getByText("지금 할 차례")).toBeInTheDocument();
    const toggle = within(org).getByRole("button", { name: "조직과 부서 자세히 보기" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(toggle.getAttribute("aria-controls"));
    expect(panel).not.toBeNull();
    expect(within(panel).getByText("조직과 부서 를 채우세요")).toBeInTheDocument();
    expect(within(panel).getByText(/화면이 빕니다/)).toBeInTheDocument();
    // 다른 줄은 접혀 있다.
    expect(within(screen.getByTestId("setup-item-tls")).getByRole("button", { name: "TLS 인증서 자세히 보기" }))
      .toHaveAttribute("aria-expanded", "false");
  });

  it("요약 띠는 서버의 두 문장과 필수 진행을 그리고, 주 동작은 지금 할 항목의 화면으로 간다", async () => {
    renderWizard();
    const band = await screen.findByTestId("setup-summary");
    expect(within(band).getByRole("heading", { level: 2, name: "필수 설정 2개가 남았습니다." })).toBeInTheDocument();
    expect(band).toHaveTextContent("필수 3개 중 1개가 끝났습니다.");
    const bar = within(band).getByRole("progressbar", { name: "필수 설정 진행" });
    expect(bar).toHaveAttribute("aria-valuenow", "1");
    expect(bar).toHaveAttribute("aria-valuemax", "3");
    const links = within(band).getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveTextContent("부서 화면 열기");
    expect(links[0].getAttribute("href")).toBe("#/departments");
    expect(links[0].className).toMatch(/containedPrimary/);
  });

  it("요약 띠가 문서 순서의 앞이다 — 좁은 화면에서도 띠가 목록 위에 선다", async () => {
    renderWizard();
    const band = await screen.findByTestId("setup-summary");
    const org = screen.getByTestId("setup-item-organization");
    expect(band.compareDocumentPosition(org) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("전부 끝나도 목록은 그대로 남고, 지금 할 차례도 주 동작도 없다", async () => {
    const done = freshItems().map((i) => ({ ...i, state: "done", status: "done", status_label: "완료", action: null, blocked_by: null, blocked_by_label: null, choices: [] }));
    serve(payload(done));
    renderWizard();
    const band = await screen.findByTestId("setup-summary");
    expect(band).toHaveAttribute("data-band-status", "done");
    expect(within(band).getByRole("heading", { level: 2, name: "기본 설정이 끝났습니다." })).toBeInTheDocument();
    expect(within(band).queryByRole("link")).toBeNull();
    expect(screen.queryByText("지금 할 차례")).toBeNull();
    expect(document.querySelectorAll("[data-setup-key]")).toHaveLength(6);
  });

  it("필수가 끝나면 선택 항목에 문제가 있어도 띠는 완료이고 둘째 문장이 그 사실을 말한다", async () => {
    const items = freshItems().map((i) => (i.required
      ? { ...i, state: "done", status: "done", status_label: "완료", action: null }
      : i.key === "mail" ? { ...i, status: "problem", status_label: "문제 있음", configured: true, choices: [] } : i));
    serve(payload(items, { subline: "메일 발송에 문제가 있습니다." }));
    renderWizard();
    const band = await screen.findByTestId("setup-summary");
    expect(band).toHaveAttribute("data-band-status", "done");
    expect(band).toHaveTextContent("메일 발송에 문제가 있습니다.");
  });
});

// ── 줄의 동작 ────────────────────────────────────────────────────────────────

describe("줄의 동작", () => {
  it("할 일이 있는 줄만 줄 위에 단추가 선다 — 끝난 줄과 앞 항목을 기다리는 줄에는 없다", async () => {
    renderWizard();
    await screen.findByTestId("setup-item-organization");
    const inline = (key) => screen.getByTestId("setup-item-" + key).querySelector("[data-row-actions]");
    expect(inline("admin_account")).toBeNull();
    expect(inline("integrations")).toBeNull();
    expect(inline("llm")).toBeNull();
    expect(within(inline("organization")).getByRole("link", { name: "부서 화면 열기" }).getAttribute("href")).toBe("#/departments");
    expect(within(inline("mail")).getByRole("button", { name: "사용하지 않음" })).toBeInTheDocument();
    expect(within(inline("tls")).getByRole("button", { name: "외부 프록시가 맡음" })).toBeInTheDocument();
  });

  it("끝난 줄을 펼치면 이동 링크와 선택 되돌리기가 펼친 칸에 있다", async () => {
    const user = userEvent.setup();
    const items = freshItems().map((i) => (i.key === "tls"
      ? { ...i, state: "done", status: "done", status_label: "완료", action: null, detail: "외부 프록시가 TLS 를 맡습니다.",
        notes: ["프록시 인증서의 만료일은 이 서버가 확인하지 않습니다."], choices: [{ key: "tls", value: "app", label: "이 서버의 인증서 사용" }] }
      : i));
    serve(payload(items));
    renderWizard();
    const tls = await screen.findByTestId("setup-item-tls");
    await user.click(within(tls).getByRole("button", { name: "TLS 인증서 자세히 보기" }));
    expect(within(tls).getByRole("button", { name: "TLS 인증서 자세히 보기" })).toHaveAttribute("aria-expanded", "true");
    expect(within(tls).getByText("프록시 인증서의 만료일은 이 서버가 확인하지 않습니다.")).toBeInTheDocument();
    expect(within(tls).getByRole("button", { name: "이 서버의 인증서 사용" })).toBeInTheDocument();
    expect(within(tls).getByRole("link", { name: "진단에서 인증서 확인" })).toBeInTheDocument();
  });

  it("앞 항목을 기다리는 줄은 무엇 때문에 막혔는지 앞 항목의 이름으로 말한다", async () => {
    const user = userEvent.setup();
    renderWizard();
    const llm = await screen.findByTestId("setup-item-llm");
    await user.click(within(llm).getByRole("button", { name: "AI 자세히 보기" }));
    expect(within(llm).getByText(/조직과 부서를 먼저 끝내야 이 항목을 진행할 수 있습니다\./)).toBeInTheDocument();
    expect(within(llm).getByText(/AI 가 살아 있어도 답이 비어 있습니다/)).toBeInTheDocument();
  });

  it("펼침 단추를 다시 누르면 접힌다 — 지금 할 줄도 사람이 접을 수 있다", async () => {
    const user = userEvent.setup();
    renderWizard();
    const org = await screen.findByTestId("setup-item-organization");
    const toggle = within(org).getByRole("button", { name: "조직과 부서 자세히 보기" });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(org).queryByText("조직과 부서 를 채우세요")).toBeNull();
  });

  it("복사할 명령은 펼친 칸의 코드 칸과 복사 단추다", async () => {
    const user = userEvent.setup();
    const items = freshItems().map((i) => (i.key === "organization"
      ? { ...i, command: "sudo clovirassist status" } : i));
    serve(payload(items));
    renderWizard();
    const org = await screen.findByTestId("setup-item-organization");
    expect(within(org).getByText("sudo clovirassist status").tagName).toBe("CODE");
    await user.click(within(org).getByRole("button", { name: "명령 복사" }));
    expect(copyMock).toHaveBeenCalledWith("sudo clovirassist status");
  });
});

// ── ④ 선택 값 ────────────────────────────────────────────────────────────────

describe("선택 값", () => {
  it("「사용하지 않음」은 선택 API 로 그 값 하나만 보내고, 돌아온 체크리스트로 다시 그린다", async () => {
    const user = userEvent.setup();
    const after = payload(freshItems().map((i) => (i.key === "mail"
      ? { ...i, state: "skipped", status: "skipped", status_label: "사용하지 않음", choice: "unused", action: null,
        detail: "사용하지 않기로 했습니다.", choices: [{ key: "mail", value: "use", label: "다시 사용" }] }
      : i)));
    apiMock.mockImplementation((path, opts) => {
      if (path === CHECKLIST) return Promise.resolve(payload(freshItems()));
      if (path === "/api/admin/setup/choices/mail") return Promise.resolve(after);
      return Promise.resolve({});
    });
    renderWizard();
    const mail = await screen.findByTestId("setup-item-mail");
    await user.click(within(mail).getByRole("button", { name: "사용하지 않음" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/setup/choices/mail", { method: "PUT", body: { value: "unused" } }));
    await waitFor(() => expect(screen.getByTestId("setup-item-mail")).toHaveAttribute("data-row-status", "skipped"));
    // 응답으로 그렸다 - 체크리스트를 다시 부르지 않았다.
    expect(apiMock.mock.calls.filter(([p]) => p === CHECKLIST)).toHaveLength(1);
    // 범용 설정 API 로 객체 전체를 덮지 않는다.
    expect(apiMock.mock.calls.some(([p]) => String(p).includes("/api/admin/settings/"))).toBe(false);
    expect(await screen.findByText("메일 발송 항목을 ‘사용하지 않음’으로 두었습니다.")).toBeInTheDocument();
  });

  it("TLS 의 「외부 프록시가 맡음」도 같은 선택 API 다", async () => {
    const user = userEvent.setup();
    renderWizard();
    const tls = await screen.findByTestId("setup-item-tls");
    await user.click(within(tls).getByRole("button", { name: "외부 프록시가 맡음" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/setup/choices/tls", { method: "PUT", body: { value: "proxy" } }));
  });

  it("선택을 바꾸지 못하면 서버의 문장을 알린다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path) => {
      if (path === CHECKLIST) return Promise.resolve(payload(freshItems()));
      return Promise.reject(Object.assign(new Error("이 항목에서 고를 수 없는 값입니다."), { status: 422 }));
    });
    renderWizard();
    const mail = await screen.findByTestId("setup-item-mail");
    await user.click(within(mail).getByRole("button", { name: "사용하지 않음" }));
    expect(await screen.findByText("이 항목에서 고를 수 없는 값입니다.")).toBeInTheDocument();
  });

  it("「다시 확인」은 체크리스트를 다시 부른다", async () => {
    const user = userEvent.setup();
    renderWizard();
    await screen.findByTestId("setup-item-organization");
    await user.click(screen.getByRole("button", { name: "다시 확인" }));
    await waitFor(() => expect(apiMock.mock.calls.filter(([p]) => p === CHECKLIST)).toHaveLength(2));
  });
});

// ── ⑤ 죽은 링크를 만들지 않는다 ──────────────────────────────────────────────

describe("링크", () => {
  it("대체 링크 표는 실제로 라우팅되는 관리자 경로만 가리킨다", () => {
    // AdminRoutes.jsx 가 명시적으로 거는 경로 + registry.js 가 만드는 경로.
    const explicit = [
      "dashboard", "search", "users", "offboarding", "settings",
      "diagnostics", "maintenance", "dev-report", "scheduler-calendar",
      "llm-console",
      // AI 연결(D-539) — 설정의 AI 탭이 화면 하나가 됐다. AdminRoutes 가 직접 건다.
      "ai-connection",
      // 조직 콘솔 셋(D-406) — registry 를 떠났지만 AdminRoutes 가 직접 건다.
      "organizations", "departments", "org-tree",
      // 메일 화면(D-548) — 설정 · 발송 기록 · 알림 메일 탭을 AdminRoutes 가 직접 건다.
      "mail",
    ];
    const known = new Set(explicit.concat(Object.keys(REGISTRY)));
    for (const [key, link] of Object.entries(SETUP_LINKS)) {
      expect(link.href.startsWith("#/")).toBe(true);
      const route = link.href.slice(2).split("?")[0];
      expect(known.has(route), `${key} 가 없는 화면(${link.href})을 가리킨다`).toBe(true);
    }
  });

  it("서버가 준 링크가 대체 표보다 먼저다", async () => {
    const items = freshItems().map((i) => (i.key === "mail"
      ? { ...i, status: "check", status_label: "확인 필요", state: "unknown", action: null, question: "연결 확인을 눌러 주세요",
        href: "#/mail", link_label: "메일 화면 열기", choices: [] }
      : i));
    serve(payload(items));
    renderWizard();
    const mail = await screen.findByTestId("setup-item-mail");
    expect(within(mail).getByRole("link", { name: "메일 화면 열기" }).getAttribute("href")).toBe("#/mail");
  });

  it("메일 · AI 항목의 대체 링크는 메일 설정 탭과 AI 연결 화면이다", () => {
    expect(SETUP_LINKS.mail).toEqual({ href: "#/mail?tab=settings", label: "메일 설정 열기" });
    expect(SETUP_LINKS.llm.href).toBe("#/ai-connection");
  });
});

// ── 권한 ─────────────────────────────────────────────────────────────────────

describe("권한", () => {
  it("시스템 관리자가 아니면 안내를 보여 주고 목록을 부르지 않는다", async () => {
    mockRole = "admin";
    renderWizard();
    await waitFor(() => expect(screen.getByText(/시스템 관리자만/)).toBeInTheDocument());
    expect(apiMock).not.toHaveBeenCalledWith(CHECKLIST);
  });
});
