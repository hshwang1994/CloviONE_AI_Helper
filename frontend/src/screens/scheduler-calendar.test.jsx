import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 스케줄러 캘린더 (PLAN Phase 6).
 *
 * 여기서 못박는 것:
 *   - 조회 구간을 **KST 달 경계**로 만든다. UTC 로 자르면 화면의 '8월'과 서버가 준 8월이
 *     9시간 어긋나 첫날/마지막날 실행이 통째로 빠진다.
 *   - 지난 실행과 앞으로의 예정을 **눈으로 구별**할 수 있다(색만이 아니라 표기로).
 *   - 서버가 "잘렸다"고 하면 그 사실을 숨기지 않는다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { SchedulerCalendar } from "./SchedulerCalendar.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { AuthProvider } from "../app/auth.jsx";

const SCHEDULES = [{ id: "s-1", name: "매일 리포트", enabled: true, timezone: "Asia/Seoul" }];

function body(extra = {}) {
  return {
    items: [],
    start: "2026-08-01T00:00:00",
    end: "2026-08-31T00:00:00",
    truncated: false,
    schedules: SCHEDULES,
    ...extra,
  };
}

// `/api/me`는 AuthProvider가 마운트되자마자 부른다 — 재시도 버튼의 역할 게이트(OPS_ROLES)가
// `useAuth().data.role`을 읽으므로, 이 계정 응답도 API 목(mock) 하나가 함께 감당한다.
const ME = { user: { id: "u-1", role: "operator" }, csrf_token: "t", features: {}, branding: {} };

function renderCalendar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <ThemeModeProvider>
          <ToastProvider>
            <ConfirmProvider>
              <MemoryRouter>
                <SchedulerCalendar />
              </MemoryRouter>
            </ConfirmProvider>
          </ToastProvider>
        </ThemeModeProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

let lastUrl = null;

// `/api/me` 는 항상 이 함수가 가로챈다 — 각 테스트는 달력 조회(그 외 경로)만 신경 쓰면 된다.
function mockApi(handler) {
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/me") return Promise.resolve(ME);
    return handler(path, opts);
  });
}

beforeEach(() => {
  apiMock.mockReset();
  lastUrl = null;
  mockApi((path) => { lastUrl = path; return Promise.resolve(body()); });
});

