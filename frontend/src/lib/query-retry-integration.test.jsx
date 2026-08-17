import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { shouldRetryQuery } from "./queryRetry.js";

/* PA-RC-0034 acceptance (1)(2): 단위 테스트(query-retry.test.js)는 shouldRetryQuery
 * 자신의 반환값만 본다 — 이 파일은 그 함수가 실제 QueryClient의 retry 옵션으로 꽂혔을 때
 * react-query의 재시도 엔진이 정말로 4xx에서 멈추는지를 본다(main.jsx와 동일하게
 * defaultOptions.queries.retry에 넣어 구성). 실측(`/board/<없는 id>`가 4회→1회)의
 * 축소판이다 — 실제 화면 대신 최소 useQuery 훅으로 같은 배선을 재현한다.
 */

function Probe({ queryFn }) {
  const q = useQuery({ queryKey: ["probe"], queryFn });
  if (q.isLoading) return <div>불러오는 중…</div>;
  if (q.isError) return <div>오류: {q.error.status}</div>;
  return <div>완료</div>;
}

function renderWithDefaultRetry(queryFn) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: shouldRetryQuery } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <Probe queryFn={queryFn} />
    </QueryClientProvider>,
  );
}

describe("전역 retry 배선 — react-query 재시도 엔진과 실제로 맞물린다 (PA-RC-0034)", () => {
  it("404는 정확히 1번만 호출한다(재시도 없음) — 기존 기본값(3회 재시도, 총 4회)과 대비", async () => {
    const queryFn = vi.fn().mockRejectedValue({ status: 404, message: "찾을 수 없음" });
    renderWithDefaultRetry(queryFn);

    await waitFor(() => expect(screen.getByText(/오류/)).toBeInTheDocument());
    expect(queryFn).toHaveBeenCalledTimes(1);
  });

  it("403도 재시도 없이 즉시 오류로 넘어간다", async () => {
    const queryFn = vi.fn().mockRejectedValue({ status: 403, message: "권한 없음" });
    renderWithDefaultRetry(queryFn);

    await waitFor(() => expect(screen.getByText(/오류/)).toBeInTheDocument());
    expect(queryFn).toHaveBeenCalledTimes(1);
  });

  it("500은 여전히 재시도한다 — 과잉 수정(재시도 전면 차단) 방지", async () => {
    const queryFn = vi.fn().mockRejectedValue({ status: 500, message: "서버 오류" });
    // react-query 기본 retryDelay는 지수 백오프(최초 재시도까지 약 1초, 다음은 약 2초)라
    // 실제 타이밍으로 기다리면 테스트가 느리고 타이밍에 취약해진다 — retryDelay만 0으로
    // 낮춰 "재시도 여부" 자체(이 RC의 관심사)를 빠르고 확정적으로 본다.
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: shouldRetryQuery, retryDelay: 0 } },
    });
    render(
      <QueryClientProvider client={qc}>
        <Probe queryFn={queryFn} />
      </QueryClientProvider>,
    );

    // shouldRetryQuery는 failureCount<2일 때 재시도하므로 총 3회(최초 + 2번 재시도) 호출된다.
    await waitFor(() => expect(queryFn.mock.calls.length).toBeGreaterThanOrEqual(3));
    await waitFor(() => expect(screen.getByText(/오류/)).toBeInTheDocument());
  });
});
