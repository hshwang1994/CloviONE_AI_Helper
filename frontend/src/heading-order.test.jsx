import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* PA-RC-0012: 문서 heading 계층이 건너뛰지 않는지 대표 화면에서 직접 렌더해 확인한다.
 *
 * `variant="h6"`가 시각 크기이면서 동시에(component= 없으면) 실제 <h6> 태그도 결정해
 * 버려, 손으로 쓴 화면 다섯 개가 h1 바로 다음에 h6을 놓았다(네 단계 건너뜀). 소스의
 * `component=` 존재 여부는 `scripts/check_heading_variant_mapping.py`가 정적으로 잡지만,
 * 그 검사는 "component=가 있다/없다"만 보지 실제 렌더 결과(진짜로 순서가 맞는가)는 못
 * 본다 — 이 파일이 그 뒤를 잇는다. 화면별로 흩어 두지 않고 한 파일에 모아 새 화면이
 * 추가돼도 같은 헬퍼로 걸리게 한다(Handoff required_tests).
 */

function assertSequentialHeadings(container, label) {
  const headings = screen
    .getAllByRole("heading", {}, { container })
    .map((el) => {
      const ariaLevel = el.getAttribute("aria-level");
      if (ariaLevel) return Number(ariaLevel);
      const m = el.tagName.match(/^H([1-6])$/);
      return m ? Number(m[1]) : null;
    })
    .filter((lvl) => lvl != null);
  expect(headings.length, `${label}: heading이 하나도 안 잡혔다`).toBeGreaterThan(0);
  let prev = headings[0];
  for (const level of headings.slice(1)) {
    expect(level, `${label}: heading 열 [${headings.join(",")}] 에서 ${prev}→${level}로 건너뜀`)
      .toBeLessThanOrEqual(prev + 1);
    prev = level;
  }
}

const apiMock = vi.fn();
vi.mock("./lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("./app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }) }));

function qcRender(children) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("heading 순서 — 건너뛰지 않는다(PA-RC-0012)", () => {
  it("LlmConsole: h1 다음이 h6이 아니라 h2다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/llm") {
        return Promise.resolve({
          config: { enabled: false, backend: "cli", executable: "claude", model: "sonnet", timeout_seconds: 120, max_concurrency: 1 },
          limits: { min_timeout_seconds: 5, max_timeout_seconds: 600, max_concurrency: 4, test_timeout_seconds: 60 },
          sources: {}, editable_keys: [],
          login: { backend: "cli", title: "t", steps: [], note: "" },
          apply_note: "", test_mode_note: "", verified: false, verified_note: "",
        });
      }
      if (path === "/api/admin/settings") return Promise.resolve({ settings: {} });
      return Promise.resolve({});
    });
    const { LlmConsole } = await import("./screens/LlmConsole.jsx");
    const { container } = qcRender(<LlmConsole />);
    await screen.findByText("지금 적용 중인 값");
    assertSequentialHeadings(container, "LlmConsole");
  });

  it("NotionConsole: h1 다음이 h6이 아니라 h2다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/notion-mapping/overview") {
        return Promise.resolve({
          apply_note: "", databases: [], token: { items: [], writable: true, directory: "", note: "", manual_instruction: null },
          sprint: { portal_window: "", sprint_database_id: "", source: "env", linked: false, finding: "", next_step: "" },
        });
      }
      return Promise.resolve({});
    });
    const { NotionConsole } = await import("./screens/NotionConsole.jsx");
    const { container } = qcRender(<NotionConsole />);
    await screen.findByText("토큰");
    assertSequentialHeadings(container, "NotionConsole");
  });

  it("MailStatus: h1 다음이 h6이 아니라 h2다", async () => {
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/admin/mail/status")) {
        return Promise.resolve({
          mail: { configured: false, problems: ["x"], server: { enabled: false, host: "", port: null, security: null, from_address: "", from_name: "" }, password_secret: null },
          counts: { queued: 0, sent: 0, failed: 0, unconfigured: 0 },
          recent_failures: [],
        });
      }
      return Promise.resolve({});
    });
    const { MailStatus } = await import("./screens/MailStatus.jsx");
    const { container } = qcRender(<MailStatus />);
    // 서버 설정은 이제 제목 딸린 카드가 아니라 속성 줄(MetaBar)이다 - 제목 위계를 재는
    // 이 시험의 기준점은 남아 있는 구역 제목이다.
    await screen.findByText("최근 실패");
    assertSequentialHeadings(container, "MailStatus");
  });

  it("SystemOps: h1 다음이 h6이 아니라 h2다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      available: true,
      info: { hostname: "srv1", timezone: "Asia/Seoul", ntp_synchronized: "yes", units: {} },
      actions: [],
    }));
    const { SystemOps } = await import("./screens/SystemOps.jsx");
    const { container } = qcRender(<SystemOps />);
    await screen.findByText("시스템 정보");
    assertSequentialHeadings(container, "SystemOps");
  });

  it("SetupWizard: 체크리스트 항목 제목이 h1 다음 h3이 아니라 h2다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/setup/checklist") {
        return Promise.resolve({
          items: [
            { key: "org", label: "조직 만들기", why: "w", state: "done", detail: "d", action: null, question: null, requires: [], requires_why: "", blocked_by: null, blocked_by_label: null },
            { key: "notion", label: "Notion 연결", why: "w", state: "todo", detail: "d", action: "a", question: null, requires: [], requires_why: "", blocked_by: null, blocked_by_label: null },
          ],
        });
      }
      return Promise.resolve({});
    });
    const { SetupWizard } = await import("./screens/SetupWizard.jsx");
    const { container } = qcRender(<SetupWizard />);
    await screen.findByText("조직 만들기");
    assertSequentialHeadings(container, "SetupWizard");
  });
});
