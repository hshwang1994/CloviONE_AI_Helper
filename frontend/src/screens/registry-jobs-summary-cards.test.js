import { describe, it, expect, vi } from "vitest";

import { REGISTRY } from "./registry.js";
import { FILTER_GROUP_ORDER, filterGroupOf } from "../ui/FilterBar.jsx";

/* VIS-120 — 작업 큐 요약 카드 6장이 전부 "지금 이 순간의 큐 깊이"(대기/실행 중/실행
 * 가능/실패/완료/취소됨)뿐이라, 셋 다 0이면 건강해 보여도 "최근에 계속 실패해 왔다"·
 * "처리가 느려지고 있다" 같은 추세 신호는 어디에도 없었다. 백엔드(app/jobs/repository.py
 * queue_stats)가 낸 recent_failed_24h·avg_processing_seconds_24h를 이 카드 목록이
 * 실제로 소비하는지 — 그리고 "0"과 "잴 것 없음"을 구별하는지 — 확인한다.
 *
 * qa-contract-change: 관리자 요약 규칙(D-501)으로 「실행 가능(ready)」은 대기와 수가 다를 때만 서고(같으면 같은 사실을 두 번 말한다),
 * 「가장 오래된 대기」는 반폭 측정 판이 아니라 카드 머리의 경보 칩(role risk)이 됐다. 전체는 겹치지 않는 상태 다섯의 합이다. 기존 카드
 * 목록 단언은 대기와 실행 가능이 갈리는 입력으로 옮겼고, 세 규칙을 각각 새로 잰다.

 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 *
 * qa-contract-change: 대기 칩의 이름이 행의 상태 배지와 같은 「대기 중」이 됐다(같은 상태가 칩은 「대기」, 행은 「대기 중」이던 결함, D-587). 칩 목록 단언은 새 이름을 기다리고, 하루가 넘는 대기 나이를 「53일 2시간」으로 읽는지 새로 잰다.
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
    expect(fast.find((c) => c.label === "평균 처리 시간(최근 24시간)").value).toBe("12.3초");

    const slow = REGISTRY.jobs.summary.cards({ ...base, avg_processing_seconds_24h: 125 }, ctx());
    expect(slow.find((c) => c.label === "평균 처리 시간(최근 24시간)").value).toBe("2분 5초");
  });

  it("평균 처리 시간을 잴 성공 이력이 없으면 0초가 아니라 null을 낸다(카드 아래 줄에 서지 않는다)", () => {
    const cards = REGISTRY.jobs.summary.cards({ ...base, avg_processing_seconds_24h: null }, ctx());
    expect(cards.find((c) => c.label === "평균 처리 시간(최근 24시간)").value).toBeNull();
  });

  it("두 카드 다 큐 깊이 카드 옆에 추가될 뿐, 기존 큐 깊이 카드를 안 지운다", () => {
    const cards = REGISTRY.jobs.summary.cards(
      { ...base, queued: 3, ready: 1, recent_failed_24h: 1, avg_processing_seconds_24h: 5 }, ctx()
    );
    const labels = cards.map((c) => c.label);
    expect(labels).toEqual(expect.arrayContaining([
      "대기 중", "실행 중", "실행 가능", "실패", "완료", "취소됨",
      "최근 24시간 실패", "평균 처리 시간(최근 24시간)",
    ]));
    // 옛 이름이 남아 같은 상태가 두 이름으로 서지 않는다.
    expect(labels).not.toContain("대기");
  });

  it("상태 칸의 대기 선택지도 행의 배지와 같은 「대기 중」이다", () => {
    const status = REGISTRY.jobs.filters.find((f) => f.key === "status");
    expect(status.options.find((o) => o.value === "queued").label).toBe("대기 중");
  });
});

/* 하루가 넘는 대기 — 「1274시간 20분」은 사람이 24로 나눠 봐야 며칠인지 읽힌다. 칩과 「대기」 열의 지연은 같은 형식기를 쓴다. */
describe("작업 큐 — 하루가 넘는 대기는 일과 시간으로 말한다", () => {
  const base = { queued: 1, running: 0, ready: 1, failed: 0, succeeded: 0, cancelled: 0 };
  const AGO = (min) => new Date(Date.now() - min * 60000).toISOString();

  it("가장 오래된 대기 칩: 76,460분(1274시간 20분)은 「53일 2시간」이다", () => {
    const chip = REGISTRY.jobs.summary.cards({ ...base, oldest_queued_at: AGO(1274 * 60 + 20) }, ctx())
      .find((c) => c.label === "가장 오래된 대기");
    expect(chip.value).toBe("53일 2시간");
  });

  it("대기 열의 지연도 같은 형식이고, 하루 안쪽은 시간과 분이다", () => {
    const col = REGISTRY.jobs.columns.find((c) => c.key === "available_at");
    expect(col.render({ status: "queued", available_at: AGO(1274 * 60 + 20) })).toBe("지연 53일 2시간");
    expect(col.render({ status: "queued", available_at: AGO(125) })).toBe("지연 2시간 5분");
    expect(col.render({ status: "queued", available_at: AGO(24 * 60) })).toBe("지연 1일");
    // 반례: 대기가 아니면 지연을 말하지 않는다.
    expect(col.render({ status: "failed", available_at: AGO(125) })).toBe("-");
  });
});

