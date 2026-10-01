import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
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
  id: "u-1",
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

  /* D-525 — 저장 중에 스위치를 끄지 않는다. 예전에는 저장이 도는 동안 모든 스위치가 비활성이 되어 하나를 누를 때마다
     목록 전체가 번쩍였고, 손잡이는 응답이 와서야 움직였다. 지금은 누른 순간 바뀌고, 저장은 한 줄로 나가며, 둘째
     요청은 첫 변경을 품는다(목록 전체를 보내는 저장이라 옛 목록에서 계산하면 앞 변경을 지운다). */
  it("저장이 도는 동안에도 스위치는 켜져 있고, 누른 순간 바뀌며, 둘째 저장은 첫 응답 뒤에 두 변경을 함께 싣는다", async () => {
    const pending = [];
    apiMock.mockImplementation((path, options) => {
      if (path === "/api/me/preferences" && options && options.method === "PATCH") {
        return new Promise((resolve) => pending.push(() => resolve(prefs(patched(options.body)))));
      }
      return route(path, options);
    });
    const patches = () => apiMock.mock.calls.filter(([p, o]) => p === "/api/me/preferences" && o && o.method === "PATCH");
    renderProfile();
    const job = await screen.findByRole("switch", { name: "작업 실패 배지 알림" });
    const mention = screen.getByRole("switch", { name: "@멘션 배지 알림" });
    expect(job).toBeChecked();
    expect(mention).toBeChecked();

    await userEvent.click(job);
    // 응답 전이다 — 누른 스위치는 이미 바뀌었고 어느 스위치도 비활성이 아니다.
    expect(job).not.toBeChecked();
    expect(job).toBeEnabled();
    expect(mention).toBeEnabled();

    await userEvent.click(mention);
    expect(mention).not.toBeChecked();
    // 둘째 저장은 아직 나가지 않았다 — 같은 대상의 저장은 한 줄이다.
    expect(patches()).toHaveLength(1);

    await act(async () => { pending[0](); });
    await waitFor(() => expect(patches()).toHaveLength(2));
    expect(patches()[1][1].body).toEqual({ muted_types: ["job_failed", "chat_mentioned"] });
    // 첫 응답(작업 실패만 뮤트)이 줄 선 둘째 토글을 되돌리지 않았다.
    expect(mention).not.toBeChecked();

    await act(async () => { pending[1](); });
    await waitFor(() => expect(screen.getByText("설정을 저장했습니다.")).toBeInTheDocument());
    expect(job).not.toBeChecked();
    expect(mention).not.toBeChecked();
    // 성공 알림은 줄이 빌 때 한 번이다 — 연달아 바꿀 때 토스트가 쌓이지 않는다.
    expect(screen.getAllByText("설정을 저장했습니다.")).toHaveLength(1);
  });

  it("저장이 실패하면 스위치는 원래 자리로 돌아가고 까닭을 알린다", async () => {
    apiMock.mockImplementation((path, options) => {
      if (path === "/api/me/preferences" && options && options.method === "PATCH") {
        return Promise.reject(new Error("설정을 저장하지 못했습니다."));
      }
      return route(path, options);
    });
    renderProfile();
    const job = await screen.findByRole("switch", { name: "작업 실패 배지 알림" });
    await userEvent.click(job);
    expect(await screen.findByText("설정을 저장하지 못했습니다.")).toBeInTheDocument();
    await waitFor(() => expect(job).toBeChecked());
  });

  it("보안 알림은 끌 수 없다는 사실을 화면이 말한다", async () => {
    renderProfile();
    expect(await screen.findByText(/보안에 관한 알림은 끌 수 없습니다/)).toBeInTheDocument();
  });

  it("프로필 큰 아바타는 사용자 id 로 그린다 — 이름이면 상단바와 다른 얼굴이 된다", async () => {
    const { autoAvatarKey, preloadAvatarStyles } = await import("../ui/DefaultAvatar.jsx");
    await preloadAvatarStyles();
    renderProfile();
    await screen.findByText("me@goodmit.co.kr");
    const face = await waitFor(() => {
      const el = document.querySelector("[data-avatar-key]");
      expect(el).toBeTruthy();
      return el;
    });
    expect(face).toHaveAttribute("data-avatar-key", autoAvatarKey("u-1"));
    expect(face.getAttribute("data-avatar-key")).not.toBe(autoAvatarKey("나"));
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

  /* WF1 R1 — Users.jsx(관리자의 다른 사용자 세션 목록)는 진작 shortUA+Tooltip으로 UA를 60자로
   * 잘라 보여줬는데, 같은 모양의 데이터를 그리는 이 화면(내 기기 목록)만 원문을 그대로 냈다.
   * 실제 브라우저 UA 문자열은 흔히 100자를 넘어 카드 폭을 밀어냈다. */
  it("긴 user-agent 는 60자로 잘려 보이고 전체 문구는 title(Tooltip)로 남는다", async () => {
    const longUA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36";
    apiMock.mockImplementation((path) => {
      if (path === "/api/me/sessions") {
        return Promise.resolve({ items: [
          { id: "s-current", current: true, created_at: "2026-08-03T00:00:00", last_seen_at: "2026-08-03T01:00:00", expires_at: "2026-08-03T08:00:00", client_ip: "10.0.0.1", user_agent: longUA },
        ] });
      }
      return route(path);
    });
    renderProfile();
    await screen.findByText("지금 이 창");
    expect(screen.queryByText(longUA)).not.toBeInTheDocument();
    const shown = screen.getByText(longUA.slice(0, 60) + "…");
    expect(shown).toBeInTheDocument();

    // 화면엔 잘린 문구뿐이지만, 전체 문구는 hover 시 Tooltip으로 여전히 확인할 수 있다(사라진 게
    // 아니라 기본으로 숨겨졌을 뿐이다).
    await userEvent.hover(shown);
    expect(await screen.findByRole("tooltip")).toHaveTextContent(longUA);
  });
});

