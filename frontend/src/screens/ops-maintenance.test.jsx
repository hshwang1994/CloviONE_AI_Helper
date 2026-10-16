import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* 유지보수 화면의 '권한 없음' 표면 계약 + 진단 스파크라인의 데이터 가드.
 *
 * 1) 쓰기 컨트롤은 **숨기지 않는다**. /maintenance는 operator·auditor(읽기 전용)도 들어오는데,
 *    예전 코드는 '미리 검증' 버튼만 `canWrite ? <Button/> : null`로 아예 렌더하지 않았다.
 *    그 역할에게는 그런 기능이 존재하지 않는 것처럼 보였고(다른 버튼들은 비활성으로 남아 있어
 *    화면 안에서 규칙까지 어긋났다), 권한을 받아도 그런 수단이 있는지 알 방법이 없었다.
 *    보이되 비활성이고, 왜 비활성인지 글자로 옆에 남긴다 — 이 테스트가 그 세 가지를 못 박는다.
 *
 * 2) errorBuckets()는 '없는 추세'를 그리지 않기 위한 가드다. 서버가 주는 건 최근 실패 20건뿐이라
 *    점이 부족하거나 전부 같은 순간이면 스파크라인을 아예 만들지 않는다(숫자만 남긴다).
 *
 * qa-contract-change: 유지보수가 판 둘(모드 판 · 늘 열린 공지 입력 판)에서 판 하나의 설정 줄 둘로 바뀌었다(D-501). 공지는 지금 문구가
 * 줄의 값으로 서고, 고치는 입력 · 미리 검증 · 공지 저장은 「수정」이 여는 창 안이다. 그래서 읽기 전용 역할의 단언이 옮긴다 — 창을 여는
 * 「수정」이 보이되 비활성이고, 이유 문장은 판 하나에 한 줄이며 두 쓰기 단추가 그 줄을 가리킨다(두 판에 한 줄씩이던 것). 공지를
 * 선택 · 복사할 수 있어야 한다는 단언은 입력의 readOnly 대신 「공지 문구가 입력 칸이 아니라 글자로 서 있다」로 잰다.
 * 초안 seeding 단언은 그 창 안의 입력을 잰다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
// 역할은 테스트마다 바꾼다 — 팩토리는 호출 시점에 읽으므로 호이스팅 문제가 없다.
let mockRole = "operator";
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: mockRole, id: "u-1" } }),
}));

import { Diagnostics, Maintenance, errorBuckets } from "./Ops.jsx";
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
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockImplementation((path) => {
    if (path === "/api/admin/settings") {
      return Promise.resolve({
        settings: {
          maintenance_mode: { value: false },
          maintenance_message: { value: "점검 중입니다." },
        },
      });
    }
    return Promise.reject(new Error("unexpected api call: " + path));
  });
});

