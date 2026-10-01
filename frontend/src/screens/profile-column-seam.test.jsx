import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* qa-contract-change: 이 화면이 「두 열 두 줄」에서 「전폭 신원 머리 + 두 열 한 줄」로 바뀌었다(5-3 시안 #5c). 줄이 하나면 「두 줄이 같은 이음매를 쓰는가」는 잴 대상이 없어진다 — 지우지 않고 방향을 바꿔 다시 적는다: 신원 머리가 정말 두 열 **밖**의 전폭인가, 그 한 줄이 여전히 공용 `pairTracks` 선언을 받는가. 단언은 늘었다.
 *
 * 내 프로필의 **신원 머리는 전폭이고, 설정 판은 한 줄에서 반반이다.**
 *
 * ## 왜 계약인가
 *
 * 사용자 지적: 「네모 칸 4개가 크기가 각각 다른데 가로는 맞춰 줄 수 없나, 따로 노는 것 같다.」
 * 실측(뷰포트 2560, 격자 2193)으로 확인한 원인은 두 줄이 서로 반대로 기울어 있던 것이다 —
 * 1줄은 0.85:1.15, 2줄은 1.15:0.85 라 열 사이 이음매가 x=1237 과 x=1561 로 324px 어긋났다.
 * 지금은 설정 줄이 하나라 그 어긋남이 생길 자리가 없다. 대신 새 실패 갈래가 생겼다:
 * **신원 머리가 두 열 안으로 들어가는 것**이다. 들어가는 순간 「내가 누구인가」가 판 하나의
 * 폭으로 줄고 아바타·이름·사실 넷·동작 셋이 세로로 접힌다 — 이 화면이 고친 바로 그 모양이다.
 *
 * ## 이 시험과 옆 시험의 분업
 *
 * **값**(반반인가)은 `s22-visual-contract.test.jsx` 가 소스에서 고정한다.
 * **여기**서는 소스가 아니라 그려진 화면에서만 보이는 것을 잰다 — 머리가 두 열 밖에 있는가,
 * 설정 줄이 정말 공용 격자 선언을 받았는가. `pairTracks` 는 `{ xs, lg }` 반응형 sx 를
 * 돌려주고 MUI(emotion)는 그것을 미디어 질의가 든 **클래스**로 컴파일하므로, 그 선언을 받은
 * 줄은 빈 클래스가 아니다. jsdom 은 폭을 계산하지 않으니(전부 0) 픽셀로 재는 길은 없고,
 * 이것이 계약에 가장 가깝다.
 *
 * 반례를 함께 잰다. 그리고 화면이 실제로 그려졌는지(판 다섯이 있는지)를 먼저 확인한다 —
 * 빈 화면에서는 이 단언들이 공짜로 통과한다.
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
  // 메일로도 받기(계획 3.4)는 같은 판 안의 아래 구획이다 - 이 구획이 있어도 왼쪽 열은 판 하나여야 한다.
  mail: {
    enabled: true, types: ["ticket_assigned"],
    catalog: [{ key: "ticket_assigned", label: "티켓 배정", help: "누군가 나를 티켓 담당자로 지정했을 때" }],
    delivery: { state: "failing", message: "메일 발송이 지금 실패하고 있어 메일 알림이 늦게 도착할 수 있습니다." },
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

/** 판을 담는 바깥 격자의 직계 자식 — [신원 머리, 설정 두 열] 이다. */
function cardRows(container) {
  const screen = container.querySelector(".c-screen");
  /* 페이지 머리(`.k-page-head`)는 판 격자가 아니다 — 경로 · 제목 줄 · 설명을 담는 한 상자다(D-528). */
  const outer = [...(screen ? screen.children : [])].reverse()
    .find((el) => el.tagName === "DIV" && !el.classList.contains("k-page-head") && el.children.length >= 2);
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

describe("내 프로필 — 신원 머리는 전폭이고 설정은 한 줄에서 반반이다", () => {
  it("바깥 격자는 [신원 머리, 설정 두 열] 둘이고 머리가 먼저다", async () => {
    const { container } = renderProfile();
    // 판이 다 그려질 때까지 기다린다 — 불러오는 동안에는 뼈대 판 하나뿐이라 그때 재면
    // 이 단언들이 공짜로 통과한다(실제로 그렇게 한 번 통과했다).
    await waitFor(() => expect(container.querySelectorAll(".MuiCard-root").length).toBeGreaterThanOrEqual(5));
    const rows = cardRows(container);
    expect(rows).toHaveLength(2);

    const [head, settings] = rows;
    /* 🔴 머리는 **판 그 자체**다 — 두 열을 담는 상자가 아니다. 여기 격자가 끼면 「내가
       누구인가」가 한 열 폭으로 줄고 아바타·이름·사실 넷·동작 셋이 세로로 접힌다. */
    expect(head.className).toContain("MuiCard-root");
    expect(settings.className).not.toContain("MuiCard-root");
    // 설정 줄은 공용 격자 선언을 받았다 — 손으로 그린 격자면 클래스가 안 붙는다.
    expect(settings.className).not.toBe("");
  });

  it("신원 머리는 두 열 **밖**이다 — 이름과 아바타가 설정 판 안으로 들어가지 않는다", async () => {
    const { container } = renderProfile();
    await waitFor(() => expect(container.querySelectorAll(".MuiCard-root").length).toBeGreaterThanOrEqual(5));
    const [head, settings] = cardRows(container);

    const avatar = container.querySelector(".k-avatar");
    expect(avatar).toBeTruthy();
    expect(head.contains(avatar)).toBe(true);
    expect(settings.contains(avatar)).toBe(false);
  });

  it("설정 줄은 판 넷을 담는다 — 왼쪽 하나, 오른쪽 셋 이상", async () => {
    const { container } = renderProfile();
    await waitFor(() => expect(container.querySelectorAll(".MuiCard-root").length).toBeGreaterThanOrEqual(5));
    const [, settings] = cardRows(container);
    expect(settings.children).toHaveLength(2);
    // 왼쪽은 판 하나(알림 설정), 오른쪽은 판들을 담는 세로 격자다.
    expect(settings.children[0].className).toContain("MuiCard-root");
    expect(settings.children[1].querySelectorAll(":scope > .MuiCard-root").length).toBeGreaterThanOrEqual(3);
  });

  it("반례 — 머리가 설정 줄 안으로 들어가면 그 시험이 깨진다", async () => {
    const { container } = renderProfile();
    await waitFor(() => expect(container.querySelectorAll(".MuiCard-root").length).toBeGreaterThanOrEqual(5));

    const [head, settings] = cardRows(container);
    settings.appendChild(head);
    // 바깥 격자가 더는 [머리, 설정] 둘이 아니다 — 첫 시험이 여기서 걸린다.
    expect(cardRows(container)).not.toHaveLength(2);
    // 그리고 아바타가 설정 줄 안으로 들어갔다 — 둘째 시험이 여기서 걸린다.
    expect(settings.contains(container.querySelector(".k-avatar"))).toBe(true);
  });

  it("반례 — 판을 못 찾으면 첫 시험의 관문에 걸린다", () => {
    const empty = document.createElement("div");
    expect(cardRows(empty)).toHaveLength(0);
    expect(empty.querySelectorAll(".MuiCard-root")).toHaveLength(0);
  });
});

/* 조용시간의 저장 단추는 페이지 동작 높이(34)다 — 입력칸(34)과 같은 높이 · 같은 윗선으로 줄(`FieldRow`)의 동작 칸에 선다
 * (핸드오프 ACCEPTANCE C1 · RULES §14, D-527). 예전에는 `alignSelf: stretch` 로 입력칸 높이(36)에 섰다. */
describe("내 프로필 — 조용시간 저장 단추", () => {
  it("저장 단추는 줄의 동작 칸에 위로 붙는 기본 단추다", async () => {
    const { container } = renderProfile();
    await waitFor(() => expect(container.querySelectorAll(".MuiCard-root").length).toBeGreaterThanOrEqual(5));
    const save = [...container.querySelectorAll("button")].find((b) => b.textContent.trim() === "시간 저장");
    expect(save).toBeTruthy();
    expect(save.className).toContain("MuiButton-sizeMedium");
    const slot = save.closest(".k-field-row-action-slot");
    expect(slot, "단추는 줄(FieldRow)의 동작 칸에 선다").toBeTruthy();
    expect(getComputedStyle(slot).alignItems).toBe("flex-start");
    expect(getComputedStyle(save).alignSelf).not.toBe("stretch");
  });
});
