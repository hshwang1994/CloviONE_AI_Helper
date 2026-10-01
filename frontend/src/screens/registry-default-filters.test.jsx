/* qa-contract-change: AI 사용 통계가 전용 화면이 되고(D-543) 정책 목록의 기본 조건 「발행됨」을 걷어(D-542) 기본 필터 집합이 승인 하나가 됐다. 프롬프트는 기능 목록이라 조건이 없다(D-541) — 그 자리는 정책의 상태 조건에 기본값이 없음을 잰다. */
/* qa-contract-change: 감사 이상 징후가 이 목록에서 빠졌다 — 그 화면의 기간 필터는 이제 화면 기본값(`value: "24"`)을 안 심고 빈 값을 서버 기본값의 이름(「최근 24시간」)으로 부른다. 「기간 전체」가 실제로는 24시간이던 것을 배포 환경에서 확인해 고친 결과다. 단언은 줄지 않았다: 이 화면이 목록에서 빠졌다는 사실을 아래 시험이 이유와 함께 따로 잰다.
 * 프롬프트도 빠졌다(D-518): 목록 첫머리가 사용처마다 기본 제공 지시문이라 「발행됨」 기본값이 그 행들을 가렸다. 아래 시험이 그 사실을 따로 잰다. */
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
      // AI 사용 통계는 전용 화면이 됐고(보기 기준은 그 화면의 세그먼티드, D-543), 정책은 기본 조건이 없다(D-542) —
      // 예전 기본값 「발행됨」은 업그레이드가 옮긴 검토 초안까지 숨겼다.
      "approvals.status=pending",
    ]);
  });

  it("프롬프트는 기능마다 한 줄이라 조건이 없고, 정책의 상태 조건에는 기본값이 없다", () => {
    // 프롬프트 기능 목록은 기능 다섯 줄이다(D-541) — 거를 것이 없다. 정책은 상태 어휘가 초안 · 적용 중 · 보관이다.
    expect(REGISTRY.prompts.filters).toBeUndefined();
    const f = REGISTRY.policies.filters.find((x) => x.key === "status");
    expect(f.value).toBeUndefined();
    expect(f.options.map((o) => [o.value, o.label])).toEqual([["draft", "초안"], ["published", "적용 중"], ["archived", "보관"]]);
  });

  it("감사 이상 징후는 화면 기본값을 안 심는다 — 빈 값이 곧 서버 기본값이다", () => {
    /* 이 화면만 목록에서 빠진 이유를 여기 적어 둔다. 서버는 언제나 창을 두고 세고
       (`app/audit/anomalies.py::DEFAULT_WINDOW_HOURS = 24`) 값을 안 보내면 24시간으로
       답한다. 그래서 화면이 기본값을 따로 심을 필요가 없고, 심으면 빈 값과 「24」가 같은
       일을 하는 두 항목이 되어 관리자가 둘을 다르게 읽는다. 빈 값의 이름을 서버 기본값
       그대로 부르는 것이 이 축의 계약이다(`allLabel`). */
    const f = REGISTRY["audit-anomalies"].filters.find((x) => x.key === "window_hours");
    expect(f.value).toBeUndefined();
    expect(f.allLabel).toBe("최근 24시간");
    expect(f.options.map((o) => o.value)).not.toContain("24");
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
