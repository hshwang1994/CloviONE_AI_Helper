import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 내 프로필의 판 넷이 **같은 세로선**에서 나뉜다.
 *
 * 사용자 지적: 「네모 칸 4개가 크기가 각각 다른데 가로는 맞춰 줄 수 없나, 따로 노는 것 같다.」
 * 실측(뷰포트 2560, 격자 2193)으로 확인한 원인은 두 줄이 서로 반대로 기울어 있던 것이다 —
 * 1줄은 0.85:1.15, 2줄은 1.15:0.85 라 열 사이 이음매가 x=1237 과 x=1561 로 324px 어긋났다.
 * 판 넷의 폭은 921/1245/1245/921 로 두 종류뿐인데 좌우가 뒤바뀌어, 세로로 흐르는 선이 하나도
 * 없었다.
 *
 * ## 이 시험과 옆 시험의 분업
 *
 * **값**(반반인가)은 `s22-visual-contract.test.jsx` 가 소스에서 고정한다.
 * **여기**서는 소스가 아니라 그려진 화면에서만 보이는 것을 잰다 — 두 줄이 정말 같은 격자
 * 선언을 받았는가. `pairTracks` 는 `{ xs, lg }` 반응형 sx 를 돌려주고 MUI(emotion)는 그것을
 * 미디어 질의가 든 **클래스**로 컴파일하므로, 같은 sx 를 받은 두 줄은 같은 클래스를 받는다.
 * 클래스가 같다는 것이 곧 이음매가 한 줄이라는 뜻이다. jsdom 은 폭을 계산하지 않으니(전부 0)
 * 픽셀로 재는 길은 없고, 이것이 계약에 가장 가깝다.
 *
 * 반례를 함께 잰다. 그리고 화면이 실제로 그려졌는지(판 넷이 있는지)를 먼저 확인한다 —
 * 빈 화면에서는 「두 줄이 같다」가 공짜로 통과한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "user", id: "u-1", display_name: "나" } }),
}));

import { Profile } from "./Profile.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const PROFILE = {
  id: "u-1", email: "me@goodmit.co.kr", display_name: "나", role: "user",
  department: "개발팀", title: "선임", last_login_at: "2026-08-03T00:00:00",
  active_session_count: 2, notion_mapping_status: "verified", avatar_url: null,
};

const PREFS = {
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
    quiet_start: "22:00", quiet_end: "08:00", quiet_now: false, reason: null, max_minutes: 1440,
  },
  tour: { version: 1, seen_version: 1, show: false, skipped: false, completed_at: "2026-08-01T00:00:00" },
};

const SESSIONS = {
  items: [
    { id: "s-current", current: true, created_at: "2026-08-03T00:00:00", last_seen_at: "2026-08-03T01:00:00", expires_at: "2026-08-03T08:00:00", client_ip: "10.0.0.1", user_agent: "Chrome" },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path === "/api/profile") return Promise.resolve(PROFILE);
    if (path === "/api/me/preferences") return Promise.resolve(PREFS);
    if (path === "/api/me/sessions") return Promise.resolve(SESSIONS);
    return Promise.resolve({});
  });
});

/** 판을 담는 바깥 격자의 직계 자식 둘 — 그 둘이 화면의 두 줄이다. */
function cardRows(container) {
  const screen = container.querySelector(".c-screen");
  const outer = [...(screen ? screen.children : [])].reverse()
    .find((el) => el.tagName === "DIV" && el.children.length >= 2);
  return outer ? [...outer.children] : [];
}

function renderProfile() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/profile"]}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider><Profile /></ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("내 프로필 — 판 넷이 같은 세로선에서 나뉜다", () => {
  it("두 줄이 같은 격자 클래스를 받는다", async () => {
    const { container } = renderProfile();
    // 판이 다 그려질 때까지 기다린다 — 불러오는 동안에는 뼈대 판 하나뿐이라 그때 재면
    // 「두 줄이 같다」가 공짜로 통과한다(실제로 그렇게 한 번 통과했다).
    await waitFor(() => expect(container.querySelectorAll(".MuiCard-root").length).toBeGreaterThanOrEqual(4));
    expect(cardRows(container)).toHaveLength(2);

    const [a, b] = cardRows(container);
    expect(a.className).not.toBe("");
    expect(a.className).toBe(b.className);
  });

  it("반례 — 한 줄만 다른 클래스를 받으면 그 시험이 깨진다", async () => {
    const { container } = renderProfile();
    await waitFor(() => expect(container.querySelectorAll(".MuiCard-root").length).toBeGreaterThanOrEqual(4));

    const rows = cardRows(container);
    rows[1].className = `${rows[1].className} css-tilted`;
    expect(rows[0].className).not.toBe(rows[1].className);
  });

  it("반례 — 판을 못 찾으면 첫 시험의 관문에 걸린다", () => {
    const empty = document.createElement("div");
    expect(cardRows(empty)).toHaveLength(0);
    expect(empty.querySelectorAll(".MuiCard-root")).toHaveLength(0);
  });
});