describe("유지보수 — 쓰기 권한이 없는 역할", () => {
  it("쓰기 버튼을 숨기지 않고, 비활성 + 보이는 이유로 남긴다", async () => {
    mockRole = "operator";
    renderMaintenance();

    const toggleBtn = await screen.findByRole("button", { name: "유지보수 모드 활성화" });
    expect(toggleBtn).toBeInTheDocument();
    expect(toggleBtn).toBeDisabled();

    // 공지를 고치는 창을 여는 단추도 존재 + 비활성이다 — 예전에 「미리 검증」이 아예 안 그려졌던 것과 같은 실수를 막는다.
    const editBtn = screen.getByRole("button", { name: "점검 공지 수정" });
    expect(editBtn).toBeInTheDocument();
    expect(editBtn).toBeDisabled();
    // 창이 열리지 않으므로 창 안의 쓰기 단추도 없다.
    expect(screen.queryByRole("dialog")).toBeNull();

    // 비활성 이유는 눈에 보이는 글자로 남아야 한다 — 판이 하나라 이유 문장도 하나다.
    expect(screen.getAllByText(/관리자, 시스템 관리자만 바꿀 수 있습니다/)).toHaveLength(1);
    // 그 이유가 스크린리더에도 닿도록 두 쓰기 단추가 같은 이유 문장을 가리킨다.
    expect(toggleBtn).toHaveAttribute("aria-describedby", "maint-locked-reason");
    expect(editBtn).toHaveAttribute("aria-describedby", "maint-locked-reason");
    expect(document.getElementById("maint-locked-reason")).toHaveTextContent(/유지보수 모드와 점검 공지는/);

    // 공지는 입력 칸이 아니라 글자로 선다 — 읽기 전용 역할도 내용을 선택 · 복사할 수 있다.
    const notice = screen.getByText("점검 중입니다.");
    expect(notice.closest("textarea, input")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("쓰기 권한이 있으면 같은 버튼이 활성화되고 이유 문구가 사라진다", async () => {
    mockRole = "admin";
    const user = userEvent.setup();
    renderMaintenance();

    const toggleBtn = await screen.findByRole("button", { name: "유지보수 모드 활성화" });
    expect(toggleBtn).toBeEnabled();
    expect(screen.queryByText(/관리자, 시스템 관리자만 바꿀 수 있습니다/)).toBeNull();
    // 「수정」이 창을 열고, 창 안에서 미리 검증 · 입력이 살아 있다.
    await user.click(screen.getByRole("button", { name: "점검 공지 수정" }));
    const dialog = await screen.findByRole("dialog", { name: "점검 공지 수정" });
    expect(within(dialog).getByRole("button", { name: "미리 검증" })).toBeEnabled();
    expect(within(dialog).getByLabelText("점검 공지")).not.toHaveAttribute("readonly");
    // 고친 것이 없으면 저장은 닫혀 있다(같은 값을 다시 저장하면 버전 기록에 빈 줄이 쌓인다).
    expect(within(dialog).getByRole("button", { name: "공지 저장" })).toBeDisabled();
  });
});

describe("유지보수 — 판 하나에 설정 줄 둘 (D-501)", () => {
  it("모드와 공지가 한 판의 두 줄이고, 공지 입력창은 「수정」을 누르기 전에는 없다", async () => {
    mockRole = "admin";
    renderMaintenance();

    await screen.findByText("유지보수 모드");
    const rows = document.querySelectorAll(".k-settingrow");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("유지보수 모드")).toBeInTheDocument();
    expect(within(rows[0]).getByText("정상")).toBeInTheDocument();
    expect(within(rows[0]).getByRole("button", { name: "변경 기록" })).toBeInTheDocument();
    expect(within(rows[1]).getByText("점검 공지")).toBeInTheDocument();
    expect(within(rows[1]).getByText("점검 중입니다.")).toBeInTheDocument();
    expect(within(rows[1]).getByRole("button", { name: "버전 기록" })).toBeInTheDocument();
    // 두 줄이 같은 판 안이다 — 예전의 판 둘(1.2 : 0.8 짝)이 아니다.
    expect(rows[0].parentElement).toBe(rows[1].parentElement);
    // 늘 열려 있던 네 줄짜리 입력창은 없다.
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("공지가 비어 있으면 빈칸이 아니라 비었다고 말한다", async () => {
    mockRole = "admin";
    apiMock.mockImplementation(() => Promise.resolve({
      settings: { maintenance_mode: { value: false }, maintenance_message: { value: "" } },
    }));
    renderMaintenance();
    expect(await screen.findByText("아직 적은 공지가 없습니다.")).toBeInTheDocument();
  });
});

describe("유지보수 — 점검 공지 초안 seeding", () => {
  it("서버 공지가 늦게 도착해도 편집기에 실린다", async () => {
    // 회귀: setMsg(fn)의 fn은 '다음 렌더에서' 실행되는데, 예전 코드는 그 안에서 ref를 읽었다.
    // ref는 setMsg를 부른 바로 다음 줄에서 이미 새 값으로 덮여 있어 비교가 항상 거짓이 됐고,
    // 그 결과 편집기가 늘 빈 채로 떴다(관리자가 현재 공지 문구를 이 화면에서 볼 수 없었다).
    // 응답을 비동기로 늦춰야 재현된다 — 캐시가 따뜻한 동기 경로에서는 지연 초기화가 가려 준다.
    mockRole = "admin";
    apiMock.mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve({
      settings: {
        maintenance_mode: { value: false },
        maintenance_message: { value: "현재 시스템 점검 중입니다." },
      },
    }), 20)));
    const user = userEvent.setup();
    renderMaintenance();

    // 늦게 온 공지가 줄의 값으로 선다.
    expect(await screen.findByText("현재 시스템 점검 중입니다.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "점검 공지 수정" }));
    const dialog = await screen.findByRole("dialog", { name: "점검 공지 수정" });
    const box = within(dialog).getByLabelText("점검 공지");
    await waitFor(() => expect(box.value).toBe("현재 시스템 점검 중입니다."));
    // 초안 == 서버 값이므로 고친 것이 없다 — 저장은 닫혀 있다.
    expect(within(dialog).getByRole("button", { name: "공지 저장" })).toBeDisabled();
  });
});

describe("진단 — 최근 작업 오류 분포(errorBuckets)", () => {
  const at = (iso) => ({ at: iso, job_type: "chat_message", error: "boom" });

  it("점이 부족하면 추세를 만들지 않는다", () => {
    expect(errorBuckets([])).toBeNull();
    expect(errorBuckets([at("2026-08-01T00:00:00"), at("2026-08-02T00:00:00")])).toBeNull();
  });

  it("전부 같은 순간이면(구간 폭 0) 만들지 않는다", () => {
    const same = "2026-08-01T00:00:00";
    expect(errorBuckets([at(same), at(same), at(same)])).toBeNull();
  });

  it("퍼져 있으면 구간별로 세고, 합계가 원본 건수와 같다", () => {
    const errs = [
      at("2026-08-01T00:00:00"), at("2026-08-01T01:00:00"),
      at("2026-08-01T02:00:00"), at("2026-08-01T12:00:00"),
    ];
    const b = errorBuckets(errs, 4);
    expect(b.counts).toHaveLength(4);
    expect(b.counts.reduce((s, n) => s + n, 0)).toBe(4);
    // 마지막 값(최댓값)이 배열 밖 인덱스로 넘어가지 않고 마지막 구간에 들어간다.
    expect(b.counts[3]).toBe(1);
    expect(b.n).toBe(4);
  });

  it("파싱할 수 없는 시각은 세지 않는다(0으로 둔갑시키지 않는다)", () => {
    const b = errorBuckets([at("nope"), at("2026-08-01T00:00:00"), at("2026-08-02T00:00:00")]);
    expect(b).toBeNull(); // 유효한 점이 2개뿐 → 추세 없음
  });

  it("화면에 그릴 때 그림 옆에 '무엇의 분포인지'를 글자로 함께 낸다", async () => {
    mockRole = "system_admin";
    apiMock.mockImplementation((path) => {
      if (path === "/api/admin/diagnostics/bundle") {
        return Promise.resolve({
          generated_at: "2026-08-03T07:00:00",
          dashboard: {
            components: { web: "up", worker: "up", scheduler: "up" },
            integrations: {}, counts: {}, jobs_24h: {}, recent_critical_audit: [],
            disk: {}, memory: {}, cert_days_remaining: null,
            last_backup_at: "2026-08-03T00:00:00", last_backup_status: "succeeded",
          },
          recent_job_errors: [
            { at: "2026-08-01T00:00:00", job_type: "chat_message", error: "boom 1" },
            { at: "2026-08-01T06:00:00", job_type: "chat_message", error: "boom 2" },
            { at: "2026-08-02T00:00:00", job_type: "chat_message", error: "boom 3" },
            { at: "2026-08-03T00:00:00", job_type: "chat_message", error: "boom 4" },
          ],
        });
      }
      return Promise.reject(new Error("unexpected api call: " + path));
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ThemeModeProvider><ToastProvider><ConfirmProvider><MemoryRouter>
          <Diagnostics />
        </MemoryRouter></ConfirmProvider></ToastProvider></ThemeModeProvider>
      </QueryClientProvider>
    );

    // 스파크라인은 aria-hidden이다 — 옆의 글자 요약만이 이 그림의 유일한 접근 경로다.
    // '전체 추세가 아니라 이 목록의 분포'라는 단서를 반드시 함께 낸다(20건만 오는 자료라서).
    expect(await screen.findByText(/최근 실패 4건의 발생 분포/)).toBeInTheDocument();
    expect(screen.getByText(/이 목록에 담긴 건들의 분포/)).toBeInTheDocument();
  });
});
