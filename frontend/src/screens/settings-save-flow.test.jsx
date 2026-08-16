import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 설정 화면의 실제 저장 흐름 + 저장 전 확인 단계.
 *
 * settings-coerce.test.jsx는 '미리 검증'(dry-run) 경로의 유효성 검사만 다룬다 — 실제 저장(PUT),
 * 저장 실패, 보안 완화 확인, 버전 롤백, 미저장 변경 보호는 어느 테스트도 거치지 않은 채였다.
 * 이 파일은 그 네 가지를 컴포넌트 렌더로 확인한다(coerce()가 export되지 않아 SettingEditor를
 * 통해서만 검증할 수 있다는 점은 settings-coerce.test.jsx와 동일).
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin" } }),
}));

import { Settings } from "./Settings.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const PAYLOAD = {
  settings: {
    conversation_retention_days: { value: 90, type: "int", description: "대화 보존", restart_required: false, is_default: true },
    allowed_email_domains: { value: ["example.com"], type: "object", description: "허용 도메인", restart_required: false, is_default: false },
  },
};

beforeEach(() => {
  apiMock.mockReset();
});

function renderSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <Settings />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

async function openEditor(user, rowLabel) {
  const row = await screen.findByRole("row", { name: "상세 보기: " + rowLabel });
  await user.click(row);
}

function isGet(opts) { return !opts || !opts.method || opts.method === "GET"; }

describe("설정 저장 흐름", () => {
  it("값을 바꾸고 저장하면 PUT이 나가고, 성공 토스트 후 편집기가 닫힌다", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/settings" && isGet(opts)) return Promise.resolve(PAYLOAD);
      if (path === "/api/admin/settings/conversation_retention_days" && opts && opts.method === "PUT") {
        return Promise.resolve({ restart_required: false });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "대화 보존 기간(일)");
    const input = await screen.findByLabelText("값");
    await user.clear(input);
    await user.type(input, "30");
    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText("설정을 저장했습니다.")).toBeInTheDocument();
    // 편집기가 닫혔다 — 값 입력 필드가 더 이상 없다.
    await waitFor(() => expect(screen.queryByLabelText("값")).toBeNull());

    const putCall = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/settings/conversation_retention_days" && o && o.method === "PUT");
    expect(putCall).toBeTruthy();
    expect(putCall[1].body).toEqual({ value: 30 });
  });

  it("저장이 실패하면 오류가 편집기 안에 남고, 편집기는 닫히지 않는다", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/settings" && isGet(opts)) return Promise.resolve(PAYLOAD);
      if (path === "/api/admin/settings/conversation_retention_days" && opts && opts.method === "PUT") {
        return Promise.reject(new Error("서버에 저장하지 못했습니다."));
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "대화 보존 기간(일)");
    const input = await screen.findByLabelText("값");
    await user.clear(input);
    await user.type(input, "30");
    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(await screen.findByText("서버에 저장하지 못했습니다.")).toBeInTheDocument();
    // 실패했으니 편집기는 그대로 열려 있어야 한다(입력값도 남아 있다).
    expect(screen.getByLabelText("값")).toHaveValue(30);
  });
});

describe("보안 완화 확인 — 허용 이메일 도메인 비우기", () => {
  function mockDomainsApi() {
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/settings" && isGet(opts)) return Promise.resolve(PAYLOAD);
      if (path === "/api/admin/settings/allowed_email_domains" && opts && opts.method === "PUT") {
        return Promise.resolve({ restart_required: false });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
  }

  it("취소하면 저장 요청이 나가지 않는다", async () => {
    mockDomainsApi();
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "계정 추가 허용 도메인");
    await user.click(await screen.findByRole("button", { name: "example.com 제거" }));
    await user.click(screen.getByRole("button", { name: "저장" }));

    const dialog = await screen.findByRole("dialog", { name: "보안 설정 변경 확인" });
    expect(dialog).toHaveTextContent(/허용 이메일 도메인을 비우면/);
    await user.click(within(dialog).getByRole("button", { name: "취소" }));

    await waitFor(() => expect(screen.queryByRole("dialog", { name: "보안 설정 변경 확인" })).toBeNull());
    const putCall = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/settings/allowed_email_domains" && o && o.method === "PUT");
    expect(putCall).toBeUndefined();
    // 편집기는 그대로 열려 있다(닫히지 않았다).
    expect(screen.getByRole("button", { name: "저장" })).toBeInTheDocument();
  });

  it("확인하면 빈 목록으로 저장된다", async () => {
    mockDomainsApi();
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "계정 추가 허용 도메인");
    await user.click(await screen.findByRole("button", { name: "example.com 제거" }));
    await user.click(screen.getByRole("button", { name: "저장" }));

    const dialog = await screen.findByRole("dialog", { name: "보안 설정 변경 확인" });
    await user.click(within(dialog).getByRole("button", { name: "변경" }));

    expect(await screen.findByText("설정을 저장했습니다.")).toBeInTheDocument();
    const putCall = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/settings/allowed_email_domains" && o && o.method === "PUT");
    expect(putCall[1].body).toEqual({ value: [] });
  });
});

