import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 저장소 수정이 남의 저장을 말없이 덮지 않는다 (settings-07 · D-240).
 *
 * 서버에는 낙관적 잠금이 처음부터 있었다 — `PATCH` 가 `base_version` 을 받으면 낡은 판일 때
 * 409 「다른 사람이 먼저 저장했습니다」로 막는다. 그런데 **화면이 그 값을 한 번도 안 보냈다.**
 * 실측: 탭 A 에서 수정 폼을 연 채 탭 B(API)로 같은 저장소의 마운트 옵션을 바꾸고, 탭 A 에서
 * 저장하면 200 이 떨어지고 탭 B 의 값이 사라졌다. 토스트는 양쪽 다 「저장했습니다」였다 —
 * 덮어썼다는 사실을 아무도 모른다.
 *
 * 반례로 함께 못박는 것: 서버가 `version` 을 안 싣는 판에서는 그 값을 **지어내지 않는다**.
 * 없는 판 번호를 0 이나 1 로 채워 보내면 멀쩡한 저장이 409 로 막힌다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { StorageProviders } from "./StorageProviders.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function provider(over) {
  return {
    id: "sp-op", name: "운영 디스크", kind: "LOCAL", role: "OPERATIONAL", enabled: true,
    version: 3,
    base_path: "/srv/clovirassist/files", mount_point: null, source: null, options: "",
    writable: true, mount: { status: "ok", path: "/srv/clovirassist/files", detail: "" },
    total_bytes: null, free_bytes: null, used_bytes: null,
    ...over,
  };
}

let patches;

function mount({ row, patchStatus = 200 } = {}) {
  patches = [];
  apiMock.mockImplementation((path, opts) => {
    if (opts && opts.method === "PATCH") {
      patches.push({ path, body: opts.body });
      if (patchStatus === 409) {
        const err = new Error("다른 사람이 먼저 저장했습니다. 새로 고친 뒤 다시 시도해 주세요.");
        err.status = 409;
        return Promise.reject(err);
      }
      return Promise.resolve({ ok: true });
    }
    return Promise.resolve({
      providers: [row], operational_ok: true, warning: null, file_count: 1,
    });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><StorageProviders /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>
  );
}

async function openEditAndSave(user) {
  await screen.findByText("운영 디스크");
  await user.click(screen.getByRole("button", { name: "운영 디스크 작업" }));
  await user.click(await screen.findByRole("menuitem", { name: "수정" }));
  const dialog = await screen.findByRole("dialog");
  await user.click(within(dialog).getByRole("button", { name: "저장" }));
  return dialog;
}

beforeEach(() => { apiMock.mockReset(); });

describe("저장소 수정 — 편집을 시작한 판을 함께 보낸다", () => {
  it("PATCH 본문에 base_version 이 실린다", async () => {
    const user = userEvent.setup();
    mount({ row: provider({ version: 3 }) });
    await openEditAndSave(user);

    await waitFor(() => expect(patches.length).toBe(1));
    expect(patches[0].path).toBe("/api/storage/providers/sp-op");
    expect(patches[0].body.base_version).toBe(3);
  });

  it("반례 — 서버가 판 번호를 안 주면 지어내지 않는다(예전과 똑같이 저장된다)", async () => {
    const user = userEvent.setup();
    mount({ row: provider({ version: undefined }) });
    await openEditAndSave(user);

    await waitFor(() => expect(patches.length).toBe(1));
    expect("base_version" in patches[0].body).toBe(false);
  });

  it("409 면 서버가 준 이유를 폼 위에 그대로 보여 준다 — 적던 값을 잃지 않는다", async () => {
    const user = userEvent.setup();
    mount({ row: provider({ version: 3 }), patchStatus: 409 });
    const dialog = await openEditAndSave(user);

    expect(await within(dialog).findByText(/다른 사람이 먼저 저장했습니다/)).toBeInTheDocument();
    // 폼이 닫히지 않았다 = 방금 적은 값이 남아 있다.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
