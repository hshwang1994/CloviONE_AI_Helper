import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 409 뒤의 「저장」이 **실제로 통한다** (R8-07).
 *
 * 낙관적 잠금이 붙으면서 409 를 받은 폼은 열린 채로 남는다 — 사람이 방금 적은 값을 잃지
 * 않으려는 판단이고 그건 옳다. 그런데 `editing` 은 「수정」을 누른 순간의 스냅샷이라
 * `version` 이 낡은 채로 얼어 있었다. 그래서 서버 문구(「새로 고친 뒤 다시 시도해 주세요」)를
 * 읽고 「저장」을 다시 누르면 **같은 낡은 판을 다시 보내** 또 409 였다. 몇 번을 눌러도 같고,
 * 빠져나가는 길은 창을 닫고 처음부터 다시 적는 것뿐이었다 — 잃지 않으려던 값을 결국 잃는다.
 *
 * 이제 화면이 그 「새로 고침」을 대신한다: 409 를 받으면 목록을 다시 받고, 다음 저장은 방금
 * 받은 판을 싣는다.
 *
 * 반례 둘: (1) 충돌이 없었으면 **편집을 시작한 판**을 그대로 보낸다 — 매번 최신 판을 실으면
 * 잠금이 아무것도 막지 못한다. (2) 창을 닫았다 다시 열면 그때의 판으로 새로 시작한다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { StorageProviders } from "./StorageProviders.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function provider(version) {
  return {
    id: "sp-op", name: "운영 디스크", kind: "LOCAL", role: "OPERATIONAL", enabled: true,
    version,
    base_path: "/srv/clovirassist/files", mount_point: null, source: null, options: "",
    writable: true, mount: { status: "ok", path: "/srv/clovirassist/files", detail: "" },
    total_bytes: null, free_bytes: null, used_bytes: null,
  };
}

let patches;

/** 서버 대역 — `conflictsFirst` 번 만큼 409 로 답하고, 그때마다 **남이 저장한 것처럼**
 *  판 번호를 하나 올린다(다음 GET 이 새 판을 준다). */
function mount({ conflictsFirst = 0, startVersion = 3 } = {}) {
  patches = [];
  let version = startVersion;
  let refused = 0;
  apiMock.mockImplementation((path, opts) => {
    if (opts && opts.method === "PATCH") {
      patches.push({ path, body: opts.body });
      if (refused < conflictsFirst) {
        refused += 1;
        version += 1;              // 남이 먼저 저장했다 — 지금 판은 이것이다.
        const err = new Error("다른 사람이 먼저 저장했습니다. 새로 고친 뒤 다시 시도해 주세요.");
        err.status = 409;
        return Promise.reject(err);
      }
      return Promise.resolve({ ok: true });
    }
    return Promise.resolve({
      providers: [provider(version)], operational_ok: true, warning: null, file_count: 1,
    });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <MemoryRouter><StorageProviders /></MemoryRouter>
      </ConfirmProvider></ToastProvider></ThemeModeProvider>
    </QueryClientProvider>,
  );
}

async function openEdit(user) {
  await screen.findByText("운영 디스크");
  await user.click(screen.getByRole("button", { name: "운영 디스크 작업" }));
  await user.click(await screen.findByRole("menuitem", { name: "수정" }));
  return screen.findByRole("dialog");
}
const save = (user, dialog) => user.click(within(dialog).getByRole("button", { name: "저장" }));

beforeEach(() => { apiMock.mockReset(); });

describe("저장소 수정 — 409 를 한 번 본 폼은 다음 저장에서 지금 판을 싣는다", () => {
  it("두 번째 「저장」이 새 판 번호로 나가고 통과한다", async () => {
    const user = userEvent.setup();
    mount({ conflictsFirst: 1, startVersion: 3 });
    const dialog = await openEdit(user);

    await save(user, dialog);
    await waitFor(() => expect(patches.length).toBe(1));
    expect(patches[0].body.base_version).toBe(3);
    // 서버가 준 이유가 폼 위에 남는다(적던 값을 잃지 않는다).
    expect(await within(dialog).findByText(/다른 사람이 먼저 저장했습니다/)).toBeInTheDocument();
    // 목록을 다시 받아 지금 판이 4 가 될 때까지 기다린다.
    await waitFor(() => expect(apiMock.mock.calls.filter((c) => !c[1] || !c[1].method).length).toBeGreaterThan(1));

    await save(user, dialog);
    await waitFor(() => expect(patches.length).toBe(2));
    expect(patches[1].body.base_version).toBe(4);
    // 통했으므로 폼이 닫힌다 — 예전에는 같은 3 을 다시 보내 영원히 409 였다.
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("반례 — 충돌이 없었으면 편집을 시작한 판을 그대로 보낸다(잠금이 살아 있다)", async () => {
    const user = userEvent.setup();
    mount({ conflictsFirst: 0, startVersion: 3 });
    const dialog = await openEdit(user);

    await save(user, dialog);
    await waitFor(() => expect(patches.length).toBe(1));
    expect(patches[0].body.base_version).toBe(3);
  });

  it("반례 — 창을 닫았다 다시 열면 그 시점의 판으로 새로 시작한다", async () => {
    const user = userEvent.setup();
    mount({ conflictsFirst: 1, startVersion: 3 });
    let dialog = await openEdit(user);

    await save(user, dialog);
    await waitFor(() => expect(patches.length).toBe(1));
    await within(dialog).findByText(/다른 사람이 먼저 저장했습니다/);
    await user.click(within(dialog).getByRole("button", { name: "취소" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    dialog = await openEdit(user);
    await save(user, dialog);
    await waitFor(() => expect(patches.length).toBe(2));
    expect(patches[1].body.base_version).toBe(4);
  });
});
