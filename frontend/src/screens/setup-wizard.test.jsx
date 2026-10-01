import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 최초 실행 셋업 마법사 화면 (9-3, P3).
 *
 * 이 화면이 지켜야 하는 것은 예쁘게 그리는 것이 아니라 **서버가 말한 사실을 바꾸지 않는
 * 것**이다. 여기서 못박는 것은 넷이다.
 *
 *   ① 서버가 준 **순서 그대로** 그린다. 화면이 상태로 다시 정렬하면(끝난 것을 아래로 등)
 *      안내 순서가 의존 순서가 아니게 되고, 사용자는 앞이 안 돼서 뒤가 안 되는 것임을
 *      영원히 모른다.
 *   ② "안 됨"과 "확인 불가"를 **다른 말로** 보여 준다. 색만 다르면 색을 못 보는 사람에게는
 *      같은 것이고, 같은 말이면 사람이 할 일과 물어볼 일이 뒤섞인다.
 *   ③ **남은 항목은 접어 둬도 계속 보인다.** 한 번 닫으면 다시 못 보는 마법사는 설정을
 *      미룬 사람에게 아무 도움이 안 된다.
 *   ④ **없는 화면으로 보내지 않는다.** 항목마다 붙는 링크는 실제로 라우팅되는 경로여야
 *      한다. 죽은 링크는 안내가 아니라 막다른 길이다.
 *
 * qa-contract-change: 진행 문장이 필수 항목을 센다(D-520) — 설치가 끝났는지는 필수 항목이 정하므로 「6개 중 1개」가 「필수 항목 6개 중 1개」가 됐다(이
 * 시험의 픽스처는 required 를 적지 않아 모든 항목이 필수다). 필수 · 선택 구역과 「사용하지 않음」, 서버가 주는 링크를 따로 잰다.
 * 그 전 변경: 레일이 「지금 할 차례」 판이 됐다(D-501). 다음 항목의 이름 · 할 일 · 고치는 화면으로 가는 링크(이 화면의 주 동작)가 레일에
 * 서고, 목록의 그 줄은 할 일과 링크를 되풀이하지 않는다 — 그래서 「안 됨에는 할 일」 단언이 레일과 다음이 아닌 항목 두 자리로 나뉜다. 남은 수는
 * 조각 문장 + 상태 요약 카드 둘에서 한 문장(「6개 중 1개가 끝났습니다. 직접 할 일이 4개, 확인할 것이 1개 남았습니다.」)으로 모였고, 접은 뒤의
 * 단언은 숫자 한 글자(「5」) 대신 그 문장 전체를 잰다. 레일에도 다음 항목의 이름이 서서 「조직과 부서」가 화면에 둘이므로, 불러왔는지는
 * 항목 표식(`setup-item-*`)으로 기다린다. 「지금 할 차례」 표지 하나 단언은 목록 안으로 좁히고, 레일이 같은 항목을 가리킨다는 단언을 더한다.
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

import { SetupWizard, SETUP_LINKS, setupProgressText } from "./SetupWizard.jsx";
import { REGISTRY } from "./registry.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const CHECKLIST = "/api/admin/setup/checklist";

function item(key, label, state, extra = {}) {
  return {
    key,
    label,
    why: `${label} 가 안 되면 화면이 빕니다.`,
    state,
    detail: `${label} 상태 설명`,
    action: state === "todo" ? `${label} 를 채우세요` : null,
    question: state === "unknown" ? `${label} 를 확인해 주세요` : null,
    requires: [],
    requires_why: "",
    blocked_by: null,
    blocked_by_label: null,
    ...extra,
  };
}

