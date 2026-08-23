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

import { SetupWizard, SETUP_LINKS } from "./SetupWizard.jsx";
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
    item("notion", "Notion 토큰과 데이터베이스", "todo", {
      requires: ["organization"],
      requires_why: "조직 단위가 먼저 있어야 합니다.",
      blocked_by: "organization",
      blocked_by_label: "조직과 부서",
    }),
    item("user_mapping", "사용자 매핑", "todo", {
      requires: ["notion"],
      blocked_by: "notion",
      blocked_by_label: "Notion 토큰과 데이터베이스",
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
    await waitFor(() => expect(screen.getByText("조직과 부서")).toBeInTheDocument());
    const keys = Array.from(document.querySelectorAll("[data-setup-key]")).map((n) =>
      n.getAttribute("data-setup-key")
    );
    expect(keys).toEqual([
      "admin_account", "organization", "notion", "user_mapping",
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
});

// ── ② 세 가지 상태 ────────────────────────────────────────────────────────────

describe("됨, 안 됨, 확인 불가", () => {
  it("세 상태를 색이 아니라 글자로 구분한다", async () => {
    renderWizard();
    await waitFor(() => expect(screen.getByText("조직과 부서")).toBeInTheDocument());
    expect(screen.getAllByText("됨").length).toBe(1);
    expect(screen.getAllByText("안 됨").length).toBe(5);
    expect(screen.getAllByText("확인 불가").length).toBe(1);
  });

  it("확인 불가에는 물어볼 것을 보여 주고 할 일을 지어내지 않는다", async () => {
    renderWizard();
    const tls = await screen.findByTestId("setup-item-tls");
    expect(within(tls).getByText(/확인해 주세요/)).toBeInTheDocument();
    expect(within(tls).queryByText(/채우세요/)).toBeNull();
  });

  it("안 됨에는 사람이 할 일을 보여 준다", async () => {
    renderWizard();
    const org = await screen.findByTestId("setup-item-organization");
    expect(within(org).getByText(/조직과 부서 를 채우세요/)).toBeInTheDocument();
  });
});

// ── 막힌 항목 ─────────────────────────────────────────────────────────────────

describe("막힌 항목", () => {
  it("무엇 때문에 막혔는지 앞 항목의 이름으로 말한다", async () => {
    renderWizard();
    const notion = await screen.findByTestId("setup-item-notion");
    expect(within(notion).getByText(/조직과 부서/)).toBeInTheDocument();
    expect(within(notion).getByText(/먼저/)).toBeInTheDocument();
  });

  it("지금 할 차례는 막히지 않은 첫 항목 하나뿐이다", async () => {
    renderWizard();
    await waitFor(() => expect(screen.getByText("조직과 부서")).toBeInTheDocument());
    const now = screen.getAllByText("지금 할 차례");
    expect(now.length).toBe(1);
    const org = screen.getByTestId("setup-item-organization");
    expect(within(org).getByText("지금 할 차례")).toBeInTheDocument();
  });
});

// ── ③ 접어도 남은 항목은 계속 보인다 ─────────────────────────────────────────

describe("끝난 뒤에도 계속 보인다", () => {
  it("목록을 접어도 남은 항목 수는 사라지지 않는다", async () => {
    const user = userEvent.setup();
    renderWizard();
    await waitFor(() => expect(screen.getByText("조직과 부서")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /목록 접기/ }));
    expect(screen.queryByTestId("setup-item-organization")).toBeNull();
    // 접어도 요약은 남는다. 이것이 사라지면 "한 번 닫으면 끝" 인 마법사가 된다.
    expect(screen.getByTestId("setup-summary")).toHaveTextContent("6");
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
    expect(keys.length).toBe(7);
  });
});

// ── ④ 죽은 링크를 만들지 않는다 ──────────────────────────────────────────────

describe("링크", () => {
  it("항목 링크는 실제로 라우팅되는 관리자 경로만 가리킨다", () => {
    // AdminRoutes.jsx 가 명시적으로 거는 경로 + registry.js 가 만드는 경로.
    const explicit = [
      "dashboard", "search", "users", "offboarding", "settings",
      "diagnostics", "maintenance", "dev-report", "scheduler-calendar",
      // 9-4, 9-5 로 생긴 두 화면. 이 목록은 AdminRoutes.jsx 의 명시 경로를 손으로 옮겨
      // 적은 것이라 새 경로가 생기면 여기도 같이 늘려야 한다.
      "notion-console", "llm-console",
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

  it("SYS-06: llm 항목은 AI 설정으로 보낸다 — probe_llm의 안내 문구가 실제로 말하는 곳과 같다", () => {
    // app/setup/probes.py::probe_llm 은 이제 Model Gateway 의 capabilities 를 읽고, 그
    // 안내가 「AI 설정을 확인하세요」라고 말한다(S11 이전에는 러너 화면이었다). 링크가
    // 다른 곳으로 가면 그 문구를 따라도 이 항목을 고칠 수 있는 화면에 도달하지 못한다.
    expect(SETUP_LINKS.llm.href).toBe("#/settings?tab=ai");
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