describe("실행 달력", () => {
  it("요일 머리글 7개와 6주치 칸을 그린다", async () => {
    renderCalendar();
    await waitFor(() => expect(apiMock).toHaveBeenCalled());
    expect(await screen.findByRole("grid")).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader")).toHaveLength(7);
    // 6주 × 7일 = 42칸. 달을 넘길 때 높이가 튀지 않게 항상 42칸이다.
    expect(screen.getAllByRole("gridcell")).toHaveLength(42);
  });

  it("조회 구간을 start/end 로 넘기고 92일을 넘기지 않는다", async () => {
    renderCalendar();
    await waitFor(() => expect(lastUrl).toBeTruthy());
    const url = new URL("http://x" + lastUrl);
    const start = new Date(url.searchParams.get("start"));
    const end = new Date(url.searchParams.get("end"));
    expect(Number.isNaN(start.getTime())).toBe(false);
    expect(end.getTime()).toBeGreaterThan(start.getTime());
    const days = (end - start) / 86400000;
    expect(days).toBeLessThanOrEqual(92);
    // 달 경계는 KST 자정 = UTC 15:00 전날. 그래서 시각이 정각 15:00 이어야 한다.
    expect(start.getUTCHours()).toBe(15);
  });

  it("지난 실행과 앞으로의 예정을 구별해 그린다", async () => {
    const todayKst = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date());
    mockApi((path) => {
      lastUrl = path;
      return Promise.resolve(body({
        items: [
          { kind: "run", schedule_id: "s-1", schedule_name: "매일 리포트",
            occurs_at: `${todayKst}T00:00:00`, status: "failed", run_id: "r-1", error_message: "대상 서비스 500" },
          { kind: "planned", schedule_id: "s-1", schedule_name: "매일 리포트",
            occurs_at: `${todayKst}T02:00:00`, status: null, run_id: null, error_message: null },
        ],
      }));
    });
    renderCalendar();
    const dots = await screen.findAllByTitle(/매일 리포트/);
    expect(dots).toHaveLength(2);
    const titles = dots.map((d) => d.getAttribute("title"));
    expect(titles.some((t) => t.includes("예정"))).toBe(true);
    expect(titles.some((t) => t.includes("실패"))).toBe(true);
    // 색이 아니라 표기로도 구별된다(○ = 예정).
    expect(dots.some((d) => d.textContent.startsWith("○"))).toBe(true);
  });

  it("점을 누르면 상세가 열리고 오류 메시지를 보여 준다", async () => {
    const todayKst = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date());
    mockApi(() => Promise.resolve(body({
      items: [{ kind: "run", schedule_id: "s-1", schedule_name: "매일 리포트",
        occurs_at: `${todayKst}T00:00:00`, status: "failed", run_id: "r-1", error_message: "대상 서비스 500" }],
    })));
    renderCalendar();
    const dot = await screen.findByTitle(/매일 리포트/);
    await userEvent.click(dot);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("실행 기록");
    expect(dialog).toHaveTextContent("대상 서비스 500");
  });

  it("서버가 잘렸다고 하면 그 사실을 숨기지 않는다", async () => {
    mockApi(() => Promise.resolve(body({ truncated: true })));
    renderCalendar();
    expect(await screen.findByText(/전부 펼치지 못했습니다/)).toBeInTheDocument();
  });

  it("일정이 하나도 없으면 만들라고 안내한다", async () => {
    mockApi(() => Promise.resolve(body({ schedules: [] })));
    renderCalendar();
    expect(await screen.findByText("등록된 실행 일정이 없습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("grid")).not.toBeInTheDocument();
  });

  // VIS-124/VIS-125: 일정은 있는데(등록 자체는 됨) 전부 비활성이면 예정이 안 만들어진다 —
  // 예전엔 그 이유를 말하지 않고 빈 42칸 격자만 그렸다.
  it("등록된 일정이 전부 비활성이면 빈 격자 대신 이유와 활성화 경로를 안내한다", async () => {
    mockApi(() => Promise.resolve(body({
      items: [], schedules: [{ id: "s-1", name: "매일 리포트", enabled: false, timezone: "Asia/Seoul" }],
    })));
    renderCalendar();
    expect(await screen.findByText("예정된 실행이 없습니다.")).toBeInTheDocument();
    expect(screen.getByText(/등록된 일정 1개가 모두 비활성 상태입니다/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "실행 일정에서 활성화" })).toHaveAttribute("href", "#/schedules");
    expect(screen.queryByRole("grid")).not.toBeInTheDocument();
  });

  it("활성 일정이 하나라도 있으면(예정이 우연히 0건이어도) 격자를 그대로 그린다", async () => {
    mockApi(() => Promise.resolve(body({
      items: [],
      schedules: [
        { id: "s-1", name: "매일 리포트", enabled: false, timezone: "Asia/Seoul" },
        { id: "s-2", name: "주간 요약", enabled: true, timezone: "Asia/Seoul" },
      ],
    })));
    renderCalendar();
    expect(await screen.findByRole("grid")).toBeInTheDocument();
    expect(screen.queryByText("예정된 실행이 없습니다.")).not.toBeInTheDocument();
  });
});

