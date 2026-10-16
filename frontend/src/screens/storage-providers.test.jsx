import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 파일 저장소 화면 (S20).
 *
 * 이 파일이 지키는 것 넷이고, 넷 다 **이 화면이 없던 동안 아무도 못 보던 사실**이다.
 *   ① 운영 저장소가 지금 쓸 수 있는지를 화면이 말한다 — 「설정돼 있다」가 아니라 「지금
 *      붙어 있다」다.
 *   ② 운영과 백업이 같은 장치면 그 경고가 뜬다. 장치가 죽는 순간 백업도 함께 죽는다.
 *   ③ 「지금 확인」은 마운트 유닛 이름까지 준다 — 안 붙어 있을 때 다음에 칠 명령이다.
 *   ④ 사용 안 함으로 바꾸는 것은 파괴적이라 파급을 말하고 확인을 받는다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { StorageProviders } from "./StorageProviders.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

const OPERATIONAL = {
  id: "sp-op", name: "운영 디스크", kind: "LOCAL", role: "OPERATIONAL", enabled: true,
  base_path: "/srv/clovirassist/files", mount_point: null, writable: true,
  mount: { status: "ok", path: "/srv/clovirassist/files", detail: "" },
  total_bytes: 100 * 1024 * 1024 * 1024, free_bytes: 60 * 1024 * 1024 * 1024,
  used_bytes: 40 * 1024 * 1024 * 1024,
};
const BACKUP_NAS = {
  id: "sp-bk", name: "백업 NAS", kind: "NFS", role: "BACKUP", enabled: true,
  base_path: "/mnt/backup/clovirassist", mount_point: "/mnt/backup", writable: false,
  mount: { status: "not_mounted", path: "/mnt/backup", detail: "마운트되지 않았습니다." },
  total_bytes: null, free_bytes: null, used_bytes: null,
};

function statusBody(over) {
  return {
    providers: [OPERATIONAL, BACKUP_NAS],
    operational_ok: true, warning: null, file_count: 236,
    ...over,
  };
}

function renderScreen() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <StorageProviders />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

const WAIT = { timeout: 8000 };

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (String(path).startsWith("/api/storage/status")) return Promise.resolve(statusBody());
    return Promise.resolve({});
  });
});

describe("파일 저장소 — 지금 쓸 수 있는가", () => {
  it("저장소마다 지금 붙어 있는지를 말한다 — 설정값이 아니라 상태다", async () => {
    renderScreen();
    const opRow = await screen.findByRole("row", { name: /운영 디스크/ }, WAIT);
    expect(within(opRow).getByText("쓸 수 있음")).toBeInTheDocument();

    const bkRow = screen.getByRole("row", { name: /백업 NAS/ });
    // 원문 슬러그(`not_mounted`)가 화면에 새면 관리자는 판정 다섯 가지를 추측해야 한다.
    expect(within(bkRow).getByText("마운트되지 않음")).toBeInTheDocument();
    expect(within(bkRow).queryByText("not_mounted")).not.toBeInTheDocument();
  });

  it("운영 저장소에 못 쓰면 '새 업로드가 실패한다'고 말한다", async () => {
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/storage/status")) {
        return Promise.resolve(statusBody({ operational_ok: false }));
      }
      return Promise.resolve({});
    });
    renderScreen();
    expect(await screen.findByText(/새 업로드가 실패합니다/, {}, WAIT)).toBeInTheDocument();
  });

  it("운영과 백업이 같은 장치면 그 경고를 그대로 보인다", async () => {
    const warning = "운영 저장소와 백업 저장소가 같은 장치에 있습니다. 장치가 고장 나면 백업도 함께 잃습니다.";
    apiMock.mockImplementation((path) => {
      if (String(path).startsWith("/api/storage/status")) {
        return Promise.resolve(statusBody({ warning }));
      }
      return Promise.resolve({});
    });
    renderScreen();
    expect(await screen.findByText(warning, {}, WAIT)).toBeInTheDocument();
  });

  it("경고가 없으면 그 문장 자체가 없다 — 반례", async () => {
    renderScreen();
    await screen.findByRole("row", { name: /운영 디스크/ }, WAIT);
    expect(screen.queryByText(/같은 장치에 있습니다/)).not.toBeInTheDocument();
  });
});

