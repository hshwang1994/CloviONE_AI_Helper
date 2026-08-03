import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 내 프로필 화면 — 세션 해제와 방해금지가 **사용자에게 정직하게 보이는가**.
 *
 * 여기서 고정하는 것:
 *   1) 지금 쓰는 창은 '현재'로 표시되고 **그 줄에는 로그아웃 버튼이 없다**. 어느 줄이
 *      이 창인지 모르면 무서워서 아무것도 못 끊는다.
 *   2) '다른 기기 모두 로그아웃'은 **확인을 받고** 나서 실행된다(되돌릴 수 없는 보안 동작).
 *   3) 방해금지 안내가 "알림은 그대로 쌓인다"를 실제로 말한다 — 무엇을 포기하는지 모르는 채
 *      켜게 두면 놓친 다음 날 이 기능을 영영 안 쓴다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u-1", display_name: "나" } }),
}));

import { Profile } from "./Profile.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const PROFILE = {
  email: "me@goodmit.co.kr", display_name: "나", role: "user",
  department: "개발팀", title: "선임", last_login_at: "2026-08-03T00:00:00",
  active_session_count: 2, notion_mapping_status: "verified", avatar_url: null,
};

function prefs(over = {}) {
  return {
    avatar: { url: null, updated_at: null },
    notifications: {
      muted_types: [],
      catalog: [
        { key: "job_failed", label: "작업 실패", help: "자동화 작업이 실패했을 때" },
        { key: "chat_mentioned", label: "@멘션", help: "채팅에서 누군가 나를 불렀을 때" },
      ],
      unmutable: ["account_locked"],
    },
    dnd: {
      enabled: false, until: null, quiet_hours_enabled: false,
      quiet_start: "22:00", quiet_end: "08:00", quiet_now: false, reason: null,
      max_minutes: 1440,
    },
    tour: { version: 1, seen_version: 1, show: false, skipped: false, completed_at: "2026-08-01T00:00:00" },
    ...over,
  };
}

const SESSIONS = {
  items: [
    { id: "s-current", current: true, created_at: "2026-08-03T00:00:00", last_seen_at: "2026-08-03T01:00:00", expires_at: "2026-08-03T08:00:00", client_ip: "10.0.0.1", user_agent: "Chrome" },
    { id: "s-other", current: false, created_at: "2026-08-01T00:00:00", last_seen_at: "2026-08-02T09:00:00", expires_at: "2026-08-03T08:00:00", client_ip: "10.0.0.9", user_agent: "Safari" },
  ],
};

function route(path, options) {
  if (path === "/api/profile") return Promise.resolve(PROFILE);
  if (path === "/api/me/preferences") {
    if (options && options.method === "PATCH") return Promise.resolve(prefs(patched(options.body)));
    return Promise.resolve(prefs());
  }
  if (path === "/api/me/sessions") return Promise.resolve(SESSIONS);
  if (path === "/api/me/sessions/revoke-others") return Promise.resolve({ ok: true, revoked_count: 1 });
  return Promise.resolve({});
}

// PATCH 응답을 서버처럼 흉내 낸다(서버는 변경 후 전체 설정을 되돌려준다).
function patched(body) {
  const dnd = { enabled: false, until: null, quiet_hours_enabled: false, quiet_start: "22:00", quiet_end: "08:00", quiet_now: false, reason: null, max_minutes: 1440 };
  if (body && body.dnd_enabled) { dnd.enabled = true; dnd.quiet_now = true; dnd.reason = "manual"; }
  return { dnd, notifications: { muted_types: (body && body.muted_types) || [], catalog: prefs().notifications.catalog, unmutable: ["account_locked"] } };
}

function renderProfile() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/profile"]}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Profile />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation(route);
});

describe("내 프로필", () => {
  it("계정 정보와 내 기기를 함께 보여 준다", async () => {
    renderProfile();
    expect(await screen.findByText("me@goodmit.co.kr")).toBeInTheDocument();
    expect(screen.getByText("개발팀")).toBeInTheDocument();
    expect(await screen.findByText("지금 이 창")).toBeInTheDocument();
    expect(screen.getByText("다른 기기")).toBeInTheDocument();
  });

  it("지금 쓰는 창에는 '이 기기 로그아웃'이 없다", async () => {
    renderProfile();
    await screen.findByText("지금 이 창");
    const buttons = screen.getAllByRole("button", { name: "이 기기 로그아웃" });
    // 세션 두 개 중 '현재'가 아닌 하나에만 붙는다.
    expect(buttons).toHaveLength(1);
  });

  it("'다른 기기 모두 로그아웃'은 확인을 받은 뒤에만 실행된다", async () => {
    renderProfile();
    const trigger = await screen.findByRole("button", { name: /다른 기기 모두 로그아웃/ });
    await userEvent.click(trigger);

    // 확인 모달이 뜨고, 아직 서버를 부르지 않았다.
    expect(await screen.findByText(/지금 보고 있는 이 창은 그대로 두고/)).toBeInTheDocument();
    expect(apiMock).not.toHaveBeenCalledWith("/api/me/sessions/revoke-others", expect.anything());

    await userEvent.click(screen.getByRole("button", { name: "모두 로그아웃" }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith("/api/me/sessions/revoke-others", {
        method: "POST", body: {},
      })
    );
  });

  it("방해금지 안내가 '알림은 그대로 쌓인다'를 말한다", async () => {
    renderProfile();
    expect(await screen.findByText(/방해금지 중에도 알림은 평소대로 쌓입니다/)).toBeInTheDocument();
  });

  it("방해금지를 켜면 지금 조용하다는 사실과 알림이 쌓이고 있다는 사실을 함께 알린다", async () => {
    renderProfile();
    const toggle = await screen.findByRole("switch", { name: "방해금지" });
    await userEvent.click(toggle);
    expect(await screen.findByText(/알림은 계속 쌓이고 있습니다/)).toBeInTheDocument();
  });

  it("유형 스위치를 끄면 그 유형만 뮤트로 보낸다(다른 유형은 그대로)", async () => {
    renderProfile();
    const jobSwitch = await screen.findByRole("switch", { name: "작업 실패 배지 알림" });
    await userEvent.click(jobSwitch);
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith("/api/me/preferences", {
        method: "PATCH", body: { muted_types: ["job_failed"] },
      })
    );
  });

  it("보안 알림은 끌 수 없다는 사실을 화면이 말한다", async () => {
    renderProfile();
    expect(await screen.findByText(/보안에 관한 알림은 끌 수 없습니다/)).toBeInTheDocument();
  });

  it("설정 조회가 실패하면 다시 시도할 길을 준다", async () => {
    apiMock.mockImplementation((path) => {
      if (path === "/api/me/preferences") {
        return Promise.reject(Object.assign(new Error("서버 오류"), { status: 500 }));
      }
      return route(path);
    });
    renderProfile();
    expect(await screen.findByText("불러오지 못했습니다")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /다시 시도/ })).toBeInTheDocument();
  });
});
