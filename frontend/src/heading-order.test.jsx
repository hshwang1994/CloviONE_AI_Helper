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
  // AI 설정 탭은 「AI 연결」 화면이 됐다(D-539) - 같은 heading 성질을 새 화면에서 잰다.
  it("AiConnection: h1 다음이 h6이 아니라 h2다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/ai") {
        return Promise.resolve({
          config: { generation_enabled: false, provider: "", auth_method: "", model: "", timeout_seconds: 60, max_concurrency: 2 },
          state: { state: "unconfigured", label: "미설정", message: "m", problems: ["p"],
            display: { key: "unconfigured", label: "미설정", kind: "muted", message: "m" } },
          providers: [], features: {}, limits: { timeout_seconds: [5, 300], max_concurrency: [1, 8] },
        });
      }
      return Promise.resolve({});
    });
    const { AiConnection } = await import("./screens/ai/AiConnection.jsx");
    const { container } = qcRender(<AiConnection />);
    await screen.findByText("제공자와 인증");
    assertSequentialHeadings(container, "AiConnection");
  });

  it("MailScreen: h1 다음이 h6이 아니라 h2다", async () => {
    // qa-contract-change: 메일 화면이 「운영 › 메일」 세 탭(설정 · 발송 기록 · 알림 메일)이 됐다(D-548) - 기준점은 설정 탭의 구획 제목이다.
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/admin/mail/status")) {
        return Promise.resolve({
          health: { state: "disabled", label: "사용 안 함", kind: "neutral", message: "메일 발송을 사용하지 않습니다.", stages: [] },
          summary: { enabled: false, host: "", port: 587, security: "starttls", from_address: "", from_name: "", username: "", password: { stored: false } },
          counts: {}, recent_failures: [], backlog: { count: 0, window_days: 7 }, base_url: { value: "https://x", problem: null },
          capabilities: { can_configure: false, can_operate: false }, notification_mail: { allowed: [], catalog: [], max_age_days: 7 },
        });
      }
      return Promise.resolve({});
    });
    const { MailScreen } = await import("./screens/mail/MailScreen.jsx");
    const { container } = qcRender(<MailScreen />);
    // qa-contract-change: 설정 탭이 여섯 구획(발송 상태 · 발신 정보 · 전달 방식과 서버 이름 · 연결과 시험 발송 · DNS 인증 진단 ·
    // 요청 내용과 기술 상세)이 됐다(D-592). 「보내는 사람」 칸은 「발신 정보」 안이다 - 기준점을 그 구획 제목으로 옮긴다.
    await screen.findByText("발신 정보");
    assertSequentialHeadings(container, "MailScreen");
  });

  it("SystemOps: h1 다음이 h6이 아니라 h2다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      available: true,
      info: { hostname: "srv1", timezone: "Asia/Seoul", ntp_synchronized: "yes", units: {} },
      actions: [],
    }));
    const { SystemOps } = await import("./screens/SystemOps.jsx");
    const { container } = qcRender(<SystemOps />);
    // '시스템 정보' 카드는 값과 변경 동작을 한 줄에 묶은 '시스템 설정' 구역으로 대체됐다
    // (지시 33) - 이 시험의 기준점은 남아 있는 구역 제목이다.
    await screen.findByText("시스템 설정");
    assertSequentialHeadings(container, "SystemOps");
  });

  it("SetupWizard: 요약 띠와 구획 제목은 h1 다음 h2, 체크리스트 항목은 그 아래 h3 이다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/setup/checklist") {
        return Promise.resolve({
          headline: "필수 설정 1개가 남았습니다.", subline: "필수 2개 중 1개가 끝났습니다.",
          required_total: 2, required_done: 1, current_key: "llm",
          items: [
            { key: "org", label: "조직 만들기", why: "w", state: "done", status: "done", status_label: "완료", detail: "d", action: null, question: null, required: true, requires: [], requires_why: "", blocked_by: null, blocked_by_label: null, notes: [], choices: [], current: false },
            { key: "llm", label: "AI 러너", why: "w", state: "todo", status: "todo", status_label: "해야 함", detail: "d", action: "a", question: null, required: true, requires: [], requires_why: "", blocked_by: null, blocked_by_label: null, notes: [], choices: [], current: true },
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
