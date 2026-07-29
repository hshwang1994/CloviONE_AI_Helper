import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* coerce()는 SettingEditor 안의 클로저(setting/val/INT_BOUNDS에 의존)라 export 할 수 없다 —
 * 동작을 바꾸지 않고 테스트하기 위해 Settings 화면을 렌더해 편집기를 열고, '미리 검증'을 눌러
 * coerce가 던지는 검증 오류 경로(int 빈값/범위초과, object JSON 오류)와 통과 경로(bool)를 확인한다.
 * 네트워크·타이머 없음: api는 mock, dry-run은 즉시 resolve. */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin" } }),
}));

import { Settings } from "./Settings.jsx";

const PAYLOAD = {
  settings: {
    conversation_retention_days: { value: 90, type: "int", description: "대화 보존", restart_required: false, is_default: true },
    document_automation_enabled: { value: true, type: "bool", description: "문서 자동화 켜기", restart_required: false, is_default: true },
    extra_object: { value: { a: 1 }, type: "object", description: "임의 객체 설정", restart_required: false, is_default: true },
  },
};

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/admin/settings" && (!opts || !opts.method || opts.method === "GET")) {
      return Promise.resolve(PAYLOAD);
    }
    return Promise.resolve({}); // dry-run / save 등은 통과로 처리
  });
});

function renderSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openEditor(user, rowLabel) {
  // 행 라벨과 '키' 열이 같은 텍스트일 수 있어(extra_object) 유일한 '상세 보기' 버튼으로 연다.
  const btn = await screen.findByRole("button", { name: "상세 보기: " + rowLabel });
  await user.click(btn);
}

describe("coerce (via SettingEditor render)", () => {
  it("int: rejects an empty value", async () => {
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "대화 보존 기간(일)");
    const input = await screen.findByLabelText("값");
    await user.clear(input);
    await user.click(screen.getByRole("button", { name: "미리 검증" }));
    expect(await screen.findByText("정수를 입력하세요.")).toBeInTheDocument();
  });

  it("int: rejects a value outside INT_BOUNDS", async () => {
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "대화 보존 기간(일)");
    const input = await screen.findByLabelText("값");
    await user.clear(input);
    await user.type(input, "9999");
    await user.click(screen.getByRole("button", { name: "미리 검증" }));
    expect(await screen.findByText("허용 범위(1~3650)를 벗어났습니다.")).toBeInTheDocument();
  });

  it("object: rejects malformed JSON", async () => {
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "extra_object");
    const textarea = await screen.findByLabelText("값(JSON)");
    fireEvent.change(textarea, { target: { value: "{ not valid json" } });
    await user.click(screen.getByRole("button", { name: "미리 검증" }));
    expect(await screen.findByText("JSON 형식이 올바르지 않습니다.")).toBeInTheDocument();
  });

  it("bool: coerces without error and passes validation", async () => {
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "문서 자동화");
    const select = await screen.findByLabelText("값");
    await user.selectOptions(select, "false");
    await user.click(screen.getByRole("button", { name: "미리 검증" }));
    expect(await screen.findByText(/검증 통과/)).toBeInTheDocument();
  });
});
