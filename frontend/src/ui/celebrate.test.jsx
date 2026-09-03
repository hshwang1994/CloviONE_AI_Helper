/* 축포가 **터질 자리에서만** 터진다.
 *
 * 이 파일이 지키는 성질은 하나다: 「목록이 0이 됐다」와 「내가 일을 끝냈다」는 다른 사실이다.
 * 검색어를 쳐서 결과가 0건이 된 사람에게 종잇조각이 쏟아지면 그것은 축하가 아니라 조롱이다.
 * 그 구별을 `useCelebrateOnCleared` 의 **조건 지문**(token)이 한다.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render } from "@testing-library/react";

const confettiSpy = vi.fn();
vi.mock("canvas-confetti", () => ({ default: (...a) => confettiSpy(...a) }));

import {
  celebrateIfCleared, useCelebrateOnCleared, resetBurstCooldown,
  celebrateIfCompleted, celebrateIfCompletedCategory, doneStatusKeys,
  celebrateCreated, celebrate, CLOVER_PATH, CLOVER_COLORS,
} from "./celebrate.js";

function Probe({ total, token }) {
  useCelebrateOnCleared(total, token);
  return null;
}

beforeEach(() => {
  // 축포는 한 벌이 끝나기 전 두 번째 요청을 접는다(ui/celebrate.js 의 겹침 방지).
  // 그 기억은 모듈 전역이라 시험 사이에 새므로 여기서 비운다.
  resetBurstCooldown();
  confettiSpy.mockClear();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
});

describe("비운 순간에만 터진다", () => {
  it("남은 건수가 0 이 아니면 아무 일도 없다", () => {
    expect(celebrateIfCleared(3)).toBe(false);
    expect(confettiSpy).not.toHaveBeenCalled();
  });

  it("셀 수 없으면(응답에 총계가 없으면) 축하하지 않는다 — 모르는 것을 축하하지 않는다", () => {
    expect(celebrateIfCleared(null)).toBe(false);
    expect(celebrateIfCleared(undefined)).toBe(false);
    expect(confettiSpy).not.toHaveBeenCalled();
  });

  it("0 이 되면 터진다", () => {
    expect(celebrateIfCleared(0)).toBe(true);
    expect(confettiSpy).toHaveBeenCalled();
  });
});

describe("목록이 비워진 순간 — 조건을 바꿔서 빈 것과 구별한다", () => {
  it("🔴 같은 조건에서 3 → 0 이면 터진다", () => {
    const { rerender } = render(<Probe total={3} token="status=open" />);
    expect(confettiSpy).not.toHaveBeenCalled();
    rerender(<Probe total={0} token="status=open" />);
    expect(confettiSpy).toHaveBeenCalled();
  });

  it("🔴 **조건이 바뀌어** 0 이 된 것에는 안 터진다 — 검색어를 쳐서 0건이 된 자리다", () => {
    const { rerender } = render(<Probe total={3} token="status=open" />);
    rerender(<Probe total={0} token="status=open&q=없는말" />);
    expect(confettiSpy).not.toHaveBeenCalled();
  });

  it("처음부터 0 이면 안 터진다 — 빈 채로 들어온 사람은 방금 끝낸 것이 아니다", () => {
    render(<Probe total={0} token="status=open" />);
    expect(confettiSpy).not.toHaveBeenCalled();
  });

  it("0 인 채로 다시 그려도 두 번 터지지 않는다", () => {
    const { rerender } = render(<Probe total={1} token="t" />);
    rerender(<Probe total={0} token="t" />);
    const first = confettiSpy.mock.calls.length;
    expect(first).toBeGreaterThan(0);
    rerender(<Probe total={0} token="t" />);
    expect(confettiSpy.mock.calls.length).toBe(first);
  });

  it("총계를 아직 모르는 동안(null)에는 기억을 더럽히지 않는다", () => {
    const { rerender } = render(<Probe total={2} token="t" />);
    rerender(<Probe total={null} token="t" />);
    rerender(<Probe total={0} token="t" />);
    expect(confettiSpy).toHaveBeenCalled();
  });
});

/* 「이 티켓을 끝냈다」 — 사용자 지적(2026-09-03): "티켓이 완료됐을 때 폭죽이 터지기로
 * 했는데 수정을 눌러서 완료 누르고 저장했을 때는 안 터짐." 그전까지 축포가 붙어 있던
 * 자리는 목록이 **비는** 순간 넷뿐이었고, 티켓 한 건을 끝낸 자리에는 아무도 없었다. */
