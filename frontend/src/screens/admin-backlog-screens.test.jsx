import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 관리자 백로그 잔여 화면(PLAN Phase 6) — registry.js 설정으로만 만든 여덟 화면.
 *
 * 설정으로 만든 화면은 "코드를 안 썼으니 안전하다"가 성립하지 않는다. 오히려 오타 하나가
 * 조용히 통과한다(잘못된 method 는 405, 잘못된 경로는 404 인데 화면은 그냥 빈 표를 그린다).
 * 그래서 여기서는 **실제로 나가는 요청**을 붙잡아 확인한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { REGISTRY } from "./registry.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderScreen(key) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={REGISTRY[key]} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("새 관리자 화면 — 레지스트리 계약", () => {
  it("여덟 화면이 전부 등록돼 있고 엔드포인트가 백엔드 경로와 맞는다", () => {
    const expected = {
      impersonation: "/api/admin/impersonation/sessions",
      "approval-delegations": "/api/admin/approval-delegations",
      announcements: "/api/admin/announcements",
      "ai-quotas": "/api/admin/ai-quotas",
      "feature-flags": "/api/admin/feature-flags",
      "audit-anomalies": "/api/admin/audit/anomalies",
      "restore-drills": "/api/admin/backups/rehearsals",
      "prompt-usage": "/api/admin/prompts/usage/stats",
      "policy-usage": "/api/admin/policies/usage/stats",
    };
    for (const [key, endpoint] of Object.entries(expected)) {
      expect(REGISTRY[key], `${key} 화면이 없다`).toBeTruthy();
      expect(REGISTRY[key].endpoint, `${key} 엔드포인트`).toBe(endpoint);
      expect(REGISTRY[key].key).toBe(key);
      // 표를 그리는 화면은 열 정의가 있어야 한다 — 없으면 빈 표만 나온다.
      expect(REGISTRY[key].columns || REGISTRY[key].columnsFrom, `${key} 열 정의`).toBeTruthy();
    }
  });

  it("기능 플래그: 끄기 버튼이 PUT 으로 enabled=false 를 보낸다", async () => {
    let sent = null;
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method) { sent = { path, ...opts }; return Promise.resolve({ name: "games_enabled", value: false }); }
      return Promise.resolve({
        items: [{
          name: "games_enabled", value: true, default: true, owner: "file",
          description: "팀 놀이 모듈", editable_here: true, has_consumer: true,
          edit_hint: "즉시 반영됩니다(재시작 불필요).",
        }],
        source: "config/feature-flags.json",
      });
    });
    renderScreen("feature-flags");
    const row = await screen.findByText("games_enabled");
    await userEvent.click(within(row.closest("tr")).getByRole("button", { name: /상세/ }));
    const drawer = await screen.findByRole("dialog");
    await userEvent.click(within(drawer).getByRole("button", { name: "끄기" }));
    // 확인 대화상자
    const confirmDialog = await screen.findByRole("dialog", { name: /확인|끌까요/ });
    await userEvent.click(within(confirmDialog).getByRole("button", { name: /확인|끄기|계속/ }));
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent.method).toBe("PUT");
    expect(sent.path).toBe("/api/admin/feature-flags/games_enabled");
    expect(sent.body).toEqual({ enabled: false });
  });

  it("기능 플래그: 설정 소유 플래그에는 켜기/끄기가 아예 없다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      items: [{
        name: "maintenance_mode", value: false, default: false, owner: "db",
        description: "유지보수 모드", editable_here: false, has_consumer: true,
        edit_hint: "이 플래그의 정본은 설정 화면입니다 — 여기서는 바꿀 수 없습니다.",
      }],
    }));
    renderScreen("feature-flags");
    const row = await screen.findByText("maintenance_mode");
    await userEvent.click(within(row.closest("tr")).getByRole("button", { name: /상세/ }));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).queryByRole("button", { name: "켜기" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "끄기" })).not.toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "설정 화면에서 열기" })).toBeInTheDocument();
  });

  it("AI 상한: 현재 사용량을 '사용 / 상한' 으로 함께 보여 준다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      items: [{
        id: "q1", scope_type: "user", user_id: "u-1", user_name: "홍길동",
        period: "day", max_calls: 20, used: 18, note: null,
        created_at: "2026-08-01T00:00:00", updated_at: "2026-08-01T00:00:00",
        resets_at: "2026-08-04T15:00:00",
      }],
      enforced_on: [{ kind: "assistant_narrative", label: "AI 도우미 문장 생성" }],
      periods: ["day", "month"],
    }));
    renderScreen("ai-quotas");
    expect(await screen.findByText("18 / 20")).toBeInTheDocument();
    expect(screen.getByText("홍길동")).toBeInTheDocument();
  });

  it("감사 이상 징후: 근거와 임계값을 상세에 그대로 보여 준다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      items: [{
        id: "failure_burst:u-1:실패가 몰려 있습니다", kind: "failure_burst", severity: "high",
        actor_id: "u-1", actor_name: "홍길동", actor_email: "hong@goodmit.co.kr",
        title: "실패가 몰려 있습니다", detail: "24시간 안에 실패한 동작이 7건입니다.",
        count: 7, threshold: 5, evidence: ["user.update (failure)", "user.update (failure)"],
        first_at: "2026-08-03T00:00:00", last_at: "2026-08-03T01:00:00",
      }],
      findings: [],
      window_hours: 24, thresholds: { failure_burst: 5 },
    }));
    renderScreen("audit-anomalies");
    const row = await screen.findByText("실패가 몰려 있습니다");
    await userEvent.click(within(row.closest("tr")).getByRole("button", { name: /상세/ }));
    const drawer = await screen.findByRole("dialog");
    expect(drawer).toHaveTextContent("user.update (failure)");
    expect(drawer).toHaveTextContent("5");
  });

  it("복구 리허설: 한 번도 안 했으면 그렇게 말한다(지어내지 않는다)", async () => {
    apiMock.mockImplementation((path) => {
      if (path.startsWith("/api/admin/backups/schedule")) {
        return Promise.resolve({
          schedule: { enabled: false, cron: "0 3 * * *", timezone: "Asia/Seoul", keep: 14 },
          last_backup: null, last_rehearsal: null,
        });
      }
      return Promise.resolve({ items: [], command: "…", note: "…" });
    });
    renderScreen("restore-drills");
    expect(await screen.findByText("복구 리허설 기록이 없습니다")).toBeInTheDocument();
    expect(await screen.findByText("한 번도 안 함")).toBeInTheDocument();
  });

  it("대리 보기: 시작 버튼이 사유까지 담아 POST 한다", async () => {
    let sent = null;
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "POST") { sent = { path, body: opts.body }; return Promise.resolve({ ok: true }); }
      return Promise.resolve({ items: [], total: 0, page_size: 20 });
    });
    renderScreen("impersonation");
    await userEvent.click(await screen.findByRole("button", { name: "대리 보기 시작" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/대상 사용자 ID/), "u-42");
    await userEvent.type(within(dialog).getByLabelText(/사유/), "문의 재현");
    await userEvent.click(within(dialog).getByRole("button", { name: /저장|시작/ }));
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent.path).toBe("/api/admin/impersonation/start");
    expect(sent.body.user_id).toBe("u-42");
    expect(sent.body.reason).toBe("문의 재현");
  });

  it("프롬프트 사용 통계: 쓰이지 않는 것을 표시한다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      items: [
        { name: "주간 보고", versions: 3, published_version: 2, latest_version: 3, latest_status: "draft",
          template_refs: 1, template_names: ["주간 템플릿"], schedule_refs: 0, schedule_names: [],
          document_runs: 12, unused: false, last_published_at: "2026-07-01T00:00:00" },
        { name: "쓰다 만 것", versions: 1, published_version: null, latest_version: 1, latest_status: "draft",
          template_refs: 0, template_names: [], schedule_refs: 0, schedule_names: [],
          document_runs: 0, unused: true, last_published_at: null },
      ],
      kind: "prompts",
    }));
    renderScreen("prompt-usage");
    expect(await screen.findByText("쓰이지 않음")).toBeInTheDocument();
    expect(screen.getByText("쓰이는 중")).toBeInTheDocument();
  });
});