// 갓 설치한 세계와 같은 모양: 앞이 끝났고, 하나가 안 됐고, 그 뒤가 막혔고, 확인 불가가 있다.
function payload(overrides = {}) {
  const items = overrides.items || [
    item("admin_account", "관리자 계정", "done"),
    item("organization", "조직과 부서", "todo"),
    /* 여기 「Notion 토큰과 데이터베이스」 항목이 있었고 사용자 매핑이 그것에 막혀 있었다.
       app/setup/steps.py 에서 그 단계가 빠지면서 매핑은 조직과 부서에 막힌다 — 이 픽스처는
       서버가 실제로 주는 목록과 같은 모양이라야 화면을 시험한 것이 된다. */
    item("user_mapping", "사용자 매핑", "todo", {
      requires: ["organization"],
      requires_why: "사람을 넣을 조직 단위가 먼저 있어야 연결이 의미를 갖습니다.",
      blocked_by: "organization",
      blocked_by_label: "조직과 부서",
    }),
    item("llm", "AI 러너", "todo", {
      requires: ["user_mapping"],
      blocked_by: "user_mapping",
      blocked_by_label: "사용자 매핑",
    }),
    item("integrations", "외부 연동", "todo", {
      requires: ["llm"],
      blocked_by: "llm",
      blocked_by_label: "AI 러너",
    }),
    item("tls", "TLS 인증서", "unknown"),
  ];
  return {
    items,
    remaining: items.filter((i) => i.state !== "done").map((i) => i.key),
    todo: items.filter((i) => i.state === "todo").map((i) => i.key),
    unknown: items.filter((i) => i.state === "unknown").map((i) => i.key),
    next_key: (items.find((i) => i.state !== "done" && !i.blocked_by) || {}).key || null,
    complete: items.every((i) => i.state === "done"),
    ...overrides,
  };
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

beforeEach(() => {
  mockRole = "system_admin";
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path === CHECKLIST) return Promise.resolve(payload());
    return Promise.resolve({});
  });
});

// ── ① 순서 ────────────────────────────────────────────────────────────────────

describe("안내 순서", () => {
  it("서버가 준 순서를 그대로 그린다", async () => {
    renderWizard();
    await screen.findByTestId("setup-item-organization");
    const keys = Array.from(document.querySelectorAll("[data-setup-key]")).map((n) =>
      n.getAttribute("data-setup-key")
    );
    expect(keys).toEqual([
      "admin_account", "organization", "user_mapping",
      "llm", "integrations", "tls",
    ]);
  });

  it("끝난 항목을 아래로 밀어내거나 목록에서 빼지 않는다", async () => {
    renderWizard();
    await waitFor(() => expect(screen.getByText("관리자 계정")).toBeInTheDocument());
    const keys = Array.from(document.querySelectorAll("[data-setup-key]")).map((n) =>
      n.getAttribute("data-setup-key")
    );
    // 끝난 admin_account 가 여전히 첫 자리다.
    expect(keys[0]).toBe("admin_account");
  });

  it("끝난 항목은 한 줄이다 — 이름 · 「됨」 · 지금 상태만 서고 까닭과 이동 링크는 없다 (D-501)", async () => {
    renderWizard();
    const done = await screen.findByTestId("setup-item-admin_account");
    expect(done).toHaveAttribute("data-setup-state", "done");
    expect(within(done).getByText("관리자 계정")).toBeInTheDocument();
    expect(within(done).getByText("됨")).toBeInTheDocument();
    expect(within(done).getByText("관리자 계정 상태 설명")).toBeInTheDocument();
    expect(within(done).queryByText(/화면이 빕니다/)).toBeNull();
    expect(within(done).queryByRole("link")).toBeNull();
    // 반례 — 남은 항목은 까닭을 그대로 펼친다.
    const tls = screen.getByTestId("setup-item-tls");
    expect(within(tls).getByText(/화면이 빕니다/)).toBeInTheDocument();
  });
});

// ── ② 세 가지 상태 ────────────────────────────────────────────────────────────

describe("됨, 안 됨, 확인 불가", () => {
  it("세 상태를 색이 아니라 글자로 구분한다", async () => {
    renderWizard();
    await screen.findByTestId("setup-item-organization");
    expect(screen.getAllByText("됨").length).toBe(1);
    expect(screen.getAllByText("안 됨").length).toBe(4);
    expect(screen.getAllByText("확인 불가").length).toBe(1);
  });

  it("확인 불가에는 물어볼 것을 보여 주고 할 일을 지어내지 않는다", async () => {
    renderWizard();
    const tls = await screen.findByTestId("setup-item-tls");
    expect(within(tls).getByText(/확인해 주세요/)).toBeInTheDocument();
    expect(within(tls).queryByText(/채우세요/)).toBeNull();
  });

  it("안 됨에는 사람이 할 일을 보여 준다 — 지금 할 차례의 할 일은 레일이 한 번 말한다", async () => {
    // 막히지 않은 「안 됨」이 둘인 설치: 앞의 것이 지금 할 차례이고 뒤의 것은 목록에서 자기 할 일을 말한다.
    const items = [
      item("admin_account", "관리자 계정", "done"),
      item("organization", "조직과 부서", "todo"),
      item("mail", "메일(SMTP) 발송", "todo"),
    ];
    apiMock.mockImplementation(() => Promise.resolve(payload({ items })));
    renderWizard();
    const rail = await screen.findByTestId("setup-summary");
    expect(within(rail).getByText(/조직과 부서 를 채우세요/)).toBeInTheDocument();
    // 목록의 그 줄은 같은 할 일을 되풀이하지 않는다(한 사실은 한 곳).
    const org = screen.getByTestId("setup-item-organization");
    expect(within(org).queryByText(/조직과 부서 를 채우세요/)).toBeNull();
    // 다음이 아닌 「안 됨」은 목록에서 자기 할 일을 말한다.
    const mail = screen.getByTestId("setup-item-mail");
    expect(within(mail).getByText(/메일\(SMTP\) 발송 를 채우세요/)).toBeInTheDocument();
    expect(screen.getAllByText(/를 채우세요/)).toHaveLength(2);
  });
});

