import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* qa-contract-change: r23 지시서(D-591)가 알림 셋(메일 알림 · 알림 배지 · 방해금지)을 왼쪽 열에 모았다 — 셋은 서로 다른 기능이고(방해금지는
 * 배지 숫자만 숨기며 메일을 멈추지 않는다) 한 열에 나란히 서야 그 차이가 읽힌다. 그래서 5-3 의 오른쪽 순서에서 방해금지만 왼쪽 알림 판 뒤로
 * 옮겼고, 오른쪽 열은 「내 기기 → 화면 효과 → 강조색 → 둘러보기」다. 단언은 두 열의 순서와 「같은 열」을 모두 잰다.
 *
 * qa-contract-change: 왼쪽 판의 이름이 「알림 설정」에서 「알림 배지」로 바뀌었다(D-550) - 메일 알림이 제 카드가 되며 이 판은 배지만
 * 다룬다. 순서 단언은 같은 판을 새 이름으로 찾는다.
 *
 * qa-contract-change: 소유자가 5-3 에서 오른쪽 열의 순서를 「내 기기 → 방해금지 → 강조색 → 둘러보기」로 직접 지정했다 — 지시 18 의 「둘러보기가 강조색보다 위」를 뒤집는다. 그 지시의 근거는 「둘러보기가 스크롤 끝에 있다」였는데, 신원 머리가 전폭으로 나가고 설정이 한 줄이 되면서 오른쪽 열은 판 넷짜리 짧은 레일이 됐다. 단언은 늘었다 — 방향만 뒤집는 대신 레일 전체의 순서를 잰다.
 *
 * 내 프로필의 **순서**와 아바타 자리.
 *
 * ## 순서가 왜 계약인가
 *
 * 오른쪽 레일 넷은 급한 순서다: **계정 안전(내 기기) → 알림이 언제 조용한가(방해금지) →
 * 이 브라우저의 취향(강조색) → 안내(둘러보기)**. 앞의 둘은 남이 내 계정으로 들어와 있는지,
 * 내가 알림을 놓치고 있는지를 답하고 뒤의 둘은 급하지 않다.
 *
 * 예전 계약은 「둘러보기가 강조색보다 위」였고(지시 18), 그 근거는 처음 온 사람이 취향부터
 * 고르고 사용법은 **스크롤 끝에서** 만난다는 것이었다. 그 근거가 지금은 약하다 — 판이 전폭
 * 머리 하나와 두 열 한 줄이라 이 레일은 화면 안에 다 들어오고, 둘러보기는 스크롤 끝이 아니라
 * 오른쪽 레일의 마지막이다(왼쪽 알림 목록이 스무 줄이라 페이지의 바닥은 그쪽이 정한다).
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
  /* 🔴 오른쪽 레일은 **급한 순서**다. 계정에 남이 들어와 있는지가 먼저이고, 취향과 안내가
     마지막이다. 하나만 재면 그 하나만 지켜지므로 넷을 이어서 잰다. */
  it("왼쪽 열은 알림 셋이다 — 메일 알림 → 알림 배지 → 방해금지가 한 열에 선다 (D-591)", async () => {
    mount();
    const badge = await screen.findByRole("heading", { name: "알림 배지" });
    const dnd = await screen.findByRole("heading", { name: "방해금지" });
    expect(order(badge, dnd)).toBe(-1);
    const column = (el) => el.closest(".MuiCard-root").parentElement;
    expect(column(dnd)).toBe(column(badge));
    // 메일 알림 판은 서버가 메일 묶음을 줄 때만 선다(이 시험의 응답에는 없다) — 서면 맨 앞이다(옆 시험이 구조로 잰다).
    const mail = screen.queryByRole("heading", { name: "메일 알림" });
    if (mail) { expect(order(mail, badge)).toBe(-1); expect(column(mail)).toBe(column(badge)); }
  });

  it("오른쪽 열은 내 기기 → 화면 효과 → 강조색 → 둘러보기 순이고 방해금지가 없다", async () => {
    mount();
    const devices = await screen.findByRole("heading", { name: /내 기기/ });
    const effects = await screen.findByRole("heading", { name: "화면 효과" });
    const accent = await screen.findByRole("heading", { name: /강조색/ });
    const tour = await screen.findByRole("heading", { name: "둘러보기" });
    const dnd = await screen.findByRole("heading", { name: "방해금지" });
    expect(order(devices, effects)).toBe(-1);
    expect(order(effects, accent)).toBe(-1);
    expect(order(accent, tour)).toBe(-1);
    const column = (el) => el.closest(".MuiCard-root").parentElement;
    expect(column(dnd)).not.toBe(column(devices));
  });

  it("신원 머리는 설정 전부보다 위에 있다 — 내가 누구인가가 먼저다", async () => {
    mount();
    /* 이 판의 제목은 사람 이름이다 — 「계정」이라는 이름표가 따로 설 자리가 없다. */
    const identity = await screen.findByRole("heading", { level: 2, name: "나" });
    const notifications = await screen.findByRole("heading", { name: "알림 배지" });
    const devices = await screen.findByRole("heading", { name: /내 기기/ });
    const tour = await screen.findByRole("heading", { name: "둘러보기" });
    expect(order(identity, notifications)).toBe(-1);
    expect(order(identity, devices)).toBe(-1);
    expect(order(identity, tour)).toBe(-1);
  });

  /* 신원 머리가 **전폭**이라는 것은 「알림 배지와 같은 줄에 서지 않는다」는 뜻이다. 한 열
     안으로 들어가면 아바타·이름·사실 넷·동작 셋이 세로로 접힌다(옆 시험이 구조로 잰다). */
  it("신원 머리는 알림 배지와 다른 판이다", async () => {
    const { container } = mount();
    const identity = await screen.findByRole("heading", { level: 2, name: "나" });
    const notifications = await screen.findByRole("heading", { name: "알림 배지" });
    const headCard = identity.closest(".MuiCard-root");
    expect(headCard).toBeTruthy();
    expect(headCard.contains(notifications)).toBe(false);
    expect(container.querySelectorAll(".MuiCard-root").length).toBeGreaterThanOrEqual(5);
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