describe("티켓을 완료로 옮긴 순간", () => {
  const STATUSES = {
    statuses: [
      { key: "계획", category: "OPEN", terminal: false },
      { key: "진행", category: "IN_PROGRESS", terminal: false },
      { key: "완료", category: "DONE", terminal: true },
      { key: "취소", category: "CANCELED", terminal: true },
    ],
  };

  it("완료 갈래만 고른다 — 취소는 종료지만 축하가 아니다", () => {
    const keys = doneStatusKeys(STATUSES);
    expect([...keys]).toEqual(["완료"]);
    expect(keys.has("취소")).toBe(false);
  });

  it("어휘가 아직 없으면 빈 집합이다 — 상태 이름을 코드에 적지 않는다", () => {
    expect(doneStatusKeys(undefined).size).toBe(0);
    expect(doneStatusKeys({}).size).toBe(0);
  });

  it("완료로 옮기면 터진다", () => {
    expect(celebrateIfCompleted("완료", doneStatusKeys(STATUSES))).toBe(true);
    expect(confettiSpy).toHaveBeenCalled();
  });

  it("취소로 옮기면 안 터진다 — 접은 일은 끝낸 일이 아니다", () => {
    expect(celebrateIfCompleted("취소", doneStatusKeys(STATUSES))).toBe(false);
    expect(confettiSpy).not.toHaveBeenCalled();
  });

  it("상태가 안 바뀐 저장에는 안 터진다 — 부르는 쪽이 빈 값을 넘긴다", () => {
    expect(celebrateIfCompleted(undefined, doneStatusKeys(STATUSES))).toBe(false);
    expect(celebrateIfCompleted("", doneStatusKeys(STATUSES))).toBe(false);
    expect(confettiSpy).not.toHaveBeenCalled();
  });

  it("판의 이동 응답은 서버가 준 갈래를 그대로 쓴다", () => {
    expect(celebrateIfCompletedCategory({ status: "완료", status_category: "DONE" })).toBe(true);
    expect(confettiSpy).toHaveBeenCalled();
    confettiSpy.mockClear();
    resetBurstCooldown();
    expect(celebrateIfCompletedCategory({ status: "취소", status_category: "CANCELED" })).toBe(false);
    expect(celebrateIfCompletedCategory(null)).toBe(false);
    expect(confettiSpy).not.toHaveBeenCalled();
  });
});

/* 🔴 한 동작에 축포는 **한 벌**이다. 내 마지막 열린 티켓을 완료로 옮기면 「끝냈다」와
 * 「할 게 없어졌다」가 동시에 참이 되고, 그때 종잇조각이 두 겹으로 쏟아진다. */
describe("겹쳐 터지지 않는다", () => {
  it("한 벌이 끝나기 전 두 번째 요청은 접는다", () => {
    expect(celebrateIfCompleted("완료", doneStatusKeys({ statuses: [{ key: "완료", category: "DONE" }] }))).toBe(true);
    const first = confettiSpy.mock.calls.length;
    expect(first).toBeGreaterThan(0);
    // 같은 동작이 만든 두 번째 신호(목록이 비었다).
    celebrateIfCleared(0);
    expect(confettiSpy.mock.calls.length).toBe(first);
  });
});

/* ── 만든 자리와 끝낸 자리는 무게가 다르다 ─────────────────────────────────
 *
 * qa-contract-change: 「움직였다(진행 중 전환)」 무게를 통째로 걷었다(2026-09-03 사용자
 * 결정: "티켓을 검증으로 바꿔도 축포가 터지고 … 일단 이건 절대 아님"). 하루에 여러 번
 * 일어나는 상태 이동마다 축하하면 그건 축하가 아니라 소음이라는 판단이다. 그 무게를 재던
 * 시험 넷은 잴 대상이 사라졌다. 남은 둘(끝냄·만듦)의 대소와 층·겹침 방지는 그대로 잰다. */
describe("자리마다 무게가 다르다", () => {
  it("만듦은 한 발, 끝냄은 세 발 — 무게가 실제로 다르다", () => {
    celebrateCreated();
    expect(confettiSpy.mock.calls.length).toBe(1);
    const created = confettiSpy.mock.calls[0][0];

    confettiSpy.mockClear();
    resetBurstCooldown();
    celebrate();
    const finished = confettiSpy.mock.calls[0][0];
    expect(finished.particleCount).toBeGreaterThan(created.particleCount);
    expect(finished.spread).toBeGreaterThan(created.spread);
  });

  /* 🔴 조각이 작으면 클로버가 **점**으로 보인다 — 사용자가 "클로버가 아닌데?" 라고 한 것이
   * 그것이다(실측: scalar 1.1 = 13px 은 점, 27px 부터 잎 넷이 보인다). 크기는 이 연출의
   * 존재 이유라 숫자로 못박는다. */
  it("클로버 조각은 알아볼 만큼 크다", () => {
    celebrateCreated();
    expect(confettiSpy.mock.calls[0][0].scalar).toBeGreaterThanOrEqual(2.2);
  });

  it("클로버는 브랜드 색으로만 쏟아진다", () => {
    celebrateCreated();
    expect(confettiSpy.mock.calls[0][0].colors).toEqual(CLOVER_COLORS);
    expect(CLOVER_COLORS).toContain("#8E75E1");
  });

  it("모든 축하는 앱 크롬 위에 뜬다 — 모달 뒤에서 터지지 않는다", () => {
    celebrateCreated();
    expect(confettiSpy.mock.calls[0][0].zIndex).toBeGreaterThan(1300);
  });

  it("겹침 방지는 두 무게가 함께 쓴다 — 저장하자마자 끝내도 한 벌이다", () => {
    celebrateCreated();
    const n = confettiSpy.mock.calls.length;
    celebrate();
    expect(confettiSpy.mock.calls.length).toBe(n);
  });
});


describe("클로버 모양", () => {
  it("잎 넷이 한 경로에 있다", () => {
    // 잎 하나가 M…Z 한 벌이므로 네 벌이다.
    expect((CLOVER_PATH.match(/M64 64/g) || []).length).toBe(4);
    expect((CLOVER_PATH.match(/Z/g) || []).length).toBe(4);
  });

  it("좌표가 마크의 뷰박스(128×128) 안에 있다", () => {
    const nums = (CLOVER_PATH.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
    expect(nums.length).toBeGreaterThan(0);
    expect(Math.min(...nums)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...nums)).toBeLessThanOrEqual(128);
  });
});