/* 관리자 요약 규칙 (D-501) — 한 사실은 한 자리, 경보는 칩, 전체는 겹치지 않는 부분의 합. */
describe("작업 큐 요약 — 한 사실 한 자리 (D-501)", () => {
  const base = { queued: 0, running: 0, ready: 0, failed: 0, succeeded: 0, cancelled: 0 };

  it("실행 가능은 대기와 같은 수면 서지 않는다 — 「대기 7」 옆 「실행 가능 7」은 같은 사실이다", () => {
    const same = REGISTRY.jobs.summary.cards({ ...base, queued: 7, ready: 7 }, ctx());
    expect(same.map((c) => c.label)).not.toContain("실행 가능");
    // 반례 — 예정 시각이 아직 안 온 대기가 있으면 실행 가능은 새 사실이라 경보 칩으로 선다.
    const differs = REGISTRY.jobs.summary.cards({ ...base, queued: 7, ready: 5 }, ctx());
    const ready = differs.find((c) => c.label === "실행 가능");
    expect(ready.value).toBe(5);
    expect(ready.role).toBe("risk");
  });

  it("가장 오래된 대기는 경보 칩이고, 1분이 안 된 대기는 칩을 세우지 않는다", () => {
    const now = Date.now();
    const old = REGISTRY.jobs.summary.cards(
      { ...base, queued: 2, oldest_queued_at: new Date(now - 125 * 60000).toISOString() }, ctx(),
    ).find((c) => c.label === "가장 오래된 대기");
    expect(old.role).toBe("risk");
    expect(old.value).toBe("2시간 5분");
    expect(old.kind).toBe("danger");
    const fresh = REGISTRY.jobs.summary.cards(
      { ...base, queued: 1, oldest_queued_at: new Date(now - 10 * 1000).toISOString() }, ctx(),
    ).find((c) => c.label === "가장 오래된 대기");
    expect(fresh).toBeUndefined();
  });

  it("가장 오래된 대기 칩을 누르면 대기로 좁힌다", () => {
    const c = ctx();
    REGISTRY.jobs.summary.cards(
      { ...base, queued: 1, oldest_queued_at: new Date(Date.now() - 30 * 60000).toISOString() }, c,
    ).find((x) => x.label === "가장 오래된 대기").onClick();
    expect(c.setFilter).toHaveBeenCalledWith("status", "queued");
  });

  it("전체는 겹치지 않는 상태 다섯의 합이다 — 실행 가능 · 최근 실패는 더하지 않는다", () => {
    const total = REGISTRY.jobs.summary.total({
      queued: 7, running: 1, ready: 7, failed: 3, succeeded: 12, cancelled: 2, recent_failed_24h: 9,
    });
    expect(total).toBe(25);
    expect(REGISTRY.jobs.summary.total({})).toBe(0);
  });
});

/* 필터 줄 순서 (D-501) — 큐를 훑는 사람이 먼저 고르는 것은 유형과 상태다. 연결된 스케줄 · 실행 건 ID 는 대개 일정
   화면의 링크가 채우는 좁히기라 줄 뒤에 선다. 순서는 `DataScreen` 이 `FILTER_GROUP_ORDER` 로 정한다(안정 정렬). */
describe("작업 큐 필터 줄 순서 (D-501)", () => {
  it("유형 → 상태 → 연결된 스케줄 → 실행 건 ID 순서로 선다", () => {
    const rank = (f) => FILTER_GROUP_ORDER.indexOf(filterGroupOf(f));
    const ordered = REGISTRY.jobs.filters
      .map((f, i) => ({ f, i }))
      .sort((a, b) => (rank(a.f) - rank(b.f)) || (a.i - b.i))
      .map((x) => x.f.label);
    expect(ordered).toEqual(["유형", "상태", "연결된 실행 일정", "실행 건 ID"]);
  });

  it("연결된 스케줄은 여전히 이름으로 고르는 칸이다 — 순서만 옮겼다", () => {
    const f = REGISTRY.jobs.filters.find((x) => x.key === "schedule_id");
    expect(f.kind).toBe("entity");
    expect(f.optionsFromRefList).toBe("schedules");
  });
});
