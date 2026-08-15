import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

    // 예전엔 이 버튼 자체가 렌더되지 않았다 — 존재 + 비활성 둘 다 확인한다.
    const checkBtn = screen.getByRole("button", { name: "미리 검증" });
    expect(checkBtn).toBeInTheDocument();
    expect(checkBtn).toBeDisabled();

    const saveBtn = screen.getByRole("button", { name: "공지 저장" });
    expect(saveBtn).toBeInTheDocument();
    expect(saveBtn).toBeDisabled();

    // 비활성 이유는 눈에 보이는 글자로 남아야 한다(모드 카드 1 + 공지 카드 1).
    expect(screen.getAllByText(/관리자, 시스템 관리자만 변경할 수 있습니다/)).toHaveLength(2);
    // 그 이유가 스크린리더에도 닿도록 버튼과 프로그래매틱하게 연결돼 있어야 한다.
    expect(toggleBtn).toHaveAttribute("aria-describedby", "maint-locked-reason");
    expect(checkBtn).toHaveAttribute("aria-describedby", "maint-locked-reason");

    // 공지는 disabled가 아니라 readOnly다 — 읽기 전용 역할도 내용을 선택·복사할 수 있어야 한다.
    const box = screen.getByLabelText("점검 공지");
    expect(box).toHaveAttribute("readonly");
    expect(box).not.toBeDisabled();
  });

  it("쓰기 권한이 있으면 같은 버튼이 활성화되고 이유 문구가 사라진다", async () => {
    mockRole = "admin";
    renderMaintenance();

    const toggleBtn = await screen.findByRole("button", { name: "유지보수 모드 활성화" });
    expect(toggleBtn).toBeEnabled();
    expect(screen.getByRole("button", { name: "미리 검증" })).toBeEnabled();
    expect(screen.queryByText(/관리자, 시스템 관리자만 변경할 수 있습니다/)).toBeNull();
    expect(screen.getByLabelText("점검 공지")).not.toHaveAttribute("readonly");
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
    renderMaintenance();

    const box = await screen.findByLabelText("점검 공지");
    await waitFor(() => expect(box.value).toBe("현재 시스템 점검 중입니다."));
    // 초안 == 서버 값이므로 '되돌리기'(변경 사항이 있을 때만 뜨는 버튼)는 없어야 한다.
    expect(screen.queryByRole("button", { name: "되돌리기" })).toBeNull();
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
