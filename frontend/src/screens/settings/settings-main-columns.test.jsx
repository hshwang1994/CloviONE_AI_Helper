import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider } from "../../ui/kit.jsx";

/* PA-RC-0037: /settings의 '항목명'(행을 식별하는 유일한 열)이 1920에서는 140px·잘림
 * 0/11이지만 1366에서 91px로 줄어 11행 중 8행이 잘렸다(예: "계정 추가 허용 도메인",
 * 141px 필요) — 같은 표의 '설명'은 566px를 그대로 유지했다. identifier:true +
 * minWidth:"10rem"으로 바닥 폭만 준다(다른 열은 예전처럼 auto 레이아웃에 맡긴다 — 앞
 * 네 열 전부에 고정 width를 주면 '설명'이 짜부라지던 DS-06 함정을 다시 밟지 않는다).
 * jsdom은 실제 픽셀 폭을 계산하지 않으므로 열 정의가 되돌아가지 않게 고정만 한다 —
 * TEST SERVER pa2_verify_no.py 재실행으로 실측 확인은 별도.
 */

const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { Settings } from "./SettingsMain.jsx";

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path === "/api/admin/settings") {
      return Promise.resolve({
        settings: {
          allowed_email_domains: {
            value: ["goodmit.co.kr"], type: "list",
            description: "계정 추가 허용 도메인. 비우면 모든 도메인을 허용합니다.",
            restart_required: false, is_default: true,
          },
        },
      });
    }
    return Promise.resolve({});
  });
});

function renderSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <Settings />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("설정 표 — '항목명' 열의 최소 폭 (PA-RC-0037)", () => {
  it("항목명 열 머리글이 기본 바닥 폭(4.5rem)이 아니라 명시적 최소 폭(10rem)을 받는다", async () => {
    renderSettings();
    const header = await screen.findByRole("columnheader", { name: "항목명" });
    expect(header).toHaveStyle({ minWidth: "10rem" });
  });

  it("'설명' 열은 이전처럼 폭이 지정되지 않는다 — auto 레이아웃이 남는 공간을 그대로 가져간다(DS-06 회귀 방지)", async () => {
    renderSettings();
    const header = await screen.findByRole("columnheader", { name: "설명" });
    expect(header).toHaveStyle({ width: "" });
    expect(header).toHaveStyle({ minWidth: "4.5rem" });
  });
});