describe("파일 저장소 — 다음에 할 일을 준다", () => {
  it("'지금 확인'이 안 붙어 있다고 답하면 붙이는 명령을 함께 보인다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path, opts) => {
      if (String(path).startsWith("/api/storage/status")) return Promise.resolve(statusBody());
      if (String(path) === "/api/storage/providers/sp-bk/probe" && opts && opts.method === "POST") {
        return Promise.resolve({ ...BACKUP_NAS, mount_unit: "mnt-backup.mount" });
      }
      return Promise.resolve({});
    });
    renderScreen();
    const bkRow = await screen.findByRole("row", { name: /백업 NAS/ }, WAIT);
    await user.click(within(bkRow).getByRole("button", { name: "백업 NAS 작업" }));
    await user.click(await screen.findByRole("menuitem", { name: "상태 확인" }, WAIT));

    await waitFor(() => expect(
      apiMock.mock.calls.some(([p, o]) => p === "/api/storage/providers/sp-bk/probe" && o && o.method === "POST")
    ).toBe(true), WAIT);
    expect(await screen.findByText(/systemctl start mnt-backup\.mount/, {}, WAIT)).toBeInTheDocument();
    /* 결과의 한마디(쓸 수 있다 · 없다)를 화면이 말한다 — 지금은 확인 결과 상자의 제목이다(토스트로
       겹쳐 말하지 않는다, 핸드오프 RULES §1). 예전에 `toast.error(…)` 가 rejected promise 안에서
       TypeError 로 죽어 «아무 일도 안 일어남» 으로 보였던 자리라, 그 한마디가 실제로 서는지를 여기서 잡는다. */
    expect(await screen.findByText("지금은 쓸 수 없습니다.", {}, WAIT)).toBeInTheDocument();
  });

  it("쓸 수 있는 저장소를 확인하면 붙이는 명령을 말하지 않는다 — 반례", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path, opts) => {
      if (String(path).startsWith("/api/storage/status")) return Promise.resolve(statusBody());
      if (String(path) === "/api/storage/providers/sp-op/probe" && opts && opts.method === "POST") {
        return Promise.resolve({ ...OPERATIONAL, mount_unit: "srv-files.mount" });
      }
      return Promise.resolve({});
    });
    renderScreen();
    const opRow = await screen.findByRole("row", { name: /운영 디스크/ }, WAIT);
    await user.click(within(opRow).getByRole("button", { name: "운영 디스크 작업" }));
    await user.click(await screen.findByRole("menuitem", { name: "상태 확인" }, WAIT));

    await waitFor(() => expect(
      apiMock.mock.calls.some(([p]) => p === "/api/storage/providers/sp-op/probe")
    ).toBe(true), WAIT);
    expect(await screen.findByText("지금 쓸 수 있습니다.", {}, WAIT)).toBeInTheDocument();
    expect(screen.queryByText(/systemctl start/)).not.toBeInTheDocument();
  });
});

describe("파일 저장소 — 되돌리기 어려운 일에는 확인을 받는다", () => {
  it("운영 저장소를 끄기 전에 업로드가 실패하게 된다고 말한다", async () => {
    const user = userEvent.setup();
    renderScreen();
    const opRow = await screen.findByRole("row", { name: /운영 디스크/ }, WAIT);
    await user.click(within(opRow).getByRole("button", { name: "운영 디스크 작업" }));
    await user.click(await screen.findByRole("menuitem", { name: "비활성화" }, WAIT));

    expect(await screen.findByText(/새 파일 업로드가 실패합니다/, {}, WAIT)).toBeInTheDocument();
    // 확인을 받기 전에는 아무것도 안 바꾼다.
    expect(apiMock.mock.calls.some(([, o]) => o && o.method === "PATCH")).toBe(false);
  });
});
