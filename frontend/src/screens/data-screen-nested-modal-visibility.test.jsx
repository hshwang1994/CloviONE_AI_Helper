import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* VIS-162 — 상세(size="lg", 992px)에서 "수정"을 누르면 그 수정 폼(필드가 많으면 역시
 * size="lg")이 상세 위에 겹쳐 열렸는데, sel(상세 상태)을 안 지워 상세 Dialog가 DOM에
 * 그대로 남아 있었다 — 두 Dialog가 같은 폭이라 하나가 다른 하나를 픽셀 하나 없이 완전히
 * 덮어, 방금 보던 상세 값들이 아무 흔적 없이 사라졌다. runAction의 navigate 분기는 이미
 * setSel(null)로 이 문제를 피하고 있었다 — 나머지 분기(수정 폼)에는 안 걸려 있었다.
 *
 * 고친 지점은 DataScreen.jsx 하나뿐이라(공용 컴포넌트) departments 화면으로 대표 검증한다
 * (data-screen-edit-diff.test.jsx와 같은 픽스처).
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

const WAIT = { timeout: 8000 };
vi.setConfig({ testTimeout: 20000 });

const DEPT = {
  id: "dep-1", name: "영업팀", org_name: "클로비원", org_id: "org-1",
  active: true, user_count: 0, created_at: "2026-08-01T00:00:00Z", parent_id: null,
};

beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
  apiMock.mockImplementation((path, opts) => {
    const method = (opts && opts.method) || "GET";
    if (String(path).startsWith("/api/admin/departments") && method === "GET") {
      return Promise.resolve({ items: [DEPT], total: 1 });
    }
    if (method === "PATCH") return Promise.resolve({ department: { ...DEPT, name: "영업2팀" } });
    return Promise.resolve({});
  });
});
afterEach(() => { window.location.hash = ""; });

async function openDetail(user) {
  const cell = await screen.findByText("영업팀", {}, WAIT);
  await user.click(cell.closest("tr"));
  return screen.findByRole("dialog", {}, WAIT);
}

describe("DataScreen 상세 → 수정 중첩 (VIS-162)", () => {
  it("수정 폼을 열면 상세 Dialog가 DOM에서 완전히 사라진다(감춰진 채 겹쳐 있지 않는다)", async () => {
    const user = userEvent.setup();
    renderScreen("departments");
    const detail = await openDetail(user);
    await user.click(within(detail).getByRole("button", { name: "수정" }));
    await waitFor(() => screen.getByRole("textbox", { name: /부서 이름/ }), WAIT);

    // MUI는 모달이 겹치면 아래 모달을 **aria-hidden으로만 감추고 DOM/픽셀은 그대로 둔다** —
    // role 기반 조회(getAllByRole("dialog"))는 접근성 트리를 따라가므로 그 상태를 "1개"로
    // 잘못 읽는다(처음 이 테스트를 짤 때 실제로 이 함정에 빠져 고쳐지지 않은 소스로도
    // 통과했다). 진짜 사라졌는지는 aria-hidden 여부와 무관하게 DOM을 직접 봐야 드러난다.
    expect(document.querySelectorAll('.MuiDialog-root[aria-hidden="true"]')).toHaveLength(0);
    // 상세에서만 보이는 값(목록 표에도 같은 텍스트가 있어 다이얼로그 안으로 좁혀서 본다)이
    // 어떤 다이얼로그 안에도 남아 있지 않아야 한다.
    const orgNameInsideAnyDialog = screen.queryAllByText("클로비원")
      .some((el) => el.closest(".MuiDialog-root"));
    expect(orgNameInsideAnyDialog).toBe(false);
  });

  it("수정을 취소하면 상세로 돌아온다(같은 행의 상세가 다시 보인다)", async () => {
    const user = userEvent.setup();
    renderScreen("departments");
    const detail = await openDetail(user);
    await user.click(within(detail).getByRole("button", { name: "수정" }));
    const editDialog = await screen.findByRole("dialog", {}, WAIT);
    await user.click(within(editDialog).getByRole("button", { name: "취소" }));

    await waitFor(() => {
      const dialogs = screen.getAllByRole("dialog");
      expect(dialogs).toHaveLength(1);
      // 상세로 돌아왔다는 증거 — 수정 폼의 "저장" 대신 상세의 "수정" 버튼이 다시 보인다.
      expect(within(dialogs[0]).getByRole("button", { name: "수정" })).toBeInTheDocument();
    }, WAIT);
  });
});
