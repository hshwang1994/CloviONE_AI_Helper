import { describe, it, expect } from "vitest";
import { finishLabelX, labelPlan, placeLabels, shortName } from "./renderer.js";

/* 구슬 이름 라벨 (D-578) — 몰린 구슬의 라벨이 서로 덮이지 않는다. 앞선 순서(초점 구슬 → 순위)대로 놓고 겹치는 것은 건너뛴다.
 * 결승 앞 깔때기에서 세 구슬의 이름이 한 덩이로 겹쳐 아무것도 읽히지 않던 장면(390 실측)이 기준이다. */

const box = (x, y, w = 40, h = 15) => ({ x, y, w, h });

describe("placeLabels", () => {
  it("겹치지 않는 라벨은 모두 선다", () => {
    const items = [box(50, 100), box(120, 100), box(50, 140)];
    expect(placeLabels(items)).toEqual(items);
  });

  it("겹치는 라벨은 앞선 것만 선다 — 뒤의 것은 건너뛴다", () => {
    const first = box(100, 100);
    const overlapping = box(110, 104);
    const clear = box(200, 100);
    expect(placeLabels([first, overlapping, clear])).toEqual([first, clear]);
  });

  it("가장자리가 닿기만 하면 겹침이 아니다", () => {
    const a = box(100, 100, 40, 15);
    const b = box(140, 100, 40, 15); // a 의 오른쪽 120 = b 의 왼쪽 120
    expect(placeLabels([a, b])).toEqual([a, b]);
  });

  it("판 위를 덮는 자리(미니맵 · 선두 칩 · 카메라 고르기) 밑의 라벨은 놓지 않는다", () => {
    const under = box(330, 30); // 오른쪽 위 선두 칩 밑
    const free = box(150, 120);
    expect(placeLabels([under, free], [{ l: 260, t: 10, r: 348, b: 90 }])).toEqual([free]);
  });

  it("건너뛴 라벨은 다음 라벨의 자리를 막지 않는다", () => {
    const a = box(100, 100);
    const skipped = box(130, 100); // a 와 겹친다
    const c = box(160, 100); // skipped 와는 겹치지만 a 와는 안 겹친다
    expect(placeLabels([a, skipped, c])).toEqual([a, c]);
  });
});

describe("labelPlan · shortName", () => {
  it("30명까지 이름 전부, 60명까지 상위 + 근처, 그 위는 번호", () => {
    expect(labelPlan(30)).toBe("all");
    expect(labelPlan(31)).toBe("top-near");
    expect(labelPlan(61)).toBe("badge");
  });

  it("이름은 12자까지, 넘치면 말줄임", () => {
    expect(shortName("가나다라마바사아자차카타")).toBe("가나다라마바사아자차카타");
    expect(shortName("가나다라마바사아자차카타파")).toBe("가나다라마바사아자차카…");
  });
});

describe("finishLabelX — 결승 글자가 카메라 고르기 밑에 숨지 않는다", () => {
  const ctl = { l: 150, t: 224, r: 348, b: 258 }; // 390 판(358 × 268)의 오른쪽 아래 컨트롤
  it("컨트롤과 겹치지 않으면 결승선 오른쪽 끝 그대로", () => {
    expect(finishLabelX(340, 150, 30, 15, [ctl])).toBe(340);
  });
  it("겹치면 컨트롤 왼쪽으로 비킨다", () => {
    expect(finishLabelX(340, 240, 30, 15, [ctl])).toBe(144);
  });
  it("가릴 것이 없으면 그대로", () => {
    expect(finishLabelX(340, 240, 30, 15)).toBe(340);
  });
});
