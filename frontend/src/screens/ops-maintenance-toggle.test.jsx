import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 유지보수 모드 전환의 실제 확인/전송 흐름.
 *
 * ops-maintenance.test.jsx는 쓰기 권한이 없을 때 버튼이 "보이되 비활성"인지만 확인한다 —
 * 쓰기 권한이 있는 관리자가 실제로 버튼을 눌렀을 때 확인 대화상자가 뜨고, 취소하면 아무 일도
 * 일어나지 않고, 확인하면 정확한 값으로 PUT이 나가는지는 어느 테스트도 거치지 않았다.
 * 점검 공지의 '미리 검증' 실패 표시도 마찬가지로 비어 있었다.
 *
 * qa-contract-change: 공지 입력 · 미리 검증 · 공지 저장이 판 위에서 「수정」이 여는 창 안으로 옮겼다(D-501) — 미리 검증 실패 시험은 창을 연 뒤
 * 같은 단언(오류가 입력 옆 alert 로 남는다)을 창 안에서 재고, 실패하면 창이 닫히지 않는다는 단언을 더한다. 옛 주석의 「토스트도 함께 뜬다」는
 * 사실이 아니었다(그 findByText 는 같은 alert 상자를 찾았다) — 단언은 그대로 두고 주석만 걷는다. 같은 저장이 한 번만 나가는지 재는
 * 시험을 더한다(`useGuardedMutation`).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "admin", id: "u-1" } }),
}));

import { Maintenance } from "./Ops.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function renderMaintenance() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Maintenance />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

let mmValue;
function mockSettingsApi() {
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) {
      return Promise.resolve({
        settings: {
          maintenance_mode: { value: mmValue },
          maintenance_message: { value: "점검 중입니다." },
        },
      });
    }
    if (path === "/api/admin/settings/maintenance_mode" && opts && opts.method === "PUT") {
      mmValue = opts.body.value;
      return Promise.resolve({});
    }
    return Promise.reject(new Error("unexpected api call: " + path + " " + (opts && opts.method)));
  });
}

beforeEach(() => {
  apiMock.mockReset();
  mmValue = false;
  mockSettingsApi();
});

describe("유지보수 모드 전환 — 확인 대화상자", () => {
  it("활성화할까요? 확인 후 승인하면 PUT이 나가고, 배너·버튼 라벨이 활성으로 바뀐다", async () => {
    const user = userEvent.setup();
    renderMaintenance();

    const toggleBtn = await screen.findByRole("button", { name: "유지보수 모드 활성화" });
    await user.click(toggleBtn);

    const dialog = await screen.findByRole("dialog", { name: "확인" });
    expect(dialog).toHaveTextContent(/유지보수 모드를 활성화할까요\?/);
    await user.click(within(dialog).getByRole("button", { name: "유지보수 모드 활성화" }));

    expect(await screen.findByText("유지보수 모드를 전환했습니다.")).toBeInTheDocument();
    // 낙관적으로 먼저 바뀌지 않는다 — 서버 값(무효화 후 재조회)을 따라 배너/버튼이 뒤늦게 활성으로 바뀐다.
    expect(await screen.findByRole("button", { name: "유지보수 모드 비활성화" })).toBeInTheDocument();
    expect(screen.getByText(/현재 유지보수 모드가 활성화되어 있습니다/)).toBeInTheDocument();

    const putCall = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/settings/maintenance_mode" && o && o.method === "PUT");
    expect(putCall[1].body).toEqual({ value: true });
  });

  it("취소하면 PUT이 나가지 않고 상태가 그대로다", async () => {
    const user = userEvent.setup();
    renderMaintenance();

    const toggleBtn = await screen.findByRole("button", { name: "유지보수 모드 활성화" });
    await user.click(toggleBtn);

    const dialog = await screen.findByRole("dialog", { name: "확인" });
    await user.click(within(dialog).getByRole("button", { name: "취소" }));

    await waitFor(() => expect(screen.queryByRole("dialog", { name: "확인" })).toBeNull());
    expect(screen.getByRole("button", { name: "유지보수 모드 활성화" })).toBeInTheDocument();
    const putCall = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/settings/maintenance_mode" && o && o.method === "PUT");
    expect(putCall).toBeUndefined();
  });

  it("이미 활성화된 상태에서는 비활성화하는 문구로 확인한다", async () => {
    mmValue = true;
    const user = userEvent.setup();
    renderMaintenance();

    const toggleBtn = await screen.findByRole("button", { name: "유지보수 모드 비활성화" });
    await user.click(toggleBtn);

    const dialog = await screen.findByRole("dialog", { name: "확인" });
    expect(dialog).toHaveTextContent("유지보수 모드를 비활성화할까요?");
    await user.click(within(dialog).getByRole("button", { name: "유지보수 모드 비활성화" }));

    expect(await screen.findByRole("button", { name: "유지보수 모드 활성화" })).toBeInTheDocument();
    const putCall = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/settings/maintenance_mode" && o && o.method === "PUT");
    expect(putCall[1].body).toEqual({ value: false });
  });
});

describe("점검 공지 — 미리 검증 실패 표시", () => {
  it("검증이 실패하면 필드 옆에 오류가 남고, 토스트도 함께 뜬다", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) {
        return Promise.resolve({
          settings: {
            maintenance_mode: { value: false },
            maintenance_message: { value: "점검 중입니다." },
          },
        });
      }
      if (path === "/api/admin/settings/maintenance_message/dry-run" && opts && opts.method === "POST") {
        return Promise.reject(new Error("공지 문구가 너무 깁니다."));
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const user = userEvent.setup();
    renderMaintenance();

    // 공지 입력과 미리 검증은 「수정」이 여는 창 안이다(D-501).
    await user.click(await screen.findByRole("button", { name: "점검 공지 수정" }));
    const dialog = await screen.findByRole("dialog", { name: "점검 공지 수정" });
    await user.click(within(dialog).getByRole("button", { name: "미리 검증" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("공지 문구가 너무 깁니다.");
    expect(await screen.findByText("공지 문구가 너무 깁니다.")).toBeInTheDocument();
    // 실패했으니 창은 닫히지 않는다 — 고칠 사람이 그 자리에서 문구를 고친다.
    expect(screen.getByRole("dialog", { name: "점검 공지 수정" })).toBeInTheDocument();
  });
});

describe("점검 공지 — 같은 저장은 한 번만 나간다 (useGuardedMutation)", () => {
  it("「공지 저장」을 연달아 눌러도 PUT 은 하나이고, 저장되면 창이 닫힌다", async () => {
    let puts = 0;
    let release;
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) {
        return Promise.resolve({
          settings: { maintenance_mode: { value: false }, maintenance_message: { value: "점검 중입니다." } },
        });
      }
      if (path === "/api/admin/settings/maintenance_message" && opts && opts.method === "PUT") {
        puts += 1;
        return new Promise((resolve) => { release = () => resolve({}); });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const user = userEvent.setup();
    renderMaintenance();

    await user.click(await screen.findByRole("button", { name: "점검 공지 수정" }));
    const dialog = await screen.findByRole("dialog", { name: "점검 공지 수정" });
    const box = within(dialog).getByLabelText("점검 공지");
    await user.clear(box);
    await user.type(box, "새 공지입니다.");
    await user.dblClick(within(dialog).getByRole("button", { name: "공지 저장" }));
    expect(puts).toBe(1);
    release();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "점검 공지 수정" })).toBeNull());
    expect(puts).toBe(1);
  });
});
