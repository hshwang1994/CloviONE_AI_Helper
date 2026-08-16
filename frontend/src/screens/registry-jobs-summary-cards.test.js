import { describe, it, expect, vi } from "vitest";

import { REGISTRY } from "./registry.js";

/* VIS-120 — 작업 큐 요약 카드 6장이 전부 "지금 이 순간의 큐 깊이"(대기/실행 중/실행
 * 가능/실패/완료/취소됨)뿐이라, 셋 다 0이면 건강해 보여도 "최근에 계속 실패해 왔다"·
 * "처리가 느려지고 있다" 같은 추세 신호는 어디에도 없었다. 백엔드(app/jobs/repository.py
 * queue_stats)가 낸 recent_failed_24h·avg_processing_seconds_24h를 이 카드 목록이
 * 실제로 소비하는지 — 그리고 "0"과 "잴 것 없음"을 구별하는지 — 확인한다.
 */
function ctx() {
  return { setFilter: vi.fn() };
}

describe("작업 큐 요약 카드 — 최근 24시간 신호 (VIS-120)", () => {
  const base = {
    queued: 0, running: 0, ready: 0, failed: 0, succeeded: 0, cancelled: 0,
  };

  it("최근 24시간 실패가 있으면 그 수를 그대로 보여주고 danger 톤을 준다", () => {
    const cards = REGISTRY.jobs.summary.cards({ ...base, recent_failed_24h: 3 }, ctx());
    const card = cards.find((c) => c.label === "최근 24시간 실패");
    expect(card.value).toBe(3);
    expect(card.kind).toBe("danger");
  });

  it("최근 24시간 실패가 0이면 danger 톤을 안 준다(잡음 방지)", () => {
    const cards = REGISTRY.jobs.summary.cards({ ...base, recent_failed_24h: 0 }, ctx());
    const card = cards.find((c) => c.label === "최근 24시간 실패");
    expect(card.value).toBe(0);
    expect(card.kind).toBeUndefined();
  });

  it("평균 처리 시간이 60초 미만이면 초 단위로, 이상이면 분+초로 보여준다", () => {
    const fast = REGISTRY.jobs.summary.cards({ ...base, avg_processing_seconds_24h: 12.3 }, ctx());
    expect(fast.find((c) => c.label === "평균 처리 시간(24h)").value).toBe("12.3초");

    const slow = REGISTRY.jobs.summary.cards({ ...base, avg_processing_seconds_24h: 125 }, ctx());
    expect(slow.find((c) => c.label === "평균 처리 시간(24h)").value).toBe("2분 5초");
  });

  it("평균 처리 시간을 잴 성공 이력이 없으면 0초가 아니라 null을 낸다(StatCard가 '-'로 그린다)", () => {
    const cards = REGISTRY.jobs.summary.cards({ ...base, avg_processing_seconds_24h: null }, ctx());
    expect(cards.find((c) => c.label === "평균 처리 시간(24h)").value).toBeNull();
  });

  it("두 카드 다 기존 6장 옆에 추가될 뿐, 기존 큐 깊이 카드를 안 지운다", () => {
    const cards = REGISTRY.jobs.summary.cards(
      { ...base, recent_failed_24h: 1, avg_processing_seconds_24h: 5 }, ctx()
    );
    const labels = cards.map((c) => c.label);
    expect(labels).toEqual(expect.arrayContaining([
      "대기", "실행 중", "실행 가능(ready)", "실패", "완료", "취소됨",
      "최근 24시간 실패", "평균 처리 시간(24h)",
    ]));
  });
});