describe("감사 로그 — 내보내기 · 이상 징후 연결", () => {
  it("내보내기 버튼이 화면에 실제로 있다(죽은 API 를 만들지 않았다)", async () => {
    apiMock.mockImplementation(() => Promise.resolve({ items: [], total: 0, page_size: 100 }));
    renderScreen("audit");
    expect(await screen.findByRole("button", { name: "CSV 내보내기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "이상 징후 보기" })).toBeInTheDocument();
  });

  it("내보내기 주소가 필터는 남기고 page/page_size 는 뺀다", () => {
    // jsdom 에서는 실제 이동을 가로챌 수 없으므로 계약 함수를 직접 부른다 —
    // DataScreen 은 이 함수의 반환값을 window.location.href 에 그대로 넣는다.
    const action = REGISTRY.audit.headerActions.find((a) => a.download);
    expect(action).toBeTruthy();
    const url = action.download("result=failure&object_type=user&page=2&page_size=100");
    expect(url).toBe("/api/admin/audit/export.csv?result=failure&object_type=user");
    expect(action.download("")).toBe("/api/admin/audit/export.csv");
  });

  it("감사 화면에서 이상 징후 화면으로 갈 수 있다", () => {
    expect(REGISTRY.audit.headerActions.some((a) => a.navigate && a.navigate() === "#/audit-anomalies")).toBe(true);
  });
});