describe("실행 상세의 재시도 액션 (M9)", () => {
  const todayKst = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());

  function bodyWithRun(status, extra = {}) {
    return body({
      items: [{ kind: "run", schedule_id: "s-1", schedule_name: "매일 리포트",
        occurs_at: `${todayKst}T00:00:00`, status, run_id: "r-1", error_message: status === "failed" ? "대상 서비스 500" : null }],
      ...extra,
    });
  }

  async function openFailedRunDetail() {
    mockApi((path) => {
      lastUrl = path;
      if (path.startsWith("/api/admin/schedules/runs/")) {
        return Promise.resolve({ ok: true, run: { id: "r-1", status: "queued" } });
      }
      return Promise.resolve(bodyWithRun("failed"));
    });
    renderCalendar();
    const dot = await screen.findByTitle(/매일 리포트/);
    await userEvent.click(dot);
    return screen.findByRole("dialog");
  }

  it("🔴 실패한 실행에는 재시도 버튼이 있고, 확인 후 재시도 API를 호출한다", async () => {
    await openFailedRunDetail();
    const retryBtn = await screen.findByRole("button", { name: "재시도" });
    await userEvent.click(retryBtn);
    // 되돌릴 수 없는 부수효과(다시 큐에 넣어 그 스케줄을 다시 실행)라 확인창을 거친다 —
    // DataScreen의 다른 운영 액션(job.retry 등)과 같은 관용. 확인창의 확인 버튼도 같은
    // 라벨("재시도")을 쓴다(DataScreen.jsx의 confirmLabel: a.label 관용과 동일).
    const buttons = await screen.findAllByRole("button", { name: "재시도" });
    await userEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      "/api/admin/schedules/runs/r-1/retry",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("성공한 실행에는 재시도 버튼이 없다", async () => {
    mockApi(() => Promise.resolve(bodyWithRun("succeeded")));
    renderCalendar();
    const dot = await screen.findByTitle(/매일 리포트/);
    await userEvent.click(dot);
    await screen.findByRole("dialog");
    expect(screen.queryByRole("button", { name: "재시도" })).not.toBeInTheDocument();
  });

  it("🔴 대기 중인 실행에는 취소 버튼이 있고, 확인 후 취소 API를 호출한다", async () => {
    mockApi((path) => {
      lastUrl = path;
      if (path.startsWith("/api/admin/schedules/runs/")) {
        return Promise.resolve({ ok: true, run: { id: "r-1", status: "skipped" } });
      }
      return Promise.resolve(bodyWithRun("queued"));
    });
    renderCalendar();
    const dot = await screen.findByTitle(/매일 리포트/);
    await userEvent.click(dot);
    await screen.findByRole("dialog");
    const cancelBtn = await screen.findByRole("button", { name: "취소" });
    await userEvent.click(cancelBtn);
    // 되돌릴 수 없는 부수효과(대기/실행 중인 작업을 실제로 중단)라 확인창을 거친다.
    const buttons = await screen.findAllByRole("button", { name: "예약 실행 취소" });
    await userEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      "/api/admin/schedules/runs/r-1/cancel",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("실행 중인 실행에도 취소 버튼이 있다", async () => {
    mockApi(() => Promise.resolve(bodyWithRun("running")));
    renderCalendar();
    const dot = await screen.findByTitle(/매일 리포트/);
    await userEvent.click(dot);
    await screen.findByRole("dialog");
    expect(await screen.findByRole("button", { name: "취소" })).toBeInTheDocument();
  });

  it("성공/실패로 끝난 실행에는 취소 버튼이 없다", async () => {
    mockApi(() => Promise.resolve(bodyWithRun("succeeded")));
    renderCalendar();
    const dot = await screen.findByTitle(/매일 리포트/);
    await userEvent.click(dot);
    await screen.findByRole("dialog");
    expect(screen.queryByRole("button", { name: "취소" })).not.toBeInTheDocument();
  });
});

describe("실행 상세 → 작업 큐로 가는 크로스링크 (FN-13/IA-02 반대 방향)", () => {
  const todayKst = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());

  it("실제 실행(run_id 있음)에는 '작업 큐에서 보기' 버튼이 있고 schedule_run_id로 딥링크한다", async () => {
    mockApi(() => Promise.resolve(body({
      items: [{ kind: "run", schedule_id: "s-1", schedule_name: "매일 리포트",
        occurs_at: `${todayKst}T00:00:00`, status: "succeeded", run_id: "r-1", error_message: null }],
    })));
    renderCalendar();
    const dot = await screen.findByTitle(/매일 리포트/);
    await userEvent.click(dot);
    await screen.findByRole("dialog");
    const btn = await screen.findByRole("button", { name: "작업 큐에서 보기" });
    await userEvent.click(btn);
    expect(window.location.hash).toBe("#/jobs?schedule_run_id=r-1");
  });

  it("예정(run_id 없음)에는 버튼이 없다 — 아직 처리한 작업이 없다", async () => {
    mockApi(() => Promise.resolve(body({
      items: [{ kind: "planned", schedule_id: "s-1", schedule_name: "매일 리포트",
        occurs_at: `${todayKst}T02:00:00`, status: null, run_id: null, error_message: null }],
    })));
    renderCalendar();
    const dot = await screen.findByTitle(/매일 리포트/);
    await userEvent.click(dot);
    await screen.findByRole("dialog");
    expect(screen.queryByRole("button", { name: "작업 큐에서 보기" })).not.toBeInTheDocument();
  });
});

describe("실행 상세의 동작은 모달 발 하나에 선다 (조합 계약 C-4 · 핸드오프 RULES §8)", () => {
  const todayKst = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());

  async function openRun(status, runId = "r-1") {
    mockApi(() => Promise.resolve(body({
      items: [{ kind: status ? "run" : "planned", schedule_id: "s-1", schedule_name: "매일 리포트",
        occurs_at: `${todayKst}T00:00:00`, status, run_id: runId, error_message: status === "failed" ? "대상 서비스 500" : null }],
    })));
    renderCalendar();
    await userEvent.click(await screen.findByTitle(/매일 리포트/));
    const dialog = await screen.findByRole("dialog");
    const footer = dialog.querySelector('[data-action-footer="modal"]');
    expect(footer).not.toBeNull();
    return footer;
  }

  it("실패한 실행: 옮겨 가는 동작 둘은 왼쪽 칸 보조, 오른쪽 끝은 닫기 → 재시도(채움 하나)이고 글자 단추가 없다", async () => {
    const footer = await openRun("failed");
    await within(footer).findByRole("button", { name: "재시도" });
    const order = [...footer.querySelectorAll("button")].map((b) => b.textContent);
    expect(order).toEqual(["이 일정 열기", "작업 큐에서 보기", "닫기", "재시도"]);
    const filled = footer.querySelectorAll(".MuiButton-contained");
    expect(filled).toHaveLength(1);
    expect(filled[0].textContent).toBe("재시도");
    expect(footer.querySelectorAll(".MuiButton-text")).toHaveLength(0);
    expect(within(footer).getByRole("button", { name: "이 일정 열기" }).className).not.toMatch(/MuiButton-contained/);
  });

  it("대기 중인 실행: 확정 자리는 실행 취소(파괴 보조)이고 채움이 없다", async () => {
    const footer = await openRun("queued");
    await within(footer).findByRole("button", { name: "취소" });
    const order = [...footer.querySelectorAll("button")].map((b) => b.textContent);
    expect(order).toEqual(["이 일정 열기", "작업 큐에서 보기", "닫기", "취소"]);
    expect(footer.querySelectorAll(".MuiButton-contained")).toHaveLength(0);
    expect(within(footer).getByRole("button", { name: "취소" }).className).toMatch(/MuiButton-outlinedError/);
  });

  it("예정: 발에는 이 일정 열기와 닫기만 서고, 몸 안에는 단추가 없다", async () => {
    const footer = await openRun(null, null);
    const order = [...footer.querySelectorAll("button")].map((b) => b.textContent);
    expect(order).toEqual(["이 일정 열기", "닫기"]);
    const dialog = screen.getByRole("dialog");
    // 발 밖의 단추는 모달 머리의 닫기(아이콘 30) 하나뿐이다 — 몸 안 단추 줄이 없다.
    const outside = [...dialog.querySelectorAll("button")].filter((b) => !footer.contains(b));
    expect(outside.map((b) => b.getAttribute("aria-label") || b.textContent)).toEqual(["닫기"]);
  });
});
