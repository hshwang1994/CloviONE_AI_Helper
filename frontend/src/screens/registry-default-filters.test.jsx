import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";

/* PA-RC-0038 acceptance (4) — "기본 필터를 가진 화면 목록이 코드에서 열거 가능하고
 * 전부 (1)(2)를 만족한다."
 *
 * (1)(2)는 DataScreen.jsx의 공유 hasFilter 분기 하나로 해결된다(datascreen-default-filter-
 * empty-state.test.jsx가 그 분기 자체를 고정한다) — 특정 화면 설정을 더 손대지 않아도
 * 기본 필터가 있는 화면은 전부 같은 계약을 받는다. 이 파일이 하는 일은 그 "기본 필터를
 * 가진 화면 목록" 자체를 코드로 고정하는 것이다 — 나중에 누가 REGISTRY에 새 기본 필터를
 * 추가하면 이 목록이 조용히 어긋나는 대신 시험이 깨져서, 최소한 그 화면이 이 계약 안에
 * 있다는 사실을 의식하게 만든다(계약 자체는 이미 자동으로 적용된다).
 */
describe("REGISTRY — 기본값이 있는 필터를 가진 화면 (PA-RC-0038 acceptance 4)", () => {
  function screensWithDefaultFilter() {
    const out = [];
    for (const [key, config] of Object.entries(REGISTRY)) {
      for (const f of config.filters || []) {
        if (f.value != null && f.value !== "") out.push({ screen: key, filterKey: f.key, defaultValue: f.value });
      }
    }
    return out;
  }

  it("기본 필터를 가진 화면·필터·기본값의 전체 집합이 고정돼 있다", () => {
    const found = screensWithDefaultFilter()
      .map((x) => `${x.screen}.${x.filterKey}=${x.defaultValue}`)
      .sort();
    // PA-RC-0038 조사 시점(2026-08-17)에 확인한 전체 집합 — grep으로 재확인:
    // `key: "[a-z_]+", type: "[a-z]+", label: "[^"]*", value: "[^"]*"` in registry/*.js
    expect(found).toEqual([
      "approvals.status=pending",
      "audit-anomalies.window_hours=24",
      "policies.status=published",
      "prompts.status=published",
    ]);
  });

  it("기본 필터를 가진 화면은 전부 emptyTitle을 갖는다(빈 상태가 진짜 빈 것이면 이 문구로 떨어진다)", () => {
    // paginated든(approvals/policies/prompts, total로 판정) 아니든(audit-anomalies, 서버가
    // page 파라미터 없이 조건에 맞는 전량을 돌려주므로 items.length가 곧 전체) filtered.length===0은
    // 두 경우 모두 "그 조건에 맞는 행이 실제로 하나도 없다"는 뜻이다 — 페이지 경계 문제가 아니다.
    const screens = new Set(screensWithDefaultFilter().map((x) => x.screen));
    for (const key of screens) {
      expect(REGISTRY[key].emptyTitle, `${key}에 emptyTitle이 없다`).toBeTruthy();
    }
  });
});