describe("메일로도 받기", () => {
  const MAIL = {
    enabled: false,
    types: ["ticket_assigned", "ticket_status_changed"],
    catalog: [
      { key: "ticket_assigned", label: "티켓 배정", help: "누군가 나를 티켓 담당자로 지정했을 때" },
      { key: "ticket_status_changed", label: "티켓 상태 변경", help: "지켜보거나 맡은 티켓의 상태가 바뀌었을 때" },
    ],
    delivery: { state: "ok", message: null },
  };

  function withMail(mail) {
    apiMock.mockImplementation((path, options) => {
      if (path === "/api/me/preferences" && !(options && options.method === "PATCH")) {
        return Promise.resolve(prefs({ mail }));
      }
      if (path === "/api/me/preferences") return Promise.resolve(prefs({ mail: { ...mail, enabled: true } }));
      return route(path, options);
    });
  }

  it("큰 스위치는 켜짐 하나만 보내고, 꺼져 있으면 유형 스위치는 누를 수 없다", async () => {
    withMail(MAIL);
    renderProfile();
    const typeSwitch = await screen.findByRole("switch", { name: "티켓 배정 메일로 받기" });
    expect(typeSwitch).toBeDisabled();
    await userEvent.click(screen.getByRole("switch", { name: "알림을 메일로도 받기" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/me/preferences", {
      method: "PATCH", body: { mail_enabled: true },
    }));
  });

  it("유형 스위치는 받을 유형 전체를 보낸다", async () => {
    withMail({ ...MAIL, enabled: true });
    renderProfile();
    await userEvent.click(await screen.findByRole("switch", { name: "티켓 배정 메일로 받기" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/api/me/preferences", {
      method: "PATCH", body: { mail_types: ["ticket_status_changed"] },
    }));
  });

  it("메일 발송이 정상이 아니면 그 까닭을 한 문장으로 먼저 말한다", async () => {
    withMail({ ...MAIL, delivery: { state: "unconfigured", message: "관리자가 메일 발송을 설정하지 않아 지금은 메일 알림이 나가지 않습니다." } });
    renderProfile();
    expect(await screen.findByText(/메일 발송을 설정하지 않아/)).toBeInTheDocument();
  });

  it("반례: 관리자가 허용한 유형이 없으면 스위치 대신 그 사실을 말한다", async () => {
    withMail({ ...MAIL, catalog: [], types: [] });
    renderProfile();
    expect(await screen.findByText(/메일로 보낼 알림을 아직 정하지 않았습니다/)).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "알림을 메일로도 받기" })).toBeNull();
  });
});
