import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 내 프로필의 **순서**와 아바타 자리 (지시 18).
 *
 * ## 순서가 왜 계약인가
 *
 * 둘러보기는 「제품을 어떻게 쓰는가」를 알려 주는 자리이고 강조색은 취향이다. 예전에는
 * 둘러보기가 이 화면 맨 아래, 강조색 **다음**이었다 — 처음 온 사람이 취향부터 고르고
 * 사용법은 스크롤 끝에서 만난다.
 *
 * 순서는 눈으로만 확인되는 종류라 조용히 되돌아간다(카드 하나를 옮기면 끝이다). 그래서
 * DOM 순서를 직접 본다.
 *
 * ## 아바타 넷
 *
 * 지시 18 이 이름으로 적은 넷 — 현재 아바타 · 사진 바꾸기 · 기본 아바타 선택 · 자르기
 * 대화상자 — 이 전부 이 화면에 있는가. 다른 화면으로 흩어지면 「내 사진을 어디서 바꾸지」의
 * 답이 두 곳이 된다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...a) => apiMock(...a), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { id: "u-1", display_name: "나", role: "user" } }),
}));

import { Profile } from "./Profile.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const PROFILE = {
  id: "u-1",
  email: "me@goodmit.co.kr", display_name: "나", role: "user",
  department: "개발팀", title: "선임", last_login_at: "2026-08-03T00:00:00",
  active_session_count: 1, notion_mapping_status: "verified", avatar_url: null,
};

const PREFS = {
  avatar: { url: null, updated_at: null },
  notifications: { muted_types: [], catalog: [], unmutable: [] },
  dnd: {
    enabled: false, until: null, quiet_hours_enabled: false,
    quiet_start: "22:00", quiet_end: "08:00", quiet_now: false, reason: null,
    max_minutes: 1440,
  },
  tour: { version: 1, seen_version: 1, show: false, skipped: false, completed_at: "2026-08-01T00:00:00" },
};

function mount() {
  apiMock.mockImplementation((url) => {
    const u = String(url);
    if (u === "/api/profile") return Promise.resolve(PROFILE);
    if (u === "/api/me/preferences") return Promise.resolve(PREFS);
    if (u === "/api/me/sessions") return Promise.resolve({ items: [] });
    return Promise.resolve({ ok: true, items: [] });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider><ToastProvider><ConfirmProvider>
          <Profile />
        </ConfirmProvider></ToastProvider></ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** 두 제목의 문서 순서. 앞엣것이 먼저면 음수다. */
function order(a, b) {
  return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
}

beforeEach(() => { apiMock.mockReset(); });

describe("내 프로필 — 순서", () => {
  it("🔴 둘러보기가 개인 UI 설정(강조색)보다 위에 있다", async () => {
    mount();
    const tour = await screen.findByRole("heading", { name: "둘러보기" });
    const accent = await screen.findByRole("heading", { name: /강조색/ });
    expect(order(tour, accent)).toBe(-1);
  });

  it("계정 카드는 둘러보기보다 위에 있다 — 내가 누구인가가 먼저다", async () => {
    mount();
    const tour = await screen.findByRole("heading", { name: "둘러보기" });
    const account = await screen.findByRole("heading", { name: /프로필 사진|계정/ });
    expect(order(account, tour)).toBe(-1);
  });
});

describe("내 프로필 — 아바타", () => {
  it("사진과 기본 아바타 선택이 둘 다 이 화면에 있다", async () => {
    mount();
    // 현재 아바타 — 사진이 없어도 기본 그림이 선다(지시 6).
    await waitFor(() => expect(document.querySelector(".k-avatar")).toBeTruthy());
    expect(await screen.findByRole("button", { name: /사진 바꾸기/ })).toBeTruthy();
    // 기본 아바타 고르개. 사진과 **다른 축**이라 사진이 없어도 있어야 한다.
    expect(await screen.findByText(/기본 아바타/)).toBeTruthy();
  });
});