// ── 막힌 항목 ─────────────────────────────────────────────────────────────────

describe("막힌 항목", () => {
  it("무엇 때문에 막혔는지 앞 항목의 이름으로 말한다", async () => {
    renderWizard();
    const mapping = await screen.findByTestId("setup-item-user_mapping");
    expect(within(mapping).getByText(/조직과 부서/)).toBeInTheDocument();
    expect(within(mapping).getByText(/먼저/)).toBeInTheDocument();
  });

  it("지금 할 차례는 막히지 않은 첫 항목 하나뿐이다", async () => {
    renderWizard();
    const org = await screen.findByTestId("setup-item-organization");
    const list = org.closest("ul");
    const now = within(list).getAllByText("지금 할 차례");
    expect(now.length).toBe(1);
    expect(within(org).getByText("지금 할 차례")).toBeInTheDocument();
    // 레일의 「지금 할 차례」 판이 같은 항목을 가리킨다.
    const rail = screen.getByTestId("setup-summary");
    expect(within(rail).getByRole("heading", { level: 2, name: "지금 할 차례" })).toBeInTheDocument();
    expect(rail.querySelector("[data-setup-now]").getAttribute("data-setup-now")).toBe("organization");
  });
});

// ── 레일 — 지금 할 차례 (D-501) ────────────────────────────────────────────────

