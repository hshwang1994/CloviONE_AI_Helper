import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 후보 목록을 **못 받은 축은 그렇다고 말한다** (R7-05).
 *
 * `config.refLists` 는 다른 화면의 리소스(사람·워크플로·일정)를 한 번에 받아 조건 축과 폼
 * 칸의 후보로 쓴다. 예전에는 `Promise.all` 이라 하나가 403 이면 이 화면의 **모든** 후보가
 * 함께 비었고, 그것을 `allSettled` 로 갈라 놓은 것이 앞선 수정이다. 그런데 실패를 빈 배열로만
 * 접어 두면 두 번째 거짓말이 남는다 — 질의가 언제나 이행되므로 오류 상태로 갈 길이 없고,
 * 후보가 0개인 축은 화면에서 「고를 것이 없다」와 똑같이 보인다. 운영자가 사람 축을 열면
 * 빈 상자만 있고, 그것은 「이 시스템에 사람이 없다」로 읽힌다. `lib/api.js` 의 FAIL-01 이
 * 금지하는 바로 그 모양이다 — 「실패인데 '데이터가 없다'고 말하는 것보다 나쁜 게 없다」.
 *
 * 여기서 고정하는 것: 실패한 축은 이유를 달고, **다른 축은 아무 영향이 없다.**
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));
vi.mock("../app/auth.jsx", () => ({ useAuth: () => ({ data: { role: "operator", id: "u-op", management: { kind: "org" } } }) }));

import { DataScreen } from "./DataScreen.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const REASON = "후보 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";

const CONFIG = {
  key: "jobs", area: "운영", title: "작업 큐", endpoint: "/api/admin/jobs",
  columns: [{ key: "kind", label: "종류", identifier: true }],
  refLists: [
    { key: "people", endpoint: "/api/admin/people", labelKey: "display_name" },
    { key: "schedules", endpoint: "/api/admin/schedules" },
  ],
  filters: [
    { key: "user_id", label: "행위자", optionsFromRefList: "people" },
    { key: "schedule_id", label: "연결된 일정", optionsFromRefList: "schedules" },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
});

function answer(peopleOk) {
  apiMock.mockImplementation((path) => {
    if (String(path).startsWith("/api/admin/people")) {
      return peopleOk
        ? Promise.resolve({ items: [{ id: "u-1", display_name: "김지훈" }] })
        : Promise.reject(Object.assign(new Error("권한이 없습니다."), { status: 403 }));
    }
    if (String(path).startsWith("/api/admin/schedules")) {
      return Promise.resolve({ items: [{ id: "s-1", name: "야간 배치" }] });
    }
    return Promise.resolve({ items: [{ id: "j-1", kind: "mail" }], total: 1 });
  });
}

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <DataScreen config={CONFIG} />
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("후보 목록을 못 받은 조건 축 (R7-05)", () => {
  it("403 이 난 축은 빈 상자로 끝내지 않고 왜 비었는지 말한다", async () => {
    answer(false);
    renderScreen();
    await screen.findByText("mail");

    expect(await screen.findByText(REASON)).toBeInTheDocument();
    // 실패한 축은 하나다 — 안내도 하나뿐이어야 한다(다른 축까지 물들면 앞 결함의 재발이다).
    expect(screen.getAllByText(REASON)).toHaveLength(1);
  });

  /* 이 하나는 **고치기 전에도 통과했어야 한다** — 실패한 축 하나가 다른 축을 비우는 것은
     앞선 `allSettled` 수정이 이미 없앤 결함이고, 이유를 다는 이번 변경이 그것을 되살리면
     안 된다. 그래서 동기점을 안내 문구가 아니라 **살아 있는 축의 후보**에 둔다. */
  it("같은 화면의 성공한 축은 후보를 그대로 들고 있다", async () => {
    const user = (await import("@testing-library/user-event")).default.setup();
    answer(false);
    renderScreen();
    await screen.findByText("mail");

    await user.click(await screen.findByRole("combobox", { name: "연결된 일정" }));
    expect(await screen.findByText("야간 배치")).toBeInTheDocument();
  });

  it("반례 — 둘 다 받아지면 아무 안내도 안 뜬다", async () => {
    answer(true);
    renderScreen();
    await screen.findByText("mail");

    expect(await screen.findByRole("combobox", { name: "행위자" })).toBeInTheDocument();
    expect(screen.queryByText(REASON)).toBeNull();
  });
});
