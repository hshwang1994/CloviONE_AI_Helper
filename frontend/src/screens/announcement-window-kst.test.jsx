import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 공지 노출 기간이 9시간 밀리던 결함 (F14).
 *
 * `<input type="datetime-local">` 은 **시간대가 없는 벽시계 문자열**("2026-08-10T09:00")을 준다.
 * 이 앱에서 사람이 읽고 쓰는 시각은 언제나 KST 다(§불변 9). 그런데 폼은 그 문자열을 그대로
 * 보냈고, 서버는 저장소 규약대로 naive 를 UTC 로 보고 저장했다 — 관리자가 '09:00 부터'로
 * 지정한 공지가 실제로는 **KST 18:00** 에 떴다.
 *
 * 규약(naive UTC 저장)은 그대로 두고 **경계에서 변환**한다. 필터 경로는 이미 그렇게 하고
 * 있었다(DataScreen.buildUrl 이 +09:00 을 붙인다) — 폼 경로만 빠져 있었다.
 *
 * 여기서는 9시간이 실제로 어긋나는 표본을 쓴다: KST 09:00 은 UTC 00:00 이다. 변환이 빠지면
 * 보내는 값이 가리키는 순간이 UTC 09:00 이 되어 정확히 9시간 어긋난다.
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

// KST 09:00 == UTC 00:00. 두 값이 9시간 다르므로 변환이 빠지면 이 단언이 반드시 깨진다.
const KST_WALL = "2026-08-10T09:00";
// 서버가 돌려주는 모양(naive UTC iso). 화면은 이것을 KST 벽시계로 되돌려 입력칸에 넣어야 한다.
const ROW_NAIVE_UTC = "2026-08-10T00:00:00";

/* 보낸 값을 **서버와 같은 규칙**으로 읽는다 (app/announcements/router.py::_naive).
 * 오프셋이 붙어 있으면 UTC 로 옮겨 naive 로 저장하고, 없으면 그 벽시계를 그대로 UTC 로 본다.
 *
 * `new Date(...).toISOString()` 만으로 판정하면 안 된다 — 러너의 로컬 시간대가 마침 KST 면
 * 오프셋 없는 문자열도 '맞는' 순간으로 파싱되어 **결함이 있는 채로 테스트가 통과한다**
 * (실제로 그렇게 한 번 초록이 나왔다). 브라우저가 어느 시간대에 있든 서버는 naive 를 UTC 로
 * 읽으므로, 판정도 서버 규칙으로 해야 한다. */
function storedAsNaiveUtc(value) {
  const s = String(value);
  if (!/[zZ]$|[+-]\d\d:?\d\d$/.test(s)) return s.length === 16 ? s + ":00" : s;
  return new Date(s).toISOString().slice(0, 19);
}

function renderScreen(items) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiMock.mockImplementation((path, options) => {
    if (path.startsWith("/api/me/views")) return Promise.resolve({ items: [] });
    if (options && options.method) return Promise.resolve({ ok: true, id: "a-1" });
    return Promise.resolve({ items: items || [], total: (items || []).length, page: 1, page_size: 20 });
  });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={REGISTRY.announcements} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

function sentBody(path) {
  const call = apiMock.mock.calls.find((c) => c[0] === path && c[1] && c[1].method);
  return call ? call[1].body : null;
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("공지 노출 기간은 KST 로 읽고 쓴다", () => {
  it("폼에 적은 KST 시각이 그 순간 그대로 서버에 간다(9시간 밀리지 않는다)", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByText("공지 배너");

    await user.click(screen.getByRole("button", { name: "+ 공지 추가" }));
    await user.type(await screen.findByLabelText(/제목/), "점검 예고");
    await user.type(screen.getByLabelText(/노출 시작/), KST_WALL);
    await user.click(screen.getByRole("button", { name: "만들기" }));

    await waitFor(() => expect(sentBody("/api/admin/announcements")).toBeTruthy());
    const body = sentBody("/api/admin/announcements");
    // 서버가 저장하게 될 naive UTC 값이 KST 09:00 과 같은 순간이어야 한다(= UTC 00:00).
    expect(storedAsNaiveUtc(body.starts_at)).toBe(ROW_NAIVE_UTC);
  });

  it("수정 폼을 열면 저장된 값이 KST 벽시계로 보인다(목록의 시각과 같은 값)", async () => {
    const user = userEvent.setup();
    renderScreen([{
      id: "a-1", title: "점검 예고", body: "", level: "info", audience: "all",
      starts_at: ROW_NAIVE_UTC, ends_at: null, active: true, dismissible: true,
      link_url: null, link_label: null, created_at: ROW_NAIVE_UTC, updated_at: ROW_NAIVE_UTC,
    }]);
    await screen.findByText("점검 예고");

    await user.click(screen.getByText("점검 예고"));
    await user.click(await screen.findByRole("button", { name: "수정" }));

    const input = await screen.findByLabelText(/노출 시작/);
    expect(input).toHaveValue(KST_WALL);
  });
});