describe("레일 — 지금 할 차례가 이 화면의 주 동작이다 (D-501)", () => {
  it("다음 항목의 고치는 화면으로 가는 링크가 레일에 하나 서고, 목록의 그 줄에는 없다", async () => {
    renderWizard();
    const rail = await screen.findByTestId("setup-summary");
    const go = within(rail).getByRole("link", { name: SETUP_LINKS.organization.label });
    expect(go.getAttribute("href")).toBe(SETUP_LINKS.organization.href);
    expect(within(rail).getAllByRole("link")).toHaveLength(1);
    const org = screen.getByTestId("setup-item-organization");
    expect(within(org).queryByRole("link")).toBeNull();
  });

  it("진행은 한 문장이다 — 같은 수를 조각 문장과 요약 카드로 두 번 세우지 않는다", async () => {
    renderWizard();
    const rail = await screen.findByTestId("setup-summary");
    expect(rail).toHaveTextContent("필수 항목 6개 중 1개가 끝났습니다. 직접 할 일이 4개, 확인할 것이 1개 남았습니다.");
    expect(within(rail).queryByText("남은 항목")).toBeNull();
    expect(document.querySelector("[data-summary-total]")).toBeNull();
  });

  it("진행 문장은 없는 갈래를 말하지 않는다", () => {
    const base = { items: [item("a", "가", "done"), item("b", "나", "todo")], todo: ["b"], unknown: [] };
    expect(setupProgressText(base)).toBe("필수 항목 2개 중 1개가 끝났습니다. 직접 할 일이 1개 남았습니다.");
    expect(setupProgressText({ ...base, items: [item("a", "가", "unknown")], todo: [], unknown: ["a"] }))
      .toBe("필수 항목 1개 중 아직 끝난 항목이 없습니다. 확인할 것이 1개 남았습니다.");
    // 선택 항목은 필수 수에 들지 않고 남은 수만 덧붙는다.
    const mixed = { items: [item("a", "가", "done"), item("m", "메일", "todo", { required: false })], optional_pending: ["m"] };
    expect(setupProgressText(mixed)).toBe("필수 항목 1개 중 1개가 끝났습니다. 선택 항목은 1개가 남아 있습니다.");
  });

  it("레일이 문서 순서의 앞이다 — 좁은 화면에서도 할 차례가 목록 위에 선다", async () => {
    renderWizard();
    const rail = await screen.findByTestId("setup-summary");
    const org = screen.getByTestId("setup-item-organization");
    expect(rail.compareDocumentPosition(org) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

// ── ③ 접어도 남은 항목은 계속 보인다 ─────────────────────────────────────────

describe("끝난 뒤에도 계속 보인다", () => {
  it("목록을 접어도 남은 항목 수는 사라지지 않는다", async () => {
    const user = userEvent.setup();
    renderWizard();
    await screen.findByTestId("setup-item-organization");

    await user.click(screen.getByRole("button", { name: /목록 접기/ }));
    expect(screen.queryByTestId("setup-item-organization")).toBeNull();
    // 접어도 요약은 남는다. 이것이 사라지면 "한 번 닫으면 끝" 인 마법사가 된다.
    const rail = screen.getByTestId("setup-summary");
    expect(rail).toHaveTextContent("필수 항목 6개 중 1개가 끝났습니다. 직접 할 일이 4개, 확인할 것이 1개 남았습니다.");
    // 할 차례도 남는다 — 목록을 접은 사람이 다음에 할 일을 잃지 않는다.
    expect(within(rail).getByRole("link", { name: SETUP_LINKS.organization.label })).toBeInTheDocument();
  });

  it("전부 끝나도 항목 목록은 그대로 남는다", async () => {
    const doneItems = payload().items.map((i) => ({
      ...i, state: "done", action: null, question: null, blocked_by: null,
      blocked_by_label: null,
    }));
    apiMock.mockImplementation(() =>
      Promise.resolve(payload({ items: doneItems, remaining: [], todo: [], unknown: [], next_key: null, complete: true }))
    );
    renderWizard();
    await waitFor(() => expect(screen.getByText("조직과 부서")).toBeInTheDocument());
    expect(screen.getByTestId("setup-summary")).toHaveTextContent(/끝났습니다/);
    const keys = Array.from(document.querySelectorAll("[data-setup-key]"));
    expect(keys.length).toBe(6);
    // 다 끝나면 할 차례도 주 동작도 없다.
    expect(screen.queryByText("지금 할 차례")).toBeNull();
    expect(within(screen.getByTestId("setup-summary")).queryByRole("link")).toBeNull();
  });
});

// ── ④ 죽은 링크를 만들지 않는다 ──────────────────────────────────────────────

describe("링크", () => {
  it("항목 링크는 실제로 라우팅되는 관리자 경로만 가리킨다", () => {
    // AdminRoutes.jsx 가 명시적으로 거는 경로 + registry.js 가 만드는 경로.
    const explicit = [
      "dashboard", "search", "users", "offboarding", "settings",
      "diagnostics", "maintenance", "dev-report", "scheduler-calendar",
      // 9-5 로 생긴 AI 관리 화면. 이 목록은 AdminRoutes.jsx 의 명시 경로를 손으로 옮겨
      // 적은 것이라 새 경로가 생기면 여기도 같이 늘려야 한다. `notion-console` 은 화면과
      // 함께 라우트도 없어져 여기서 뺐다 — 남겨 두면 죽은 링크를 검사가 눈감아 준다.
      "llm-console",
      // AI 연결(D-539) — 설정의 AI 탭이 화면 하나가 됐다. AdminRoutes 가 직접 건다.
      "ai-connection",
      // 조직 콘솔 셋(D-406) — registry 를 떠났지만 AdminRoutes 가 직접 건다
      // (ORG_CONSOLE_KEYS). registry 키 합산만 믿으면 살아 있는 이 경로들을
      // 죽은 링크로 오판한다.
      "organizations", "departments", "org-tree",
    ];
    const known = new Set(explicit.concat(Object.keys(REGISTRY)));
    for (const [key, link] of Object.entries(SETUP_LINKS)) {
      expect(link.href.startsWith("#/")).toBe(true);
      const route = link.href.slice(2).split("?")[0];
      expect(known.has(route), `${key} 가 없는 화면(${link.href})을 가리킨다`).toBe(true);
    }
  });

  it("링크가 있는 항목은 그 링크를 화면에 그린다", async () => {
    renderWizard();
    const runners = await screen.findByTestId("setup-item-llm");
    const anchor = within(runners).getByRole("link");
    expect(anchor.getAttribute("href")).toBe(SETUP_LINKS.llm.href);
  });

  it("메일 항목은 설정 표의 메일 줄을 연다 — 메일 발송 화면의 「메일 설정 열기」와 같은 곳 · 같은 이름이다", () => {
    expect(SETUP_LINKS.mail).toEqual({ href: "#/settings?setting=smtp", label: "메일 설정 열기" });
  });

  it("SYS-06: llm 항목은 AI 설정으로 보낸다 — probe_llm의 안내 문구가 실제로 말하는 곳과 같다", () => {
    // app/setup/probes.py::probe_llm 은 이제 Model Gateway 의 capabilities 를 읽고, 그
    // 안내가 「AI 설정을 확인하세요」라고 말한다(S11 이전에는 러너 화면이었다). 링크가
    // 다른 곳으로 가면 그 문구를 따라도 이 항목을 고칠 수 있는 화면에 도달하지 못한다.
    expect(SETUP_LINKS.llm.href).toBe("#/ai-connection");
  });
});

// ── 권한 ─────────────────────────────────────────────────────────────────────

describe("권한", () => {
  it("시스템 관리자가 아니면 안내를 보여 주고 목록을 부르지 않는다", async () => {
    mockRole = "admin";
    renderWizard();
    await waitFor(() =>
      expect(screen.getByText(/시스템 관리자만/)).toBeInTheDocument()
    );
    expect(apiMock).not.toHaveBeenCalledWith(CHECKLIST);
  });
});

// ── 필수와 선택, 사용하지 않음 (D-520) ─────────────────────────────────────────

describe("필수와 선택", () => {
  function optionalPayload(extra = {}) {
    const items = [
      item("admin_account", "관리자 계정", "done", { required: true }),
      item("mail", "메일(SMTP) 발송", "todo", {
        required: false, optional_choice: "mail", choice: "use", configured: false,
        href: "#/settings?setting=smtp", link_label: "메일 설정 열기",
      }),
      item("organization", "조직과 부서", "done", { required: true }),
      item("llm", "AI", "skipped", { required: false, optional_choice: "llm", choice: "unused", configured: false,
        detail: "사용하지 않기로 했습니다.", action: null }),
      item("tls", "TLS 인증서", "done", { required: true }),
    ];
    return payload({
      items, remaining: ["mail"], todo: ["mail"], unknown: [], skipped: ["llm"], optional_pending: ["mail"],
      required_remaining: [], next_key: "mail", complete: true, summary: "정상 설치입니다(AI 사용 안 함).", ...extra,
    });
  }

  it("필수 항목과 선택 항목이 다른 구역에 서고, 필수가 끝나면 설치가 끝났다고 말한다", async () => {
    apiMock.mockImplementation((path) => Promise.resolve(path === CHECKLIST ? optionalPayload() : {}));
    renderWizard();
    const required = await screen.findByRole("region", { name: "필수 항목" });
    const optional = screen.getByRole("region", { name: "선택 항목" });
    expect(within(required).getByTestId("setup-item-organization")).toBeInTheDocument();
    expect(within(optional).getByTestId("setup-item-mail")).toBeInTheDocument();
    expect(screen.getByTestId("setup-summary")).toHaveTextContent("필수 설정이 모두 끝났습니다. 정상 설치입니다(AI 사용 안 함).");
    expect(within(optional).getByText("사용하지 않음")).toBeInTheDocument();
  });

  it("「사용하지 않음으로 표시」가 다른 선택을 지킨 채 한 값만 바꾼다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path) => Promise.resolve(path === CHECKLIST ? optionalPayload() : {}));
    renderWizard();
    const mail = await screen.findByTestId("setup-item-mail");
    await user.click(within(mail).getByRole("button", { name: "사용하지 않음으로 표시" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/admin/settings/setup_optional_choices",
      { method: "PUT", body: { value: { mail: "unused", llm: "unused" } } }));
    const llm = screen.getByTestId("setup-item-llm");
    expect(within(llm).getByRole("button", { name: "사용하기로 바꾸기" })).toBeInTheDocument();
  });

  it("서버가 준 링크가 대체 표보다 먼저다", async () => {
    const items = optionalPayload().items.map((i) => (i.key === "mail"
      ? { ...i, state: "unknown", action: null, question: "연결 확인을 눌러 주세요", href: "#/mail", link_label: "메일 발송 화면 열기" }
      : i));
    apiMock.mockImplementation((path) => Promise.resolve(path === CHECKLIST
      ? optionalPayload({ items, next_key: null }) : {}));
    renderWizard();
    const mail = await screen.findByTestId("setup-item-mail");
    expect(within(mail).getByRole("link", { name: "메일 발송 화면 열기" }).getAttribute("href")).toBe("#/mail");
  });
});