describe("유효성 검사 — 도메인 추가 입력", () => {
  it("점이 없는 값은 형식 오류로 즉시 거부하고, 칩을 추가하지 않는다", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/settings" && isGet(opts)) return Promise.resolve(PAYLOAD);
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "계정 추가 허용 도메인");
    const domainInput = await screen.findByLabelText("도메인 추가");
    await user.type(domainInput, "invalid");
    await user.click(screen.getByRole("button", { name: "추가" }));

    expect(await screen.findByText("도메인 형식이 아닙니다(예: example.com), 점(.)을 포함해야 합니다.")).toBeInTheDocument();
    // 잘못된 값은 칩으로 추가되지 않았다 — 기존 도메인만 그대로 있다.
    expect(screen.queryByRole("button", { name: "invalid 제거" })).toBeNull();
    expect(screen.getByRole("button", { name: "example.com 제거" })).toBeInTheDocument();
  });
});

describe("버전 기록 롤백", () => {
  it("확인 후 선택한 버전으로 롤백 요청을 보내고, 편집기까지 함께 닫는다", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/settings" && isGet(opts)) return Promise.resolve(PAYLOAD);
      if (path === "/api/admin/settings/conversation_retention_days/versions" && isGet(opts)) {
        return Promise.resolve({ items: [{ version: 1, snapshot: { value: 60 }, created_at: "2026-08-01T00:00:00" }] });
      }
      if (path === "/api/admin/settings/conversation_retention_days/rollback" && opts && opts.method === "POST") {
        return Promise.resolve({});
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "대화 보존 기간(일)");
    await user.click(screen.getByRole("button", { name: "버전 기록" }));

    const versionsDialog = await screen.findByRole("dialog", { name: "대화 보존 기간(일), 버전 기록" });
    expect(within(versionsDialog).getByText("60일")).toBeInTheDocument();
    await user.click(within(versionsDialog).getByRole("button", { name: "이 버전으로 롤백" }));

    const confirmDialog = await screen.findByRole("dialog", { name: "버전 롤백" });
    await user.click(within(confirmDialog).getByRole("button", { name: "롤백" }));

    expect(await screen.findByText("버전 1(으)로 롤백했습니다.")).toBeInTheDocument();
    const rollCall = apiMock.mock.calls.find(([p, o]) => p === "/api/admin/settings/conversation_retention_days/rollback" && o && o.method === "POST");
    expect(rollCall[1].body).toEqual({ version: 1 });
    // 롤백 후엔 편집기 자체(값이 바뀌지 않았던 = not dirty)도 함께 닫힌다.
    await waitFor(() => expect(screen.queryByLabelText("값")).toBeNull());
  });
});

describe("미저장 변경 보호", () => {
  it("바꾼 값을 그대로 두고 닫으려 하면 확인을 받고, 취소하면 편집기가 열려 있다", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/settings" && isGet(opts)) return Promise.resolve(PAYLOAD);
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const user = userEvent.setup();
    renderSettings();
    await openEditor(user, "대화 보존 기간(일)");
    const input = await screen.findByLabelText("값");
    await user.clear(input);
    await user.type(input, "5");
    await user.click(screen.getByRole("button", { name: "취소" }));

    const dialog = await screen.findByRole("dialog", { name: "확인" });
    expect(dialog).toHaveTextContent(/수정한 내용이 저장되지 않았습니다/);
    await user.click(within(dialog).getByRole("button", { name: "취소" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "확인" })).toBeNull());
    expect(screen.getByLabelText("값")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "취소" }));
    const dialog2 = await screen.findByRole("dialog", { name: "확인" });
    // dialog2 안에는 "닫기"라는 이름의 버튼이 둘이다 — 제목줄의 X(닫기) 아이콘 버튼과, 이 확인의
    // confirmLabel("닫기") 제출 버튼. 후자만 눌러야 하므로 하단 작업줄(footer)로 범위를 좁힌다.
    const footer2 = dialog2.querySelector(".MuiDialogActions-root");
    await user.click(within(footer2).getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(screen.queryByLabelText("값")).toBeNull());
  });
});
